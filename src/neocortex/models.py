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


class ClipResult(BaseModel):
    """clip 操作的结构化结果，供 CLI / GUI 统一消费。

    Q14 决策：new_or_pending_clusters 只是标记，不在 clip 阶段生成 stub concepts/*.md。
    """
    saved_path: str
    clip: Clip
    # ok | skipped_no_key | skipped_user_opt_out | failed
    llm_status: str = "skipped_user_opt_out"
    llm_error: str | None = None
    existing_cluster_delta: list[ClusterDelta] = Field(default_factory=list)
    new_or_pending_clusters: list[str] = Field(default_factory=list)
    related_notes: list[RelatedNoteRef] = Field(default_factory=list)
