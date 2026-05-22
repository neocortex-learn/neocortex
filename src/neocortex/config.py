"""Configuration management for Neocortex."""

from __future__ import annotations

import base64
import json
import os
import socket
import uuid
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from typing import Any

from neocortex.models import AppConfig, Clip, Flashcard, GapProgress, Profile, RecommendationRecord

_ENC_PREFIX = "enc:"
_SALT = b"neocortex-api-key-salt"


def _get_machine_fingerprint() -> str:
    hostname = socket.gethostname()
    username = os.environ.get("USER", os.environ.get("USERNAME", "default"))
    return f"{username}@{hostname}"


def _derive_fernet_key() -> bytes:
    fingerprint = _get_machine_fingerprint().encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    key_bytes = kdf.derive(fingerprint)
    return base64.urlsafe_b64encode(key_bytes)


def _encrypt(plaintext: str) -> str:
    fernet = Fernet(_derive_fernet_key())
    token = fernet.encrypt(plaintext.encode())
    return _ENC_PREFIX + token.decode()


def _decrypt(ciphertext: str) -> str:
    if not ciphertext.startswith(_ENC_PREFIX):
        return ciphertext
    raw = ciphertext[len(_ENC_PREFIX):]
    fernet = Fernet(_derive_fernet_key())
    try:
        token = raw.encode()
        return fernet.decrypt(token).decode()
    except Exception:
        token = base64.urlsafe_b64decode(raw)
        return fernet.decrypt(token).decode()


def get_data_dir() -> Path:
    data_dir = Path.home() / ".neocortex"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_notes_dir() -> Path:
    """Get the notes directory. Uses config setting, defaults to ~/Documents/Neocortex."""
    cfg_path = _config_path()
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            custom = data.get("output_settings", {}).get("notes_dir")
            if custom and custom != "~/.neocortex/notes":
                notes_dir = Path(custom).expanduser()
                notes_dir.mkdir(parents=True, exist_ok=True)
                return notes_dir
        except (json.JSONDecodeError, OSError):
            pass
    notes_dir = Path.home() / "Documents" / "Neocortex"
    notes_dir.mkdir(parents=True, exist_ok=True)
    return notes_dir


def append_log(action: str, detail: str) -> None:
    """Append an activity entry to log.md in the notes directory.

    Actions: read, ask, insight, compile, lint, clip, review
    """
    from datetime import date

    try:
        log_path = get_notes_dir() / "log.md"
        line = f"## [{date.today().isoformat()}] {action} | {detail}\n\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _config_path() -> Path:
    return get_data_dir() / "config.json"


def _profile_path() -> Path:
    return get_data_dir() / "profile.json"


def load_config() -> AppConfig:
    path = _config_path()
    if not path.exists():
        return AppConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    api_key = data.get("api_key")
    if api_key and isinstance(api_key, str) and api_key.startswith(_ENC_PREFIX):
        try:
            data["api_key"] = _decrypt(api_key)
        except Exception:
            import warnings
            warnings.warn("Failed to decrypt API key. Please reconfigure with: neocortex config --api-key <key>")
            data["api_key"] = None
    github_token = data.get("github_token")
    if github_token and isinstance(github_token, str) and github_token.startswith(_ENC_PREFIX):
        try:
            data["github_token"] = _decrypt(github_token)
        except Exception:
            import warnings
            warnings.warn("Failed to decrypt GitHub token. Please reconfigure with: neocortex config --github-token <token>")
            data["github_token"] = None
    return AppConfig.model_validate(data)


def save_config(config: AppConfig) -> None:
    import tempfile
    data = config.model_dump(mode="json")
    if data.get("api_key") and not data["api_key"].startswith(_ENC_PREFIX):
        data["api_key"] = _encrypt(data["api_key"])
    if data.get("github_token") and not data["github_token"].startswith(_ENC_PREFIX):
        data["github_token"] = _encrypt(data["github_token"])
    path = _config_path()
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def is_experimental(feature: str) -> bool:
    """Check if an experimental feature is enabled in config."""
    cfg = load_config()
    return feature in cfg.experimental


def load_profile() -> Profile:
    path = _profile_path()
    if not path.exists():
        return Profile()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Profile.model_validate(data)


def save_profile(profile: Profile) -> None:
    import tempfile
    path = _profile_path()
    data = profile.model_dump(mode="json")
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_json(filename: str, default: Any = None) -> Any:
    """Generic JSON file loader from data dir."""
    path = get_data_dir() / filename
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def _save_json(filename: str, data: Any) -> None:
    """Atomic JSON file writer to data dir (temp file + rename)."""
    import tempfile
    path = get_data_dir() / filename
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


def load_recommendations(status: str | None = None) -> list[RecommendationRecord]:
    """Load recommendation records, optionally filtered by status."""
    raw = _load_json("recommendations.json", default=[])
    if not isinstance(raw, list):
        return []
    records = []
    for item in raw:
        try:
            rec = RecommendationRecord.model_validate(item)
            if status is None or rec.status == status:
                records.append(rec)
        except Exception:
            continue
    return records


def save_recommendations(records: list[RecommendationRecord]) -> None:
    """Save all recommendation records."""
    _save_json("recommendations.json", [r.model_dump(mode="json") for r in records])


def load_gap_progress() -> dict[str, GapProgress]:
    """Load gap progress tracking data."""
    raw = _load_json("gap_progress.json", default={})
    if not isinstance(raw, dict):
        return {}
    result = {}
    for key, val in raw.items():
        try:
            result[key] = GapProgress.model_validate(val)
        except Exception:
            continue
    return result


def save_gap_progress(progress: dict[str, GapProgress]) -> None:
    """Save gap progress tracking data."""
    _save_json("gap_progress.json", {k: v.model_dump(mode="json") for k, v in progress.items()})


def update_gap_status(gap_name: str, profile: Profile) -> str:
    """Update gap status after reading related content. Returns new status.

    Status flow: gap → learning → (probe verification) → verified → (delayed retest) → known
    Reading alone moves gap → learning. Further promotion requires probe verification.
    """
    from datetime import date as _date
    from neocortex.scanner.profile import normalize_gap_name
    gap_name = normalize_gap_name(gap_name)
    progress = load_gap_progress()
    entry = progress.get(gap_name)
    if entry is None:
        entry = GapProgress(status="gap", first_seen=_date.today().isoformat())
        progress[gap_name] = entry

    if entry.status == "known":
        return "known"

    entry.reads += 1
    entry.last_read = _date.today().isoformat()

    if entry.status == "gap":
        entry.status = "learning"
    # learning / verified: stay as-is on read alone — probe verification required

    progress[gap_name] = entry
    save_gap_progress(progress)
    return entry.status


def verify_gap(gap_name: str, profile: Profile) -> str:
    """Promote a gap after successful probe verification. Returns new status.

    - learning (reads >= 2) + probe passed → verified
    - verified (7+ days since verified_at) + probe passed → known
    """
    from datetime import date as _date
    from neocortex.scanner.profile import normalize_gap_name
    gap_name = normalize_gap_name(gap_name)
    progress = load_gap_progress()
    entry = progress.get(gap_name)
    if entry is None:
        return "gap"

    if entry.status == "learning" and entry.reads >= 2:
        entry.status = "verified"
        entry.verified_at = _date.today().isoformat()
    elif entry.status == "verified" and entry.verified_at:
        verified_date = _date.fromisoformat(entry.verified_at)
        if (_date.today() - verified_date).days >= 7:
            entry.status = "known"
            for domain in profile.skills.domains.values():
                if gap_name in domain.gaps:
                    domain.gaps.remove(gap_name)
            for integration in profile.skills.integrations.values():
                if gap_name in integration.gaps:
                    integration.gaps.remove(gap_name)

    progress[gap_name] = entry
    save_gap_progress(progress)
    return entry.status


def load_flashcards(notes_dir: Path) -> list[Flashcard]:
    fc_dir = notes_dir / ".flashcards"
    if not fc_dir.exists():
        return []
    cards: list[Flashcard] = []
    for f in fc_dir.glob("*.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                continue
            for item in raw:
                cards.append(Flashcard.model_validate(item))
        except (json.JSONDecodeError, OSError, Exception):
            continue
    return cards


def save_flashcards(notes_dir: Path, note_stem: str, cards: list[Flashcard]) -> None:
    import tempfile
    fc_dir = notes_dir / ".flashcards"
    fc_dir.mkdir(parents=True, exist_ok=True)
    path = fc_dir / f"{note_stem}.json"
    data = [c.model_dump(mode="json") for c in cards]
    fd, tmp_path = tempfile.mkstemp(dir=str(fc_dir), suffix=".tmp")
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


def get_due_flashcards(notes_dir: Path) -> list[Flashcard]:
    from datetime import date as _date
    today = _date.today().isoformat()
    all_cards = load_flashcards(notes_dir)
    return [c for c in all_cards if not c.next_review or c.next_review <= today]


def load_feeds() -> list[dict]:
    """Load feed configurations from feeds.json. Returns [{url, name}]."""
    raw = _load_json("feeds.json", default=[])
    if not isinstance(raw, list):
        return []
    return [f for f in raw if isinstance(f, dict) and "url" in f]


def save_feeds(feeds: list[dict]) -> None:
    """Save feed configurations to feeds.json."""
    _save_json("feeds.json", feeds)


def load_feed_history() -> dict[str, str]:
    """Load feed history (url -> last_seen_id) from feed_history.json."""
    raw = _load_json("feed_history.json", default={})
    if not isinstance(raw, dict):
        return {}
    return raw


def save_feed_history(history: dict[str, str]) -> None:
    """Save feed history."""
    _save_json("feed_history.json", history)


def load_claims() -> dict[str, list[dict]]:
    """Load claims grouped by concept name."""
    raw = _load_json("claims.json", default={})
    if not isinstance(raw, dict):
        return {}
    return raw


def save_claims(claims: dict[str, list[dict]]) -> None:
    """Save claims."""
    _save_json("claims.json", claims)


def load_belief_changes() -> list[dict]:
    """Load belief change history."""
    raw = _load_json("belief_changes.json", default=[])
    if not isinstance(raw, list):
        return []
    return raw


def save_belief_changes(changes: list[dict]) -> None:
    """Save belief change history."""
    _save_json("belief_changes.json", changes)


def load_clips(notes_dir: Path) -> list[Clip]:
    """Load all clips from clips/ directory."""
    clips_dir = notes_dir / "clips"
    if not clips_dir.exists():
        return []
    clips: list[Clip] = []
    for f in sorted(clips_dir.glob("*.md")):
        clip = _parse_clip_file(f)
        if clip:
            clips.append(clip)
    return clips


def _parse_clip_file(path: Path) -> Clip | None:
    """Parse a clip markdown file into a Clip object."""
    import re
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm_match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not fm_match:
        return None

    fm_text = fm_match.group(1)
    content = fm_match.group(2).strip()

    fields: dict[str, str | list[str]] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            items = [item.strip().strip('"').strip("'") for item in val[1:-1].split(",") if item.strip()]
            fields[key] = items
        else:
            fields[key] = val.strip('"').strip("'")

    clip_id = fields.get("id", "")
    if not clip_id or not isinstance(clip_id, str):
        return None

    def _str(k: str, default: str = "") -> str:
        v = fields.get(k, default)
        return v if isinstance(v, str) else default

    def _list(k: str) -> list[str]:
        v = fields.get(k, [])
        return v if isinstance(v, list) else []

    def _opt_str(k: str) -> str | None:
        v = fields.get(k)
        if v is None or v == "" or v == "null":
            return None
        return v if isinstance(v, str) else None

    def _safe_int(v: str) -> int:
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    return Clip(
        id=clip_id,
        source=_str("source", "manual"),
        content=content,
        title=_str("title"),
        clip_type=_str("clip_type", "thought"),
        auto_tags=_list("auto_tags"),
        related_concepts=_list("related_concepts"),
        status=_str("status", "inbox"),
        summary=_str("summary"),
        relevance=_str("relevance"),
        priority=_str("priority"),
        topic=_str("topic"),
        created_at=_str("created_at"),
        processed_at=_opt_str("processed_at"),
        promoted_to=_opt_str("promoted_to"),
        next_surface=_str("next_surface"),
        surface_count=_safe_int(_str("surface_count", "0") or "0"),
    )


def save_clip(notes_dir: Path, clip: Clip) -> Path:
    """Save a clip as markdown file. Returns the file path."""
    import re
    import tempfile
    clips_dir = notes_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = clip.created_at or "undated"
    slug = re.sub(r"[^\w\s-]", "", clip.title or clip.id)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-").lower()[:50]
    filename = f"{date_prefix}-{slug}.md" if slug else f"{date_prefix}-{clip.id}.md"

    tags_str = "[" + ", ".join(f'"{t}"' for t in clip.auto_tags) + "]" if clip.auto_tags else "[]"
    concepts_str = "[" + ", ".join(f'"{c}"' for c in clip.related_concepts) + "]" if clip.related_concepts else "[]"

    frontmatter_lines = [
        "---",
        f"id: {clip.id}",
        f"source: {clip.source}",
        f"title: {clip.title}",
        f"clip_type: {clip.clip_type}",
        f"auto_tags: {tags_str}",
        f"related_concepts: {concepts_str}",
        f"status: {clip.status}",
        f"summary: {clip.summary}",
        f"relevance: {clip.relevance}",
        f"priority: {clip.priority}",
        f"topic: {clip.topic}",
        f"created_at: {clip.created_at}",
        f"processed_at: {clip.processed_at or ''}",
        f"promoted_to: {clip.promoted_to or ''}",
        f"next_surface: {clip.next_surface}",
        f"surface_count: {clip.surface_count}",
        "---",
    ]
    md_content = "\n".join(frontmatter_lines) + "\n\n" + clip.content

    path = clips_dir / filename
    fd, tmp_path = tempfile.mkstemp(dir=str(clips_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(md_content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return path


def filter_known_gaps(profile: Profile) -> None:
    """Remove gaps already marked as known from profile. Called after scan."""
    progress = load_gap_progress()
    known_gaps = {k for k, v in progress.items() if v.status == "known"}
    if not known_gaps:
        return
    for domain in profile.skills.domains.values():
        domain.gaps = [g for g in domain.gaps if g not in known_gaps]
    for integration in profile.skills.integrations.values():
        integration.gaps = [g for g in integration.gaps if g not in known_gaps]
