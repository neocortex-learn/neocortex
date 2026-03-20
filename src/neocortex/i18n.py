"""Internationalization strings for Neocortex CLI."""

from __future__ import annotations

from neocortex.models import Language

STRINGS: dict[str, dict[str, str]] = {
    # ── General ──
    "scanning": {
        "en": "Scanning project...",
        "zh": "正在扫描项目...",
    },
    "analyzing": {
        "en": "Analyzing with LLM...",
        "zh": "正在用 LLM 分析...",
    },
    "done": {
        "en": "Done!",
        "zh": "完成！",
    },
    "error": {
        "en": "Error",
        "zh": "错误",
    },

    # ── Init questionnaire ──
    "init_welcome": {
        "en": "Let's get to know you.",
        "zh": "让我们了解一下你。",
    },
    "init_role": {
        "en": "Your current role?",
        "zh": "你目前的角色？",
    },
    "init_experience": {
        "en": "Years of programming experience?",
        "zh": "编程经验年数？",
    },
    "init_goal": {
        "en": "What's your learning goal right now?",
        "zh": "你当前的学习目标是什么？",
    },
    "init_style": {
        "en": "How do you prefer to learn?",
        "zh": "你更喜欢哪种学习方式？",
    },
    "init_language": {
        "en": "Preferred language for notes?",
        "zh": "笔记使用什么语言？",
    },
    "init_done": {
        "en": "Profile initialized! Run [bold]neocortex scan[/bold] to analyze your projects.",
        "zh": "画像已初始化！运行 [bold]neocortex scan[/bold] 来分析你的项目。",
    },

    # ── Role choices ──
    "role_backend": {"en": "Backend Engineer", "zh": "后端工程师"},
    "role_frontend": {"en": "Frontend Engineer", "zh": "前端工程师"},
    "role_fullstack": {"en": "Full-stack Engineer", "zh": "全栈工程师"},
    "role_student": {"en": "Student", "zh": "学生"},
    "role_self_taught": {"en": "Self-taught Developer", "zh": "自学开发者"},

    # ── Experience choices ──
    "exp_0_1": {"en": "0-1 years", "zh": "0-1 年"},
    "exp_1_3": {"en": "1-3 years", "zh": "1-3 年"},
    "exp_3_5": {"en": "3-5 years", "zh": "3-5 年"},
    "exp_5_plus": {"en": "5+ years", "zh": "5+ 年"},

    # ── Learning goal choices ──
    "goal_system_design": {"en": "System design & architecture", "zh": "系统设计与架构"},
    "goal_new_framework": {"en": "New language/framework", "zh": "新语言/框架"},
    "goal_interview": {"en": "Interview prep", "zh": "面试准备"},
    "goal_level_up": {"en": "Level up at current job", "zh": "在当前工作中提升"},
    "goal_side_project": {"en": "Building a side project", "zh": "做个人项目"},

    # ── Learning style choices ──
    "style_code": {"en": "Explain with real code examples", "zh": "用真实代码示例讲解"},
    "style_theory": {"en": "Theory first, then practice", "zh": "先理论，后实践"},
    "style_do_it": {"en": "Just tell me what to do", "zh": "直接告诉我怎么做"},
    "style_compare": {"en": "Compare with things I already know", "zh": "用我已知的知识做类比"},

    # ── Language choices ──
    "lang_en": {"en": "English", "zh": "English"},
    "lang_zh": {"en": "中文", "zh": "中文"},

    # ── Config ──
    "config_saved": {
        "en": "Configuration saved.",
        "zh": "配置已保存。",
    },
    "config_no_provider": {
        "en": "No LLM provider configured. Run [bold]neocortex config --provider <name> --api-key <key>[/bold]",
        "zh": "未配置 LLM 提供商。运行 [bold]neocortex config --provider <name> --api-key <key>[/bold]",
    },
    "config_show": {
        "en": "Current configuration:",
        "zh": "当前配置：",
    },

    # ── Scan ──
    "scan_no_projects": {
        "en": "No project paths provided.",
        "zh": "未提供项目路径。",
    },
    "scan_not_found": {
        "en": "Project path not found: {path}",
        "zh": "项目路径不存在：{path}",
    },
    "scan_project": {
        "en": "Scanning: {name}",
        "zh": "正在扫描：{name}",
    },
    "scan_detected": {
        "en": "Detected: {langs} | {frameworks}",
        "zh": "检测到：{langs} | {frameworks}",
    },
    "scan_complete": {
        "en": "Scan complete. Profile updated.",
        "zh": "扫描完成。画像已更新。",
    },

    # ── Profile ──
    "profile_title": {
        "en": "Skill Profile",
        "zh": "技能画像",
    },
    "profile_empty": {
        "en": "No profile data yet. Run [bold]neocortex scan[/bold] first.",
        "zh": "还没有画像数据。请先运行 [bold]neocortex scan[/bold]。",
    },
    "profile_languages": {"en": "Languages", "zh": "编程语言"},
    "profile_frameworks": {"en": "Frameworks & Tools", "zh": "框架与工具"},
    "profile_domains": {"en": "Domains", "zh": "技术领域"},
    "profile_integrations": {"en": "Integrations", "zh": "第三方集成"},
    "profile_architecture": {"en": "Architecture", "zh": "架构模式"},
    "profile_exported": {
        "en": "Profile exported to {path}",
        "zh": "画像已导出到 {path}",
    },

    # ── Skill levels ──
    "level_beginner": {"en": "Beginner", "zh": "入门"},
    "level_proficient": {"en": "Proficient", "zh": "熟练"},
    "level_advanced": {"en": "Advanced", "zh": "进阶"},
    "level_expert": {"en": "Expert", "zh": "精通"},

    # ── Read ──
    "read_fetching": {
        "en": "Fetching content...",
        "zh": "正在获取内容...",
    },
    "read_outline_title": {
        "en": "Personalized outline for: {title}",
        "zh": "个性化大纲：{title}",
    },
    "read_outline_confirm": {
        "en": "Proceed with this outline?",
        "zh": "按此大纲继续？",
    },
    "read_generating": {
        "en": "Generating personalized notes...",
        "zh": "正在生成个性化笔记...",
    },
    "read_saved": {
        "en": "Note saved: {path}",
        "zh": "笔记已保存：{path}",
    },
    "read_marker_skip": {"en": "skip", "zh": "跳过"},
    "read_marker_brief": {"en": "brief overview", "zh": "简要概览"},
    "read_marker_deep": {"en": "deep dive", "zh": "深入学习"},

    # ── Feedback ──
    "feedback_prompt": {
        "en": "How was this note?",
        "zh": "这篇笔记怎么样？",
    },
    "feedback_too_easy": {"en": "Too easy", "zh": "太简单"},
    "feedback_just_right": {"en": "Just right", "zh": "刚好"},
    "feedback_too_hard": {"en": "Too hard", "zh": "太难"},
    "feedback_skip": {"en": "Skip", "zh": "跳过"},

    # ── Import ──
    "import_parsing": {
        "en": "Parsing {source} export...",
        "zh": "正在解析 {source} 导出文件...",
    },
    "import_extracting": {
        "en": "Extracting insights from {count} messages...",
        "zh": "正在从 {count} 条消息中提取洞察...",
    },
    "import_done": {
        "en": "Import complete. Profile updated with chat insights.",
        "zh": "导入完成。画像已更新聊天洞察。",
    },
    "import_no_messages": {
        "en": "No messages found in export.",
        "zh": "导出文件中未找到消息。",
    },
    "import_cleared": {
        "en": "Chat insights cleared from profile.",
        "zh": "已从画像中清除聊天洞察。",
    },

    # ── Notes ──
    "notes_title": {
        "en": "Knowledge Base",
        "zh": "知识库",
    },
    "notes_empty": {
        "en": "No notes yet. Run [bold]neocortex read <url>[/bold] to get started.",
        "zh": "还没有笔记。运行 [bold]neocortex read <url>[/bold] 开始学习。",
    },
    "notes_no_match": {
        "en": "No notes matching: {query}",
        "zh": "没有匹配的笔记：{query}",
    },
}


def t(key: str, lang: Language = Language.EN, **kwargs: str) -> str:
    """Get a translated string by key."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang.value, entry.get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text
