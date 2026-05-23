# Neocortex 技术架构

> 本文档记录已实现的技术架构设计。产品方向见 [VISION.md](VISION.md)，竞品分析和理论基础见 [RESEARCH.md](RESEARCH.md)。

---

## 1. 现状与差距

### Neocortex 已有

| 能力 | 对应模块 | 状态 |
|---|---|---|
| 内容摄取（URL/PDF/EPUB/微信） | `reader/fetcher.py` | ✅ |
| 个性化笔记生成 | `reader/teacher.py` | ✅ |
| Obsidian 兼容输出 | `cmd_read.py` (frontmatter + Mermaid) | ✅ |
| 全文搜索 + 向量检索 | `search.py` (FTS5 + fastembed) | ✅ |
| 个性化问答 | `asker.py` (ask/chat) | ✅ |
| 闭环追踪 | `tracker.py` + `config.py` | ✅ |
| 学习路径推荐 | `recommender.py` | ✅ |
| 认知收敛 | `converger.py` | ✅ |
| 视觉卡片 | `reader/card.py` | ✅ |
| 技能校准 | `prober.py` + calibration | ✅ |

### Karpathy 工作流的实现状态

| 能力 | 状态 | 对应模块 |
|---|---|---|
| **概念编译层** — 跨笔记聚合为互联的概念 wiki | ✅ 已实现 | `compiler.py` + `cmd_compile.py` |
| **知识索引** — LLM 自维护的语义目录 | ✅ 已实现 | `compiler.py`（INDEX.md 生成） |
| **问答沉淀** — ask/chat 输出回流知识库 | ✅ 已实现 | `cmd_knowledge.py`（insights/） |
| **知识健康检查** — 矛盾检测、覆盖分析、连接发现 | ✅ 已实现 | `linter.py` + `cmd_lint.py`（7 项检查） |
| **丰富输出** — 概念图可视化、学习周报 | ✅ 已实现 | `cmd_visualize.py`（map + digest） |

---

## 2. 设计目标

1. **知识 > 笔记**：单篇笔记是原材料，概念条目才是知识资产
2. **增量编译**：每次 `read` 后自动更新受影响的概念，不需要手动触发全量编译
3. **零手工维护**：INDEX.md、概念条目、双向链接全由 LLM 写和维护，用户只需阅读
4. **与已有系统深度集成**：概念 = gap 的知识化身，编译结果直接驱动推荐和校准
5. **Obsidian 原生**：所有产出都是纯 Markdown + wikilinks，Obsidian 图谱视图直接可用
6. **渐进增强**：不改变现有工作流，新功能是叠加而非替换

---

## 3. 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  入口层                                                            │
│  CLI（Typer）            HTTP / WebSocket（FastAPI，Sprint 0）     │
│  cmd_*.py                cmd_serve.py → server/app.py             │
└──────────┬───────────────────────────┬───────────────────────────┘
           │                           │
           │              ┌────────────▼────────────┐
           │              │  services/*.py            │
           │              │  纯函数包装层（无 Rich/    │
           │              │  Typer）— HTTP/GUI 入口   │
           │              └────────────┬────────────┘
           │                           │
┌──────────▼───────────────────────────▼───────────────────────────┐
│                      用户工作流                                    │
│  read → compile → ask/chat → lint → recommend → read              │
│         ↑ 自动      ↑ 沉淀     ↑ 健康                              │
└──────┬──────────────┬─────────┬───────────────────────────────────┘
       │              │         │
┌──────▼──────┐ ┌─────▼───┐ ┌──▼───────────┐
│   编译引擎   │ │ 沉淀引擎 │ │   健检引擎    │
│ compiler.py │ │ (扩展    │ │  linter.py   │
│             │ │  asker)  │ │  verifier.py │
└──────┬──────┘ └─────┬───┘ └──────────────┘
       │              │
┌──────▼──────────────▼──────────────────────┐
│              知识库（笔记目录）                │
│  *.md          笔记                          │
│  concepts/     概念条目                       │
│  insights/     问答沉淀                       │
│  INDEX.md      语义目录                       │
│  _reports/     lint/verify 报告               │
└────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────┐
│   已有系统                       │
│  gap_progress.json              │ ← 概念证据驱动 gap 状态迁移
│  recommendations.json           │ ← 概念覆盖率影响推荐
│  neocortex.sqlite               │ ← FTS5 + 向量索引
│  profile.json                   │ ← 概念掌握度更新 skills
│  server.{pid,port,token}        │ ← GUI 服务发现（serve 运行时）
└─────────────────────────────────┘
```

**服务层分工**：CLI 路径（`cmd_*.py`）直接调引擎；HTTP 路径走 `services/*.py`
（去掉 Rich/Typer/Prompt，便于 server 复用）。两条路径共享同一组底层引擎
（clipper/compiler/asker/...）。详见 [SERVER.md](SERVER.md)。

### 目录结构变化

```
~/Documents/Neocortex/          （笔记目录，现有 + 新增）
├── INDEX.md                    # 新增：LLM 自维护的知识地图
├── *.md                        # 现有：阅读笔记（不动）
├── concepts/                   # 新增：概念条目
│   ├── event-sourcing.md
│   ├── cqrs.md
│   └── ...
└── insights/                   # 新增：问答沉淀
    ├── 2026-04-03-crdt-vs-ot.md
    └── ...
```

---

## 4. 已交付模块速查

§1–§3 描述的设计在 2026-04 至 2026-05 期间陆续落地。完整模块列表见
[CLAUDE.md](../CLAUDE.md) 的"目录结构"段。下表是核心引擎的现状对应：

| 模块 | 文件 | 状态备注 |
|---|---|---|
| 概念编译 | `compiler.py` + `cmd_compile.py` | 增量 + 全量 + content-hash 缓存 |
| 知识索引 | `compiler.py`（INDEX.md / overview.md 生成） | `kb compile --full` 产 overview.md |
| 问答沉淀 | `cmd_knowledge.py` + `asker.py` | Query 反写自动 save_insight |
| 健康检查 | `linter.py` + `cmd_lint.py` | 8 项检查（孤岛 / 断链 / 陈旧 / 覆盖 / 重复 / 衰减 / 探索 / 低忠实度） |
| 忠实度验证 | `verifier.py` + `cmd_verify.py` | 原子事实分解 + 独立审查员 + 三级深度 |
| 概念图可视 | `cmd_visualize.py` | `kb map` Mermaid + `learn digest` 周报 |
| 视觉卡片 | `reader/card.py` | Playwright 渲染 PNG |
| 服务层 | `services/*.py` + `server/` | HTTP/WS 入口，4 层安全模型，详见 [SERVER.md](SERVER.md) |
| 去重 | `dedup.py` | URL 规范化 + frontmatter 查重（services 层调用） |

---

## 5. 设计文档归档

原始的"详细设计 → 实现计划 → Karpathy 对比"四章节（约 650 行）已归档到
[`_archive/2026-04-compile-lint-design.md`](_archive/2026-04-compile-lint-design.md)，
保留当时的接口签名、prompt 思路与未来设想，供回溯参考。git 历史里也能查到。

下次再有大改造（如 GUI 客户端、远程多用户、知识图谱 embedding 重做）时，
应当**新开一份设计文档**而不是在本架构文档里塞未来计划——本文档只描述现状。
