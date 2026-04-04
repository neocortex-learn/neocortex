# Neocortex 命令速查

> 27 个命令，覆盖从一条推文到一本书的完整学习流程。
> 安装：`pip install neocortex-ai`（开发中用 `pip install -e .`）

---

## 快速开始

```bash
# 首次使用三步走
neocortex init                    # 选语言、角色、扫描项目
neocortex config --provider ...   # 配置 LLM（见下方）
neocortex read <url>              # 读第一篇文章
```

### 配置 LLM

```bash
# DeepSeek（推荐，便宜）
neocortex config --provider openai-compat --api-key sk-xxx --base-url https://api.deepseek.com --model deepseek-chat

# Claude
neocortex config --provider claude --api-key sk-ant-xxx

# OpenAI
neocortex config --provider openai --api-key sk-xxx

# 其他兼容接口（硅基流动、Moonshot 等）
neocortex config --provider openai-compat --api-key xxx --base-url https://api.xxx.com --model xxx
```

---

## 一、每日使用（高频）

### `neocortex daily` — 今日浮现

每天打开看一下，系统会浮现旧碎片（带知识库上下文更新）+ 到期闪卡提醒 + 碎片聚类提示。

```bash
neocortex daily
```

好奇心驱动，不是自律驱动——看看今天有什么新发现。

---

### `neocortex clip` — 碎片捕获（~5 秒）

看到任何值得记的内容，随手 clip。1 次 LLM 调用做轻度处理：归纳、关联概念、个人相关性、分类。

```bash
# 捕获一条推文
neocortex clip https://x.com/karpathy/status/123456

# 捕获一个想法
neocortex clip "微服务的运维成本可能比开发成本高"

# 捕获一个链接
neocortex clip https://martinfowler.com/articles/event-sourcing.html

# 从剪贴板捕获（macOS）
neocortex clip --paste
```

---

### `neocortex review` — 间隔复习

SM-2 算法调度的闪卡复习。显示问题→按回车看答案→5 级评分。每张卡标注知识层次（事实/概念/程序）。

```bash
neocortex review              # 默认最多 20 张
neocortex review --count 10   # 只复习 10 张
```

---

## 二、阅读与学习

### `neocortex read` — 阅读生成笔记

核心命令。读一篇文章/PDF/EPUB，生成个性化笔记 + 闪卡 + 练习 + 概念编译。

```bash
# 读一篇网页文章
neocortex read https://example.com/article

# 读本地文件
neocortex read ~/Downloads/paper.pdf
neocortex read ~/Books/chapter.epub

# 带焦点
neocortex read https://... --focus "性能优化"

# 带问题
neocortex read https://... --question "这个方案和 Redis 比有什么优势？"

# 快速筛选模式（不生成笔记，只输出一句话摘要 + P0/P1/P2 优先级）
neocortex read --scan https://...

# 深度模式（八维概念解剖）
neocortex read --deep https://...

# 生成音频版
neocortex read --audio https://...
```

**输出**：
- 个性化笔记（.md，Mermaid 图表，按你的水平调整深度）
- 闪卡（.flashcards.json，三层：事实/概念/程序）
- 练习（.exercises.md，应用到你自己项目的实践题）
- 概念编译（自动提取概念、生成条目、插入 wikilinks）

---

### `neocortex research` — 主动搜索

给一个主题，系统自动搜索网页、排序筛选、让你选择后直接进入 read 流程。

```bash
neocortex research "Event Sourcing 快照策略"
neocortex research "微服务 vs 单体 架构决策" --count 8
```

不需要 API key，用 DuckDuckGo 搜索。

---

### `neocortex explore` — 扫描作者/站点

发现一个好作者？一键扫描他的所有文章，按你的技能盲区排优先级。AI 替你选，不替你读。

```bash
# 扫描一个博客的归档页
neocortex explore https://yage.ai/archives.html

# 扫描任何有文章列表的页面
neocortex explore https://someone.com/blog
```

**流程**：抓取文章列表 → LLM 批量评估优先级（P0/P1/P2）→ 按优先级分组展示 → 你选择要读哪些 → 其余存为 clip。

---

### `neocortex feed` — RSS 订阅

订阅 RSS 源，自动拉取新文章，LLM 按你的技能盲区筛选相关内容。

```bash
# 添加订阅
neocortex feed --add https://martinfowler.com/feed.atom

# 查看订阅列表
neocortex feed --list

# 拉取新文章并筛选
neocortex feed

# 删除订阅
neocortex feed --remove https://...
```

---

### `neocortex recommend` — 学习路径推荐

基于你的技能画像推荐下一步该学什么。有序的学习路径，带依赖关系（前置步骤完成后才解锁下一步）。

```bash
neocortex recommend              # 推荐 5 步
neocortex recommend --count 10   # 推荐 10 步
```

---

## 三、知识管理

### `neocortex inbox` — 碎片管理

管理 clip 捕获的碎片。

```bash
# 查看待处理碎片
neocortex inbox

# 交互式逐条处理（keep/delete/read/skip）
neocortex inbox --process

# AI 批量标注优先级
neocortex inbox --auto

# 碎片聚类 → 综合为正式笔记（同概念 3+ 条碎片时）
neocortex inbox --synthesize
```

---

### `neocortex compile` — 概念编译

把散落的笔记编译成互联的概念 wiki。自动提取概念、生成条目、插入 wikilinks、维护 INDEX.md。

```bash
neocortex compile          # 增量编译（只处理变化的笔记）
neocortex compile --full   # 全量重编译
```

通常不需要手动跑——`read` 命令会自动增量编译。

---

### `neocortex lint` — 知识库健康检查

6 项检查：孤岛笔记、断裂链接、陈旧概念、覆盖盲区、重复概念、衰减预警。打分 0-100。

```bash
neocortex lint          # 只检查
neocortex lint --fix    # 自动修复可修的问题
```

---

### `neocortex notes` — 笔记列表

```bash
neocortex notes                     # 列出所有笔记
neocortex notes --search "事件溯源"  # 搜索
neocortex notes --search "React" --open  # 搜索并打开
```

---

### `neocortex index` — 重建搜索索引

```bash
neocortex index   # 重建 FTS5 全文索引 + 向量嵌入
```

---

## 四、问答与探索

### `neocortex ask` — 单次提问

带你的技能画像 + 知识库上下文的 AI 问答。

```bash
neocortex ask "Event Sourcing 和 CQRS 的区别是什么？"
neocortex ask --save "微服务的拆分粒度怎么把握？"   # 回答保存到知识库
```

---

### `neocortex chat` — 多轮对话

交互式聊天，退出时可选保存对话为 insight。

```bash
neocortex chat
# 输入问题，多轮对话
# 输入 exit 或连按两次回车退出
```

---

## 五、可视化与复盘

### `neocortex map` — 概念图

生成 Mermaid 格式的概念关系图，Obsidian 可直接渲染。

```bash
neocortex map                              # 全局概念图
neocortex map --domain "web-backend"       # 按领域筛选
neocortex map --around "Event Sourcing"    # 某概念的关联网络
```

---

### `neocortex digest` — 学习周报/月报

```bash
neocortex digest              # 最近 7 天
neocortex digest --days 30    # 最近 30 天（自动触发月度反思）
```

输出：笔记数、新增概念、闪卡复习、知识复杂性分数、衰减概念数、收敛报告。

---

### `neocortex growth` — 成长追踪

```bash
neocortex growth   # 查看推荐完成率、gap 进度
```

---

### `neocortex card` — 视觉卡片

把笔记转为可分享的 PNG 卡片。

```bash
neocortex card                     # 最新的笔记
neocortex card path/to/note.md     # 指定笔记
neocortex card --theme light       # 浅色主题
```

---

## 六、画像管理

### `neocortex init` — 初始化

首次使用：选语言、角色、经验、目标、扫描项目。

```bash
neocortex init
```

---

### `neocortex scan` — 扫描项目

扫描本地项目或 GitHub 仓库，更新技能画像。

```bash
neocortex scan ~/Documents/my-project        # 本地项目
neocortex scan --github username              # GitHub 仓库
neocortex scan --github username/repo         # 指定仓库
```

---

### `neocortex profile` — 查看画像

```bash
neocortex profile             # 查看技能画像
neocortex profile --json      # JSON 格式导出
```

---

### `neocortex config` — 配置管理

```bash
neocortex config                              # 查看当前配置
neocortex config --provider claude --api-key sk-ant-xxx
neocortex config --language zh                # 切换语言
neocortex config --github-token ghp_xxx       # 配置 GitHub token
```

---

### `neocortex import` — 导入聊天记录

从 ChatGPT 或 Claude 的导出文件中分析学习轨迹。

```bash
neocortex import chatgpt ~/Downloads/conversations.json
neocortex import claude ~/Downloads/claude-export.json
```

---

## 七、推荐使用流程

### 日常（每天 5 分钟）

```bash
neocortex daily     # 看看今天浮现了什么
neocortex review    # 复习到期的闪卡
```

### 碎片捕获（随时）

```bash
neocortex clip "..."              # 看到什么有意思的随手存
neocortex clip https://...        # 存个链接
```

### 深度学习（有空的时候）

```bash
neocortex inbox                   # 看看积累了哪些碎片
neocortex read <url>              # 挑一篇深入读
neocortex research "某个主题"     # 或者让系统帮你找
neocortex explore <archive-url>   # 发现好作者？扫描他所有文章
```

### 周末复盘

```bash
neocortex digest                  # 本周学了什么
neocortex lint                    # 知识库健康检查
neocortex map                     # 看看概念图谱长什么样
neocortex inbox --synthesize      # 碎片聚类生成综合笔记
```

### 月度回顾

```bash
neocortex digest --days 30        # 月度反思：知识演化、方向偏差、认知更新
```

---

## 文件结构

```
~/.neocortex/                       # 应用数据（不需要碰）
├── config.json                    # LLM 配置
├── profile.json                   # 技能画像
├── recommendations.json           # 推荐记录
├── gap_progress.json              # 盲区进度
├── claims.json                    # 声明数据
├── belief_changes.json            # 信念变更日志
├── compile_cache.json             # 编译缓存
├── feeds.json                     # RSS 订阅
├── feed_history.json              # Feed 去重
└── neocortex.sqlite               # 搜索索引

~/Documents/NeocortexNotes/         # 笔记目录（Obsidian vault）
├── INDEX.md                       # 知识地图（自动维护）
├── concepts/                      # 概念条目（自动生成）
├── insights/                      # 问答沉淀
├── clips/                         # 碎片存储
├── maps/                          # 概念图
├── web-backend/                   # 按主题分类的笔记
├── mobile-development/
├── general/
├── .flashcards/                   # 闪卡数据
└── diagrams/                      # Mermaid SVG
```
