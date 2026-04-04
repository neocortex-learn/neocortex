# Neocortex 命令速查

> 6 个顶层命令 + 4 个子命令组，覆盖从一条推文到一本书的完整学习流程。
> 安装：`pip install neocortex-ai`（开发中用 `pip install -e .`）

---

## 快速开始

```bash
# 首次使用
neocortex profile init                    # 选语言、角色、扫描项目
neocortex profile config --provider ...   # 配置 LLM（见下方）
neocortex read <url>                      # 读第一篇文章
```

### 配置 LLM

```bash
# DeepSeek（推荐，便宜）
neocortex profile config --provider openai-compat --api-key sk-xxx --base-url https://api.deepseek.com --model deepseek-chat

# Claude
neocortex profile config --provider claude --api-key sk-ant-xxx

# OpenAI
neocortex profile config --provider openai --api-key sk-xxx

# 其他兼容接口（硅基流动、Moonshot 等）
neocortex profile config --provider openai-compat --api-key xxx --base-url https://api.xxx.com --model xxx
```

---

## 顶层命令（每天用）

### `read` — 阅读生成笔记

```bash
neocortex read https://example.com/article        # 读网页
neocortex read ~/Downloads/paper.pdf               # 读 PDF
neocortex read --scan https://...                  # 快速筛选（一句话摘要 + P0/P1/P2）
neocortex read --deep https://...                  # 深度模式（八维概念解剖）
neocortex read --focus "性能优化" https://...       # 带焦点
neocortex read --audio https://...                 # 生成音频版
```

输出：个性化笔记 + 闪卡（三层）+ 练习 + 概念编译。

---

### `clip` — 碎片捕获（~5 秒）

```bash
neocortex clip https://x.com/karpathy/status/123   # 推文
neocortex clip "微服务的运维成本可能比开发成本高"     # 想法
neocortex clip https://martinfowler.com/...         # 链接
neocortex clip --paste                              # 从剪贴板（macOS）
```

1 次 LLM 调用：归纳 + 关联概念 + 个人相关性 + 自动分类。

---

### `inbox` — 碎片管理

```bash
neocortex inbox                  # 查看待处理碎片
neocortex inbox --process        # 交互式逐条处理（keep/delete/read/skip）
neocortex inbox --auto           # AI 批量标注优先级
neocortex inbox --synthesize     # 碎片聚类 → 综合为正式笔记
```

---

### `daily` — 今日浮现

```bash
neocortex daily     # 浮现旧碎片 + 到期闪卡 + 聚类提示
```

好奇心驱动——看看今天系统发现了什么。

---

### `review` — 间隔复习

```bash
neocortex review              # 默认最多 20 张
neocortex review --count 10   # 只复习 10 张
```

SM-2 算法调度，每张卡标注层次（事实/概念/程序）。

---

### `ask` — 问答

```bash
neocortex ask "Event Sourcing 和 CQRS 的区别？"    # 单次提问
neocortex ask --save "微服务拆分粒度怎么把握？"      # 保存到知识库
neocortex ask --chat                                # 多轮对话
```

带技能画像 + 知识库上下文。

---

## `kb` — 知识库管理

```bash
neocortex kb compile [--full]                      # 概念编译（通常自动，不需要手动跑）
neocortex kb lint [--fix]                          # 健康检查（0-100 分）
neocortex kb map [--domain X] [--around Y]         # Mermaid 概念图
neocortex kb notes [--search X] [--open]           # 笔记列表/搜索
neocortex kb card [note.md] [--theme light]        # 生成 PNG 视觉卡片
```

---

## `discover` — 内容发现

```bash
neocortex discover explore <rss-url>               # 扫描作者全部文章，按 gap 排序
neocortex discover research "某个主题"              # DuckDuckGo 搜索 + LLM 排序
neocortex discover feed --add <rss-url>            # 添加 RSS 订阅
neocortex discover feed --list                     # 查看订阅
neocortex discover feed                            # 拉取新文章 + gap 筛选
```

---

## `learn` — 学习路径

```bash
neocortex learn recommend [--count 10]             # 推荐下一步学什么
neocortex learn recommend --plan                   # 生成详细学习计划
neocortex learn digest [--days 30]                 # 学习周报/月报
neocortex learn opportunities                      # 匹配开源/岗位机会
```

---

## `profile` — 画像管理

```bash
neocortex profile                                  # 查看技能画像
neocortex profile --json                           # JSON 导出
neocortex profile init                             # 首次初始化
neocortex profile config [--provider X --api-key Y] # 配置管理
neocortex profile scan ~/my-project                # 扫描项目更新画像
neocortex profile scan --github username            # 扫描 GitHub
neocortex profile import chatgpt export.json       # 导入聊天记录
```

---

## 推荐使用流程

### 每天（5 分钟）

```bash
neocortex daily                          # 看浮现
neocortex review                         # 复习闪卡
```

### 随时

```bash
neocortex clip "..."                     # 随手存
neocortex clip https://...
```

### 有空时

```bash
neocortex inbox                          # 看碎片
neocortex read <url>                     # 深入读
neocortex discover explore <rss>         # 扫描好作者
neocortex discover research "主题"        # 搜索学习
```

### 周末

```bash
neocortex learn digest                   # 本周总结
neocortex kb lint                        # 健康检查
neocortex kb map                         # 概念图谱
neocortex inbox --synthesize             # 碎片综合
```

### 月度

```bash
neocortex learn digest --days 30         # 月度反思
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
├── concepts/                      # 概念条目
├── insights/                      # 问答沉淀
├── clips/                         # 碎片存储
├── maps/                          # 概念图
├── web-backend/                   # 按主题分类的笔记
├── general/
├── .flashcards/                   # 闪卡数据
└── diagrams/                      # Mermaid SVG
```
