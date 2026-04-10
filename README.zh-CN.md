# Neocortex

[English](README.md) | 中文

> AI 驱动的个人知识库工具。
>
> 随手存，自动整理，需要时搜到。

Neocortex 像管理代码仓库一样管理你的知识——有输入（clip），有编译（compile），有索引（search），有健康检查（lint/verify）。零摩擦存入推文、文章、想法，LLM 自动编译成概念图谱，需要时一搜就到。

灵感来自 Karpathy 的 ["LLM Knowledge Bases"](https://karpathy.ai/) 工作流：原始素材 → 编译产物 → 可检索的输出。

## 为什么做 Neocortex？

你的收藏夹、稍后阅读、推文书签——都是坟场。存了就再也找不到了。

Neocortex 用三层架构解决这个问题：

```
clip（随手存）→  compile（LLM 整理）→  search/ask（搜到）
```

它还理解**你**——扫描你的项目构建技能画像，生成跳过你已会内容的个性化笔记。

| 工具 | 轻松存 | 自动整理 | 需要时找到 | 懂你 |
|------|:------:|:--------:|:----------:|:----:|
| Pocket / Instapaper | 是 | 否 | 勉强 | 否 |
| Obsidian | 手动 | 手动 | 插件 | 否 |
| NotebookLM | 否 | 是 | 是 | 否 |
| **Neocortex** | **是** | **是** | **是** | **是** |

## 快速开始

### 安装

```bash
uv pip install neocortex-ai

# 或者直接运行，无需安装
uvx neocortex-ai
```

### 初始化和配置

```bash
neocortex profile init                                # 首次设置（30 秒）
neocortex profile config --provider claude --api-key sk-xxx  # 配置 LLM
```

### 存和搜（轻路径）

```bash
neocortex clip https://x.com/karpathy/status/123      # 存一条推文——零 LLM 成本
neocortex clip "Redis Pub/Sub 有顺序保证"               # 存一个想法
neocortex kb compile                                   # 编译进概念图谱
neocortex search "redis pub/sub"                       # 搜到
neocortex ask "之前存过的关于消息排序的内容？"              # AI 从知识库回答
```

### 扫描和深度学习（重路径）

```bash
neocortex profile scan ~/projects/my-app              # 构建技能画像
neocortex read https://ddia.vonng.com/ch8/            # 个性化深度笔记
neocortex learn recommend                             # 学习路径 + 探测验证
```

## 命令

### 顶层命令

| 命令 | 说明 |
|------|------|
| `neocortex clip <source>` | 存任何东西——URL、推文、想法、书签（默认零 LLM，`--process` 启用 AI 标签） |
| `neocortex search <query>` | 搜索所有笔记、碎片、概念、洞察 |
| `neocortex ask <question>` | 提问——AI 从你的知识库搜索回答（或 `--chat` 对话模式） |
| `neocortex read <source>` | 深度阅读——URL/PDF/EPUB 个性化笔记 + Mermaid 图表 |
| `neocortex review` | 间隔复习闪卡（SM-2 算法） |
| `neocortex inbox` | 管理碎片（`--process`、`--auto`、`--synthesize`） |
| `neocortex daily` | 每日简报——浮现碎片 + 到期复习 + 编译提醒 |

### `profile` — 画像管理

| 命令 | 说明 |
|------|------|
| `neocortex profile` | 查看技能画像（`--export`、`--json`、`--edit`） |
| `neocortex profile init` | 首次设置：角色、经验、目标、语言 |
| `neocortex profile config` | 配置 LLM 提供商、API Key 和偏好 |
| `neocortex profile scan` | 扫描本地项目或 GitHub 仓库（`--github`、`--update`） |
| `neocortex profile import` | 导入 ChatGPT/Claude 聊天记录以丰富画像 |

### `kb` — 知识库

| 命令 | 说明 |
|------|------|
| `neocortex kb notes` | 列出或搜索笔记（`--search`） |
| `neocortex kb card` | 将笔记生成为 PNG 视觉卡片 |
| `neocortex kb compile` | 将笔记编译为互联的概念 wiki（`--verify` 编译后验证） |
| `neocortex kb verify` | 验证概念条目是否忠于源笔记（`--fix`/`--trend`/`--depth deep`） |
| `neocortex kb lint` | 知识库健康检查（8 项检查 + `--fix` 自动修复） |
| `neocortex kb map` | 生成 Mermaid 概念图（`--domain`、`--around`） |

### `learn` — 学习路径与进度

| 命令 | 说明 |
|------|------|
| `neocortex learn recommend` | 个性化学习推荐（`--plan`、`--count`） |
| `neocortex learn opportunities` | 发现匹配技能的开源和工作机会 |
| `neocortex learn digest` | 生成指定时段的学习周报（`--days`） |

### `discover` — 内容发现

| 命令 | 说明 |
|------|------|
| `neocortex discover explore <url>` | 探索某作者的文章列表，按相关性排序 |
| `neocortex discover research <topic>` | 搜索与你的知识盲区相关的文章 |
| `neocortex discover feed` | 管理 RSS 订阅，发现相关文章 |

详细用法参见 [docs/COMMANDS.md](docs/COMMANDS.md)。

## 工作原理

### 1. 三层知识架构

像代码仓库一样，有源码、构建产物、输出：

```
~/Documents/Neocortex/          （你的知识库）
├── clips/                      ← 原始输入（推文、书签、想法）
├── general/                    ← 深度笔记（read 生成）
├── concepts/                   ← 编译产物（自动生成的概念 wiki）
├── insights/                   ← 保存的问答（ask 生成）
├── INDEX.md                    ← 自动维护的知识地图
└── .search.db                  ← FTS5 + 向量混合搜索索引
```

### 2. 轻路径：Clip → Compile → Search

**Clip**（零摩擦）：存任何东西——URL、推文、想法。默认不调 LLM，零成本。

**Compile**（`kb compile`）：LLM 批量处理 clips 和笔记——提取概念、生成 wiki 条目、重建搜索索引。攒够几条就跑一次。

**Search/Ask**：`search` 做全文 + 语义混合搜索。`ask` 自动搜索知识库，把相关内容注入 AI 的回答上下文。

### 3. 重路径：Read → Probe → Review

用于你想深入理解的内容：

**Read** 生成个性化笔记——对照技能画像标记每个章节（`跳过` / `简要` / `重点`），嵌入 Mermaid 图表，用你的项目做类比。

**Probe** 验证真实理解，四种题型（边界情况、错误检测、设计权衡、行为预测）。盲区状态只有通过验证才升级——读了不算会。

**Review** SM-2 间隔复习，交错排列闪卡。

### 4. 智能项目扫描

高效提取代码库关键信号（每项目约 2K tokens，< $0.05）：

```
配置检测 → 代码统计 → 关键文件采样 → 架构信号
    ↓
LLM 分析 → 技能画像（每个技能 = level + confidence）
```

### 5. 知识信心衰减

基于 Hidalgo 的研究（年衰减率约 50%），概念信心值随时间自动衰减。系统通过复习、每日简报和健康检查浮现正在衰减的概念。

## 支持的 LLM 提供商

自带 API Key，Key 只存在本地 `~/.neocortex/config.json`。

| 提供商 | 模型 | 配置 |
|--------|------|------|
| **Anthropic** | Claude Opus, Sonnet, Haiku | `--provider claude` |
| **OpenAI** | GPT-4o, GPT-4.1, o3 | `--provider openai` |
| **Google** | Gemini 2.5 Pro/Flash | `--provider gemini` |
| **OpenAI 兼容** | Kimi、MiniMax、DeepSeek、通义、GLM 等 | `--provider openai-compat --base-url <url>` |

## 数据与隐私

- **所有数据留在本地。** 画像、笔记、配置都存在 `~/.neocortex/`
- **用户笔记是纯 Markdown 文件**，存放在 `~/Documents/Neocortex/`（可通过 `neocortex profile config --notes-dir` 配置）
- **API Key 本地存储。** 只发送给你选择的 LLM 提供商
- **代码不会上传。** 只有结构化摘要会发给 LLM 分析
- **无遥测。** 不追踪、不分析、不回传

## 路线图

**知识库（轻路径）**
- [x] 零 LLM 碎片捕获（推文、URL、想法）
- [x] 混合搜索（FTS5 + 向量）覆盖所有内容类型
- [x] 独立 `search` 命令
- [x] `ask`/`chat` 动态知识库上下文
- [x] 概念编译 + 知识索引
- [x] 知识库健康检查（8 项 lint 规则 + 自动修复）
- [x] 忠实度验证（FACTScore + Hermes 独立审查）
- [x] 每日简报：碎片浮现 + 编译提醒
- [x] 知识信心衰减（Hidalgo 模型）

**深度学习（可选）**
- [x] 三级个性化阅读（快速筛选 / 标准 / 深度）
- [x] Socratic Probe——4 种题型对齐 Bloom 认知层级
- [x] 元认知校准（预测 vs 实际）
- [x] 盲区验证门槛（读了不算会）
- [x] 间隔复习闪卡（SM-2 算法）
- [x] 学习路径推荐 + 机会匹配

**基础设施**
- [x] CLI 框架（7 个顶层命令 + 4 个子命令组）
- [x] 多 LLM 提供商支持（Claude、OpenAI、Gemini、OpenAI 兼容）
- [x] 项目扫描（本地 + GitHub，支持 12 种语言）
- [x] 内容发现（explore、research、RSS 订阅）
- [x] 聊天记录导入（ChatGPT / Claude）
- [x] 概念图可视化 + 学习周报
- [x] 语音输出 / TTS
- [x] 国际化（英文、中文）
- [ ] 插件系统——社区贡献的技能提取器
- [ ] Web/App 版本

## 贡献

欢迎贡献！请提交 Issue 或 Pull Request。

## 许可证

MIT License. 详见 [LICENSE](LICENSE)。
