# Wiki 编译模式拓展设计

> 借鉴 Karpathy 的 "LLM Knowledge Bases" 方法论，拓展 Neocortex 的知识管理能力。
> 本文档记录思考来源、对照分析、以及具体的拓展方案。

---

## 1. 思考来源

### 1.1 Karpathy 的 "LLM Knowledge Bases" 推文 (2026-04-03)

**原始推文**: https://x.com/karpathy/status/2039805659525644595
**Idea File**: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

核心洞察：

> "我最近的 token 消耗越来越多地用在**操作知识**上，而不是操作代码。"

他提出了一套用 LLM 增量构建和维护个人 wiki 的方法论：

- **三层架构**：`raw/`（不可变原始素材）→ `wiki/`（LLM 生成维护）→ Schema（LLM 工作手册）
- **四个操作**：Ingest（摄入）、Compile（编译）、Query（查询）、Lint（健康检查）
- **核心类比**："Obsidian 是 IDE，LLM 是程序员，wiki 是代码库"
- **关键设计**：`index.md`（内容索引）+ `log.md`（时间线）；Query 结果反写回 wiki

他还认可了 Farzapedia（@FarzaTV 的个人维基）项目，提出个性化方案的四个原则：
1. **Explicit** — 知识可见、可检视
2. **Yours** — 数据归自己
3. **File over app** — 通用文件格式
4. **BYOAI** — 接入任意 AI

### 1.2 yanhua 的落地实践文章 (2026-04-03)

**推文**: https://x.com/i/status/2039966047378583815 (@yanhua1010)

这篇是 Karpathy 方法论的中文落地实践（24 万浏览，3246 收藏），补充了实操细节：

- **三层目录** + 额外的平台内容目录（给读者看 vs 给自己看分离）
- **三个摄入入口**：Web Clipper（网页）、Podwise（播客）、手动剪藏（推文等）
- **编译批处理**：攒 5-10 篇 raw 后一次编译，而非实时
- **outputs/ 独立层**：`outputs/qa/`（Q&A 存档）+ `outputs/health/`（健康报告）
- **每次对话都变成库存**："你每跟 AI 聊一次，知识库就增加一层"
- **周度健康检查**：一致性、完整性、孤岛检查，报告持久化
- **别上来就搞 RAG**：100 篇以内，索引文件就够了

### 1.3 与 Neocortex 的关系

Karpathy 方法论和 Neocortex 在架构上高度重叠，但各有侧重：

- **Karpathy/yanhua** 是通用知识管理——适合任何人、任何领域
- **Neocortex** 是个性化学习引擎——面向开发者的技能成长

两者互补：Karpathy 的方法告诉 AI "你是谁"（知识积累），Neocortex 告诉 AI "你要去哪里"（学习规划）。

---

## 2. 对照分析

### 2.1 已对齐（不需要动）

| 能力 | Karpathy | Neocortex | 对比 |
|------|----------|-----------|------|
| 概念提取 | wiki 自动生成概念页 | `compiler.py` → `concepts/` | 平齐 |
| Wikilink | 双向链接 | 首次出现自动链接 + 别名 | 平齐 |
| 主索引 | `index.md` 按分类列出 | `INDEX.md` 按领域分组 + 覆盖率 | Neocortex 更丰富 |
| 健康检查 | Lint 3-4 项 | `linter.py` 7 项检查 | Neocortex 更全 |
| 搜索 | qmd (BM25 + 向量) | FTS5 + fastembed 混合搜索 | 平齐 |
| 文件格式 | Markdown + YAML frontmatter | 完全一致 | 平齐 |
| Obsidian 兼容 | 原生 | 原生 | 平齐 |

### 2.2 Neocortex 独有优势（Karpathy 没有的）

| 能力 | 说明 |
|------|------|
| 画像驱动的个性化阅读 | outline 按用户技能标记 skip/brief/deep |
| 信心衰减 | Hidalgo 年衰减 50%，知识不复习就贬值 |
| 矛盾检测 + 信念审计 | claim 冲突分类 + `belief_changes.json` 审计链 |
| 间隔复习 | SM-2 + 自动闪卡 + 关系卡 |
| 学习路径 | step + depends_on 依赖图 |
| 技能校准 | Socratic Probe + 阅读反馈 + Bloom 被动分析 |

### 2.3 Neocortex 缺失的（需要拓展的）

| 缺失 | Karpathy/yanhua 怎么做 | 影响 |
|------|------------------------|------|
| Query 反写 | 问答结果自动存文件 + 编译进知识图 | 知识不能复利增长 |
| 活动时间线 | `log.md` append-only 时间线 | 学习轨迹不可见 |
| 全局综述 | `overview.md` 叙事性综合 | 缺少"森林"视角 |
| Lint 报告持久化 | `outputs/health/` 周报 + 趋势 | 改善不可度量 |
| Ingest 涟漪 | 一次 ingest 触动 10-15 页 | 知识网络连接不够密 |
| Clip → 概念打通 | 所有素材统一 ingest | 碎片是死胡同 |
| 播客摄入 | Podwise 转录 → markdown → 编译 | 缺少高质量信息源 |

---

## 3. 拓展方案

### 3.1 [P0] Query 反写 — 让每次对话都变成库存

**问题**：`ask`/`chat` 产生的洞察消散在聊天记录里，不进入知识图。

**现状**：`ask --save` 能保存到 `insights/`，但默认不触发，保存后不编译。

**方案**：

```
ask/chat 回答生成后
    ↓ LLM 快速评估（轻量 prompt，几十 token）
    │  问题："这个回答是否包含新的知识综合、跨概念连接、或原创分析？"
    │
    ├─ 是 → 自动保存为 insight 文件
    │       → 调用 compile_note() 提取概念、更新知识图
    │       → append_log("ask", question_summary + " → saved")
    │       → 终端提示："💡 洞察已保存并编译"
    │
    └─ 否 → 跳过
            → append_log("ask", question_summary)
```

**改动文件**：
- `asker.py` — 在 `ask()` 和 `ChatSession` 的回答流程后加 LLM 评估 + 自动保存
- `cmd_knowledge.py` — 移除 `--save` 的手动交互提示（改为自动判断）

**设计要点**：
- 评估 prompt 要极简，避免每次问答都多一次完整 LLM 调用
- 可以用 provider 的小模型（如 haiku）做评估，大模型做回答
- 保存的 insight 要有 `type: insight` frontmatter，source 标记为 `ask`/`chat`
- 编译后的概念应标记 `evidence_source: insight`，与笔记来源区分

---

### 3.2 [P0] log.md 活动时间线

**问题**：学习活动散落在 git history 和各种 JSON 文件里，不可浏览。

**方案**：

在 `config.py` 新增 `append_log()` 函数：

```python
def append_log(action: str, detail: str) -> None:
    """Append activity to log.md. Lightweight, never fails."""
    line = f"## [{date.today().isoformat()}] {action} | {detail}\n\n"
    log_path = get_notes_dir() / "log.md"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
```

**调用点**（每个只加一行）：
- `cmd_read.py` — `read` 完成后：`append_log("read", title)`
- `cmd_knowledge.py` — `ask` 完成后：`append_log("ask", question[:80])`
- `cmd_knowledge.py` — insight 保存后：`append_log("insight", title)`
- `cmd_lint.py` — lint 完成后：`append_log("lint", f"score: {score}")`
- `cmd_clip.py` — clip 完成后：`append_log("clip", title)`
- `cmd_compile.py` — compile 完成后：`append_log("compile", f"{n} notes compiled")`
- `reviewer.py` — review 完成后：`append_log("review", f"{n} cards reviewed")`

**输出示例**：
```markdown
## [2026-04-05] read | Attention Is All You Need
## [2026-04-05] ask | Transformer 和 RNN 的本质区别 → saved as insight
## [2026-04-05] compile | 3 notes compiled, 5 concepts updated
## [2026-04-06] lint | score: 85 (+5)
## [2026-04-06] review | 5 cards reviewed, 4 passed
## [2026-04-07] clip | @karpathy on LLM Knowledge Bases
```

**设计要点**：
- 纯追加，不读不改已有内容，零性能开销
- 格式化前缀 `## [date] action |` 便于 grep/解析
- 失败静默（`try/except` 包裹），不影响主流程
- log.md 不参与搜索索引和编译，纯记录用途
- 可被 `overview.md` 和 `daily` 命令读取作为上下文

---

### 3.3 [P1] Lint 报告持久化 + 趋势追踪

**问题**：`kb lint` 结果只输出到终端，无法回看或追踪趋势。

**方案**：

每次 lint 自动保存报告到 `_reports/lint-{date}.md`：

```markdown
---
type: lint-report
date: 2026-04-05
score: 85
grade: A
issues: {error: 0, warning: 2, info: 3}
---

# Lint Report — 2026-04-05

**Score: 85 / 100** (Grade: A)

## Warnings (2)
- [stale] concept "event-sourcing" 的 source_notes 包含已删除笔记
- [decay] concept "cqrs" confidence 已衰减至 0.22

## Info (3)
- [coverage] profile gap "GraphQL" 无对应概念
- ...
```

终端输出增加趋势行：
```
Score: 85 / 100 (A)  ▲ +5 vs 上次 (2026-03-29)
```

**改动文件**：
- `cmd_lint.py` — lint 完成后保存报告文件 + 读取上次报告计算趋势
- `config.py` — `append_log("lint", f"score: {score} ({delta:+d})")`

**设计要点**：
- 报告存 `_reports/` 目录（下划线前缀表示元数据，不是用户笔记）
- 只保留最近 12 份，超出按日期清理
- 趋势计算：读取 `_reports/` 下最近一份报告的 frontmatter score 字段

---

### 3.4 [P1] overview.md 全局综述

**问题**：`INDEX.md` 是机械性目录，缺少"这些知识串起来意味着什么"的全局视角。

**方案**：

在 `compiler.py` 中新增 `generate_overview()` 函数，在 `compile_all()` 末尾调用：

```
LLM 输入：
  - INDEX.md（概念列表 + 覆盖率）
  - profile（技能、gaps、经验）
  - log.md 最近 20 行（学习动态）
  - belief_changes.json 最近条目（信念演变）

LLM 输出 overview.md：
  ## 知识地图
  你的知识库目前覆盖 N 个领域...主要深入在 X 和 Y...

  ## 跨领域连接
  分布式系统的 CAP 理论和你在学的数据库事务有直接关联...

  ## 信念演变
  关于 microservices，你的理解经历了从 A 到 B 的转变...

  ## 盲区提示
  你的笔记大量涉及后端架构但完全没碰前端性能优化...

  ## 建议方向
  基于当前知识结构，最有价值的下一步是...
```

**触发时机**：
- `compile --all` 末尾自动生成
- `daily` 命令可选引用
- 不在每次增量 `compile_note()` 时触发（太频繁，浪费 token）

**改动文件**：
- `compiler.py` — 新增 `generate_overview()`
- `cmd_compile.py` — `compile_all()` 末尾调用

---

### 3.5 [P1] Ingest 涟漪效应

**问题**：`read` 一篇新文章只影响自身 + 相关 concept 页面，已有笔记的交叉引用不会更新。

**现状**：`related_notes` 的语义更新只在 `compile_all()` 时批量执行。

**方案**：

将 `compile_note()` 中的涟漪范围扩大：

```
compile_note(new_note)
    ↓ 提取 concepts [A, B, C]
    ↓
    对每个 concept：
    ├─ 更新 concept 页面（已有 ✓）
    └─ 找到其他引用该 concept 的笔记（通过 concept.source_notes）
       → 在这些笔记的 related_notes block 中加入 new_note（如果语义相似度 > 阈值）
    ↓
    更新 new_note 自身的 related_notes block（已有，但只在 compile_all 时做）
    ↓
    INDEX.md 更新（已有 ✓）
```

**改动文件**：
- `compiler.py` — `compile_note()` 增加 related_notes 增量更新逻辑

**设计要点**：
- 只更新与新笔记共享 concept 的笔记，不全量扫描
- related_notes block 用 `## Related Notes` 标记，幂等更新（替换而非追加）
- 设置更新上限（最多更新 5 篇最相关笔记），防止一次 ingest 改动太多文件

---

### 3.6 [P2] Clip → 概念图打通

**问题**：clip 和 note 是两个平行数据流，clip 的 `related_concepts` 不参与知识图。

**方案**（轻量，不破坏现有架构）：

```
clip 保存时：
  ↓ 如果 clip.related_concepts 非空
  ↓   对每个 concept：
  │     如果 concept 页面存在 → 在 source 列表中追加 clip 引用
  │     → concept.evidence_count += 1
  │
  ↓ 如果 clip.priority == "P0" 且 clip.content 足够长（>200 字）
  ↓   自动触发 compile_note()（把 clip 当微型笔记编译）
  │
  inbox synthesize 保持不变（3+ clips → 综合笔记 → 正常编译）
```

**改动文件**：
- `clipper.py` — `save_clip()` 后增加 concept 联动
- `compiler.py` — 允许对短文本做轻量编译（跳过 outline 阶段）

---

### 3.7 [P2] 播客摄入

**问题**：播客是高质量信息源（深度对话、专家经验），但 Neocortex 目前不支持音频输入。

**现状**：
- Neocortex 的 `read` 支持 URL、PDF、EPUB、图片、微信公众号
- 播客转录工具已成熟：Podwise（SaaS）、Whisper（本地）、各平台自带字幕
- yanhua 的实践中，Podwise 是三大摄入入口之一

**方案**：分两步走。

**Step 1：Markdown 转录导入（零开发成本）**

用户用外部工具（Podwise / Whisper / 手动复制字幕）将播客转为 Markdown 文件，
然后用 `neocortex read <file.md>` 正常处理。

这一步不需要改代码，只需要在文档中说明工作流：
```
播客 → Podwise/Whisper 转录 → markdown 文件
     → neocortex read podcast-transcript.md --focus "关键话题"
     → 个性化笔记 + 闪卡 + 概念编译
```

**Step 2：音频文件直接读取（需要开发）**

在 `reader/` 中新增 `audio.py` 处理器：

```
neocortex read podcast.mp3
    ↓ 检测文件类型为音频
    ↓ 调用转录引擎：
    │   优先：Whisper API（openai.audio.transcriptions.create）
    │   备选：本地 whisper.cpp（离线）
    │   备选：Google Speech-to-Text
    ↓ 转录文本 → 按说话人分段（如果模型支持 diarization）
    ↓ 进入正常 read pipeline：outline → notes → compile
```

**改动文件**（Step 2）：
- `reader/audio.py` — 新增音频转录处理器
- `reader/fetcher.py` — `ContentFetcher` 识别音频文件类型，路由到 audio 处理器
- `pyproject.toml` — 可选依赖 `openai`（已有）或 `whisper`

**设计要点**：
- Step 1 零成本，立即可用，优先推荐给用户
- Step 2 的转录成本较高（Whisper API ~$0.006/min），需要在文档中提示
- 长播客（>1h）需要分段处理，避免超出 LLM 上下文窗口
- frontmatter 增加 `type: podcast` + `duration` + `speakers` 字段
- 播客笔记的 outline 策略可能需要调整：对话体不适合 skip/brief/deep 的段落标记，
  改为按话题段落划分

---

## 4. 实施计划

### 第一轮：P0（改动最小，价值最大）

| 序号 | 项目 | 改动文件 | 预估改动量 |
|------|------|----------|-----------|
| 1 | log.md 活动时间线 | `config.py` + 6 个 cmd 文件各加一行 | ~30 行 |
| 2 | Query 反写 | `asker.py` + `cmd_knowledge.py` | ~80 行 |

### 第二轮：P1（中等改动，体验提升明显）

| 序号 | 项目 | 改动文件 | 预估改动量 |
|------|------|----------|-----------|
| 3 | Lint 报告持久化 | `cmd_lint.py` | ~60 行 |
| 4 | overview.md 全局综述 | `compiler.py` + `cmd_compile.py` | ~100 行 |
| 5 | Ingest 涟漪效应 | `compiler.py` | ~80 行 |

### 第三轮：P2（新能力拓展）

| 序号 | 项目 | 改动文件 | 预估改动量 |
|------|------|----------|-----------|
| 6 | Clip → 概念图打通 | `clipper.py` + `compiler.py` | ~60 行 |
| 7 | 播客摄入 Step 1 | 仅文档 | 0 行 |
| 8 | 播客摄入 Step 2 | `reader/audio.py` + `reader/fetcher.py` | ~150 行 |

---

## 5. 不做的（以及为什么）

| 方向 | 为什么不做 |
|------|----------|
| 编译规范外置到 CLAUDE.md | Neocortex 是工具不是脚手架，prompt 内置更稳定 |
| raw/wiki 分层 | Neocortex 的笔记本身就是个性化编译产物，不是原始剪藏 |
| RAG / 向量数据库 | 已有 FTS5 + fastembed 混合搜索，当前规模够用 |
| 批量编译模式 | Neocortex 的增量编译（每次 read 后立即编译）更适合个人学习场景 |
| 平台内容目录分离 | Neocortex 的用户是学习者不是内容创作者，不需要 draft/publish 分离 |

---

## 6. 实施结果

> 2026-04-05 全部实施完成，765 tests passed, 0 failed。

### 实际改动文件

| 文件 | 改动内容 |
|------|---------|
| `config.py` | 新增 `append_log()` |
| `asker.py` | 新增 `evaluate_insight_value()` |
| `cmd_read.py` | 接入 log |
| `cmd_knowledge.py` | Query 反写 + chat 自动保存 + review 接入 log |
| `cmd_compile.py` | 接入 log |
| `cmd_lint.py` | 报告持久化 + 趋势追踪 + 接入 log |
| `cmd_clip.py` | clip→概念联动 + 接入 log |
| `compiler.py` | `generate_overview()` + `_ripple_related_notes()` |
| `reader/audio.py` | 新建，Whisper API / 本地转录 |
| `reader/fetcher.py` | 音频路由 |
| `i18n.py` | 3 个新 i18n 键 |
| `CLAUDE.md` | 播客/log/反写/overview 文档 |

### 用户可感知的变化

1. **ask/chat 不再弹保存确认** — 自动评估，有价值的洞察静默保存 + 编译
2. **笔记目录多了 log.md** — 所有操作自动追加，学习轨迹一目了然
3. **`kb lint` 显示趋势** — `Score: 85 ▲ +5 vs 上次检查`，报告存 `_reports/`
4. **`kb compile --full` 生成 overview.md** — 叙事性全局综述
5. **`read` 后相关笔记自动更新** — 涟漪效应，最多更新 5 篇
6. **`clip` 自动联动概念页** — evidence_count + 1
7. **`read` 支持音频** — mp3/m4a/wav 等，自动转录

---

## 7. 社区精选留言分析（10 条）

> 来源：Karpathy idea file gist 评论区精选
> 分析日期：2026-04-05

### 7.1 已覆盖的洞察

| # | 留言要点 | 作者 | Neocortex 对应 |
|---|---------|------|---------------|
| 1 | 个性化作为一等公民层："来源 + 读者语境 + 模板" | dkushnikov | **已有且更强** — outline 的 skip/brief/deep 基于用户画像个性化 |
| 4 | 每个任务产生两个输出（用户答案 + Wiki 更新） | bluewater8008 | ✅ Query 反写 — ask 回答 + insight 编译 |
| 5 | 开发专属编译工具，query 结果归档回 wiki | xoai | ✅ Neocortex 整体就是这个工具 |
| 7 | 闭环复利：query 结果存入 notes，下次查询受益 | VictorVVedtion | ✅ insight 编译进概念图 |

### 7.2 值得后续跟进的洞察

| # | 留言要点 | 作者 | 价值 | 实施思路 |
|---|---------|------|------|---------|
| **3** | "不做内容发明"硬约束 — LLM 是速记员不是代笔 | peas | **高** — 防止知识库被 LLM 幻觉污染 | overview.md 和 insight 反写中标记 `source_type: llm_synthesis`，与 `source_type: user_note` 区分；lint 新增检查项：综合内容占比超过阈值时警告 |
| **4** | Token 预算分层 L0→L3 — 强制先读索引再读全文 | bluewater8008 | **中高** — 扩展时必要 | 当前 ask 只截取 INDEX.md 前 2000 字符；可改为：先读 INDEX 定位相关概念 → 再读相关概念页 → 必要时读原始笔记。分层检索比暴力截断更精准 |
| **9** | 发散性检查 — 摄入后自动生成"反面论点与数据空白" | localwolfpackai | **中** — 对抗确认偏误 | 在 `compile_note()` 中可选生成 `## Counterarguments` 段落；或在 lint 中新增检查：某概念所有 source 来自同一立场时建议补充对立来源 |
| **8** | 反转思路 — 数据进 SQLite，渲染为 Markdown | mpazik | **中** — 扩展到千篇以上时考虑 | 当前 FTS5 + fastembed 已有 SQLite 基础；如果未来笔记量过千，可以考虑 DB-first 架构 |

### 7.3 参考但不采纳的洞察

| # | 留言要点 | 作者 | 不采纳原因 |
|---|---------|------|----------|
| 2 | inbox/foundations/data 四阶段目录 | umbex | Neocortex 已有 notes/concepts/insights/clips 分层，不需要再加一套 |
| 6 | 知识库作为"状态管理" | KeremSalman | 理念认同，但 Neocortex 面向学习场景而非全生活状态管理 |
| 10 | 定时提示词让 Claude 每天维护知识库 | tkgally | `daily` 命令已有类似功能，自动化可通过 cron 实现 |
