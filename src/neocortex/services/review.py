"""Shared review service — CLI 与 HTTP 的唯一复习业务路径。

职责（Typer / FastAPI 层都不允许绕开这里直接改卡片）：

- 带 storage_path 的卡片加载：每张卡记住自己来自哪个 JSON 文件，
  写回永远回到原文件。relationship card（source_note 为空）实际存放在
  ``.flashcards/_relationships.json``，绝不能再用 source_note 反推文件名。
- 唯一的 :func:`get_review_queue_summary`：active/suspended 过滤、due_total、
  next_due_date、default 候选队列。``services/daily.py`` 的 due 数字和
  review session 创建都必须调它，保证两边永远一致。
- 服务端强制 session 上限 ``MAX_SESSION_CARDS = 5``。
- 评分（SM-2 更新 + 原子写回 + 标准卡 concept confidence boost）与
  软淘汰（suspend/restore）。
- 跨进程写锁：CLI 与 server 可能同时在跑，线程锁不够，用 flock。

幂等设计（为 HTTP 重试 / 崩溃恢复服务）：

变更被拆成 compute → apply 两段。:func:`compute_outcome` 产出 before/after
**绝对值**快照（含 concept boost 的绝对目标 confidence），:func:`apply_outcome`
只做"把状态设置为 after"的赋值动作 —— 重复 apply 同一个 outcome 不会二次
推进调度、不会二次 boost。Slice 1 的事件存储把 outcome 持久化后即可安全重放。
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from neocortex.models import Flashcard
from neocortex.reviewer import get_review_session, is_active, is_due, sm2_update

# 服务端强制的单次 session 上限（MVP 假设参数，见自用闭环计划 §二）。
MAX_SESSION_CARDS = 5

# GUI 四档 → SM-2 quality 映射。
#
# 有意决策：GUI 把 SM-2 的 quality 0/1/2 折叠为一个 Again 档。当前
# ``sm2_update()`` 对所有 quality < 3 的行为完全相同（interval=1、
# review_count=0、ease_factor 不变），三档在调度上没有区别，GUI 没必要
# 让用户在三个等价选项里纠结。如果未来 reviewer.py 让 0/1/2 语义分化，
# ``tests/test_review_service.py::TestQualityFolding`` 会失败并要求
# 重新审视这个映射 —— 不要静默改这里。
GUI_QUALITY_MAP: dict[str, int] = {
    "again": 0,
    "hard": 3,
    "good": 4,
    "easy": 5,
}

# 参与幂等快照比较的调度字段（绝对值）。
SCHEDULE_FIELDS: tuple[str, ...] = (
    "interval",
    "ease_factor",
    "next_review",
    "review_count",
    "last_review",
    "suspended",
)


class CardNotFoundError(KeyError):
    """指定 card_id 在 vault 闪卡存储里不存在。"""


class ReviewServiceError(RuntimeError):
    """review service 层的通用错误（存储文件损坏等）。"""


# ── 存储表达 ──


@dataclass
class StoredCard:
    """一张卡 + 它真实所在的 JSON 文件。写回只认 storage_path。"""

    card: Flashcard
    storage_path: Path
    storage_key: str  # 文件 stem，如 "_relationships"


@dataclass
class ReviewQueueSummary:
    """由唯一实现计算的复习队列摘要。"""

    total_active: int
    due_total: int
    next_due_date: str | None
    queue: list[StoredCard] = field(default_factory=list)


@dataclass
class ReviewOutcome:
    """一次状态变更的完整描述（before/after 均为绝对值快照）。

    apply 是幂等的：重复 apply 只是把同样的绝对值再赋一遍。
    """

    card_id: str
    # ``.flashcards`` 内的单文件相对引用（例如 ``note-a.json``）。不能持久化
    # 绝对路径，否则整个 Neocortex layout 移动后 pending 事件无法恢复。
    storage_path: str
    action: str  # "grade" / "suspend" / "restore"
    quality: int | None
    before: dict
    after: dict
    concept_boost: dict | None = None  # {"concept_path", "confidence", "last_updated"}


# ── 加载 ──


def load_stored_cards(notes_dir: Path) -> list[StoredCard]:
    """加载全部卡片并记录每张卡的真实存储文件。

    与 ``config.load_flashcards`` 同样的容错策略（坏文件/坏条目跳过），
    但保留 storage_path，供写回使用。
    """
    fc_dir = notes_dir / ".flashcards"
    if not fc_dir.exists():
        return []
    stored: list[StoredCard] = []
    for f in sorted(fc_dir.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            try:
                card = Flashcard.model_validate(item)
            except Exception:
                continue
            stored.append(StoredCard(card=card, storage_path=f, storage_key=f.stem))
    return stored


def find_stored_card(notes_dir: Path, card_id: str) -> StoredCard:
    for s in load_stored_cards(notes_dir):
        if s.card.id == card_id:
            return s
    raise CardNotFoundError(card_id)


# ── 队列摘要（唯一实现）──


def get_review_queue_summary(notes_dir: Path, today: str | None = None) -> ReviewQueueSummary:
    """active/suspended 过滤 + due 统计 + default 候选队列的唯一入口。

    ``services/daily.py`` 的 ``due_flashcard_count`` 与
    ``POST /api/review/session`` 的 ``due_total`` 都来自这里，
    同一卡片快照下两者必然相等。
    """
    if today is None:
        today = date.today().isoformat()
    stored = load_stored_cards(notes_dir)
    active = [s for s in stored if is_active(s.card)]

    by_id: dict[str, StoredCard] = {}
    for s in active:
        by_id.setdefault(s.card.id, s)

    ordered = get_review_session(
        [s.card for s in active],
        max_cards=len(active) or 1,
        mode="default",
        today=today,
    )
    queue: list[StoredCard] = []
    seen: set[str] = set()
    for card in ordered:
        if card.id in by_id and card.id not in seen and is_due(card, today):
            queue.append(by_id[card.id])
            seen.add(card.id)

    future_dates = sorted(
        s.card.next_review
        for s in active
        if s.card.next_review and s.card.next_review > today
    )
    return ReviewQueueSummary(
        total_active=len(active),
        due_total=len(queue),
        next_due_date=future_dates[0] if future_dates else None,
        queue=queue,
    )


def clamp_session_limit(limit: int | None) -> int:
    """服务端强制 limit <= MAX_SESSION_CARDS，非法值收敛到边界。"""
    if limit is None:
        return MAX_SESSION_CARDS
    return max(0, min(int(limit), MAX_SESSION_CARDS))


def select_session_cards(summary: ReviewQueueSummary, limit: int | None) -> list[StoredCard]:
    return summary.queue[: clamp_session_limit(limit)]


# ── 跨进程写锁 ──


@contextmanager
def review_write_lock(notes_dir: Path):
    """flock 排它锁。CLI 与 HTTP server 是不同进程，线程锁保护不了并发写，
    所有卡片状态变更（compute+apply 全程）必须持有该锁。"""
    fc_dir = notes_dir / ".flashcards"
    fc_dir.mkdir(parents=True, exist_ok=True)
    lock_path = fc_dir / ".lock"
    with open(lock_path, "w", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# ── 快照 ──


def snapshot_schedule(card: Flashcard) -> dict:
    return {name: getattr(card, name) for name in SCHEDULE_FIELDS}


def _storage_reference(notes_dir: Path, storage_path: Path) -> str:
    """把真实卡片文件收敛为 ``.flashcards`` 内的安全、可移动引用。"""
    fc_dir = (notes_dir / ".flashcards").resolve()
    candidate = storage_path.resolve()
    try:
        rel = candidate.relative_to(fc_dir)
    except ValueError as exc:
        raise ReviewServiceError(f"card storage escapes .flashcards: {storage_path}") from exc
    if len(rel.parts) != 1 or rel.suffix != ".json":
        raise ReviewServiceError(f"invalid card storage reference: {rel}")
    return rel.as_posix()


def _resolve_storage_reference(notes_dir: Path, storage_ref: str) -> Path:
    """解析持久化的卡片文件引用，并兼容旧版绝对路径 pending 事件。

    旧版绝对路径只取安全 basename，再映射到**当前** layout 的 ``.flashcards``；
    这样移动项目后仍能恢复，也不会按 SQLite 中的路径写出 vault。
    """
    raw = Path(storage_ref)
    if not storage_ref or raw.name != storage_ref and not raw.is_absolute():
        raise ReviewServiceError(f"invalid card storage reference: {storage_ref!r}")
    name = raw.name if raw.is_absolute() else storage_ref
    if name in ("", ".", "..") or Path(name).suffix != ".json" or Path(name).name != name:
        raise ReviewServiceError(f"invalid card storage reference: {storage_ref!r}")
    fc_dir = (notes_dir / ".flashcards").resolve()
    candidate = (fc_dir / name).resolve()
    try:
        candidate.relative_to(fc_dir)
    except ValueError as exc:
        raise ReviewServiceError(f"card storage escapes .flashcards: {storage_ref!r}") from exc
    return candidate


# ── compute（不落盘）──


def compute_outcome(
    notes_dir: Path,
    stored: StoredCard,
    action: str,
    quality: int | None = None,
) -> ReviewOutcome:
    """计算一次变更的 before/after 绝对值快照，不写任何文件。"""
    card = stored.card
    before = snapshot_schedule(card)
    boost: dict | None = None

    if action == "grade":
        if quality is None:
            raise ValueError("grade requires quality")
        updated = card.model_copy()
        sm2_update(updated, quality)
        after = snapshot_schedule(updated)
        # concept confidence boost 只发生在标准卡成功评分时。
        # relationship card 的 concept 是 "A <> B" 组合标签，不对应单个
        # concept 文件；在模型能保存两个明确 concept ID 之前不伪造 boost。
        if quality >= 3 and card.card_type == "standard" and card.concept:
            boost = compute_concept_boost(notes_dir, card.concept)
    elif action == "suspend":
        after = dict(before)
        after["suspended"] = True
    elif action == "restore":
        after = dict(before)
        after["suspended"] = False
    else:
        raise ValueError(f"unknown action: {action!r}")

    return ReviewOutcome(
        card_id=card.id,
        storage_path=_storage_reference(notes_dir, stored.storage_path),
        action=action,
        quality=quality,
        before=before,
        after=after,
        concept_boost=boost,
    )


def _safe_concept_path(notes_dir: Path, slug: str) -> Path | None:
    """slug → concepts/<slug>.md，拒绝一切路径逃逸（concept 名来自卡片数据，
    不可信：绝对路径 / ".." / 分隔符 / 点开头都不允许离开 concepts/）。"""
    if not slug or slug.startswith((".", "/", "~")) or "/" in slug or "\\" in slug:
        return None
    concepts_dir = (notes_dir / "concepts").resolve()
    candidate = (notes_dir / "concepts" / f"{slug}.md").resolve()
    try:
        candidate.relative_to(concepts_dir)
    except ValueError:
        return None
    return candidate


def compute_concept_boost(notes_dir: Path, concept_name: str) -> dict | None:
    """计算 boost 后的**绝对**目标 confidence，供幂等 apply。
    同时记录 before_confidence，apply 时用于三态判断（未应用/已应用/冲突）。"""
    from neocortex.decay import REVIEW_BOOST, boost_confidence, decayed_confidence

    slug = concept_name.strip().lower().replace(" ", "-")
    concept_path = _safe_concept_path(notes_dir, slug)
    if concept_path is None or not concept_path.exists():
        return None
    try:
        content = concept_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    conf_match = re.search(r"^confidence:\s*([\d.]+)", content, re.MULTILINE)
    date_match = re.search(r"^last_updated:\s*(\S+)", content, re.MULTILINE)
    if not conf_match:
        return None
    old_conf = float(conf_match.group(1))
    old_date = date_match.group(1) if date_match else ""
    current = decayed_confidence(old_conf, old_date)
    new_conf = boost_confidence(current, REVIEW_BOOST)
    return {
        "concept_path": (Path("concepts") / f"{slug}.md").as_posix(),
        "before_confidence": old_conf,
        "confidence": round(new_conf, 4),
        "last_updated": date.today().isoformat(),
    }


# ── apply（幂等落盘）──


def apply_outcome(notes_dir: Path, outcome: ReviewOutcome) -> None:
    """把 outcome.after 的绝对值写回原 JSON 文件（原子替换），
    并把 concept confidence 设置为绝对目标值。重复调用安全。

    只合并目标卡 dict 的 SCHEDULE_FIELDS，文件里的其他条目（包括当前
    模型无法解析的坏条目 / 版本偏移条目）**原样保留**——容错读取绝不能
    变成破坏性写回。目标卡缺失则整次失败且不写文件。
    """
    path = _resolve_storage_reference(notes_dir, outcome.storage_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewServiceError(f"cannot read card storage {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ReviewServiceError(f"card storage {path} is not a list")

    targets = [
        item for item in raw
        if isinstance(item, dict) and item.get("id") == outcome.card_id
    ]
    if not targets:
        raise CardNotFoundError(outcome.card_id)
    for item in targets:
        for name in SCHEDULE_FIELDS:
            if name in outcome.after:
                item[name] = outcome.after[name]

    atomic_save_raw(path, raw)

    if outcome.concept_boost:
        _apply_concept_boost(notes_dir, outcome.concept_boost)


def atomic_save_raw(path: Path, data: list) -> None:
    """原子写回原始 JSON list（temp file + os.replace）。
    调用方负责保证 data 里保留了所有不认识的原始条目。"""
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _apply_concept_boost(notes_dir: Path, boost: dict) -> None:
    """把 concept 的 confidence / last_updated 设置为绝对目标值。

    三态幂等：当前值 == before → 应用；== 目标值 → 已应用过，跳过；
    其他值 → 有更新的合法写者（如 CLI 又复习了同 concept），保留新状态、
    不用旧快照回滚。boost 快照可能从 SQLite 恢复而来，路径必须重新校验。
    """
    # concept_path 来自持久化快照，不可信——重新做逃逸校验
    rel = Path(boost["concept_path"])
    if rel.is_absolute() or rel.parts[:1] != ("concepts",):
        return
    concept_path = _safe_concept_path(notes_dir, rel.stem)
    if concept_path is None or not concept_path.exists():
        return
    try:
        content = concept_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    conf_match = re.search(r"^confidence:\s*([\d.]+)", content, re.MULTILINE)
    if not conf_match:
        return
    current = float(conf_match.group(1))
    if current == boost["confidence"]:
        return  # 已应用（重放/恢复路径）
    if "before_confidence" in boost and current != boost["before_confidence"]:
        return  # 期间有更新的合法写入，不回滚

    content = re.sub(
        r"^confidence:\s*[\d.]+",
        f"confidence: {boost['confidence']:.4f}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^last_updated:\s*\S+",
        f"last_updated: {boost['last_updated']}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    fd, tmp_path = tempfile.mkstemp(dir=str(concept_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(concept_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── 一步式入口（CLI 用）──


def grade_card(notes_dir: Path, card_id: str, quality: int) -> ReviewOutcome:
    """评分一张卡：锁内重读磁盘状态 → compute → apply。"""
    with review_write_lock(notes_dir):
        stored = find_stored_card(notes_dir, card_id)
        outcome = compute_outcome(notes_dir, stored, "grade", quality=quality)
        apply_outcome(notes_dir, outcome)
    return outcome


def set_card_suspended(notes_dir: Path, card_id: str, suspended: bool) -> ReviewOutcome:
    """软淘汰 / 撤销。卡片保留在原 JSON，只翻 suspended 标记。"""
    action = "suspend" if suspended else "restore"
    with review_write_lock(notes_dir):
        stored = find_stored_card(notes_dir, card_id)
        outcome = compute_outcome(notes_dir, stored, action)
        apply_outcome(notes_dir, outcome)
    return outcome


# ── 源笔记路径解析 ──


def resolve_source_path(notes_dir: Path, source_note: str) -> str | None:
    """把卡片的 source_note 解析成 vault-relative POSIX 路径。

    - 新卡逐步保存 vault-relative path（含 "/"）：校验仍在 vault 内且存在；
    - 旧卡只有 basename：在 vault 内做唯一匹配，0 或 >1 个候选都返回 None
      （source_available=false），绝不猜；
    - 绝对路径 / ~ / ".." 逃逸一律拒绝。
    """
    if not source_note:
        return None
    raw = source_note.strip()
    if not raw or raw.startswith(("/", "~")):
        return None
    rel = Path(raw)
    if any(part == ".." for part in rel.parts):
        return None
    vault = notes_dir.resolve()

    if len(rel.parts) > 1:
        candidate = (vault / rel).resolve()
        try:
            candidate.relative_to(vault)
        except ValueError:
            return None
        if candidate.is_file():
            return rel.as_posix()
        return None

    # basename-only（旧数据）：唯一匹配才接受；跳过点目录（.flashcards 等）。
    matches = [
        p
        for p in vault.rglob(rel.name)
        if p.is_file()
        and not any(part.startswith(".") for part in p.relative_to(vault).parts[:-1])
    ]
    if len(matches) == 1:
        return matches[0].relative_to(vault).as_posix()
    return None


# ── 人可读汇总日志（从 CLI 抽出）──


def log_review_summary(reviewed: int, correct: int) -> None:
    from neocortex.config import append_log

    append_log("review", f"{reviewed} cards, {correct} correct")
