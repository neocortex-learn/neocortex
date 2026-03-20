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
    lines: int = 0
    frameworks: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)


class DomainSkill(BaseModel):
    level: SkillLevel = SkillLevel.BEGINNER
    evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class IntegrationSkill(BaseModel):
    level: SkillLevel = SkillLevel.BEGINNER
    providers: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ArchitectureSkill(BaseModel):
    level: SkillLevel = SkillLevel.BEGINNER
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


# ── Learning recommendations ──

class Recommendation(BaseModel):
    topic: str
    reason: str
    resources: list[str] = Field(default_factory=list)
    expected_benefit: str = ""
    priority: str = "medium"  # high / medium / low


# ── App config ──

class ProviderType(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    OPENAI_COMPAT = "openai-compat"


class ScanSettings(BaseModel):
    max_file_lines: int = 100
    exclude_patterns: list[str] = Field(default_factory=lambda: [
        "node_modules", "venv", ".venv", ".git", "dist", "build",
        "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
        "target", "vendor", ".next", ".nuxt",
    ])


class OutputSettings(BaseModel):
    auto_open: bool = True
    notes_dir: str = "~/.neocortex/notes"
    language: Language = Language.EN


class AppConfig(BaseModel):
    provider: ProviderType | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
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
