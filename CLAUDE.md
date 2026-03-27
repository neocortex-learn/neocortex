# Neocortex 开发规范

## 项目概述
Neocortex 是一个 AI 驱动的开发者技能分析和个性化学习助手。Python CLI 工具。

## 技术栈
- Python 3.10+, Typer + Rich + InquirerPy (CLI), Pydantic (数据模型)
- LLM: anthropic, openai, google-genai SDK
- 内容: httpx, readability-lxml, pymupdf, ebooklib, markdownify
- TTS: edge-tts
- 搜索: SQLite FTS5
- 测试: pytest + pytest-asyncio

## 开发命令
```bash
pip install -e .          # 安装开发版
python -m pytest tests/   # 运行测试
neocortex --help          # 查看 CLI 帮助
```

## 代码规范
- 所有文件使用 `from __future__ import annotations`
- 数据模型用 Pydantic BaseModel（在 models.py 中集中定义）
- LLM 调用都是 async 的，CLI 用 asyncio.run() 包装
- 面向用户的文本通过 i18n.py 的 t() 函数获取
- CLI 命令内部用延迟导入（在函数内 import）
- 测试用 pytest，async 测试用 @pytest.mark.asyncio + AsyncMock

## 目录结构
```
src/neocortex/
├── cli.py          # CLI 入口，共享工具，init/config 命令
├── cmd_scan.py     # scan + profile 命令
├── cmd_read.py     # read + 匹配 + 反馈
├── cmd_learn.py    # recommend + plan + growth + converge + opportunities
├── cmd_knowledge.py # notes + card + index + ask + chat
├── cmd_import.py   # import 命令
├── config.py       # 配置、画像、推荐记录、gap 进度读写
├── models.py       # 所有 Pydantic 数据模型
├── i18n.py         # 中英文国际化
├── recommender.py  # 学习路径推荐（结构化上下文 + gap 关联）
├── tracker.py      # 推荐跟踪：阅读 → 匹配推荐 → 更新 gap 状态
├── scan_cache.py   # 扫描结果缓存（按 git HEAD / 文件 mtime）
├── asker.py        # 交互式问答
├── growth.py       # 技能成长追踪
├── tts.py          # 音频输出
├── search.py       # SQLite FTS5 搜索
├── llm/            # LLM 适配层（含 describe_image）
├── scanner/        # 项目扫描（含 gap 同义词规范化）
├── reader/         # 内容阅读 + 笔记生成（URL/PDF/EPUB/图片/微信公众号）
└── importer/       # 聊天记录导入
```

## 核心机制

### 技能评估（Socratic Probe）
Code scan 只是冷启动（confidence: low），真实技能水平通过日常使用渐进校准：
- `recommend`/`read` 时：LLM 基于用户自己的代码问 1-2 个问题验证该领域水平
- `ask`/`chat` 时：被动分析问题质量（Bloom 层级），更新 confidence
- `read` 后：难度反馈（一键），调整校准
- 长期不练的技能：confidence 衰减
- 每个技能 = level + confidence（0-1）+ last_verified + verification_method
- `prober.py` 负责生成和评估验证问题

### 闭环学习
推荐 → 阅读 → 自动匹配推荐 → 更新 gap 状态 → 下次推荐更精准。
- 数据流：`recommend` 生成有序学习路径 → `read` 自动匹配（三级：URL/域名关键词/用户确认）→ gap 状态迁移（gap → learning → known）→ 下次 `recommend` 跳过已完成
- 存储：`~/.neocortex/recommendations.json` + `~/.neocortex/gap_progress.json`

### 学习路径（参考 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 的渐进式设计）
推荐不再是平铺的独立主题，而是**有序的学习路径**：
- 每条推荐有 `step`（学习顺序）和 `depends_on`（前置主题列表）
- 前置未完成的步骤处于锁定状态，完成后自动解锁下游步骤
- LLM prompt 要求按"基础→进阶"顺序排列，建立知识依赖关系
- `tracker.get_unlocked_recommendations()` 过滤出当前可学的步骤

### Gap 语义去重
`scanner/profile.py` 中的同义词表（`_GAP_SYNONYMS`）将 LLM 输出的不同表述归一化为统一名称。新发现的同义词直接加到表里。

### Token 优化（参考 learn-claude-code 的 Skill 按需加载思路）
`_build_context()` 按域分组展示 gap（减少重复 domain/level 标签），阅读历史只传标题不传完整路径，降低每次 LLM 调用的 token 消耗。

### 可视化笔记（Mermaid 图表）
笔记不再是纯文字墙，LLM 在生成笔记时自然嵌入 Mermaid 图表：
- 每篇笔记开头自动生成 **mindmap** 展示主题结构（从 outline 的 deep/brief 项构建）
- 流程用 flowchart，多方交互用 sequenceDiagram，结构关系用 classDiagram，状态变化用 stateDiagram
- 图表紧跟相关文字（空间邻近原则），不集中放在末尾
- 用户需要用支持 Mermaid 渲染的 Markdown 工具查看（Obsidian、Typora、VS Code 等）

### 写作质量（参考 [ljg-skills](https://github.com/lijigang/ljg-skills) 的论文阅读原则）
笔记生成 prompt 内置 7 条写作红线：口语检验、零术语优先、推理外显、变形替代定义、
落点在能用、一句一事、诚实。确保笔记是"活人在说话"而非"机器在汇报"。

### 视觉卡片（`neocortex card`）
将笔记转为可分享的 PNG 卡片（`reader/card.py`）。HTML 模板 + Playwright 截图。
深色/浅色主题，自动提取关键章节。Playwright 未安装时降级为 HTML 卡片。

### 概念深度解剖（`neocortex read --deep`）
参考 ljg-learn 的八维框架，从历史、辩证、现象、语言、形式、存在、美感、元反思
八个角度切开概念，最终压缩为一句顿悟 + ASCII 结构图。适合理论性内容。

### 知识管理（参考 Readwise/Obsidian）
笔记存储三层分离：
- **应用数据**（`~/.neocortex/`）：config、profile、数据库、缓存。用户不需要碰。
- **用户笔记**（`~/Documents/Neocortex/`，可配置）：纯 Markdown 文件，Finder 直接可见。
  通过 `neocortex config --notes-dir <path>` 可指向 Obsidian vault 或任意目录。
- **Frontmatter 元数据**：每篇笔记头部包含 source、date、tags、related_gaps 等 YAML 字段，
  兼容 Obsidian 图谱视图和其他知识管理工具。

## 注意事项
- Commit message 用中文
- 不要在 commit message 中加 Co-Authored-By
- 新增面向用户的文本必须同时添加中英文 i18n
- LLM 响应可能包含 <think> 标签（推理模型），已在 openai_compat.py 中统一剥离
- gap 名称必须通过 `normalize_gap_name()` 规范化后再存储/比较
- JSON 文件写入使用原子写入（temp file + os.replace），见 `config.py._save_json`
- 推荐必须包含 `step` 和 `depends_on` 字段，保持学习路径的有序性

## 设计参考
- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) — 渐进式学习路径设计、Skill 按需加载、任务依赖图
- [Obsidian](https://obsidian.md) — 本地 Markdown vault 模型、用户拥有文件
- [Readwise Reader](https://readwise.io/read) — 阅读→高亮→复习闭环、间隔复习算法
- [ljg-skills](https://github.com/lijigang/ljg-skills) — 论文阅读写作原则、视觉卡片生成、概念八维解剖
- [OpenClaw 扩张人生边界](https://mp.weixin.qq.com/s/fxJTb_3fduvs0MLn7nL99w) — AI 应和个人能力框架挂钩；信息→归档→累计→收敛=认知资产；能力-机会匹配
- [Gumloop 创始人访谈](https://mp.weixin.qq.com/s/anlBeR3jI3e4SYgPK0DWIg) — "AI 加持而非替代"、"只自动化你理解的东西"、"少数人用 AI 学习底层原理会更快变卓越"——验证了 Neocortex 的方向

## 外部工具依赖（可选）
- `wechat-article-to-markdown` — 微信公众号文章抓取，`neocortex read` 自动检测微信 URL 并调用
  安装：`uv tool install wechat-article-to-markdown`
- `mmdc`（mermaid-cli）— Mermaid 图表渲染为 SVG 图片
  安装：`npm install -g @mermaid-js/mermaid-cli`
