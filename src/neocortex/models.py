"""Data models for Neocortex."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ── Skill levels ──

class SkillLevel(str, Enum):
    BEGINNER = "beginner"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"
    EXPERT = "expert"


# ── Skills (from code scanning) ──

class LanguageSkill(BaseModel):
    level: SkillLevel = SkillLevel.BEGINNER
    confidence: float = 0.3
    last_verified: str | None = None
    lines: int = 0
    frameworks: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)


class DomainSkill(BaseModel):
    level: SkillLevel = SkillLevel.BEGINNER
    confidence: float = 0.3
    last_verified: str | None = None
    evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class IntegrationSkill(BaseModel):
    level: SkillLevel = SkillLevel.BEGINNER
    confidence: float = 0.3
    last_verified: str | None = None
    providers: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ArchitectureSkill(BaseModel):
    level: SkillLevel = SkillLevel.BEGINNER
    confidence: float = 0.3
    last_verified: str | None = None
    patterns: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class Skills(BaseModel):
    languages: dict[str, LanguageSkill] = Field(default_factory=dict)
    domains: dict[str, DomainSkill] = Field(default_factory=dict)
    integrations: dict[str, IntegrationSkill] = Field(default_factory=dict)
    architecture: dict[str, ArchitectureSkill] = Field(default_factory=dict)


# ── Persona (from init questionnaire) ──

class Role(str, Enum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "full-stack"
    STUDENT = "student"
    SELF_TAUGHT = "self-taught"


class ExperienceRange(str, Enum):
    JUNIOR = "0-1"
    MID = "1-3"
    SENIOR = "3-5"
    EXPERT = "5+"


class LearningGoal(str, Enum):
    SYSTEM_DESIGN = "system_design"
    NEW_FRAMEWORK = "new_framework"
    INTERVIEW = "interview_prep"
    LEVEL_UP = "level_up"
    SIDE_PROJECT = "side_project"


class LearningStyle(str, Enum):
    CODE_EXAMPLES = "code_examples"
    THEORY_FIRST = "theory_first"
    JUST_DO_IT = "just_do_it"
    COMPARE_WITH_KNOWN = "compare_with_known"


class Language(str, Enum):
    EN = "en"
    ZH = "zh"
    JA = "ja"
    KO = "ko"


class Persona(BaseModel):
    role: Role | None = None
    experience_years: ExperienceRange | None = None
    learning_goal: LearningGoal | None = None
    learning_style: LearningStyle | None = None
    language: Language = Language.EN


# ── Chat insights (from chat history import) ──

class QuestionAsked(BaseModel):
    topic: str
    level: str  # beginner / intermediate / advanced
    date: str
    summary: str


class ChatInsights(BaseModel):
    source: str  # "chatgpt" or "claude"
    imported_at: str
    message_count: int = 0
    date_range: list[str] = Field(default_factory=list)
    questions_asked: list[QuestionAsked] = Field(default_factory=list)
    topics_discussed: list[str] = Field(default_factory=list)
    confusion_points: list[str] = Field(default_factory=list)
    growth_trajectory: str = ""


# ── Learning history (auto-tracked) ──

class TopicRead(BaseModel):
    source: str
    title: str
    date: str
    focus: str | None = None
    feedback: str | None = None  # "too_easy", "just_right", "too_hard"


class LearningHistory(BaseModel):
    topics_read: list[TopicRead] = Field(default_factory=list)
    topic_frequency: dict[str, int] = Field(default_factory=dict)


# ── Difficulty calibration ──

class Calibration(BaseModel):
    level_offset: int = 0
    consecutive_too_easy: int = 0
    consecutive_too_hard: int = 0


# ── User profile (aggregate) ──

class Profile(BaseModel):
    skills: Skills = Field(default_factory=Skills)
    chat_insights: ChatInsights | None = None
    persona: Persona = Field(default_factory=Persona)
    learning_history: LearningHistory = Field(default_factory=LearningHistory)
    calibration: Calibration = Field(default_factory=Calibration)


# ── Profile snapshots (growth tracking) ──

class ProfileSnapshot(BaseModel):
    date: str
    skills: Skills = Field(default_factory=Skills)
    total_lines: int = 0
    total_projects: int = 0
    notes_count: int = 0


# ── Learning recommendations ──

class Recommendation(BaseModel):
    topic: str
    reason: str
    resources: list[str] = Field(default_factory=list)
    expected_benefit: str = ""
    priority: str = "medium"  # high / medium / low
    related_gaps: list[str] = Field(default_factory=list)
    step: int = 0
    depends_on: list[str] = Field(default_factory=list)


class Resource(BaseModel):
    """推荐资源"""
    title: str
    url: str = ""
    type: str = "article"  # article / doc / book / video / tutorial


class GapProgress(BaseModel):
    """单个技能 gap 的学习进度"""
    status: str = "gap"  # gap / learning / verified / known
    reads: int = 0
    first_seen: str = ""
    last_read: str | None = None
    verified_at: str | None = None
    calibration_history: list[dict] = Field(default_factory=list)


class RecommendationRecord(BaseModel):
    """推荐跟踪记录"""
    id: str
    topic: str
    resources: list[Resource] = Field(default_factory=list)
    related_gaps: list[str] = Field(default_factory=list)
    step: int = 0
    depends_on: list[str] = Field(default_factory=list)
    created_at: str = ""
    status: str = "pending"  # pending / completed / skipped
    completed_at: str | None = None
    notes_generated: list[str] = Field(default_factory=list)


# ── Opportunities ──

class Opportunity(BaseModel):
    """A matched opportunity (job, OSS issue, project)."""
    type: str = "oss"  # oss / job
    title: str
    url: str = ""
    source: str = ""
    skills_matched: list[str] = Field(default_factory=list)
    skills_missing: list[str] = Field(default_factory=list)
    match_score: float = 0.0
    difficulty: str = "any"
    fetched_at: str = ""


# ── App config ──

class ProviderType(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    OPENAI_COMPAT = "openai-compat"


class ScanSettings(BaseModel):
    max_file_lines: int = 100
    exclude_patterns: list[str] = Field(default_factory=lambda: [
        # Version control
        ".git",
        # JavaScript / Node.js
        "node_modules", ".next", ".nuxt",
        # Python
        "venv", ".venv", "env", ".env",
        "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", ".eggs",
        # Build output
        "dist", "build", ".build", "out",
        # Java / Kotlin / Android
        "target", ".gradle",
        # Go
        "vendor",
        # iOS / macOS
        "Pods", "Carthage", "DerivedData",
        # C/C++
        "cmake-build-debug", "cmake-build-release",
        # Vendored dependencies
        "third_party", "third-party", "external",
    ])


class OutputSettings(BaseModel):
    auto_open: bool = True
    notes_dir: str = "~/Documents/Neocortex"
    language: Language = Language.EN


class AppConfig(BaseModel):
    provider: ProviderType | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    github_token: str | None = None
    scan_settings: ScanSettings = Field(default_factory=ScanSettings)
    output_settings: OutputSettings = Field(default_factory=OutputSettings)
    experimental: list[str] = Field(default_factory=list)
    # Q11: 配置了 LLM key 时 `neocortex clip` 默认走即时关联；设 False 退回零 LLM 路径。
    clip_default_process: bool = True


# ── Reader models ──

class OutlineItem(BaseModel):
    title: str
    marker: str  # "skip", "brief", "deep"
    reason: str


class Outline(BaseModel):
    source: str
    items: list[OutlineItem] = Field(default_factory=list)


# ── Scanner models ──

class ProjectInfo(BaseModel):
    path: str
    name: str
    languages: dict[str, int] = Field(default_factory=dict)  # lang -> lines
    config_files: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    architecture_signals: list[str] = Field(default_factory=list)
    summary: str = ""


# ── Spaced repetition (flashcards) ──

class Flashcard(BaseModel):
    id: str
    source_note: str
    question: str
    answer: str
    concept: str = ""
    difficulty: str = "medium"  # easy / medium / hard
    knowledge_layer: str = "conceptual"  # factual / conceptual / procedural
    card_type: str = "standard"  # standard / relationship
    interval: int = 1
    ease_factor: float = 2.5
    next_review: str = ""
    review_count: int = 0
    last_review: str | None = None
    # 软淘汰标记：suspended 卡不进入任何复习队列/统计，但保留在原 JSON 里
    # 以便撤销和质量分析。旧 JSON 没有该字段 → 默认 False（向后兼容）。
    suspended: bool = False


class ReviewStats(BaseModel):
    date: str
    cards_reviewed: int = 0
    correct: int = 0
    incorrect: int = 0
    skipped: int = 0


# ── Concept compilation ──

class ConceptRef(BaseModel):
    """从笔记中提取的概念引用。"""
    name: str
    definition_brief: str = ""
    related_to: list[str] = Field(default_factory=list)


class ConceptEntry(BaseModel):
    """概念条目的元数据。"""
    name: str
    aliases: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    skill_level: SkillLevel = SkillLevel.BEGINNER
    confidence: float = 0.3
    evidence_count: int = 0
    last_updated: str = ""
    source_notes: list[str] = Field(default_factory=list)


class CompileResult(BaseModel):
    """编译结果统计。"""
    notes_processed: int = 0
    concepts_created: int = 0
    concepts_updated: int = 0
    wikilinks_inserted: int = 0
    index_updated: bool = False
    conflicts: list[dict] = Field(default_factory=list)
    # 已翻译好的用户可见文案（如搜索索引重建失败），供 cmd_compile.py 展示。
    warnings: list[str] = Field(default_factory=list)


class CompileJobStatus(BaseModel):
    """HTTP compile job 状态快照（POST /api/compile + GET /api/compile/status）。

    compile 是分钟级长任务，HTTP 层用后台任务 + 轮询而不是同步阻塞。
    ``accepted`` 只对 POST 响应有意义：False 表示已有任务在跑，本次未启动新任务。
    """
    state: str = "idle"  # idle | running | done | failed
    accepted: bool = True
    force: bool = False
    current: int = 0
    total: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    result: CompileResult | None = None
    error: str | None = None


# ── Lint ──

class LintIssue(BaseModel):
    type: str  # orphan, broken_link, stale, coverage_gap, duplicate, suggestion
    severity: str = "warning"  # error, warning, info
    message: str
    details: str = ""
    auto_fixable: bool = False


class LintReport(BaseModel):
    score: int = 100
    issues: list[LintIssue] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


# ── Verify ──

class FactVerdict(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNVERIFIABLE = "unverifiable"


class AtomicFact(BaseModel):
    """从概念条目中分解出的原子事实。"""
    text: str
    section: str = ""
    concept: str = ""


class Evidence(BaseModel):
    """支撑某个原子事实的证据片段。"""
    source_note: str
    excerpt: str
    matched_by: str = "keyword"  # keyword | semantic | llm


class FactCheck(BaseModel):
    """单个事实的验证结果。"""
    fact: AtomicFact
    verdict: FactVerdict = FactVerdict.UNVERIFIABLE
    evidence: list[Evidence] = Field(default_factory=list)
    explanation: str = ""


class ConceptVerification(BaseModel):
    """单个概念条目的验证结果。"""
    concept_name: str
    fact_checks: list[FactCheck] = Field(default_factory=list)
    supported_count: int = 0
    unsupported_count: int = 0
    unverifiable_count: int = 0

    @property
    def total_facts(self) -> int:
        return len(self.fact_checks)

    @property
    def supported_ratio(self) -> float:
        if not self.fact_checks:
            return 1.0
        return self.supported_count / len(self.fact_checks)


class VerifyReport(BaseModel):
    """知识库忠实度验证报告。"""
    fidelity_score: int = 100
    concepts_verified: int = 0
    total_facts: int = 0
    supported: int = 0
    unsupported: int = 0
    unverifiable: int = 0
    concept_results: list[ConceptVerification] = Field(default_factory=list)
    overview_checks: list[FactCheck] = Field(default_factory=list)
    claims_checks: list[FactCheck] = Field(default_factory=list)
    consistency_checks: list[FactCheck] = Field(default_factory=list)
    depth: str = "standard"
    date: str = ""


# ── Clip ──

class Clip(BaseModel):
    id: str
    source: str
    content: str
    title: str = ""
    clip_type: str = "thought"
    auto_tags: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    status: str = "inbox"
    summary: str = ""
    relevance: str = ""
    priority: str = ""
    topic: str = ""
    takeaways: list[str] = Field(default_factory=list)
    diagram: str = ""
    created_at: str = ""
    processed_at: str | None = None
    promoted_to: str | None = None
    next_surface: str = ""
    surface_count: int = 0


class ClusterDelta(BaseModel):
    """已有概念页的 evidence_count 增长记录。"""
    concept: str
    count_before: int
    count_after: int


class RelatedNoteRef(BaseModel):
    """指向 vault 中已有笔记的相关性引用。"""
    filename: str
    title: str
    snippet: str = ""
    reason: str = ""


class ReadResult(BaseModel):
    """Structured result of a `read` (deep note) operation.

    Mirrors the CLI ``cmd_read`` core flow: fetch → outline → generate_notes
    → save. Aborts (fetch failed, LLM error mid-stream) come back with
    ``aborted=True`` + ``abort_reason``.
    """
    saved_path: str
    title: str
    source: str
    topic_dir: str
    word_count: int = 0
    deep_topics: list[str] = Field(default_factory=list)
    brief_topics: list[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
    aborted: bool = False
    abort_reason: str | None = None
    # True when an existing note with the same source URL was returned
    # instead of re-running fetch/outline/N×LLM. saved_path points to the
    # original; LLM cost and clutter both avoided.
    reused: bool = False


class AskResult(BaseModel):
    """ask 操作的结构化结果：一问一答 + 是否自动 save 为 insight。

    Query 反写：若 LLM 判定回答含新综合 / 跨概念连接（``evaluate_insight_value``
    返回 True），自动写入 insights/ 并返回相对路径。否则 ``saved_as_insight=None``。

    Aborted（provider 未配置 / LLM 调用失败）：``aborted=True`` + ``abort_reason``，
    answer 为空字符串。
    """
    question: str
    answer: str
    saved_as_insight: str | None = None  # vault 相对路径或 None
    elapsed_seconds: float = 0.0
    aborted: bool = False
    abort_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)  # 非致命失败（如洞察评估挂了）


class ConceptMap(BaseModel):
    """Concept map (Mermaid graph) for the GUI map panel.

    The GUI just renders ``mermaid_source`` straight through MermaidView;
    metadata fields drive the header chip (count + filter description).
    ``concepts_returned == 0`` is a valid state: the vault has no concepts
    yet (run ``kb compile`` first).
    """
    mermaid_source: str
    concepts_returned: int = 0
    edges_returned: int = 0
    filter_description: str = "none"  # "domain=ai" / "around=transformer" / "none"


class SurfacingItem(BaseModel):
    """A clip that should be re-surfaced today (saved 3/7/14/30/60 days ago)."""
    clip_id: str = ""           # 8-char uuid from save_clip; required for /api/daily/surface
    saved_path: str
    title: str
    summary: str = ""
    days_ago: int = 0
    related_concepts: list[str] = Field(default_factory=list)
    # Optional LLM "what's changed since you saved this" context (~1 sentence).
    context_update: str = ""
    # True when the concept this clip touches has matured (≥3 evidences).
    absorbed: bool = False


class SurfaceUpdate(BaseModel):
    """Result of marking a clip as surfaced (or absorbed)."""
    clip_id: str
    next_surface: str        # YYYY-MM-DD, when this clip will resurface next
    surface_count: int       # how many times it's been surfaced now
    absorbed: bool           # True → next_surface jumped to +180 days


class ClusterSuggestion(BaseModel):
    """A concept appearing in ≥3 inbox clips → synthesis candidate."""
    concept: str
    clip_count: int


class HealthPulse(BaseModel):
    """Knowledge-base health snapshot: latest lint + verify scores w/ trend."""
    lint_score: int | None = None
    lint_delta: int | None = None      # vs previous report
    lint_sparkline: str = ""           # last 8 reports, ASCII blocks
    lint_stale_days: int | None = None
    verify_score: int | None = None
    verify_delta: int | None = None
    verify_sparkline: str = ""


class DailyBriefing(BaseModel):
    """Output of ``services/daily.build_briefing``.

    Read-only: building a briefing does NOT advance ``next_surface`` schedules
    (the CLI ``daily`` command does that; the GUI version is lighter — user
    must click a surfacing item to mark it surfaced explicitly, future work).
    """
    date: str  # YYYY-MM-DD
    surfacing: list[SurfacingItem] = Field(default_factory=list)
    due_flashcard_count: int = 0
    cluster_suggestions: list[ClusterSuggestion] = Field(default_factory=list)
    uncompiled_count: int = 0
    health_pulse: HealthPulse = Field(default_factory=HealthPulse)


class ClipResult(BaseModel):
    """clip 操作的结构化结果，供 CLI / GUI 统一消费。

    Q14 决策：new_or_pending_clusters 只是标记，不在 clip 阶段生成 stub concepts/*.md。

    Aborted 状态（fetch 硬失败）：``aborted=True`` + ``abort_reason`` 携带原因，
    其余字段为占位空值（``saved_path=""``，``clip`` 是默认空 Clip）。HTTP 端点返回
    200 OK + aborted=true（请求本身合法，上游抓取失败属业务结果而非协议错误）。
    """
    saved_path: str
    clip: Clip
    # ok | skipped_no_key | skipped_user_opt_out | skipped_weak_fetch | failed
    llm_status: str = "skipped_user_opt_out"
    llm_error: str | None = None
    existing_cluster_delta: list[ClusterDelta] = Field(default_factory=list)
    new_or_pending_clusters: list[str] = Field(default_factory=list)
    related_notes: list[RelatedNoteRef] = Field(default_factory=list)
    # 抓取硬失败时由 service 设置；CLI / GUI 渲染时显示拒收提示。
    aborted: bool = False
    abort_reason: str | None = None
    # 同 URL 已经剪过 → 直接返回旧笔记路径，不写新文件、不调 LLM。
    reused: bool = False
