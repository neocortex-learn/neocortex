# Neocortex

[English](README.md) | 中文

> AI 驱动的开发者技能分析与个性化学习助手。
>
> 扫描你的项目，构建技能画像，只学你**需要的**。

Neocortex 通过分析你的实际代码（而不是简历）来了解你会什么、有多深、缺什么。当你丢给它一本书、一篇文章或一份文档时，它会生成个性化的学习笔记——跳过你已经懂的，专注你需要补的。

## 为什么做 Neocortex？

每个开发者的学习需求都不一样。一个做过 3 套实时消息系统的高级工程师不需要听"WebSocket 是什么"——他需要的是"你的 Redis Pub/Sub 架构有双写一致性问题，该怎么修"。

现有工具都做不到这一点：

| 工具 | 懂内容 | 懂你 | 个性化 |
|------|:------:|:----:|:------:|
| NotebookLM | 是 | 否 | 否 |
| ChatGPT / Claude | 是 | 一点点 | 否 |
| Coursera / Udemy | 是 | 否 | 否 |
| **Neocortex** | **是** | **是** | **是** |

核心原理：Neocortex 通过分析你的代码构建真实的技能画像，然后在你的[最近发展区](https://zh.wikipedia.org/wiki/%E8%BF%91%E4%BE%A7%E5%8F%91%E5%B1%95%E5%8C%BA%E9%97%B4)内精准教学。

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

### 扫描和学习

```bash
neocortex profile scan ~/projects/my-app              # 构建技能画像
neocortex profile                                     # 查看画像
neocortex read https://ddia.vonng.com/ch8/            # 个性化笔记
neocortex learn recommend                             # 学习路径
neocortex ask "Raft 和 Paxos 该怎么选？"                # 带画像上下文的问答
```

## 命令

### 顶层命令

| 命令 | 说明 |
|------|------|
| `neocortex read <source>` | 阅读 URL/PDF/EPUB，生成个性化笔记 |
| `neocortex ask <question>` | 提问（或 `--chat` 进入对话模式），带画像上下文 |
| `neocortex review` | 间隔复习闪卡（SM-2 算法） |
| `neocortex clip <source>` | 快速捕获碎片（推文、想法、书签）到知识库 |
| `neocortex inbox` | 管理碎片（`--process`、`--auto`、`--synthesize`） |
| `neocortex daily` | 每日简报——浮现旧碎片 + 到期复习 |

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

### 1. 智能项目扫描

Neocortex 不会把你的整个代码库喂给 LLM，而是高效提取关键信号：

```
项目目录
    ↓
1. 配置检测     → package.json, requirements.txt, go.mod, build.gradle
2. 代码统计     → 按语言统计行数、文件数、项目结构
3. 关键文件采样 → 模型、处理器、路由、Schema、测试
4. 架构信号     → 设计模式、第三方集成、基础设施
    ↓
结构化摘要（每个项目约 2K tokens）
    ↓
LLM 分析 → 技能画像（JSON）
```

成本很低——扫描一个项目通常不到 $0.05。

### 2. 个性化阅读（两阶段管道）

**阶段 1 — 大纲分析**（快速，低成本）：
1. 获取并解析内容（URL、PDF、EPUB、微信公众号文章）
2. 对照画像标记每个章节：`✓ 跳过` / `△ 简要` / `★ 重点`
3. 展示个性化大纲，等你确认

**阶段 2 — 笔记生成**：
4. 在你的水平上生成笔记，自然嵌入 Mermaid 图表
5. 用你做过的项目做类比
6. 自动提取闪卡用于间隔复习
7. 触发增量概念编译

三种阅读深度：`--scan`（快速筛选）、默认（标准阅读）、`--deep`（八维深度解剖）。

### 3. 知识编译

笔记是原材料，概念才是知识资产。每次阅读后：

- **概念提取** — LLM 从笔记中识别概念
- **Wiki 生成** — 每个概念生成专门条目，包含来源、关联、开放问题
- **Wikilink 插入** — 笔记中自动嵌入 `[[概念]]` 链接（兼容 Obsidian）
- **INDEX.md** — LLM 维护的知识地图，展示覆盖率和掌握度

### 4. 知识信心衰减

基于 Hidalgo 的研究（年衰变率约 50%），概念的信心值随时间自动衰减。系统通过复习、每日简报和健康检查浮现正在衰减的概念。

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

- [x] CLI 框架（6 个顶层命令 + 4 个子命令组）
- [x] 多 LLM 提供商支持（Claude、OpenAI、Gemini、OpenAI 兼容）
- [x] 项目扫描（本地 + GitHub，支持 12 种语言）
- [x] 三级个性化阅读（快速筛选 / 标准 / 深度）
- [x] 概念编译 + 知识索引
- [x] 间隔复习闪卡（SM-2 算法）
- [x] 知识库健康检查（8 项 lint 规则 + 自动修复）
- [x] 知识库忠实度验证（FACTScore 原子事实分解 + Hermes 独立审查）
- [x] 内容发现（explore、research、RSS 订阅）
- [x] 碎片捕获（clip、inbox、daily 浮现）
- [x] 知识信心衰减模型
- [x] 阅读后微反思
- [x] 技能校准（Socratic Probe）
- [x] 聊天记录导入（ChatGPT / Claude）
- [x] 学习路径推荐 + 机会匹配
- [x] 概念图可视化 + 学习周报
- [x] 语音输出 / TTS
- [x] 国际化（英文、中文）
- [ ] 插件系统——社区贡献的技能提取器
- [ ] Web/App 版本（学生版）

## 贡献

欢迎贡献！请提交 Issue 或 Pull Request。

## 许可证

MIT License. 详见 [LICENSE](LICENSE)。
