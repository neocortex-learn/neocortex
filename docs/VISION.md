# Neocortex 产品方向

> 产品方向和未来功能设计。已实现的架构见 [ARCHITECTURE.md](ARCHITECTURE.md)，竞品分析见 [RESEARCH.md](RESEARCH.md)。

---

## 1. 修订后的实现计划

> 加入竞品分析后，原 4 个 Phase 扩展为 6 个。

### Phase 1: 概念编译 + 知识索引（核心，不变）

1. `models.py` — 新增 ConceptRef、ConceptEntry、CompileResult 等模型
2. `compiler.py` — 编译引擎：概念提取、条目生成、wikilink 插入、INDEX.md 生成
3. `cmd_read.py` — 在 read 流程末尾接入增量编译
4. CLI `compile` 命令 — 全量编译入口
5. `search.py` — 扩展索引范围到 concepts/ 和 insights/

### Phase 2: 间隔复习（最大的竞品差距）

6. `reviewer.py` — SM-2 调度引擎
7. `reader/teacher.py` — 笔记生成时自动提取闪卡
8. CLI `review` 命令 — 交互式复习会话
9. 闪卡表现 → 概念 confidence 联动

### Phase 3: 问答沉淀 + 问答增强（不变）

10. `asker.py` — 问答上下文增加知识库信息
11. `cmd_knowledge.py` — ask/chat 增加保存提示
12. insight 保存 + 增量编译

### Phase 4: 健康检查 + 语义自动链接

13. `linter.py` — 9 项检查 + --fix 自动修复
14. CLI `lint` 命令
15. 向量自动链接（复用 fastembed）
16. 笔记末尾自动附加 "Related Notes" 区块

### Phase 5: 可视化 + 学习胶囊

17. CLI `map` 命令 — Mermaid 概念图
18. CLI `digest` 命令 — 学习周报
19. `read` 增强：自动生成实践练习（.exercises.md）
20. slides 导出（Marp）

### Phase 6: 主动扩展 ✅ 已完成

21. CLI `research` 命令 — ddgs 搜索 + LLM 排序 + 自动进入 read pipeline
22. CLI `feed` 命令 — RSS/来源订阅 + gap 智能过滤
23. recommender 上下文增加概念覆盖率 + 复习表现

### Phase 7: 知识衰变与深化 ✅ 已完成

> 受 César Hidalgo《The Infinite Alphabet》启发。
> 核心论点：知识年衰变率约 50%，"写下来"不等于保存了知识，知识只有在被激活时才能工作。

24. 信心衰减机制 — `decay.py` 实现 Hidalgo 年衰减 50% 模型，惰性计算
25. 三层知识模型 — 闪卡按事实/概念/程序分层生成和复习
26. 概念关系衰变 — 不仅测试单个概念，也测试概念间的连接

---

## 2. Phase 7 详细设计：知识衰变与深化

### 2.1 信心衰减机制

**问题**：当前 `ConceptEntry.confidence` 和 `DomainSkill.confidence` 是静态值，
设定后永不变化。违背了"年衰变 50%"的规律。

**设计**：

数据层：在 `ConceptEntry` 和 profile skills 中已有 `confidence` 和 `last_verified`/`last_updated` 字段。
不需要改模型，只需要在读取时计算衰减后的值。

```python
def decayed_confidence(confidence: float, last_updated: str, today: str) -> float:
    """计算衰减后的信心值。年衰减 50% ≈ 月衰减 5.6%。"""
    months = months_between(last_updated, today)
    monthly_decay = 0.056
    return confidence * (1 - monthly_decay) ** months
```

触发衰减计算的时机（惰性计算，不定时任务）：
- `review` 命令启动时：计算所有概念的当前 confidence，衰减过阈值的闪卡优先复习
- `lint` 检查时：新增 `check_decaying_concepts()`，报告进入危险区的概念
- `digest` 周报时：展示本周衰减最严重的概念
- `profile` 命令时：显示的 confidence 是衰减后的实际值

Confidence 恢复：
- 复习闪卡且通过（quality >= 3）→ 对应概念 confidence += 0.05（上限 1.0），更新 last_updated
- 新增笔记涉及该概念（compile 时检测）→ confidence += 0.1
- 不是重置为 1.0，是渐进恢复——要多次复习才能完全恢复

### 2.2 三层知识闪卡

**问题**：当前闪卡不区分知识层次，LLM 生成的卡片类型随机。

**设计**：

修改 `Flashcard` 模型新增 `knowledge_layer` 字段：
```python
class Flashcard(BaseModel):
    # ... 现有字段 ...
    knowledge_layer: str = "conceptual"  # factual / conceptual / procedural
```

修改 `generate_flashcards()` prompt，要求 LLM 按层分配：
- 事实层 1-2 张："X 是什么" / "X 的三个组成部分"
- 概念层 2-3 张："为什么选 X 而不选 Y" / "X 和 Z 是什么关系"
- 程序层 1-2 张："在什么场景下用 X" / "用 X 解决 Y 问题的第一步是什么"

`review` 命令显示卡片时标注层次（[Fact] / [Concept] / [Procedure]），
复习统计按层分别报告正确率，帮用户发现自己是"知道概念但不会用"还是"会用但说不清原理"。

### 2.3 概念关系衰变

**问题**：当前只测试单个概念的记忆，不测试概念间连接的健康度。

**设计**：

新增一类特殊闪卡——"关系卡"（relationship flashcard）：
```python
class Flashcard(BaseModel):
    # ... 现有字段 ...
    card_type: str = "standard"  # standard / relationship
```

关系卡在编译时自动生成，测试两个关联概念之间的连接：
- "Event Sourcing 和 CQRS 通常一起使用，为什么？"
- "从 Event Sourcing 到 Saga Pattern 的演进路径是什么？"

关系卡的复习表现影响两个概念之间边的"强度"。
`map` 概念图中可以用线条粗细或颜色表示边的强度。

### 2.4 知识复杂性分数

**设计**：

```
复杂性 = 概念数量 × 平均掌握深度 × 连接密度
```

- 概念数量：concepts/ 目录下的条目数
- 平均掌握深度：所有概念 decayed_confidence 的均值
- 连接密度：概念间 related_concepts 边数 / 可能的最大边数

在 `profile` 命令中显示：
```
Knowledge Complexity: 42 (15 concepts × 0.7 depth × 4.0 connectivity)
```

在 `digest` 周报中追踪趋势：
```
Complexity: 38 → 42 (+10.5%) this week
```

---

## 3. Phase 8 设计：分级阅读 + 反思周期 + 认知冲突 ✅ 已完成

> 基于 SuperMemo 增量阅读、Tiago Forte 渐进式摘要、Piaget 认知失衡、
> AGM 信念修正等研究成果设计。

### 3.1 理论基础

**三个主题的交汇——阅读-反思-修正循环**：

```
READ（分级）          REFLECT（反思）         REVISE（冲突）
───────────           ──────────────           ─────────────
L1 快速筛选 ────────── 跳过反思                 不检测冲突
L2 标准阅读 ────────── 单篇微反思 ──────────── 被动冲突扫描
L3 深度阅读 ────────── 深度反思提示 ─────────── 主动冲突检测
                              │                        │
                              ▼                        ▼
                       周度综合反思 ──────────── 冲突摘要
                              │                        │
                              ▼                        ▼
                       月度回顾 ────────────── 信念修正
```

**关键参数（研究支撑）**：

| 参数 | 推荐值 | 来源 |
|---|---|---|
| 阅读分级 | 3 级（scan/read/deep） | Kintsch 构建-整合模型 |
| 反思比例 | 40% 的文章触发反思 | 变比率强化研究 |
| 单篇反思 | 3 个提示，~1-2 分钟 | Moon (2004) |
| 周度反思 | 1 个综合提示，~5 分钟 | Readwise 模型 |
| 月度反思 | 画像 + 信念更新，~15 分钟 | 概念变化理论 |
| 冲突检测置信度 | ≥ 0.75 才报告 | NLI benchmark |
| 声明提取比 | 文章 10-30% 成为声明 | SuperMemo 提取率 |
| 自动修正阈值 | 仅事实/时间类，置信度 > 0.9 | AGM 最小变化原则 |

### 3.2 分级阅读（`read --scan`）

**认知科学基础**：Kintsch 的三层文本表征——表面形式（原文）→ 文本基础（命题/语义）→ 情境模型（整合先验知识）。深度学习需要构建情境模型，但不是每篇文章都值得这个投入。

**3 级是最优数量**：
- 2 级太粗（需要中间档）
- 5 级（如渐进式摘要）适合笔记**管理**但对阅读**深度**太多——用户分不清 L3 和 L4
- 3 级映射认知科学：表面 / 语义 / 情境
- 3 级映射真实行为：浏览 / 阅读 / 研究

**实现设计**：

```python
@app.command()
def read(
    source: str = typer.Argument(...),
    scan: bool = typer.Option(False, "--scan", help="Quick scan: 1-line summary + priority"),
    deep: bool = typer.Option(False, "--deep", help="Deep analysis with 8-dimension anatomy"),
    # ... 现有参数 ...
) -> None:
```

| 级别 | Flag | 流程 | 输出 | LLM 调用 |
|---|---|---|---|---|
| **L1 Scan** | `--scan` | fetch → 1 次 LLM（标题+前 500 字→摘要+优先级） | 终端输出一句话 + P0/P1/P2，不保存文件 | 1 次 |
| **L2 Standard** | 默认 | 现有完整流程 | 笔记 + 闪卡 + 练习 + 编译 | 3-5 次 |
| **L3 Deep** | `--deep` | 现有 `--deep` + 额外声明提取 + 关系分析 | 深度笔记 + 更多闪卡 + 声明数据 | 5-7 次 |

**L1 Scan 的 prompt**：
```
一句话总结这篇文章的核心观点。
评估优先级（基于用户的技能盲区）：
- P0: 直接填补活跃盲区
- P1: 相关但非直接
- P2: 有意思但不紧急
输出 JSON: {"summary": "...", "priority": "P0|P1|P2", "relevant_gaps": [...]}
```

**自动级别选择**（`feed` 和 `research` 集成）：

| 信号 | → L1 | → L2 | → L3 |
|---|---|---|---|
| 匹配活跃 gap？ | 不匹配 | 部分匹配 | 直接匹配 |
| 用户水平 vs 内容难度 | 远超 | 接近 | 挑战区 |
| 内容类型 | 新闻、列表 | 教程、文章 | 论文、规范 |
| 该领域已读文章数 | 多 | 适中 | 少/无 |

**SuperMemo 增量阅读的借鉴——阅读队列**（长期）：

SuperMemo 的核心洞察：不是读完 A 再读 B，而是 5000 篇文章并行处理，
每天优先队列弹出 20-50 个项目。低优先级的自然延后（知识达尔文主义）。

Neocortex 可以实现轻量版：
- `feed` 和 `research` 产出的文章进入阅读队列（`~/.neocortex/reading_queue.json`）
- 每篇有优先级（P0/P1/P2）
- `neocortex next` 命令弹出最高优先级的文章进入 `read`
- 读过的出队，未读的按 gap 变化动态调整优先级

### 3.3 反思周期

**认知科学基础**：
- 间隔反思 ≠ 间隔重复。重复问"还记得 X 吗？"，反思问"X 和 Y 怎么联系，你的理解变了吗？"
- Hatton & Smith (1995)：4 种反思类型，只有对话式反思和批判式反思（Bloom L4-6）提升深度学习
- Moon (2004)：结构化提示的日志比自由书写有效 ~35%
- Moulton et al. (2006)：做间隔反思的外科医生诊断准确率高 23%

**单篇微反思（40% 触发率）**：

在 `read` 完成后，以 40% 概率触发（优先在匹配 gap 的文章上触发）。
3 个结构化提示，每个一句话回答：

1. **意外**（Bloom L4 分析）："这篇文章什么最让你意外，或与你的预期不同？"
2. **连接**（Bloom L5 评估）："这与 [自动建议的相关概念] 有什么关系？"
3. **应用**（Bloom L3 应用）："你能把哪个具体点用到自己的工作中？"

存储为笔记 frontmatter 的 `reflection` 字段：
```yaml
reflection:
  surprise: "没想到 Event Sourcing 的快照策略这么影响性能"
  connection: "和 CQRS 的读模型重建有关联"
  application: "可以在 gap_progress 存储中尝试事件流方式"
```

**"连接"提示的自动建议**：从该笔记 compile 提取的概念中，
选一个已有笔记覆盖的概念作为连接锚点。

**周度反思（现有 `digest` 扩展）**：

在 `digest` 输出末尾加一个综合提示：
- 自动生成："本周你读了 X 篇关于 [主题] 的文章。"
- 提问："跨越这些文章，最大的收获或共同线索是什么？"
- 提问："有什么改变了你对 [活跃 gap] 的看法？"
- 用户回答存储为 `insights/weekly-reflect-{date}.md`

**月度反思（`digest --days 30` 触发）**：

当 `digest` 的 `--days` ≥ 28 时自动触发月度反思模式：

1. **知识演化**：LLM 对比本月初和月末的概念状态，识别新增/更新/衰减的概念
2. **方向偏差**：本月实际学了什么 vs 推荐路径计划学什么 → 偏差分析
3. **认知更新**：哪些反思提到了"意外"或"与预期不同" → 汇总认知变化
4. **下月建议**：基于偏差和认知更新，调整推荐权重

输出为 `insights/monthly-reflect-{date}.md`，格式：
```markdown
# 月度反思 2026-04

## 知识演化
- 新增 5 个概念：...
- 3 个概念 confidence 提升：...
- 2 个概念进入衰减区：...

## 方向偏差
- 计划学分布式系统，实际 60% 时间在前端
- 原因分析：feed 推荐偏向前端文章

## 认知更新
- 关于 Event Sourcing：从"适合所有场景"修正为"仅适合审计密集场景"
- 关于微服务：从"越小越好"修正为"取决于团队规模"

## 下月建议
- 分布式系统的 3 个 gap 已 45 天未进展，建议优先
- 减少前端阅读比例，除非出现 P0 文章
```

**避免成为负担的设计**：
- 单篇反思：只 40% 触发，可跳过，~1 分钟
- 周度反思：digest 输出后附加，不强制回答
- 月度反思：自动生成大部分内容，用户只需确认/修正
- 核心：反思结果直接影响推荐和 gap 权重——用户看到因果关系就不会觉得是负担

### 3.4 认知冲突检测

**认知科学基础**：
- Piaget 的认知失衡：学习发生在不平衡的边界——新信息不符合已有模式时
- Limón (2001)：经历认知冲突的学生概念变化是未经历者的 2 倍
- D'Mello et al. (2014)：困惑（失衡的一种形式）与学习收益相关，**但仅当困惑在 5 分钟内被解决时**。未解决的困惑反而损害学习
- Chinn & Brewer (1993)：面对异常数据的 7 种反应中，只有"理论改变"代表深度学习，其余是防御机制

→ **设计原则**：呈现冲突，但也提供脚手架帮助解决。不要只说"这两条矛盾"——帮用户思考解决方案。

**声明提取（compile 时）**：

在 `compile_note` 的概念提取之后，增加声明提取步骤（仅 L2/L3 阅读触发）：

```python
async def extract_claims(content: str, provider: LLMProvider) -> list[dict]:
    """提取文章核心声明。返回 [{claim, concept, context, confidence}]"""
```

Prompt：
```
从以下笔记中提取 3-5 个核心声明（factual claims）。
每个声明是一个可以被验证或反驳的具体论断。
不要提取观点或偏好，只提取事实性声明。
输出 JSON: [{"claim": "...", "concept": "相关概念名", "context": "适用条件"}]
```

声明存储在概念条目的 frontmatter 中：
```yaml
claims:
  - claim: "Event Sourcing 的快照应每 100 个事件打一次"
    source: event-sourcing-2026-03-15.md
    date: 2026-03-15
```

**冲突分类（3 级）**：

| 类型 | 例子 | 系统行为 |
|---|---|---|
| **时间/事实性** | "React 用 class" vs "React 用 hooks" | 自动修正：标记旧的为过时 |
| **上下文性** | "微服务更好" vs "单体更好" | 呈现 + 提示："在什么条件下各自成立？" |
| **深层/模型性** | 两种互斥的架构思维 | 呈现为学习机会 + 生成苏格拉底问题引导解决 |

**LLM 分类 prompt**：
```
给定两条声明：
A: "{claim_a}" (来源: {source_a}, {date_a})
B: "{claim_b}" (来源: {source_b}, {date_b})

分类为：
1. temporal - 时间差异导致（技术演进）
2. contextual - 不同上下文下各自成立
3. genuine - 真正的矛盾，需要用户判断
4. no_conflict - 实际不矛盾

输出 JSON: {"type": "...", "explanation": "...", "resolution_hint": "..."}
```

**检测时机**：
- `compile_note` 时：新声明 vs 同概念已有声明 → 被动检测
- `lint` 时：全量交叉检测 → 主动检测
- 检测到冲突时：终端警告 + 概念条目追加 "Conflicts" 区块

**信念演化追踪**：

当冲突被解决（用户在反思中标记），记录变化：
```yaml
# 在概念条目中
belief_changes:
  - date: 2026-04-03
    from: "快照每 100 事件打一次"
    to: "快照频率取决于查询模式，读多写少时更频繁"
    trigger: microservices-patterns-2026-03-25.md
```

这创建了一个"信念变更日志"——月度反思时可以回顾"这个月我的哪些理解发生了修正"。

### 3.5 实现计划

按优先级和依赖关系排序：

| 优先级 | 任务 | 依赖 | 改动量 |
|---|---|---|---|
| 1 | `read --scan` 快速筛选 | 无 | 小：cmd_read + teacher.py 加 scan prompt |
| 2 | 单篇微反思（3 提示） | 无 | 中：cmd_read 末尾 + 存储 |
| 3 | 声明提取 | compile | 中：compiler.py + 概念 frontmatter |
| 4 | 被动冲突检测 | 声明提取 | 中：compiler.py + 分类 prompt |
| 5 | 周度反思增强 | digest 已有 | 小：cmd_visualize 加提示 |
| 6 | 月度反思 | digest 已有 | 中：新增月度模式 |
| 7 | 冲突分类 + 脚手架 | 冲突检测 | 中：linter.py 增强 |
| 8 | 信念演化追踪 | 冲突检测 | 小：概念 frontmatter 字段 |
| 9 | 阅读队列 + `next` 命令 | feed/research | 大：新数据模型 + 命令 |

---

## 4. Phase 9 设计：碎片化知识捕获 ✅ 已完成

> 核心问题：日常大部分知识输入是碎片化的（推文、微博、短想法），但当前工具只为长内容设计。
> 在 Agent 时代，一个工具应该能处理从一条推文到一本书的全部内容光谱。

### 4.1 设计原则

> 来源：Readwise Reader、Tiago Forte 渐进式摘要、Obsidian 社区实践、nb CLI

**原则 1：捕获和处理是不同的认知模式**

捕获时要求零决策、零延迟。分类、标签、总结全部延后。
Obsidian 社区的共识：先全部扔进 inbox，每周批量处理。

**原则 2：处理深度应与实际使用成正比，而非预测的重要性**

Tiago Forte 的渐进式摘要：大部分笔记永远停在 L1（原文存档），只有 10-20% 到 L2（标记重点），
只有真正要用的才到 L4（自己写总结）。这是刻意的——不浪费精力在"可能有用"的内容上。

**原则 3：按内容重量自动分级，不需要用户判断**

| 内容类型 | 字数 | 自动深度 | 处理 |
|---|---|---|---|
| 推文/想法/语录 | < 300 字 | highlight | 存原文 + 自动打标签，不调 LLM |
| 文章/博文 | 300-8000 字 | note | 标准 read 流程 |
| 论文/书籍/长文 | > 8000 字 | study | 深度 read + 闪卡 + 练习 |

URL 特征覆盖字数规则：`x.com`/`weibo.cn` → highlight，`arxiv.org`/`.pdf` → study。

**原则 4：轻内容通过显式行动变成重内容**

```
clip（即时捕获）→ inbox（待处理）→ scan（快速筛选）→ read（深度学习）
```

每一步都是用户主动升级，系统从不自动把一条推文膨胀成 16KB 笔记。

### 4.2 新增命令

#### `neocortex clip <source>` — 即时捕获（< 3 秒）

```bash
# 捕获一条推文
neocortex clip https://x.com/karpathy/status/123456

# 捕获一段想法
neocortex clip "Event Sourcing 的快照策略可能和 CQRS 的读模型重建有关"

# 捕获一个链接（只存书签，不读内容）
neocortex clip https://martinfowler.com/articles/event-sourcing.html

# 从剪贴板捕获
neocortex clip --paste
```

**发生了什么**：
1. 如果是 URL → 用 httpx 抓取标题和前 300 字（推文直接抓全文）
2. 如果是文本 → 直接存
3. 自动打标签（关键词提取，**不调 LLM**，纯粹 split + 匹配 gap 列表）
4. 存入 `~/Documents/NeocortexNotes/clips/` 目录
5. 状态标记为 `inbox`
6. 全程 < 3 秒

**轻度处理（1 次 LLM 调用，~5 秒）**：
1. 一句话归纳：这条内容在说什么
2. 关联概念：与知识库中哪些已有概念相关（读 INDEX.md 做匹配）
3. 个人相关性：基于用户 profile，这条信息对你意味着什么（一句话）
4. 自动分类：归入哪个主题目录

输出示例：
```
  ✓ 已捕获

  📌 LLM Knowledge Bases (@karpathy)
     归纳：用 LLM 把原始文档编译成互联的 Markdown wiki，替代传统 RAG
     关联：[[概念编译]], [[知识索引]]
     对你：你的 Neocortex 项目正在做类似的事，可以参考他的 lint 和 health check 思路
     分类：web-backend/
```

#### `neocortex inbox` — 碎片管理

```bash
# 查看待处理的碎片
neocortex inbox
# 输出：
#   Inbox (12 items)
#   ━━━━━━━━━━━━━━━━
#   1. [tweet]    @karpathy: LLM Knowledge Bases...     3 days ago
#   2. [thought]  Event Sourcing 快照策略...              2 days ago
#   3. [bookmark] Martin Fowler - Event Sourcing          1 day ago
#   ...

# 交互式处理（逐条）
neocortex inbox --process
# 对每条：
#   → [k] Keep  保留为参考资料（移入对应主题目录）
#   → [d] Delete 删除
#   → [r] Read  升级为完整阅读（进入 read pipeline）
#   → [s] Skip  跳过，下次再看

# AI 批量处理
neocortex inbox --auto
# LLM 一次性：
#   → 给所有碎片生成一句话摘要
#   → 关联到已有概念
#   → 推荐哪些值得深入阅读（标记 P0/P1/P2）
```

### 4.3 数据模型

```python
class Clip(BaseModel):
    id: str
    source: str                          # URL 或 "manual"
    content: str                         # 原文内容
    title: str = ""                      # 自动提取或用户输入
    clip_type: str = "thought"           # tweet / bookmark / thought / snippet / quote
    auto_tags: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)  # inbox --auto 时填充
    status: str = "inbox"                # inbox / reference / promoted / archived
    summary: str = ""                    # inbox --auto 时填充
    priority: str = ""                   # inbox --auto 时填充 P0/P1/P2
    created_at: str = ""
    processed_at: str | None = None
    promoted_to: str | None = None       # 升级为完整笔记后的文件路径
```

### 4.4 存储

碎片存为轻量 Markdown，一个文件一条，包含 LLM 轻度处理结果：

```markdown
---
type: clip
clip_type: tweet
source: "https://x.com/karpathy/status/123"
created_at: 2026-04-05
status: inbox
auto_tags: [knowledge-base, llm, obsidian]
summary: "用 LLM 把原始文档编译成互联的 Markdown wiki，替代传统 RAG"
relevance: "你的 Neocortex 项目正在做类似的事，可以参考他的 lint 思路"
related_concepts: [概念编译, 知识索引]
topic: web-backend
---

# LLM Knowledge Bases

> @karpathy · 2026-04-03

LLM Knowledge Bases: Something I'm finding very useful recently...

## 关联
- [[概念编译]] — 本条内容描述的方法与概念编译引擎的设计高度吻合
- [[知识索引]] — Karpathy 的 INDEX 文件维护方式可以参考
```

目录结构：
```
NeocortexNotes/
├── clips/              ← 碎片存储（inbox 状态）
│   ├── 2026-04-05-karpathy-llm-kb.md
│   └── 2026-04-05-event-sourcing-thought.md
├── general/            ← 处理后的非技术内容
├── web-backend/        ← 处理后的技术笔记
├── concepts/
├── insights/
└── INDEX.md
```

当碎片被 `Keep` 时 → 移入对应主题目录（用 `_resolve_topic_dir` 逻辑）。
当碎片被 `Read` 时 → 用其 URL 调用 `read` pipeline，完成后标记 `promoted`。

### 4.5 与现有系统的集成

| 现有系统 | 碎片如何参与 |
|---|---|
| **FTS5 搜索** | 碎片在 `clip` 时立即进入索引，`ask`/`chat` 可以搜到 |
| **概念关联** | `clip` 时 LLM 自动匹配已有概念，在碎片中插入 `[[wikilinks]]`。碎片成为概念的弱证据 |
| **概念编译** | 碎片不触发完整编译，但概念条目的"来源"中会列出相关碎片（轻量引用） |
| **推荐系统** | 碎片的关联概念作为"用户正在关注该领域"的信号，影响推荐优先级 |
| **知识衰减** | 碎片给相关概念一个微弱的 confidence boost（+0.02，远小于 read 的 +0.1） |
| **反思** | 碎片不触发反思。周度 digest 中显示"本周捕获 N 条碎片，关联了 M 个概念" |
| **`read --scan`** | scan 结果可以存为碎片（bookmark + 优先级），而不是丢弃 |
| **Obsidian 图谱** | 碎片中的 `[[wikilinks]]` 让它出现在 Obsidian 图谱中，与笔记和概念形成网络 |

### 4.6 内容光谱的完整覆盖

改完后，Neocortex 覆盖从推文到书籍的全光谱：

```
轻 ──────────────────────────────────────────────────── 重

clip          read --scan      read            read --deep
(轻度捕获)     (快速筛选)       (标准学习)       (深度研究)

~5秒          ~30秒            ~3分钟           ~5分钟
1次 LLM       1次 LLM          3-5次 LLM        5-7次 LLM
归纳+关联+     摘要+优先级      笔记+闪卡+练习    深度笔记+解剖+更多闪卡
分类+相关性    可选存为 clip     自动存储+编译      自动存储+编译+声明提取
```

### 4.7 解决"收藏了就不看"——点、线、面机制

> 微信/微博/Twitter 收藏的核心痛点：收藏 → 沉底 → 永远不看。
> 即使翻出来也是孤立的点，连不成线，形不成面。

**三个问题和解决方案**：

#### 问题 1：不会再看（resurface）

碎片需要**主动回到你面前**，而不是等你想起来去翻。

**方案：`neocortex daily`（每日浮现）**

```bash
neocortex daily
# 输出：
#
#   今日浮现（3 条旧碎片 + 2 条到期闪卡）
#   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
#   📌 30 天前你收藏了：
#      "Event Sourcing 的快照策略取决于查询模式" — @某博主
#      当时关联了 [[Event Sourcing]]，现在这个概念已有 3 篇笔记
#      → 这条碎片已被你后来的学习覆盖 ✓
#
#   📌 14 天前你收藏了：
#      "团队超过 8 人就不该用单体架构" — Martin Fowler
#      关联了 [[微服务]]，但你的知识库中还没有这个概念的笔记
#      → 建议：neocortex read 深入了解
#
#   📌 7 天前你有个想法：
#      "FOPO 的评价过滤中间件思路可以用在 code review 流程中"
#      → 这个想法还没有被展开。要写成一篇笔记吗？[y/n]
#
#   🃏 今日到期闪卡：5 张
#      → neocortex review
```

浮现逻辑：
- 新碎片 3 天后第一次浮现（防止当天看过就忘）
- 此后按间隔递增浮现：7 天、14 天、30 天、60 天
- 浮现时附带**上下文更新**：自从你收藏后，关联概念发生了什么变化？
- 如果碎片已被后续学习覆盖（关联概念有了深度笔记）→ 标记为"已吸收"，降低浮现频率
- 如果碎片一直未被展开 → 持续浮现，直到用户显式 archive

**关键设计**：每次浮现不是简单地"提醒你看过这个"，而是**带着知识库的当前状态告诉你这条碎片现在意味着什么**。

#### 问题 2：点连不成线（connect）

系统应该自动发现碎片之间的关系，而不是等用户自己去翻。

**方案：clip 自动聚类 + 趋势提醒**

当同一个概念累积了 3+ 条碎片时，系统在下一次 `daily` 或 `digest` 中提示：

```
  🔗 发现碎片聚类：
     你在过去 2 周收藏了 4 条关于 [[微服务]] 的内容：
     1. "团队超过 8 人就不该用单体架构" (Martin Fowler)
     2. "微服务的最大成本是运维复杂性" (@某开发者)
     3. "Shopify 从微服务回归单体的经验" (HN)
     4. 你的想法："我们的项目是不是过度微服务化了？"

     这 4 个点已经形成一条线：关于微服务的利弊权衡。
     → 建议：neocortex read 找一篇深度文章系统学习
     → 或者：neocortex research "微服务 vs 单体 架构决策"
```

聚类逻辑：
- 按 `related_concepts` 分组
- 同一概念 3+ 条碎片 → 触发聚类提示
- LLM 生成一句话总结这些碎片之间的共同线索

#### 问题 3：点不会长成面（synthesize）

当碎片聚类足够大，系统应该**自动把点连成线**——生成一篇综合笔记。

**方案：`inbox --synthesize`（碎片综合）**

```bash
neocortex inbox --synthesize
# 或在 digest --days 30 时自动触发

# 系统找到所有碎片聚类（同概念 3+ 条），对每个聚类：
#   1. 读取所有相关碎片的内容
#   2. LLM 生成一篇综合笔记：
#      - 提炼共同主题
#      - 标注不同来源的不同观点（可能有矛盾！）
#      - 生成 1-2 个开放问题
#      - 推荐下一步阅读方向
#   3. 保存为正式笔记（进入主题目录，不再是碎片）
#   4. 原始碎片标记为 "synthesized"，链接到综合笔记
```

综合笔记格式：

```markdown
---
type: note
via: synthesis
synthesized_from: [clip-1.md, clip-2.md, clip-3.md, clip-4.md]
date: 2026-04-15
---

# 微服务 vs 单体：从 4 条碎片中浮现的认知

## 线索
你在两周内从不同来源收集了关于微服务架构决策的 4 个视角...

## 共识
- 微服务不是银弹，团队规模和运维能力是关键约束
- 成功案例（Shopify 回归单体）证明"先单体、后拆分"可能更稳妥

## 分歧
- Fowler 认为 8 人是分界线，而 Shopify 的经验表明即使大团队也可能回归

## 你的位置
- 你的想法"过度微服务化"暗示你可能正在经历类似的反思

## 下一步
- 深入阅读：Sam Newman 的《Building Microservices》第 2 版
- 或研究：neocortex research "monolith to microservices migration decision"
```

**这就是从"面"的层面解决问题**——4 条孤立的碎片自动变成了一篇有观点、有分歧、有方向的认知笔记。

#### 完整的"点→线→面"流转

```
点（clip）                线（connect）              面（synthesize）
─────────                ──────────                ──────────────
收藏一条推文     ──3天──→  浮现：带上下文回顾    ──聚类──→  发现 4 条碎片
收藏一篇短文     ──7天──→  浮现：概念有新进展             都关于 [[微服务]]
记录一个想法     ──14天─→  浮现：你后来学了相关            ↓
                          内容，已覆盖 ✓            自动综合为正式笔记
                                                   ↓
                                              碎片标记为 "已吸收"
                                              概念 confidence 提升
                                              推荐下一步深入方向
```

### 4.8 实现计划（更新）

| 优先级 | 任务 | 改动量 |
|---|---|---|
| 1 | Clip 数据模型 + 存储函数 | 小：models.py + config.py |
| 2 | `clip` 命令 + 轻度 LLM 处理（归纳/关联/相关性/分类）| 中：新建 cmd_clip.py + clipper.py |
| 3 | `inbox` 命令（列表 + 交互处理 + promote to read）| 中：cmd_clip.py 扩展 |
| 4 | `daily` 命令（浮现旧碎片 + 到期闪卡 + 上下文更新）| 中：新建 cmd_daily.py |
| 5 | 碎片聚类检测（同概念 3+ 条时提示）| 中：daily/digest 中检测 |
| 6 | `inbox --synthesize`（碎片聚类 → 综合笔记）| 中：LLM 综合 + 笔记生成 |
| 7 | `read --scan` 结果可选存为 clip | 小：cmd_read.py 修改 |
| 8 | FTS5 索引覆盖 clips/ | 小：search.py 已支持 rglob |
| 9 | digest 显示碎片统计 + 聚类趋势 | 小：cmd_visualize.py |
---

## 5. Phase 10：explore 命令——扫描一个作者/站点的全部内容

> 场景：发现一个写得好的作者（如 grapeot/yage.ai），想快速了解他写了什么，哪些最值得读。
> 核心问题：AI 看了不等于你看了。AI 应该替你**选**，而不是替你**读**。

### 5.1 设计

```bash
neocortex explore https://yage.ai/archives.html
# 或
neocortex explore https://someone.com/blog
```

**流程**：

```
抓取站点文章列表（标题 + URL + 摘要）
  → 每篇用 scan 逻辑做快速评估（P0/P1/P2 + 一句话摘要 + gap 匹配）
  → 生成作者概览（主题分布、写作方向）
  → 终端输出排序列表，按优先级降序
  → 用户选择哪些要深入 read
  → 选中的逐个进入 read pipeline
  → 未选中的存为 clip（bookmark 状态，将来 daily 可浮现）
```

**关键决策**：

| 问题 | 决策 | 理由 |
|---|---|---|
| 是 Neocortex 功能还是新 Agent？ | Neocortex 子命令 | 输出要进知识库，筛选依赖 profile |
| AI 看完直接生成笔记？ | 不。只扫描+排序，用户选择后才 read | AI 看了 ≠ 你看了 |
| 未选中的文章怎么办？ | 存为 clip | 将来 daily 可浮现，不丢失 |
| 工具还是服务？ | 工具（手动触发） | CLI 不该有后台进程 |

### 5.2 输出格式

```
  探索：grapeot (yage.ai)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  概览：AI 工作流与效率方法论，偏向实践落地。15 篇文章。

  P0（直接填补你的盲区）：
  1. 用好AI的第一步：停止和AI聊天
     → AI-first 工作流设计，与你的架构落地 gap 直接相关
  2. ...

  P1（相关但非紧急）：
  3. ...
  4. ...

  P2（有意思但不急）：
  5. ...

  选择要阅读的文章编号（如 1 2 4），或回车跳过：
```

### 5.3 实现要点

**文章列表抓取**：
- 用 httpx 抓取 archives/blog 页面
- 用 readability 或正则提取文章链接和标题
- 如果页面是标准博客结构（`<a href="...">title</a>`），大部分情况能自动提取

**批量 scan**：
- 不逐篇调 LLM（太慢太贵）
- 把所有标题+摘要合成一次 LLM 调用，让 LLM 批量排序
- 输入：文章列表 + 用户 gap 列表
- 输出：每篇的优先级 + 一句话理由

**作者概览**：
- 同一次 LLM 调用中顺便生成
- 存为 clip（clip_type="author_overview"）

---

## 6. 产品叙事：活的知识，而不是死的收藏

### 5.1 一个所有人都有的问题

打开你的微信收藏、微博收藏、Twitter 书签、Pocket 稍后读。数一数，有多少条你收藏后再也没看过？

大多数人的答案是：**90% 以上。**

收藏夹是知识的墓地。每一条被存下来的信息，在收藏的那一刻就已经死了。
你的大脑在存的时候有个幻觉："我存了，就等于我知道了"。但你不知道。
你只是把"学习"这件事推迟了——推迟到一个永远不会到来的"以后"。

现有的所有工具都在解决两个问题：
- **怎么存**（Pocket、Raindrop、收藏夹）
- **怎么找**（Obsidian 搜索、Notion AI、Readwise）

但没有人解决最核心的问题：**存了之后，它怎么活着？**

### 5.2 Neocortex 的洞察

> **一条信息的价值不是它被存下来那一刻决定的，而是随着你后续学到的东西不断变化的。**

你 3 个月前收藏了一条 @karpathy 的推文，讲"用 LLM 编译知识库"。
当时你觉得"有意思"，存了，然后忘了。

3 个月后，你读了 5 篇关于知识管理的文章，做了一个 Obsidian vault，
用 LLM 生成了概念图谱，实现了间隔复习系统。

**现在再看那条推文，它的含义完全不同了。**
当时你看到的是"一个人的做法"，现在你看到的是"验证了你正在做的方向"。
你能看到他的方案中哪些你已经实现了、哪些他有你没有、哪些他走了弯路。

这不是推文变了——是**你变了**，所以推文的价值变了。

**没有任何现有工具能捕捉到这个变化。** 因为没有工具同时拥有：
1. 你的知识状态（profile、概念图谱、confidence 衰减）
2. 你的历史碎片（clips）
3. 两者之间的动态关系

Neocortex 是第一个同时拥有这三者的系统。

### 5.3 收藏不是终点，是种子

在 Neocortex 里，`clip` 不是"存起来以后看"，而是**播下一颗种子**。

种子被播下后，它不会安静地躺在那里。它会：

**发芽**（3 天后浮现）：
```
📌 3 天前你收藏了：
   "微服务的最大成本是运维复杂性" — @某开发者
   你目前没有关于 [[微服务]] 的笔记
   → 这是一个新方向的信号
```

**长出根**（发现聚类）：
```
🔗 你在过去 2 周收藏了 4 条关于 [[微服务]] 的内容
   这些碎片正在形成一条线：关于微服务的利弊权衡
   → 是时候深入了解了？
```

**开花**（综合为知识）：
```
✨ 系统从你的 4 条碎片综合出了一篇笔记：
   "微服务 vs 单体：从碎片中浮现的认知"
   包含共识、分歧、和你的位置
   → 4 个孤立的点变成了一个有观点的面
```

**与其他植物交织**（进入知识网络）：
```
🌐 新综合笔记与已有概念 [[分布式系统]]、[[架构设计]] 建立了连接
   你的知识复杂性分数从 42 上升到 48
   → 知识在生长
```

### 5.4 "今日浮现"——每天打开 Neocortex 的理由

现有学习工具的留存问题：用户需要**意志力**才会打开。
"我应该复习了"、"我应该读新文章了"——这些都是自律驱动，反人性。

Neocortex 的 `daily` 命令用**好奇心**驱动：

> "我好奇今天系统会浮现什么——哪条旧碎片有了新含义？哪些点连成了线？"

这是 Readwise 每日邮件能让用户坚持 3 年的原因：**重新遇见自己的想法是有愉悦感的**。
Neocortex 更进一步——不只是重新展示，而是**带着你现在的知识状态重新解读**。

用户打开 `neocortex daily`，看到的不是"你 30 天前存了这条"，而是：

> "你 30 天前存了这条关于 Event Sourcing 的推文。
> 那时你的知识库里没有这个概念。
> 现在你已经读了 3 篇相关文章，概念 confidence 从 0.3 升到 0.72。
> **这条推文中提到的 '快照策略' 正好是你的概念条目里标记的开放问题。**
> → 要深入研究吗？"

这个浮现不是机械的间隔提醒。它是**知识状态感知的**——系统知道你这 30 天里学了什么，
所以它能判断哪些旧碎片**此刻**最值得重新看。

### 5.5 留存飞轮

```
clip（播种）
  → daily 浮现（好奇心驱动，每天 2 分钟）
    → 发现旧碎片有新含义（愉悦感）
      → 知识库越大，浮现越精准、越有价值
        → 越想 clip 更多内容
          → 正向循环
```

关键机制：
- **越用越好**：碎片越多 + 笔记越多 → 交叉匹配空间越大 → 浮现越精彩
- **低门槛启动**：clip 只需 5 秒，不需要"留出时间学习"
- **自然升级**：碎片聚类后用户自然想深入 → 从 clip 流向 read，不需要催促
- **衰减制造紧迫感**：概念 confidence 在衰减 → "你上个月学的 X 快忘了"→ 驱动复习

### 5.6 与竞品的根本区别

| | 传统收藏工具 | Readwise | Neocortex |
|---|---|---|---|
| **收藏后** | 沉底 | 定期重现 | 带知识上下文重现 |
| **碎片关系** | 无 | 无 | 自动聚类 + 综合 |
| **个性化** | 无 | 随机重现 | 基于 profile + 概念 + confidence |
| **知识演化** | 无 | 无 | 碎片价值随学习动态变化 |
| **驱动力** | 自律（"我应该看"） | 习惯（每日邮件） | 好奇心（"今天有什么新发现"） |
| **终态** | 收藏夹 = 墓地 | 高亮 = 提醒 | 碎片 = 种子 → 知识 |

**一句话定位**：

> Neocortex 不是让你"存了以后找"的工具。
> 它是让你"存了以后，它自己会长大"的工具。

### 5.7 这件事为什么现在才能做

三个前提条件同时满足了：

1. **LLM 足够便宜**：每条碎片一次轻度 LLM 调用（归纳 + 关联 + 相关性）的成本
   降到了可以忽略的水平。2023 年这样做一条 0.1 美元，现在 0.001 美元。

2. **LLM 足够好**：GPT-4 级别的模型能准确判断"这条推文和你知识库中的 [[Event Sourcing]] 概念
   有什么关系"。2022 年的模型做不到这个精度。

3. **个人知识图谱成为可能**：Obsidian 和 Markdown 生态让"本地的、用户拥有的、结构化的
   知识库"成为标准做法。5 年前这需要自建数据库。

**Neocortex 站在这三个趋势的交叉点上。**

---

## 6. 知识资产的 AI-first 开放——让所有 AI 都懂你

> 来源：grapeot《用好AI的第一步：停止和AI聊天》(yage.ai, 2026-03)
> 核心框架：上中下三策——下策信息消失，中策人类友好但 AI 难消费，上策 AI-first

### 6.1 问题：知识库被锁在 Neocortex 里

Neocortex 建了一个结构完善的个人知识库：profile.json（技能画像）、INDEX.md（知识地图）、
concepts/（概念条目）、claims.json（事实声明）、.flashcards/（复习数据）。

但这些数据**只有 Neocortex 自己能用**。

用户在 Cursor 里写代码时，Cursor 不知道他的技能水平。
用户在 Claude Code 里做项目时，Claude Code 不知道他的知识盲区。
用户跟任何 AI 聊天时，那个 AI 不知道他已经读了什么、学了什么、在什么概念上挣扎。

grapeot 的"资产积累"洞察：**"你用得越多、积累越多，AI 就越懂你"**。
但前提是积累的资产能被所有 AI 消费，而不只是被一个工具独占。

### 6.2 愿景：Neocortex 知识库 = 你的 AI 上下文层

Neocortex 的定位应该从"一个学习工具"扩展为**"你的个人知识 API"**。

```
你的任何 AI 工具
    │
    ├─ Cursor（写代码）──→ 读 profile.json → 知道你的水平 → 更精准的代码建议
    │
    ├─ Claude Code（做项目）──→ 读 INDEX.md + concepts/ → 知道你学了什么 → 不重复解释
    │
    ├─ ChatGPT/其他 AI（聊天）──→ 读你的知识图谱 → 跳过你已知的 → 直击盲区
    │
    └─ 未来的任何 Agent ──→ 读你的完整画像 → 真正个性化的服务
            │
            ▼
    ~/Documents/NeocortexNotes/     ← AI-first 格式
    ~/.neocortex/                   ← 结构化数据
```

### 6.3 已经具备的条件

Neocortex 的数据**已经是 AI-first 格式**（grapeot 说的"上策"）：

| 数据 | 格式 | AI 可消费性 |
|---|---|---|
| 技能画像 | `profile.json` | 直接 JSON，任何 agent 可读 |
| 知识地图 | `INDEX.md` | Markdown，已用于 ask/chat 上下文 |
| 概念条目 | `concepts/*.md` | 结构化 Markdown + frontmatter |
| 事实声明 | `claims.json` | 直接 JSON |
| 学习历史 | `recommendations.json` + `gap_progress.json` | 直接 JSON |
| 信念变更 | `belief_changes.json` | 直接 JSON |
| 闪卡数据 | `.flashcards/*.json` | 直接 JSON |

不需要额外做格式转换——数据已经是 AI-ready 的。

### 6.4 实现路径

**短期（零开发成本）：文档指南**

写一份指南，教用户怎么在其他 AI 工具中引用 Neocortex 数据：

```markdown
# 在 Claude Code 中使用 Neocortex 画像

在项目的 CLAUDE.md 中添加：
  参考用户技能画像：~/.neocortex/profile.json
  参考知识库索引：~/Documents/NeocortexNotes/INDEX.md
  用户的知识盲区和学习进度见：~/.neocortex/gap_progress.json

# 在 Cursor 中使用
在 .cursorrules 中引用同样的路径。
```

**中期：Agent Skill 封装**

把 Neocortex 封装为 Agent Skills 规范（agentskills.io），让 Claude Code / Cursor / Windsurf 原生支持：
- `neocortex-profile` skill：读取和解释用户画像
- `neocortex-knowledge` skill：搜索和引用知识库内容
- `neocortex-gaps` skill：查看用户的技能盲区

**长期：MCP Server**

把 Neocortex 做成 MCP Server，通过标准协议暴露知识库：
- `get_profile()` → 返回技能画像
- `search_knowledge(query)` → 搜索笔记和概念
- `get_gaps()` → 返回技能盲区
- `get_concepts()` → 返回概念图谱

任何支持 MCP 的 AI 工具都能连接，实现"一处积累，处处可用"。

### 6.5 这意味着什么

当 Neocortex 从"独立工具"变成"知识 API"：

- 你在 Neocortex 里 `read` 一篇文章 → 知识更新 → 所有 AI 工具立刻感知到你变了
- 你在 Cursor 里写了新代码 → 可以触发 Neocortex 更新画像 → 推荐路径自动调整
- 你用 Claude Code 问了个问题 → 回答基于你的完整知识状态 → 不浪费时间解释你已知的

**一处学习，处处受益。你的知识不再是孤岛，而是所有 AI 交互的共享地基。**

---

## 7. 开放问题

1. **概念粒度**：多细算一个概念？"React" 是一个概念还是 "React Hooks"、"React Server Components" 各算一个？
   - 倾向：按用户的学习粒度来，LLM 提取时参考 gap 列表的粒度
   - 同义词系统兜底，太细的可以合并

2. **大规模性能**：100 篇笔记时增量编译很快，1000 篇呢？
   - 编译缓存保证只处理变化的笔记
   - INDEX.md 如果太大，可以分域生成（`INDEX-distributed.md`, `INDEX-frontend.md`）
   - 目前不需要过早优化，先跑起来

3. **概念条目的"声音"**：概念条目应该是客观的 wiki 风格，还是延续笔记的个性化风格？
   - 倾向：混合。核心定义客观，"从你的项目看" 部分个性化
   - 这是 Neocortex 相比通用 wiki 的差异化

4. **多语言概念**：同一个概念中英文名不同（"事件溯源" vs "Event Sourcing"）
   - aliases 字段覆盖
   - `normalize_gap_name()` 已有多语言同义词基础

5. **离线/无 LLM 模式**：编译和 lint 需要 LLM，如果用户没配置 provider 怎么办？
   - compile/lint 命令检查 provider，没有则提示配置
   - wikilink 插入和断链检查等不需要 LLM 的操作仍可离线执行

6. **闪卡质量**：LLM 自动生成的闪卡质量参差不齐怎么办？
   - V1 先上线，收集用户"跳过/删除"的卡片模式
   - 在 prompt 中加入反例："不要出纯记忆题，要出'为什么'和'怎么选'的题"
   - 让用户可以编辑/删除生成的闪卡
   - 参考 RemNote：好的闪卡 = 最小知识原则 + 一张卡只测一个点

7. **Research 命令的来源可信度**：自动搜索的文章质量怎么保证？
   - 优先从 recommend 系统已有的资源库中选取
   - Web search 结果经过 LLM 可信度评估（域名声誉、内容质量）
   - 用户确认后才进入 read pipeline，不是完全自动

8. **Feed 的信噪比**：RSS 推送 + gap 过滤后，仍然可能噪音太多？
   - 从严格过滤开始（只推送高度匹配 gap 的文章）
   - 用户反馈（读/跳过）训练过滤阈值
   - 限制每日推送上限（如 3-5 篇）

9. **闪卡与概念编译的交互**：闪卡复习表现怎样影响概念状态？
   - 概念下所有闪卡的平均正确率 > 80% 且复习 3+ 轮 → confidence 提升
   - 连续 2 次答错同一张卡 → 对应概念标记为"需要强化"
   - 不要过度自动化——confidence 变化是渐进的，不会因为一次答错就大幅下调

10. **衰减速率的个性化**：50% 年衰减是组织级数据，个人学习者的衰减率可能不同
    - V1 先用 50% 作为默认值
    - 长期可以根据用户复习表现动态调整：如果用户长间隔后仍然答对，说明衰减比预期慢
    - 可以按领域调整：用户主业领域衰减慢（天天在用），非主业领域衰减快

11. **关系卡的生成时机**：概念关系卡应该什么时候生成？
    - compile 时自动生成（两个概念都有 2+ 笔记时）
    - 不要太早——只有一篇笔记的概念还不稳定，生成关系卡意义不大
    - 数量控制：每对概念最多 1-2 张关系卡

12. **知识复杂性分数的校准**：怎么让分数有意义？
    - 需要足够多的用户数据才能校准
    - V1 先展示原始数字 + 趋势，不做跨用户对比
    - 长期可以参考 Hidalgo 的经济复杂性指数方法论

---

