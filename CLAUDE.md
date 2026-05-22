# Neocortex 开发规范

## 项目概述
Neocortex 是一个 AI 驱动的个人知识库工具。Python CLI。

核心理念：把知识库当代码仓库管——有 intake（clip），有 compile（概念提取），有 search（检索），有 health check（lint/verify）。
- **轻路径（默认）**：clip（零 LLM 存入）→ compile（批量整理）→ ask/search（搜到）
- **重路径（可选）**：read（深度笔记）→ probe（验证）→ review（复习）

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

## CLI 命令结构
```
顶层命令（9 个）：clip, search, ask (--chat), read, review, inbox, daily, serve
子命令组：
  kb:       notes, card, compile, lint, verify, map
  discover: explore, research, feed
  learn:    recommend (--plan), digest, opportunities
  profile:  init, config, scan, import, 默认（查看画像）
```

`serve` 启动本地 FastAPI server（127.0.0.1 + Bearer token），供 GUI 客户端（SwiftUI / Tauri）调用。详见 `docs/SERVER.md` 与本文件下方的 server/services 层说明。

## 目录结构
```
src/neocortex/
├── cli.py          # CLI 入口，app + 4 个子 app（kb/discover/learn/profile）
├── cmd_scan.py     # profile 组：scan + profile（callback）
├── cmd_read.py     # 顶层：read + 匹配 + 反馈
├── cmd_learn.py    # learn 组：recommend (--plan) + opportunities；保留 growth/converge 函数
├── cmd_knowledge.py # 顶层：ask (--chat) + review；kb 组：notes + card
├── cmd_import.py   # profile 组：import 命令
├── cmd_compile.py  # kb 组：compile（概念编译）
├── cmd_lint.py     # kb 组：lint（知识库健康检查）
├── cmd_verify.py   # kb 组：verify（忠实度验证）
├── cmd_visualize.py # kb 组：map；learn 组：digest
├── cmd_clip.py     # 顶层：clip + inbox
├── cmd_daily.py    # 顶层：daily（含 _show_health_pulse — lint/fidelity 趋势）
├── cmd_search.py   # 顶层：search（FTS5 + 向量混合检索）
├── cmd_serve.py    # 顶层：serve（启动 FastAPI 本地 server，写 ~/.neocortex/server.{pid,port,token}）
├── cmd_explore.py  # discover 组：explore
├── cmd_research.py # discover 组：research
├── cmd_feed.py     # discover 组：feed
├── clipper.py      # 碎片捕获处理引擎（URL/文本/截图，默认零 LLM）
├── dedup.py        # URL 规范化 + frontmatter 查重（仅 services 层调用，CLI 路径暂不去重）
├── compiler.py     # 概念编译引擎（提取、生成、wikilink、索引、语义链接）
├── converger.py    # 认知收敛（跨笔记综合高层理解）
├── decay.py        # 知识信心衰减（Hidalgo 年衰减 50% 模型）
├── discovery.py    # 自动发现本地项目（onboarding 用）
├── explorer.py     # 站点探索引擎（扫描作者文章列表并排序）
├── feeder.py       # RSS 订阅引擎（获取 feed + gap 智能过滤）
├── linter.py       # 知识库健康检查（孤岛、断链、陈旧、覆盖盲区、重复、衰减、建议探索、低忠实度共 8 项）
├── verifier.py     # 忠实度验证引擎（原子事实分解 → 源笔记溯源 → 独立审查判定）
├── planner.py      # 学习计划生成器（结构化周计划）
├── prober.py       # Socratic Probe 技能校准（4 种题型 + 元认知校准）
├── researcher.py   # 网络搜索引擎（搜索 gap 相关文章 + LLM 排序）
├── reviewer.py     # SM-2 间隔复习调度引擎
├── config.py       # 配置、画像、推荐记录、gap 进度、闪卡读写
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
├── matcher/        # 推荐匹配（base 策略 + GitHub 机会匹配）
├── importer/       # 聊天记录导入
├── services/       # 纯函数服务层（无 Rich/Typer/交互），HTTP server 入口
│                   # clip / read / ask / daily / notes / visualize
└── server/         # FastAPI 本地 server（Sprint 0）
    ├── app.py         # create_app() 工厂 + healthz + version
    ├── runtime.py     # PID/port/token 文件管理（0600）
    ├── security.py    # SecurityMiddleware + WS 握手校验
    └── routes/        # 7 个 router：clip/read/notes/search/ask/daily/map
```

## Server / Services 层（Sprint 0）

**目的**：把 CLI 内部逻辑包装成 HTTP 友好的纯函数入口，给 GUI 客户端（SwiftUI / 未来 Tauri）调用。

- **`services/*.py`**（6 个）：从 cmd_*.py 提取出来的纯异步函数，不带 Rich/Typer/Prompt。
  公共接口示例：`services.clip.clip_text()`、`services.read.read_url(on_progress=...)`、
  `services.daily.build_briefing()`、`services.ask.ask_question()`、
  `services.notes.delete_note()`、`services.visualize.build_concept_map()`。
- **`server/app.py`**：`create_app(token, port) -> FastAPI`，注册 7 个路由 + healthz + version。
  禁用 Swagger / OpenAPI（减少暴露面），不挂 CORS（依赖浏览器 SOP 隔离）。
- **`server/security.py`**：四层防御 Bearer token + Host 严格匹配 + Origin 白名单
  （`null` / `tauri://localhost`）+ 变更方法强制 `Content-Type: application/json`。
  WebSocket 在 `validate_ws_handshake()` 中复用同一组检查（Starlette HTTP 中间件不拦 WS）。
- **`server/runtime.py`**：启动时随机分配端口 + 随机 token，写入
  `~/.neocortex/server.{pid,port,token}`（token 文件 0600，从首次 syscall 起就是 0600）。
  GUI 客户端读这三个文件做服务发现。
- **关键约束**：CLI 不依赖 services（`cmd_clip.py` / `cmd_read.py` 直接调引擎），
  只有 server 路由强制走 services；将来 CLI 收敛到 services 是单独的迁移工作。

**Routes 速查**（全部 `prefix="/api"`，除 `/healthz`）：

| Method | Path | 用途 |
|---|---|---|
| GET | `/healthz` | 公开活性探针（不需要 token，Host 仍校验） |
| GET | `/api/version` | 最小鉴权端点（双重身份：smoke test） |
| POST | `/api/clip` | URL/文本捕获，返回 `ClipResult` |
| POST | `/api/read` | 深度阅读（同步阻塞 30s–3min），返回 `ReadResult` |
| WS | `/api/read/ws` | 同 `/api/read` 但实时推送 fetch/outline/chunk 进度 |
| POST | `/api/notes/delete` | 删除笔记（POST 体，不是 DELETE 方法） |
| GET | `/api/search` | FTS5 + 向量混合检索 |
| POST | `/api/ask` | 单次问答，触发 query 反写为 insight |
| GET | `/api/daily` | 今日浮现 briefing |
| POST | `/api/daily/surface` | 标记 clip 已浮现，推进调度 |
| GET | `/api/map` | 返回 Mermaid 概念图源码 |

**注意**：CLI 路径下 clip/read **不去重**，去重只在 services 层（`services/clip.py:75`、
`services/read.py:123` 调 `dedup.find_existing`）。commit 33a3884 描述与代码现状有出入。

## 实验性功能开关

`profile config --enable-experimental <feature>` / `--disable-experimental <feature>`
把功能名追加到 `cfg.experimental: list[str]`。
其他模块用 `config.is_experimental(feature: str) -> bool` 查询是否启用。
当前未提交（cli.py / config.py / i18n.py / cmd_daily.py 已加，待合入）。

## 核心机制

### 技能评估（Socratic Probe）
Code scan 只是冷启动（confidence: low），真实技能水平通过日常使用渐进校准：
- `recommend`/`read` 时：LLM 基于用户自己的代码问 1-2 个问题验证该领域水平
- `ask`/`chat` 时：被动分析问题质量（Bloom 层级），更新 confidence
- `read` 后：难度反馈（一键），调整校准
- 长期不练的技能：confidence 衰减
- 每个技能 = level + confidence（0-1）+ last_verified + verification_method
- `prober.py` 负责生成和评估验证问题

#### 四种探测题型（对齐 Bloom 认知层级）
根据当前 confidence 自动选择题型：
- **understanding**（<0.3 confidence）：边界情况、失败模式、设计决策——验证基础理解
- **prediction**（0.3-0.5）：给出代码/场景，预测行为——验证心智模型可执行性
- **error_detection**（0.5-0.7）：给出含错误的 AI 解释，识别问题——验证监督能力
- **design_tradeoff**（>0.7）：两种方案比较，评估权衡——验证专家判断力

#### 元认知校准
每次 Probe 前可选自评（1-4），结束后显示预测 vs 实际的偏差。
记录在 `GapProgress.calibration_history` 中，帮助用户识别"能力幻觉"盲区。

### 闭环学习
推荐 → 阅读 → 自动匹配推荐 → 更新 gap 状态 → 下次推荐更精准。
- 数据流：`recommend` 生成有序学习路径 → `read` 自动匹配（三级：URL/域名关键词/用户确认）→ gap 状态迁移（见下方）→ 下次 `recommend` 跳过已完成
- 存储：`~/.neocortex/recommendations.json` + `~/.neocortex/gap_progress.json`

#### Gap 状态流转（读了不算会，必须通过验证）
```
gap → (首次阅读) → learning → (reads≥2 + Probe≥solid) → verified → (7天后延迟复测) → known
```
- `gap → learning`：首次相关阅读自动迁移
- `learning → verified`：需要 reads ≥ 2 且通过 Socratic Probe（理解 ≥ solid）
- `verified → known`：距 verified_at ≥ 7 天后再次通过 Probe（延迟复测，防止短期记忆）
- 阅读单独**不再**自动升级到 known，确保"读过 ≠ 学会"

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

### 视觉卡片（`neocortex kb card`）
将笔记转为可分享的 PNG 卡片（`reader/card.py`）。HTML 模板 + Playwright 截图。
深色/浅色主题，自动提取关键章节。Playwright 未安装时降级为 HTML 卡片。

### 概念深度解剖（`neocortex read --deep`）
参考 ljg-learn 的八维框架，从历史、辩证、现象、语言、形式、存在、美感、元反思
八个角度切开概念，最终压缩为一句顿悟 + ASCII 结构图。适合理论性内容。

### 知识管理（参考 Readwise/Obsidian）
笔记存储三层分离：
- **应用数据**（`~/.neocortex/`）：config、profile、数据库、缓存。用户不需要碰。
- **用户笔记**（`~/Documents/Neocortex/`，可配置）：纯 Markdown 文件，Finder 直接可见。
  通过 `neocortex profile config --notes-dir <path>` 可指向 Obsidian vault 或任意目录。
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

### 播客/音频摄入
`neocortex read` 支持音频文件直接转录并生成笔记：
```bash
neocortex read podcast.mp3              # 自动转录 + 笔记生成
neocortex read interview.m4a --focus "关键话题"
```

支持格式：mp3, mp4, m4a, wav, ogg, flac, webm

转录后端（按优先级）：
1. OpenAI Whisper API（需要 openai SDK + API key，~$0.006/min）
2. 本地 whisper CLI（`pip install openai-whisper`，免费但较慢）

长音频（>25MB）自动分段处理（需要 ffmpeg）。

**替代工作流**：如果不想安装转录工具，可以用 Podwise 等第三方服务将播客转为 Markdown，
再 `neocortex read transcript.md` 正常处理。

### 知识库活动日志（log.md）
所有操作自动追加到笔记目录下的 `log.md`，记录学习轨迹：
```
## [2026-04-05] read | Attention Is All You Need
## [2026-04-05] ask | Transformer 和 RNN 的区别 → saved as insight
## [2026-04-06] lint | score: 85 (+5)
```

### Query 反写
`ask`/`chat` 的回答经 LLM 自动评估，包含新知识综合的回答自动保存为 insight 并编译进概念图。
无需手动 `--save`，知识在每次对话中复利增长。

### 知识库全局综述（overview.md）
`kb compile --full` 完成后自动生成 `overview.md`，包含：
- 知识地图叙述
- 跨领域连接
- 信念演变
- 盲区提示
- 建议方向

### 忠实度验证（`neocortex kb verify`）
借鉴 Karpathy LLM Knowledge Base 的 audit 思路和 jumperz Swarm Agent 的 Hermes 独立审查员模式，
验证 compile 产出的概念条目是否忠于源笔记，防止 LLM 幻觉在知识库中累积。

核心机制（FACTScore 方法）：
1. **原子事实分解**：LLM 将概念条目拆解为 3-8 条可验证的原子事实
2. **源笔记溯源**：关键词匹配（中文 bigram / 英文分词）在源笔记中定位证据，零 LLM 成本
3. **独立审查判定**：独立 LLM 调用（不看生成过程）判定每条事实为 SUPPORTED / UNSUPPORTED / UNVERIFIABLE
4. **Overview 交叉验证**（deep 模式）：验证 overview.md 中的跨概念声明
5. **Claims 交叉验证**（deep 模式）：对比 claims.json 与概念条目，检测声明漂移
6. **自一致性检查**（deep 模式）：SelfCheckGPT 思路，对低忠实度概念多次采样检查断言一致性

三级深度：
- `--depth shallow`：零 LLM 成本，纯关键词匹配，秒出结果
- `--depth standard`（默认）：每概念 2 次 LLM 调用，完整验证管道
- `--depth deep`：标准验证 + overview 交叉验证 + claims 漂移检测 + 自一致性检查

评分公式：`fidelity_score = 100 × (supported + 0.5 × unverifiable) / total`

功能：
- `--fix`：低忠实度概念自动降低 confidence（<0.5 乘 0.8，<0.8 乘 0.9）
- `--trend`：ASCII sparkline 展示历史 fidelity score 变化
- `--full`：忽略缓存，强制验证所有概念

集成点：
- `kb compile --verify`：编译后自动验证
- `kb lint` 自动读取最近的 verify 报告，低于 70 分报 info，低于 50 分报 warning
- VerifyCache：基于 SHA256 跳过未变化的概念，`--full` 强制跳过
- 报告存储：`_reports/verify-{date}.md`，保留最近 12 份
- 活动日志：自动追加到 `log.md`

## 外部工具依赖（可选）
- `wechat-article-to-markdown` — 微信公众号文章抓取，`neocortex read` 自动检测微信 URL 并调用
  安装：`uv tool install wechat-article-to-markdown`
- `mmdc`（mermaid-cli）— Mermaid 图表渲染为 SVG 图片
  安装：`npm install -g @mermaid-js/mermaid-cli`
- `openai` SDK — 音频转录（Whisper API）
  安装：`pip install openai`
- `openai-whisper` — 本地音频转录
  安装：`pip install openai-whisper`
- `ffmpeg` — 大音频文件分段（>25MB 自动使用）
  安装：`brew install ffmpeg`
