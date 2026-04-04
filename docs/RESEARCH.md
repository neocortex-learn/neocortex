# Neocortex 研究笔记

> 竞品调研、学术理论和外部灵感的记录。技术架构见 [ARCHITECTURE.md](ARCHITECTURE.md)，产品方向见 [VISION.md](VISION.md)。

---

## 1. 竞品分析与新增功能

> 以下基于对 30+ 竞品的调研，按 Neocortex 可借鉴的价值排序。

### 1.1 竞品全景

#### AI 个人知识管理

| 产品 | 定位 | Neocortex 可借鉴 |
|---|---|---|
| [Khoj](https://github.com/khoj-ai/khoj) (33.8k⭐) | 开源 AI 第二大脑，支持多平台/多 LLM | 多平台接入（Obsidian 插件、浏览器、WhatsApp）；自定义 agent + 定时自动化 |
| [Mem.ai](https://get.mem.ai) | AI 思维伙伴，自动构建知识图谱 | 后台自动构建知识图谱；自然语言检索整个笔记库 |
| [Saner.AI](https://www.saner.ai) | 零摩擦 AI 第二大脑 | 跨应用全局捕获（侧边栏）；集合级综合报告 |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | 本地私有 AI 知识库 | Workspace 隔离（每个项目独立上下文）；无代码 agent 工作流 |
| [Sider Wisebase](https://sider.ai/wisebase) | AI 知识库 + 深度研究 | Deep Research（自动扫描 100+ 来源，产出报告，自动归档回知识库）|

#### AI 开发者学习

| 产品 | 定位 | Neocortex 可借鉴 |
|---|---|---|
| [Workera](https://www.workera.ai) | AI 技能评估平台 | 自适应测试（难度实时调整）；10,000+ 技能库；预测未来 6 个月技能需求 |
| [CodeSignal](https://codesignal.com) | AI 编程技能评测 | 评估"与 AI 协作编程"的能力；"Cosmo" AI 导师实时上下文指导 |
| [Codecademy](https://www.codecademy.com) | 交互式编程教育 | **Vibe Learning**：从用户实际项目代码生成个性化学习路径；Build + Learn 双标签 |
| [Exercism](https://exercism.org) | CLI-first 编程练习 + 人类导师 | 82 种语言、7,792 道练习；人类导师反馈代码质量和惯用法 |
| [Brilliant](https://brilliant.org) | 交互式 STEM 学习 | 交互式视觉课程（比被动阅读有效 6 倍）|

#### 第二大脑 / PKM

| 产品 | 定位 | Neocortex 可借鉴 |
|---|---|---|
| [Heptabase](https://heptabase.com) | 可视化知识管理（白板） | 空间画布——拖拽排列概念卡片，看到传统大纲看不到的关系 |
| [Tana](https://tana.inc) | 结构化 PKM | **Supertag**：给笔记定义 schema（如"会议"标签自动有参与者、Action Items 字段）|
| [Logseq](https://logseq.com) | 开源大纲式 PKM | 块级引用（任何 bullet 可在任何地方嵌入/查询）；内置闪卡 |
| [Reor](https://github.com/reorproject/reor) (8.5k⭐) | 本地 AI 笔记（自动链接） | **向量自动链接**：写笔记时侧边栏实时显示语义相关笔记 |
| [InfraNodus](https://infranodus.com/obsidian-plugin) | Obsidian 3D 知识图谱 | **Gap 可视化**：3D 网络图显示概念簇之间的空白——"你应该在这里建一条桥" |
| [Atomic](https://github.com/kenforthewin/atomic) | 自托管知识库 | **Wiki 综合**：读取同一标签下所有笔记，生成带引用的 wiki 文章；单 SQLite 文件存一切 |

#### 阅读 + 复习

| 产品 | 定位 | Neocortex 可借鉴 |
|---|---|---|
| [Readwise Reader](https://readwise.io/read) | 阅读→高亮→间隔复习 | 30+ 来源同步高亮；YouTube 字幕高亮；Ghostreader AI 摘要/问答 |
| [RemNote](https://www.remnote.com) | 笔记 = 闪卡 | **笔记即闪卡**：任何 bullet 可变成闪卡（Q&A / 填空 / 图片遮挡）|
| [SuperMemo](https://www.supermemo.pro) | 间隔重复鼻祖 | **增量阅读**：同时阅读上千篇文章，提取片段转为闪卡，全部用 SM-18 调度 |
| [Recall](https://www.getrecall.ai) | AI 个人百科 | 自动构建知识图谱 + 间隔复习；支持 YouTube/播客/TikTok |
| [BeeMind](https://beemind.app) | 轻量阅读 + SRS | **兴趣过滤**：用自然语言描述兴趣，AI 自动匹配内容进入复习队列 |
| [Screvi](https://screvi.com) | 高亮管理 + SRS | **实体书扫描**：拍照高亮页面，Gemini AI 提取文本 |
| [Glasp](https://glasp.co) | 社交高亮 + AI 分身 | **AI Clone**：从阅读历史构建用户的数字化身，能替你回答问题 |
| [Strater AI](https://strater.in) | AI 学习胶囊 | **学习胶囊**：一个来源 → 摘要 + 测验 + 闪卡 + 思维导图，一站式学习单元 |

### 1.2 关键缺口（按影响排序）

竞品调研揭示了 5 个 Neocortex 目前完全缺失、且多个竞品已验证的功能方向：

#### 缺口 1：间隔复习（Spaced Repetition）— 最大空白

**现状**：Neocortex 生成笔记后就结束了。没有复习机制，知识留存依赖用户自觉。

**竞品证据**：RemNote、Recall、Screvi、BeeMind、SuperMemo、Strater 都有 SRS。RemNote 最优雅——笔记和闪卡是同一个对象。

**设计方案**：`neocortex review`

```
笔记生成时 → LLM 自动从笔记中提取 5-10 个 Q&A 对（闪卡）
           → 存储在笔记同目录的 .flashcards.json 中
           → 每张卡有 SM-2 调度参数（interval, ease_factor, next_review）

neocortex review
  → 从所有 .flashcards.json 中选出今日到期的卡片
  → 交互式展示：先显示问题，用户思考后按键显示答案
  → 用户评分（1-5），更新 SM-2 参数
  → 结束时显示统计（已复习 / 正确率 / 明日到期数）
```

闪卡格式（存储在每篇笔记旁的 `.flashcards.json`）：

```json
[
  {
    "id": "uuid",
    "source_note": "event-sourcing-2026-03-15.md",
    "question": "Event Sourcing 和传统 CRUD 的核心区别是什么？",
    "answer": "CRUD 存最终状态，ES 存每一步变化。当前状态 = 所有事件的重放。",
    "concept": "event-sourcing",
    "difficulty": "medium",
    "interval": 1,
    "ease_factor": 2.5,
    "next_review": "2026-04-04",
    "review_count": 0
  }
]
```

与概念系统联动：
- 闪卡关联到概念（`concept` 字段）
- 复习表现影响概念的 `confidence` 值
- 连续答错的卡片 → 对应概念 confidence 下降 → 可能触发新的推荐
- 全部通过的概念 → confidence 上升 → gap 状态可能升级

**关键参考**：
- SM-2 算法简单可靠，足够 V1
- RemNote 的"笔记即闪卡"理念——不要让用户单独创建闪卡，从笔记自动生成
- SuperMemo 的增量阅读——复习不只是闪卡，也可以是重读笔记的重点段落

#### 缺口 2：语义自动链接 — 零手工发现关联

**现状**：笔记之间没有链接。概念编译（Phase 1）会建立 wikilinks，但那是 LLM 显式提取的。

**竞品证据**：Reor 用向量相似度自动链接；InfraNodus 用 3D 网络图发现 gap。

**设计方案**：复用现有 `search.py` 的 fastembed 向量

```
每篇笔记/概念条目已有 embedding（现在只用于 hybrid_search）
  → 编译时计算笔记间的 cosine similarity
  → 相似度 > 0.6 的笔记对自动建立 [[Related]] 链接
  → 概念条目的 "关联概念" 部分由向量共现 + LLM 确认共同生成
```

额外功能——**写作时的实时关联提示**（类似 Reor 的侧边栏）：

这在 CLI 中不太现实，但可以在 `neocortex read` 生成笔记后，附加一个"相关笔记"区块：

```markdown
---
## 🔗 Related Notes (auto-linked)
- [[building-event-stores-2026-03-20]] (similarity: 0.82)
- [[microservices-patterns-2026-03-25]] (similarity: 0.71)
- [[concepts/cqrs]] (similarity: 0.68)
```

#### 缺口 3：Deep Research — 知识库主动扩展

**现状**：Neocortex 是被动的——用户给 URL，它才读。不会主动发现和摄取新内容。

**竞品证据**：Sider Wisebase 的 Deep Research 自动扫描 100+ 来源；Karpathy 也提到 LLM 用 web search 补全缺失信息。

**设计方案**：`neocortex research <topic>`

```
neocortex research "Event Sourcing 的快照策略"
  → LLM 分析当前知识库中该主题的覆盖情况
  → 识别缺失的子主题和开放问题
  → 调用 web search 发现高质量文章（复用现有 httpx）
  → 自动 fetch + 生成笔记（复用 read pipeline）
  → 触发增量编译
  → 报告："找到 5 篇文章，生成了 3 篇笔记，新增 2 个概念"
```

与 lint 的 "建议探索" 联动：
- `neocortex lint` 发现 "你学了 X 和 Y，但没探索它们的交集 Z"
- `neocortex research Z` 自动扩展这个领域

这让知识库从"被动记录"变成"主动生长"。

#### 缺口 4：学习胶囊（Learning Capsule）— 一站式学习单元

**现状**：`neocortex read` 生成笔记，但笔记只是文字。没有配套的练习、测验、闪卡。

**竞品证据**：Strater AI 的 Capsule（摘要 + 测验 + 闪卡 + 思维导图）；Codecademy 的 Build + Learn 双标签。

**设计方案**：增强 `read` 的输出，一篇文章生成完整的学习胶囊

```
neocortex read <url>
  → 现有：生成个性化笔记（.md）
  → 新增：自动生成闪卡（.flashcards.json）   ← 缺口 1
  → 新增：生成 2-3 道实践练习（.exercises.md） ← 本缺口
  → 新增：更新概念条目和 INDEX.md              ← Phase 1 的概念编译
```

练习不是算法题，而是把所学应用到用户自己项目的提示：

```markdown
## 练习 1：在你的项目中应用 Event Sourcing
你的 Neocortex 项目用 gap_progress.json 追踪状态变化。
思考：如果把它改成 Event Sourcing 模式，需要怎么改？
提示：每次 `update_gap_status()` 调用是一个事件...

## 练习 2：设计一个快照策略
当前 gap_progress 有 N 个条目。如果改成事件流，多久应该打一次快照？
写出你的计算逻辑。
```

#### 缺口 5：兴趣过滤 + 内容推送 — 从手动到半自动

**现状**：用户需要自己找文章喂给 `neocortex read`。推荐只给出主题和资源链接，不会主动摄取。

**竞品证据**：BeeMind 的兴趣标签自动过滤；Readwise 的 RSS 集成；Recall 支持 YouTube/播客。

**设计方案**：`neocortex feed`（RSS/来源订阅 + 智能过滤）

```yaml
# ~/.neocortex/feeds.yaml
feeds:
  - url: "https://martinfowler.com/feed.atom"
    filter: "architecture, distributed systems"
  - url: "https://overreacted.io/rss.xml"
    filter: "react, frontend"
  - type: "github-trending"
    languages: ["python", "typescript"]
    filter: "match my gaps"
```

```
neocortex feed
  → 拉取所有 feed 的新文章
  → LLM 对比用户 gap 列表，筛选出相关文章
  → 展示推荐列表，用户选择要读的
  → 选中的直接进入 read pipeline
```

"match my gaps" 是关键——利用现有的 profile.gaps 自动判断文章是否值得读。

### 1.3 Neocortex 的护城河

竞品调研也确认了 Neocortex 的独有优势，这些是没有竞品做到的：

| 独有能力 | 最接近的竞品 | 为什么 Neocortex 更好 |
|---|---|---|
| 代码扫描 → 技能画像 | Workera（问卷测评）| 从实际代码分析，不是问卷；对开发者更准确 |
| CLI-first 开发者工作流 | Exercism（CLI 练习）| Exercism 只有练习，没有知识管理 |
| Gap → 推荐 → 阅读 → 追踪 → 再推荐 闭环 | 无 | 没有竞品打通完整闭环 |
| 学习路径依赖图（step + depends_on）| Codecademy（课程有顺序）| Codecademy 是固定课程，Neocortex 是动态个性化路径 |
| Socratic Probe 渐进校准 | CodeSignal（AI 导师）| CodeSignal 用于评测，不用于日常学习中的被动校准 |
| 概念编译 + gap 联动（Phase 1 后）| Atomic（wiki 综合）| Atomic 不关联技能画像，只是通用 wiki |

---

## 2. 理论基础：Hidalgo 知识三定律

> 来源：César Hidalgo, *The Infinite Alphabet* (Penguin Random House, 2025)
> 播客：Machine Learning Street Talk, 2025-12-28, ~90 min
>
> Hidalgo 是图卢兹经济学院教授，MIT 集体学习中心前主任，2018 年复杂系统拉格朗日奖得主。
> 他为知识的增长、扩散和价值估算建立了一套类物理定律的分析框架。

### 2.1 知识不是可以随意复制的文件

**非竞争性 + 非同质性**

Paul Romer（2018 诺奖）说知识是 non-rival 的——我教你一首歌自己还是会唱。
Hidalgo 补充了第二个属性：non-fungible（非同质性）。知识由无数独特的"字母"组成，
一张永远在扩展的字母表。一个人/团队拥有哪些字母、如何组合，决定了能力边界。

**书本没有知识，团队才有**

> "书只是思想的存档记录，知识只有在被人或团队'激活'时才能工作。"

制造一架客机的知识没有任何个体能完整持有，它分布在人、机器、手册、经验和社会关系构成的网络中。
卡内基梅隆的 Linda Argote 的组织学习模型：组织是连接人、工具和概念的网络，学习来自网络的重新配置。

→ **对 Neocortex 的启示**：笔记是存档，不是知识。概念网络 + 定期复习 + 实践练习 = 激活。
  这验证了 read → compile → review → exercise 闭环的设计方向。

**三层知识**

Hidalgo 用侦探小说做类比：
1. **事实性**（Factual）：墙上有弹孔，昨晚七点有通电话。传播成本极低。
2. **概念性**（Conceptual）：侦探把线索串成完整故事，解释动机和因果。
3. **程序性**（Procedural）：把血迹送去 DNA 实验室。经济中大部分有价值的知识是这种——
   面包师知道怎么做面包，修理工知道怎么修发动机。这些知识不来自科学验证，但让世界运转。

→ **对 Neocortex 的启示**：当前闪卡 prompt 说"不要纯记忆题"，但没有显式区分层次。应该按三层分别生成：
  - 事实层：1-2 张快速回忆卡（"这是什么"）
  - 概念层：2-3 张因果推理卡（"为什么 / 怎么选"）
  - 程序层：exercises.md（"在你的项目中怎么用"）
  复习时用户能看到自己在哪个层次卡住。

### 2.2 知识的时间定律：学习曲线 → 摩尔曲线

**学习曲线**

1916 年 Thurstone 的打字学习数据：速度对累积练习量呈幂律，开头飞快然后递减。
1936 年 Wright 在飞机制造成本中发现同样的关系。
1965 年 Rapping 用二战自由轮船数据证明：工时下降纯粹来自经验，跟技术升级和资本投入无关。

**架构创新与破坏性创新**

Henderson 的架构创新：看似微小的改动杀死巨头。Barnes & Noble → Amazon 的知识距离远大于"直接寄给消费者"这一步。

Christensen 的破坏性创新：单条学习曲线趋平，但多代技术更替让整体呈指数。
摩尔定律 = 多条 S 曲线的包络线。新技术刚出现时比现有技术差（晶体管收音机、数码相机），
但天花板更高，交叉窗口就是颠覆发生的时刻。

Bloom 指出：维持指数增长需要越来越大的团队。第一个晶体管 3 个人做出来，今天设计一颗芯片需要庞大的协作体系。

### 2.3 知识衰变——Neocortex 最该关注的定律

**衰变速度远超直觉**

> 自由轮船数据：知识月衰减 3%-6%，年化约 50%。

宝丽来的故事：2008 年停产，Florian Kaps 花 310 万美元买下最后一座工厂的全部设备，
签了十年租约，雇回了"the A team, the star team"。设备在，厂房在，人也在。
结果 2010 年第一批胶片色彩严重偏移，化学药剂从封口处渗漏，照片几周内褪色。
花了十年才接近 1970 年代的品质。

原因：关键化学原料已停产，供应链断了，原始配方无法复刻。
衰变的对象不仅是人脑中的经验，还有整个协作网络和供应体系。

NASA 登月同理：Saturn V 图纸还在，计算机强了两万倍，但工厂拆了，模具回收了，
技师全退休了。50 年没有登月级别的工程实践，知识就衰变了。超过 900 亿美元至今没把人送回月球表面。

日本伊势神宫每 20 年重建一次：表面维护建筑，实际维护建造技术。每次重建在训练下一代工匠。
欧洲保护原始结构，伊势保存知识本身。

→ **对 Neocortex 的启示**：

  **信心衰减公式**：
  ```
  monthly_decay = 0.056  # 年衰减 50% → 月衰减 ~5.6%
  new_confidence = confidence * (1 - monthly_decay) ^ months_since_last_review
  ```

  当 confidence 降到阈值以下：
  - lint 发出警告："概念 X 已 60 天未复习，confidence 从 0.8 降到 0.55"
  - review 自动将相关闪卡提升优先级
  - digest 周报显示"本周 3 个概念进入衰变危险区"

  复习/新增笔记 → confidence 恢复（不是重置，是 boost）。

### 2.4 知识的空间扩散

知识扩散受两重约束：

**地理距离**：1975 年美军撤出西贡后越南人被随机安置到美国各地，1995 年禁运解除后
当年接收了更多越南移民的州与越南贸易量更大。人走到哪里，知识扩散到哪里。

**知识的几何结构**（产品空间 / 相关性原则）：每个产业是一棵树，国家是住在树上的猴子，
经济发展就是跳到相邻的树上。二战后意大利被禁止造飞机，航空工程师 D'Ascanio 设计了 Vespa 踏板摩托。
日本川西航空、德国亨克尔也从航空转向轻型车辆——因为摩托车和飞机在产品空间中是邻居。

移民打破近距离约束：本地创业者擅长短距离跳跃，移民更擅长帮经济体进入不相关领域。
美国 1970 年代以后的诺贝尔奖得主中 60%-70% 出生于国外或有移民经历。

→ **对 Neocortex 的启示**：学习路径的 `depends_on` 就是产品空间中的邻近关系。
  recommender 应该区分"短距离跳跃"（强化已有领域的深度）和"长距离跳跃"（探索不相关领域），
  并在推荐中显式标注。lint 的"建议探索"检查已经在做类似的事。

### 2.5 知识的载体与价值

**最低运载量（Minimum Viable Payload）**

威尔士企业家 John Hughes 50 多岁时获得在乌克兰开发煤铁的特许权，装了数艘船、
一百多名工人和全套设备。三年后产出生铁，建起苏联最主要的钢铁产区之一。
这座城市最初叫 Yuzovka（Hughes 的俄语音译），今天叫顿涅茨克。

Samuel Slater 14 岁进入英格兰纺棉工厂当学徒，21 岁时假扮农民逃到美国，
一年内在罗德岛建成美国第一座成功的水力纺棉厂，启动美国工业革命。
此前 Pawtucket 的人根据口述仿造完全失败——必须有亲身操作经验的人到场才行。

→ **对 Neocortex 的启示**：知识转移需要"最低运载量"。单篇笔记不够，
  需要概念条目 + 来源笔记网络 + 关系图 + 闪卡 + 练习 = 完整的知识包。
  这验证了概念编译的设计——一个概念不是一个文件，是一个包含多个来源、
  关联概念和实践练习的网络。

**无限字母表与复杂性预测**

如果知识是无限字母表，评估经济潜力就是数字母。Hidalgo 从出口数据构建"国家×产品"矩阵，
提取复杂性排序指标，发现该指标能预测经济增长。

→ **对 Neocortex 的启示**：用户的"概念数量 × 掌握深度"可以构建类似的复杂性指标。
  profile 命令可以展示一个"知识复杂性分数"，比单纯列技能更有信息量。

### 2.6 LLM 与知识

> "Is it because the LLM has knowledge? Is it because I have knowledge?
>  Or is it because we are wiser when we are together?"
>
> — Hidalgo

他认为"LLM 拥有知识吗"这个问题问错了。知识是集体现象，重要的是 LLM 是否提升了
人类的集体学习能力。他搬到法国后用 LLM 了解当地税法，见会计师时能问出更好的问题。

→ **对 Neocortex 的启示**：这正是 Neocortex 的产品哲学——AI 不替代学习，而是加速学习。
  "AI 加持而非替代"（来自 Gumloop 创始人访谈）+ "只自动化你理解的东西" = Neocortex 的定位。

---

## 3. 未来方向：Agent 式知识检索

> 来源：Mintlify ChromaFs 工程博客（2026-04），@dotey 转述
> 526 赞 / 745 收藏，HN 热议

### 3.1 Mintlify 的方案

Mintlify 给 AI 文档助手造了一套假文件系统 ChromaFs：AI 以为自己在用 grep/cat/ls 浏览文件，
实际每个命令被拦截翻译成 Chroma 数据库查询。

- 会话启动从 46 秒降到 100 毫秒
- 月均 85 万次对话，年省 7 万美元计算成本
- grep 最难虚拟化：先用元数据粗筛 → 批量预取到缓存 → 内存精确匹配
- 权限控制：初始化时裁剪文件树，没权限的路径 AI 连路径都看不到
- 所有写操作返回"只读文件系统"错误，无状态

### 3.2 更深层的洞察

HN 讨论中的关键观点：

> **RAG ≠ 向量检索。RAG 里的 R 是 Retrieval，可以是任何方式：全文搜索、SQL、甚至翻电话簿。
> 把 RAG 绑死在向量数据库上，是早期技术路径的惯性。**

RAG 概念流行时 LLM 还不太会用工具，向量检索是最省事的方案。
现在模型的工具调用和推理能力上来了，让 AI 自己决定用什么方式找信息，比预设检索管道更灵活。

这与 Claude Code 的做法相通：不是把所有信息预检索好喂给模型，
而是给模型一套探索工具，让它自己决定看什么、怎么找。

### 3.3 对 Neocortex 的启示

**当前状态**：`ask`/`chat` 加载 INDEX.md（≤2000 字符）作为上下文注入 system prompt。
这是"预检索"模式——在 LLM 调用前就决定了它能看到什么。

**当前够用的原因**：知识库规模小（~100 篇笔记），INDEX.md + 概念条目的三层导航
（目录 → 摘要 → 原文）在这个规模下足够精准。

**未来方向**（知识库 500+ 笔记后考虑）：

把 `ask`/`chat` 改造为 **Agent + 工具调用模式**：

```
用户提问
  → LLM 决定需要什么信息
  → 调用工具：search(query) / read_concept(name) / read_note(filename) / list_concepts(domain)
  → 拿到结果后可能再调用更多工具
  → 综合所有信息生成回答
```

工具定义（类似 Mintlify 的假文件系统，但用 Neocortex 自己的数据层）：

| 工具 | 对应 | 说明 |
|---|---|---|
| `search(query)` | FTS5 / hybrid search | 全文搜索笔记和概念 |
| `read_concept(name)` | concepts/{slug}.md | 读取概念条目全文 |
| `read_note(filename)` | notes_dir/{filename} | 读取笔记全文 |
| `list_concepts(domain?)` | INDEX.md 的概念列表 | 列出所有或某领域的概念 |
| `get_flashcards(concept)` | .flashcards/*.json | 获取某概念的闪卡 |

好处：
- LLM 按需读取，不浪费上下文窗口
- 支持多步推理（先搜索 → 发现线索 → 深入读取）
- 知识库再大也不受 system prompt 长度限制

实现路径：
- 使用 Anthropic/OpenAI 的 function calling / tool use API
- 现有 `LLMProvider.chat()` 需要扩展支持 tools 参数
- 或者用简单的 ReAct 循环（不依赖原生 tool use）

**触发条件**：当 INDEX.md 超过 4000 字符，或 `ask` 的回答质量明显下降时，启动这个改造。
在此之前，当前方案成本更低、更简单。

---

## 4. 竞品深潜：tutor-skills 与 Obsidian Agent 生态

> 来源：Obsidian skills 生态调研（2026-04）
> 相关项目：kepano/obsidian-skills、RoundTable02/tutor-skills (586⭐)、
> RAIT-09/obsidian-agent-client、Claudian 插件

### 4.1 tutor-skills — 最接近的竞品

**定位**：Claude Code skill，把 PDF/文档/代码库转为 Obsidian 学习 vault。

**9 阶段流水线**：
1. 源文件发现（PDF/TXT/MD/HTML/EPUB）
2. 内容分析 → 层级主题结构 + 依赖映射
3. 标签规范（英文 kebab-case）
4. Vault 目录结构（编号文件夹按主题）
5. Dashboard 生成（MOC + 速查 + 易错点）
6. 概念笔记（对比表 + ASCII 图 + 模式识别）
7. 练习题（每主题 8+ 题，fold callout 做主动回忆）
8. 交叉链接（wiki-link）
9. 自审（质量检查清单）

**4 种复习模式**：诊断 / 弱点强化 / 选章节 / 困难模式
**5 级掌握度**：Unmeasured → Weak → Fair → Good → Mastered
**代码库模式**：扫描代码生成 onboarding 学习材料（不是画像，是教材）

### 4.2 对比分析

**tutor-skills 有而 Neocortex 缺的**：

| 功能 | 可借鉴之处 |
|---|---|
| Dashboard（MOC + 速查 + 易错点） | INDEX.md 可以增加 Quick Reference 和 Exam Traps 区块 |
| 4 种复习模式 | review 命令可以加 `--mode diagnostic/drill/hard` |
| 5 级掌握度 | gap→learning→known 太粗，可以细化为 5 级 |
| Fold callout 主动回忆 | 笔记中嵌入 Obsidian callout 做 inline 复习，不依赖外部 JSON |
| 代码库 onboarding 模式 | scan 扫描后除了画像还可以生成学习材料 |
| 易错点识别 | 让 LLM 在笔记生成时标注常见误区 |

**Neocortex 有而 tutor-skills 缺的（护城河）**：

| 功能 | 为什么对手难做 |
|---|---|
| 代码扫描 → 个性化技能画像 | 需要 scanner + profile + gap 同义词整套基础设施 |
| 闭环推荐系统 | recommend → read → track → re-recommend 跨命令状态追踪 |
| 知识衰减（Hidalgo 模型） | 需要 decay.py + confidence 时间衰减 + SM-2 联动 |
| RSS + 主动研究 | feed + research 命令 + ddgs 搜索 |
| 多 LLM 提供商 | Claude/OpenAI/Gemini/兼容层，tutor-skills 只能用 Claude Code |
| 概念编译 + 语义链接 | compiler + fastembed 向量自动链接 |

### 4.3 可借鉴的改进

**短期（改动小，价值高）**：

1. **review --mode**：增加诊断模式（随机抽查覆盖所有概念）和弱点强化模式（只复习 struggling 概念的卡）
2. **掌握度细化**：gap → weak → fair → good → mastered（5 级），与 confidence 数值对应
3. **易错点**：在 `generate_flashcards` 的 prompt 中让 LLM 额外输出 1-2 个 "common mistakes"

**中期**：

4. **Dashboard 增强**：INDEX.md 增加 Quick Reference（每个概念一行速查）和 Exam Traps（常见误区汇总）
5. **代码库学习模式**：`neocortex scan --learn` 从扫描结果生成该项目的学习材料（架构解释、关键模式、入门练习）

**长期**：

6. **Obsidian Callout 内嵌复习**：在笔记中直接生成 `> [!question]- Q` 折叠 callout，
   用户在 Obsidian 中阅读时就可以自测，不需要单独跑 review 命令

### 4.4 Obsidian 生态集成路径

当前 Neocortex 是独立 CLI。未来有两条集成路径：

**路径 A：做成 Agent Skill**
- 把 Neocortex 核心功能封装为 Agent Skills 规范（agentskills.io）
- 用户通过 `npx skills add neocortex` 安装
- 在 Claude Code / Cursor / Windsurf 中直接使用
- 好处：零安装摩擦，借用 Agent Client Plugin 在 Obsidian 中运行

**路径 B：做成 Obsidian 插件**
- 把核心逻辑移植为 TypeScript Obsidian 插件
- 好处：纯 Obsidian 体验，不依赖外部 CLI
- 代价：重写工作量大，放弃 Python 生态（LLM SDK、fastembed 等）

**推荐**：先走路径 A（Skill 化），成本低，覆盖面广。路径 B 等产品验证后再考虑。

---

## 5. 竞品深潜：scholar-skill 与分级阅读

> 来源：EESJGong/scholar-skill (101⭐)，Obsidian 学术研究深度解构系统
> Axton 画图 Skills：mermaid-visualizer、obsidian-canvas-creator（chaye7417）

### 5.1 scholar-skill — 学术阅读的分级系统

**L1-L3 分级阅读**：

| 级别 | 时间 | 覆盖范围 | 输出 | 适用 |
|---|---|---|---|---|
| L1 快速筛选 | 5 分钟 | 标题、摘要、图表 | 一句话 + P0/P1/P2 优先级 | 海量论文筛选 |
| L2 标准阅读 | 45 分钟 | 引言、方法、实验、结论 | 3-5KB 笔记 + 5-8 条记忆 | 日常论文处理 |
| L3 精读 | 2.5 小时 | 全文 + 补充材料 | 10-15KB 笔记 + 知识升级 + 程序规则 | 核心论文 |

**三层反思体系**：
- L1 反思（单篇后）：检查理解、疑问、下一步行动
- L2 反思（周度）：知识增长、缺失链接、研究方向、风险评估
- L3 反思（月度）：知识演化、方向调整、认知修正

**人类确认机制**：关键事项（新 MOC、核心论文、认知冲突、方向调整）进入 Inbox 等待人工裁决，不自动执行。

**异步任务**：L3 精读需 2.5 小时，依赖 `durable-task-runner` 做进度追踪、中断恢复。

### 5.2 Axton 画图 Skills

| Skill | 功能 | 与 Neocortex 关系 |
|---|---|---|
| mermaid-visualizer | 文本→Mermaid 图表，自动选择图表类型 | 低，我们已有 Mermaid 生成 |
| obsidian-canvas-creator | 文本→.canvas 文件，支持 MindMap/Freeform 布局 | 中，可作为 `map` 命令的 canvas 输出格式 |
| excalidraw-diagram | 手绘风格 Excalidraw 图表 | 低，不是我们方向 |

### 5.3 对 Neocortex 的启示

**启示 1：分级阅读深度**

当前 `read` 命令不分级，一律走完整流程（outline → notes → flashcards → exercises → compile）。
应该支持分级：

| Neocortex 级别 | 对应 scholar-skill | 流程 | 输出 |
|---|---|---|---|
| `--depth quick` | L1 | 只 fetch + LLM 一句话摘要 + 优先级 | 一行摘要，不生成笔记 |
| `--depth standard`（默认） | L2 | 现有完整流程 | 笔记 + 闪卡 + 练习 + 编译 |
| `--depth deep` | L3 | 现有 `--deep`（八维解剖）+ 额外深度 | 深度笔记 + 更多闪卡 + 关系分析 |

`quick` 模式的关键价值：用户可以快速筛选 `feed` 或 `research` 推荐的文章，
决定哪些值得 standard/deep 阅读。

**启示 2：反思周期**

当前：单篇后有 feedback（太简单/刚好/太难），周度有 `converge`/`digest`。
缺失：月度反思。

应新增 `neocortex reflect` 命令或在 `digest --days 30` 时自动触发月度反思：
- 这个月学了什么 vs 计划学什么 → 偏差分析
- 哪些认知发生了更新（新笔记推翻了旧概念）
- 下个月的方向建议

**启示 3：认知冲突实时检测**

当前 `lint` 有矛盾检测但需手动运行。应该在 `compile_note` 时就检测：
新笔记的核心观点是否与已有概念条目矛盾。如果检测到，在终端警告并在概念条目中标注。

---

## 6. 理论基础：Tulving 记忆系统与 Neocortex 的映射

> 来源：Tulving (1972) 记忆分类框架 + Claude Code 泄露代码的记忆模块分析
> 对比：Claude Code、LangMem、Mem0、Zep、EverMemOS、MemOS、OpenClaw

### 6.1 Tulving 三层记忆

Endel Tulving (1972) 将记忆分为三类：

| 类型 | 定义 | 问题 |
|---|---|---|
| **情境记忆**（Episodic） | 我经历了什么 | 记录过去 |
| **语义记忆**（Semantic） | 我知道什么 | 提炼规律 |
| **程序记忆**（Procedural） | 我会做什么 | 指导行动 |

三者构成循环：**经历 → 知识 → 技能 → 新的经历**。

情境记忆的细节会逐渐遗忘，压缩为语义记忆（规律和知识）。
语义记忆逐渐内化为程序记忆（"知道怎么做"的能力）。
程序记忆指导行动，产生新的经历（情境记忆）。

### 6.2 Claude Code 的记忆实现

| 层级 | Claude Code 的做法 |
|---|---|
| 情境记忆 | 每轮对话以 JSONL 格式存储；SessionMemory 做实时蒸馏 |
| 语义记忆 | 轮次结束后 fork 子 Agent（extractMemories）提取持久化内容，写入带 YAML 头的 MD 文件 |
| 程序记忆 | `feedback` 记忆类型：记录负反馈（不要做什么）和正反馈（确认做对的），兼顾正负 |
| 记忆巩固 | `autoDream` 机制：后台整合修剪，碎片重新组织、合并、更新 |

**Claude Code 的关键设计**：正负反馈兼顾。多数系统只记纠正（负反馈），导致 Agent 越学越保守。
Claude Code 同时记录"做对了"（正反馈），让 Agent 保持行动力。

**Claude Code 的不足**：
- 无语义化召回（用 LLM 扫 metadata 代替向量检索，上限 200 文件）
- 遗忘策略粗（24 小时 or 5 轮对话触发整合）
- 无关联网络（记忆是孤立文件）

### 6.3 OpenClaw 的记忆设计

不追求全量记忆，优先解决"记忆什么时候该被用"。

三层收敛：全局层 → 工作区层 → 任务层，只在必要时才把上下文拉进来。

> "记忆不是资产，正确使用记忆的能力才是。"

设计侧重于**重建临时的记忆网络**，而非永久存储一切。

### 6.4 Neocortex 与 Tulving 框架的映射

Neocortex 无意中实现了 Tulving 三层记忆的完整循环：

| Tulving | Neocortex 对应 | 具体实现 |
|---|---|---|
| **情境记忆** | clips + 阅读历史 | `clip` 捕获碎片，`read` 记录 learning_history |
| **语义记忆** | concepts + INDEX.md | `compile` 从笔记提取概念，生成知识图谱 |
| **程序记忆** | exercises + procedural flashcards | `read` 生成实践练习，`review` 强化程序记忆 |

| Tulving 循环 | Neocortex 对应 | 具体实现 |
|---|---|---|
| 情境 → 语义（压缩） | 碎片 → 综合笔记 | `inbox --synthesize` 聚类综合 |
| 语义 → 程序（内化） | 概念 → 技能 | `review`（SM-2 复习）+ confidence 衰减 |
| 程序 → 新情境（行动） | 练习 → 新阅读 | exercises 引导实践 → 产生新问题 → 新的 `read` |
| 记忆巩固（autoDream） | 定期整合 | `daily`（浮现）+ `lint`（健检）+ `digest`（反思） |

### 6.5 Neocortex 相比 Claude Code 的优势和不足

**Neocortex 做到了而 Claude Code 没做的**：

| 能力 | Neocortex | Claude Code |
|---|---|---|
| 语义化召回 | FTS5 + fastembed 向量检索 | LLM 扫 metadata（200 文件上限） |
| 关联网络 | 概念图谱 + wikilinks + 关系卡 | 孤立文件 |
| 知识衰减 | Hidalgo 模型（月衰减 5.6%） | 无（或粗粒度） |
| 冲突检测 | 声明提取 + 三级分类 + 信念追踪 | 无 |
| 碎片→知识循环 | clip → daily 浮现 → synthesize | 无 |

**Claude Code 做到了而 Neocortex 可以借鉴的**：

| 能力 | Claude Code | Neocortex 现状 | 可改进 |
|---|---|---|---|
| 实时蒸馏 | SessionMemory 边对话边整理 | 无（read 完才处理） | 中期 |
| 正反馈记录 | feedback 类型兼顾正负 | review 只记分数，不区分正负模式 | 可加 |
| autoDream 后台整合 | 自动触发 | `daily` 需手动运行 | 可做定时任务 |

---

## 7. Tulving 记忆框架深入研究

> 来源：Tulving (1972, 1985, 1995, 2002) 原始论文 + 记忆巩固研究综述
> 关键数字均有实验文献支撑

### 7.1 三层记忆的完整模型

Tulving 的框架不只是 1972 年的两分法，经历了多次迭代：

| 年份 | 贡献 | 核心概念 |
|---|---|---|
| 1972 | 情境 vs 语义记忆 | 两种不同的存储系统 |
| 1985 | 加入程序记忆 + 层级关系 | 程序→语义→情境，逐层叠加 |
| 1995 | SPI 模型 | 串行编码、并行存储、独立提取 |
| 2002 | 心理时间旅行（Chronesthesia） | 情境记忆不只是"回放"，是"模拟引擎" |

**SPI 模型**（Serial-Parallel-Independent）是最关键的：

- **S（串行编码）**：信息自下而上进入——先程序处理（感知/运动）→ 再语义编码（提取意义）→ 最后情境编码（绑定个人上下文）。**不经过语义处理就无法形成情境记忆。**
- **P（并行存储）**：编码后三个系统独立并行存储各自的表征，互不干扰。
- **I（独立提取）**：三个系统可以独立检索。你可以回忆一个事实（语义）而不记得何时学的（情境）；可以骑自行车（程序）而不知道骑车的原理（语义）。

**2002 年的心理时间旅行**：情境记忆不只是"录像机"，而是**模拟引擎**——同一个系统既能回忆过去，也能想象未来场景。海马体在"回忆过去"和"想象未来"时同等活跃。

→ **对 Neocortex 的启示**：`daily` 的浮现不应只展示"你过去存了什么"，还应支持"基于你已知的，未来你可能需要什么"——这正是情境记忆的模拟功能。

### 7.2 编码特异性原则

Tulving & Thomson (1973)：

> 记忆检索的效果取决于检索线索与编码时存储的上下文之间的匹配程度。

经典实验：学习"钢琴"时如果上下文是"那人搬起了钢琴"（重物），那么检索线索"重的东西"比"乐器"更有效——即使"乐器"在语义上更相关。

→ **对 Neocortex 的启示**：
- clip 捕获时存储的 `related_concepts`、`relevance`（"对你意味着什么"）就是编码上下文
- 检索时不应只用语义相似度（向量搜索），还应考虑捕获时的上下文（"你当时在学什么"）
- frontmatter 中的 `related_gaps` 字段就是编码上下文的一种形式

### 7.3 记忆巩固：情境→语义的压缩机制

**互补学习系统理论**（McClelland et al., 1995）：

- 海马体：快速学习具体事件（模式分离，稀疏编码）
- 大脑皮层：缓慢学习统计规律（重叠分布表征）
- 巩固 = 海马体在休息/睡眠时"重播"事件，逐步训练皮层

**睡眠与巩固**：
- 一晚睡眠比等量清醒时间提升记忆保持 20-30%（Walker & Stickgold, 2006）
- 慢波睡眠中海马体尖波涟漪重播最近事件 → 驱动语义巩固
- 睡眠优先巩固情绪显著的记忆
- **睡眠促进洞察**——从事件中提取隐藏规则和模式（Wagner et al., 2004）

→ **对 Neocortex 的启示**：`daily` 命令就是系统级的"睡眠巩固"——从碎片中发现模式、
建立连接、识别趋势。最佳运行时机是一天的开始（隔夜巩固后）。

### 7.4 再巩固——记忆每次被提取时都会改变

**Nader et al. (2000) 里程碑发现**：

当一个已巩固的记忆被重新激活（回忆），它会暂时回到不稳定状态。
必须再次巩固（再巩固），否则可能被削弱或修改。提取后有 ~6 小时的可修改窗口。

**关键含义**：
- 记忆不是固定录像——每次提取都是重建，重建后的版本成为新的记忆
- 带有新上下文信息的提取可以修改原始记忆（这是知识更新的机制）
- 预测误差驱动更新——当期望与现实不匹配时触发再巩固

→ **对 Neocortex 的启示**：
- 笔记应该是活的——`daily` 浮现旧碎片时附带知识库变化，就是在创造再巩固条件
- `inbox --synthesize` 将碎片综合为新笔记 = 再巩固 + 知识更新
- 冲突检测（claims.json）= 识别预测误差 → 触发信念修正

### 7.5 关键数字

| 指标 | 数值 | 来源 |
|---|---|---|
| 无意义材料遗忘速度 | 1 小时忘 56%，1 天忘 66% | Ebbinghaus (1885) |
| 有意义材料保持率 | 3 年后 ~60%，25 年后 ~40% | Bahrick (1984) |
| 无复习时语义存活率 | 原始信息的 10-20% | Brewer (1988) |
| 最佳间隔比例 | 目标保持期的 10-20% | Cepeda et al. (2008) |
| 稳定所需成功检索次数 | 5-7 次间隔递增 | Karpicke & Roediger (2008) |
| 睡眠巩固增益 | 比清醒期高 20-30% | Walker & Stickgold (2006) |
| 工作记忆容量 | ~4 个组块 | Cowan (2001) |
| 测试效应优势（1 周后） | 56% vs 42% 保持率 | Roediger & Karpicke (2006) |
| 再巩固窗口 | 激活后 ~6 小时 | Nader et al. (2000) |

**最佳间隔时间表**（Cepeda et al., 2008）：

| 目标保持期 | 首次间隔 | 后续间隔 |
|---|---|---|
| 1 周 | 1 天 | — |
| 1 月 | ~1 周 | ~2 周 |
| 3 月 | ~2 周 | ~1 月 |
| 1 年 | ~3-4 周 | 每次 ×2 递增 |
| 5+ 年 | ~2 月 | 每次 ×2-3 递增 |

经验法则：**最佳间隔 ≈ 目标保持期的 10-20%**。

### 7.6 对 Neocortex 的 10 条设计原则

基于 Tulving 框架 + 记忆巩固研究：

1. **上下文丰富的捕获**：存储不只是内容，还有获取上下文（编码特异性）
2. **主动优于被动**：生成和检索优于重读（测试效应 + 生成效应）
3. **间隔，不集中**：间隔递增的复习（间隔效应）→ SM-2 已实现
4. **交叉主题**：复习时混合不同领域（交叉效应）→ 可优化推荐
5. **巩固期**：批量处理提取模式 = 模拟睡眠巩固 → `daily` + `compile`
6. **活的笔记**：笔记在每次访问时演化（再巩固）→ 概念条目更新
7. **难度校准**：让检索有挑战但可达（适度困难）→ calibration 已实现
8. **多检索路径**：丰富元数据创造多条访问路线（编码变异性）→ frontmatter 标签
9. **遗忘是功能性的**：修剪低价值信息减少干扰 → confidence 衰减已实现
10. **情境→语义是目标**：系统应主动帮用户将经历转化为持久知识 → 整个 pipeline

### 7.7 Neocortex 现有架构与 Tulving 的匹配度

| 原则 | 匹配度 | 说明 |
|---|---|---|
| 上下文捕获 | ⭐⭐⭐ | clip 有 relevance/related_concepts，但缺"用户当时在做什么" |
| 主动检索 | ⭐⭐⭐⭐ | review 闪卡是纯检索练习，Socratic probe 也是 |
| 间隔复习 | ⭐⭐⭐⭐⭐ | SM-2 完整实现 |
| 交叉主题 | ⭐⭐ | 复习按笔记分组，没有跨领域交叉 |
| 巩固期 | ⭐⭐⭐ | compile + daily，但不是自动后台运行 |
| 活的笔记 | ⭐⭐⭐ | 概念条目更新，但普通笔记不会演化 |
| 难度校准 | ⭐⭐⭐⭐ | calibration + level_offset |
| 多检索路径 | ⭐⭐⭐⭐ | FTS5 + 向量 + frontmatter + wikilinks |
| 功能性遗忘 | ⭐⭐⭐⭐ | confidence 衰减 + lint 健检 |
| 情境→语义 | ⭐⭐⭐⭐⭐ | clip → synthesize → concepts 完整管线 |

**主要差距**：交叉主题复习（review 应混合不同领域的卡片）和自动后台巩固（daily 需手动）。

---

