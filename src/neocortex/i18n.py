"""Internationalization strings for Neocortex CLI."""

from __future__ import annotations

from neocortex.models import Language

STRINGS: dict[str, dict[str, str]] = {
    # ── General ──
    "scanning": {
        "en": "Scanning project...",
        "zh": "正在扫描项目...",
        "ja": "プロジェクトをスキャン中...",
        "ko": "프로젝트 스캔 중...",
    },
    "analyzing": {
        "en": "Analyzing with LLM...",
        "zh": "正在用 LLM 分析...",
        "ja": "LLM で分析中...",
        "ko": "LLM으로 분석 중...",
    },
    "done": {
        "en": "Done!",
        "zh": "完成！",
        "ja": "完了！",
        "ko": "완료!",
    },
    "error": {
        "en": "Error",
        "zh": "错误",
        "ja": "エラー",
        "ko": "오류",
    },

    # ── Init questionnaire ──
    "init_welcome": {
        "en": "Let's get to know you.",
        "zh": "让我们了解一下你。",
        "ja": "あなたについて教えてください。",
        "ko": "당신에 대해 알려주세요.",
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
        "ja": "プロファイル初期化完了！[bold]neocortex scan[/bold] を実行してプロジェクトを分析しましょう。",
        "ko": "프로필 초기화 완료! [bold]neocortex scan[/bold]을 실행하여 프로젝트를 분석하세요.",
    },

    # ── Init onboarding ──
    "init_scanning_title": {
        "en": "Let me find your projects...",
        "zh": "让我找找你的项目...",
    },
    "init_discovering": {
        "en": "Scanning for projects...",
        "zh": "正在搜索项目...",
    },
    "init_no_projects": {
        "en": "No projects found. You can scan manually later: neocortex scan <path>",
        "zh": "没找到项目。你可以稍后手动扫描：neocortex scan <path>",
    },
    "init_found_projects": {
        "en": "Found {count} projects:",
        "zh": "找到 {count} 个项目：",
    },
    "init_more_projects": {
        "en": "and {count} more",
        "zh": "还有 {count} 个",
    },
    "init_scan_confirm": {
        "en": "Scan these projects to build your profile?",
        "zh": "扫描这些项目来构建你的画像？",
    },
    "init_complete": {
        "en": "Setup complete! I now know your skills.",
        "zh": "设置完成！我已经了解你的技能了。",
    },
    "init_next_steps": {
        "en": "What to do next:",
        "zh": "接下来可以：",
    },
    "init_hint_read": {
        "en": "Read an article with personalized notes",
        "zh": "读文章，生成个性化笔记",
    },
    "init_hint_ask": {
        "en": "Ask anything, I know your background",
        "zh": "问问题，我了解你的背景",
    },
    "init_hint_recommend": {
        "en": "See what you should learn next",
        "zh": "看看你该学什么",
    },
    "init_hint_profile": {
        "en": "View your full skill profile",
        "zh": "查看完整技能画像",
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
        "ja": "設定を保存しました。",
        "ko": "설정이 저장되었습니다.",
    },
    "config_no_provider": {
        "en": "No LLM provider configured. Run [bold]neocortex config --provider <name> --api-key <key>[/bold]",
        "zh": "未配置 LLM 提供商。运行 [bold]neocortex config --provider <name> --api-key <key>[/bold]",
    },
    "config_show": {
        "en": "Current configuration:",
        "zh": "当前配置：",
        "ja": "現在の設定：",
        "ko": "현재 설정:",
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
        "ja": "スキャン完了。プロファイルを更新しました。",
        "ko": "스캔 완료. 프로필이 업데이트되었습니다.",
    },

    # ── Profile ──
    "profile_title": {
        "en": "Skill Profile",
        "zh": "技能画像",
        "ja": "スキルプロファイル",
        "ko": "스킬 프로필",
    },
    "profile_empty": {
        "en": "No profile data yet. Run [bold]neocortex scan[/bold] first.",
        "zh": "还没有画像数据。请先运行 [bold]neocortex scan[/bold]。",
        "ja": "プロファイルデータがありません。まず [bold]neocortex scan[/bold] を実行してください。",
        "ko": "프로필 데이터가 없습니다. 먼저 [bold]neocortex scan[/bold]을 실행하세요.",
    },
    "profile_languages": {
        "en": "Languages",
        "zh": "编程语言",
        "ja": "プログラミング言語",
        "ko": "프로그래밍 언어",
    },
    "profile_frameworks": {
        "en": "Frameworks & Tools",
        "zh": "框架与工具",
        "ja": "フレームワーク・ツール",
        "ko": "프레임워크 및 도구",
    },
    "profile_domains": {
        "en": "Domains",
        "zh": "技术领域",
        "ja": "技術領域",
        "ko": "기술 도메인",
    },
    "profile_integrations": {
        "en": "Integrations",
        "zh": "第三方集成",
        "ja": "外部連携",
        "ko": "외부 연동",
    },
    "profile_architecture": {
        "en": "Architecture",
        "zh": "架构模式",
        "ja": "アーキテクチャ",
        "ko": "아키텍처",
    },
    "profile_exported": {
        "en": "Profile exported to {path}",
        "zh": "画像已导出到 {path}",
    },

    # ── Skill levels ──
    "level_beginner": {
        "en": "Beginner",
        "zh": "入门",
        "ja": "初心者",
        "ko": "입문",
    },
    "level_proficient": {
        "en": "Proficient",
        "zh": "熟练",
        "ja": "中級",
        "ko": "숙련",
    },
    "level_advanced": {
        "en": "Advanced",
        "zh": "进阶",
        "ja": "上級",
        "ko": "고급",
    },
    "level_expert": {
        "en": "Expert",
        "zh": "精通",
        "ja": "エキスパート",
        "ko": "전문가",
    },

    # ── Read ──
    "read_fetching": {
        "en": "Fetching content...",
        "zh": "正在获取内容...",
        "ja": "コンテンツを取得中...",
        "ko": "콘텐츠를 가져오는 중...",
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
        "ja": "パーソナライズされたノートを生成中...",
        "ko": "맞춤형 노트를 생성 중...",
    },
    "read_saved": {
        "en": "Note saved: {path}",
        "zh": "笔记已保存：{path}",
        "ja": "ノートを保存しました：{path}",
        "ko": "노트가 저장되었습니다: {path}",
    },
    "read_marker_skip": {"en": "skip", "zh": "跳过"},
    "read_marker_brief": {"en": "brief overview", "zh": "简要概览"},
    "read_marker_deep": {"en": "deep dive", "zh": "深入学习"},

    # ── Feedback ──
    "feedback_prompt": {
        "en": "How was this note?",
        "zh": "这篇笔记怎么样？",
        "ja": "このノートはいかがでしたか？",
        "ko": "이 노트는 어떠셨나요?",
    },
    "feedback_too_easy": {
        "en": "Too easy",
        "zh": "太简单",
        "ja": "簡単すぎる",
        "ko": "너무 쉬움",
    },
    "feedback_just_right": {
        "en": "Just right",
        "zh": "刚好",
        "ja": "ちょうどいい",
        "ko": "딱 적당함",
    },
    "feedback_too_hard": {
        "en": "Too hard",
        "zh": "太难",
        "ja": "難しすぎる",
        "ko": "너무 어려움",
    },
    "feedback_skip": {
        "en": "Skip",
        "zh": "跳过",
        "ja": "スキップ",
        "ko": "건너뛰기",
    },

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

    # ── Recommend ──
    "recommend_generating": {
        "en": "Generating learning recommendations...",
        "zh": "正在生成学习建议...",
        "ja": "学習レコメンドを生成中...",
        "ko": "학습 추천을 생성 중...",
    },
    "recommend_title": {
        "en": "Learning Recommendations",
        "zh": "学习路径推荐",
        "ja": "学習レコメンド",
        "ko": "학습 추천",
    },
    "recommend_empty": {
        "en": "Could not generate recommendations. Try again later.",
        "zh": "未能生成推荐。请稍后重试。",
    },
    "recommend_benefit": {
        "en": "Benefit:",
        "zh": "预期收益：",
    },
    "recommend_resources": {
        "en": "Resources:",
        "zh": "推荐资源：",
    },

    # ── Growth ──
    "growth_title": {
        "en": "Skill Growth",
        "zh": "技能成长",
        "ja": "スキル成長",
        "ko": "스킬 성장",
    },
    "growth_no_data": {
        "en": "No snapshots yet. Run [bold]neocortex scan[/bold] to start tracking.",
        "zh": "还没有快照数据。运行 [bold]neocortex scan[/bold] 开始追踪。",
    },
    "growth_snapshots": {
        "en": "{count} snapshots recorded",
        "zh": "已记录 {count} 次快照",
    },
    "growth_current": {
        "en": "Current:",
        "zh": "当前：",
    },
    "growth_new_langs": {
        "en": "New languages learned:",
        "zh": "新学的语言：",
    },
    "growth_level_ups": {
        "en": "Level ups:",
        "zh": "技能升级：",
    },
    "growth_new_domains": {
        "en": "New domains explored:",
        "zh": "新探索的领域：",
    },
    "growth_gaps_closed": {
        "en": "Gaps closed:",
        "zh": "已补的盲区：",
    },

    # ── Audio / TTS ──
    "audio_generating": {
        "en": "Generating audio...",
        "zh": "正在生成音频...",
    },
    "audio_saved": {
        "en": "Audio saved: {path}",
        "zh": "音频已保存：{path}",
    },

    # ── Ask ──
    "ask_thinking": {
        "en": "Thinking...",
        "zh": "正在思考...",
        "ja": "考え中...",
        "ko": "생각 중...",
    },

    # ── Chat ──
    "chat_welcome": {
        "en": "Neocortex Chat (type 'exit' to quit)",
        "zh": "Neocortex 对话模式（输入 exit 退出）",
        "ja": "Neocortex チャット（exit で終了）",
        "ko": "Neocortex 채팅 (exit 입력으로 종료)",
    },
    "chat_profile_loaded": {
        "en": "Your profile is loaded. Ask me anything.",
        "zh": "已加载你的画像，问我任何问题。",
        "ja": "プロファイルを読み込みました。何でも聞いてください。",
        "ko": "프로필이 로드되었습니다. 무엇이든 물어보세요.",
    },
    "chat_prompt": {
        "en": "You",
        "zh": "你",
        "ja": "あなた",
        "ko": "You",
    },
    "chat_goodbye": {
        "en": "Goodbye!",
        "zh": "再见！",
        "ja": "さようなら！",
        "ko": "안녕히 가세요!",
    },

    # ── GitHub ──
    "github_cloning": {
        "en": "Cloning {repo}...",
        "zh": "正在克隆 {repo}...",
    },
    "github_listing": {
        "en": "Listing repositories for {user}...",
        "zh": "正在列出 {user} 的仓库...",
    },
    "github_no_token": {
        "en": "GitHub token not configured. Run: neocortex config --github-token <token>",
        "zh": "未配置 GitHub token。运行：neocortex config --github-token <token>",
    },
    "github_scanning": {
        "en": "Scanning {count} repositories...",
        "zh": "正在扫描 {count} 个仓库...",
    },
    "github_no_repos": {
        "en": "No repositories found for {user}.",
        "zh": "未找到 {user} 的仓库。",
    },
    "github_clone_failed": {
        "en": "Failed to clone {repo}: {error}",
        "zh": "克隆 {repo} 失败：{error}",
    },
    "github_api_error": {
        "en": "GitHub API error: {error}",
        "zh": "GitHub API 错误：{error}",
    },
    "github_token_saved": {
        "en": "GitHub token saved.",
        "zh": "GitHub token 已保存。",
    },

    # ── Notes ──
    "notes_title": {
        "en": "Knowledge Base",
        "zh": "知识库",
        "ja": "ナレッジベース",
        "ko": "지식 베이스",
    },
    "notes_empty": {
        "en": "No notes yet. Run [bold]neocortex read <url>[/bold] to get started.",
        "zh": "还没有笔记。运行 [bold]neocortex read <url>[/bold] 开始学习。",
        "ja": "ノートがありません。[bold]neocortex read <url>[/bold] を実行して学習を始めましょう。",
        "ko": "아직 노트가 없습니다. [bold]neocortex read <url>[/bold]을 실행하여 학습을 시작하세요.",
    },
    "notes_no_match": {
        "en": "No notes matching: {query}",
        "zh": "没有匹配的笔记：{query}",
    },

    # ── Index / Search ──
    "index_building": {
        "en": "Building search index...",
        "zh": "正在构建搜索索引...",
    },
    "index_done": {
        "en": "Indexed {count} notes.",
        "zh": "已索引 {count} 篇笔记。",
    },
    "search_result": {
        "en": "Search results for: {query}",
        "zh": "搜索结果：{query}",
    },
    "index_embedding": {
        "en": "Generating embeddings...",
        "zh": "正在生成向量索引...",
    },
    "index_embedding_done": {
        "en": "Embeddings generated.",
        "zh": "向量索引已生成。",
    },
    "index_embedding_skip": {
        "en": "Embeddings skipped (fastembed not installed).",
        "zh": "向量索引已跳过（fastembed 未安装）。",
    },

    # ── Plan ──
    "plan_generating": {
        "en": "Generating learning plan...",
        "zh": "正在生成学习计划...",
        "ja": "学習プランを生成中...",
        "ko": "학습 계획을 생성 중...",
    },
    "plan_saved": {
        "en": "Learning plan saved: {path}",
        "zh": "学习计划已保存：{path}",
        "ja": "学習プランを保存しました：{path}",
        "ko": "학습 계획이 저장되었습니다: {path}",
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
