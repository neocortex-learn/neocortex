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
    status: str = "gap"  # gap / learning / known
    reads: int = 0
    first_seen: str = ""
    last_read: str | None = None


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
