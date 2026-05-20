# Mac 客户端 + 产品重新定位 提案

> 状态：草稿 v0.6（2026-05-20）
> 用途：捋清"为什么要做客户端"+"它和 Neocortex 现状的关系"+"下一步动作"。**会持续迭代**，所有想法先进这里，不直接动代码。
> 维护：每次讨论后追加 changelog，不要静默覆盖。

---

## 1. 起因：一次坦诚的"自己用不起来"

我自己写的工具，自己用不起来。多轮反馈中暴露的真正痛点（按顺序排）：

1. **CLI 切换成本**：浏览器 → 终端 → 浏览器，看到一条好内容根本不会去做这个动作链。
2. **复制粘贴也不对**：输入摩擦不是问题——**没有反馈才是**。粘完不知道存到哪了，不知道关联了什么，没有"累积感"。
3. **碎片化更不对**：粘贴在 A、阅读在 Obsidian、找东西在 B——三个地方切等于哪个都不用。

→ 真正要的是：**一个窗口**，粘进去 → 立刻看到这条落在哪 / 关联到什么 / 哪个主题在长大。**capture 不是目的，看着知识库在长大才是奖励。**

---

## 2. 还有一个被忽略的场景：家庭知识管理

5 岁半的儿子在学拼音和英语。我看到的儿童教育文章、收藏的资源、给他买书的笔记，**完全没工具可管**。这个需求和"我自己的技能成长"是两套画像，但底层都是"剪藏 + 整理 + 关联 + 找回"。

→ 隐含需求：**多 vault**，至少两个（个人 / 儿子），互不污染。

---

## 3. 这事和市场上已有的笔记产品什么关系？

需要诚实对比，避免重复造轮子。

| 产品 | capture 体验 | AI 关联 | 累积感 | 数据主权 | 多 vault | 与本项目重叠度 |
|---|---|---|---|---|---|---|
| **有道云笔记 @ 微博** | 微博评论 @ 一键存 | ❌（旧）/ 弱 | 低（列表） | ❌ 云端 | ❌ | 入口思路像 |
| **Cubox** | 浏览器扩展 / Share / 邮件 | ✅ 摘要+标签 | 中 | ❌ 云端 | ❌ | **高** |
| **Readwise Reader** | 扩展 / Share / RSS | ✅ 高亮+复习 | 高（每日 review） | ❌ 云端 | ❌ | 中 |
| **Mymind** | 扩展 / Share | ✅ 自动标签 | 高（视觉墙） | ❌ 云端 | ❌ | 中 |
| **Heptabase / Tana / Reflect** | 手动 | ✅ 双链/AI | 中（白板/图谱） | 半本地 | ✅ | 中 |
| **Notion AI** | 通用 | ✅ | 低 | ❌ 云端 | ✅ | 低 |
| **Obsidian + plugins** | 手动 + 插件 | 视插件 | 取决于插件 | ✅ 本地 | ✅ | 高（已是我们的存储后端） |

### 我们的差异点（站得住的）

1. **本地优先存储 + Markdown 原生 + 用户自带 key**：vault 是磁盘上的 Markdown 文件，Obsidian/Finder 直接可见，用户拥有文件；LLM 调用使用用户自己配置的 anthropic/openai/gemini key——**内容处理仍会按用户配置发送到所选 LLM 提供商，不是"完全离线"**，但数据主权和成本可控。
2. **概念图 + 忠实度验证**：现有 `kb compile` 提概念建 wikilink、`kb verify` 用 FACTScore 防 LLM 幻觉。这是**真知识库**做派，不是"AI 摘要 + 标签"就完。
3. **多 vault + 自定义 pipeline**：同一引擎可以跑"个人剪藏"、"开发者技能成长"、"儿童教育策展"等不同模式。
4. **CLI + GUI 同根**：脚本化 / 自动化场景仍然能用 CLI 编排，是云笔记产品给不了的。

### 我们的劣势（要承认的）

1. **Share Extension / 浏览器扩展生态**：Cubox / Mymind 多年迭代，分享按钮无处不在。我们 v1 大概率只有 Mac 主窗口。
2. **手机端**：人家都有 iOS app，我们没有（暂时）。
3. **冷启动孤独**：他们有社群、有官方账号、有持续推荐。我们就一个人用。

→ **结论**：和现有产品**有重叠但不是同一个东西**。重叠在 capture 入口和 AI 整理，差异在"本地优先 + 概念知识库 + 多模式"。值得继续做，但要清醒：**capture 体验上短期追不上 Cubox**，所以差异化必须靠"看着知识在长大"和"完全你自己的"。

---

## 4. Neocortex 现状 vs 这个新需求

### 现状定位（来自 README）
**AI 驱动的个人知识库工具**：
- 轻路径（默认）：`clip` → `kb compile` → `ask / search`
- 重路径（可选）：`read` → `probe / review / recommend`

所以 **Neocortex 已经是"个人知识库工具"了**，技能成长（scan/profile/gap/probe/recommend）只是其中一条增强路径，**不是产品主体**。之前文档把它写成"开发者技能成长追踪工具"是误判，已修正。

代码层面已经包含的能力：
- 剪藏（`clip`，含 `--process` LLM 后处理）
- Markdown vault + frontmatter（Obsidian 兼容）
- FTS5 + fastembed 语义搜索
- 概念编译（`kb compile`，wikilink + 索引 + 语义链接）
- 忠实度验证（`kb verify`，FACTScore）
- 间隔复习（`review`，SM-2）
- 学习推荐（`learn recommend`）

### 新需求的定位
**让"个人知识库"真的能用起来 + 扩到家庭场景**：
- 剪藏微博 / Twitter / 微信公众号 / 任意 URL / 文字（capture 入口）
- 自动关联 + 主题归类（反馈）
- 一眼看到"我在累积什么"（累积感）
- 多 vault（自己 / 家庭 / 儿童教育）

### 重叠 vs 不重叠

```
┌─────────────────────────────────────────┐
│  内核（通用知识库）— 所有场景共用         │
│  · clipper（剪藏 + LLM 后处理）          │
│  · compiler（概念提取 + wikilink）       │
│  · search（FTS5 + fastembed）           │
│  · reader（URL/PDF/EPUB/微信/音频）      │
│  · 存储（Markdown + frontmatter）        │
│  · linter / verifier（健康度）           │
└─────────────────────────────────────────┘
        │                          │
        ▼                          ▼
┌──────────────────┐      ┌──────────────────┐
│ 默认模式: 知识库  │      │ 增强模式: 技能成长 │
│ · 多源剪藏 + 关联 │      │ · scan code      │
│ · 主题策展       │      │ · gap / probe    │
│ · 关联浏览       │      │ · recommend      │
│ · 不必 probe     │      │ · review (SM-2)  │
└──────────────────┘      └──────────────────┘
```

### 是不是同一个产品？

**同一个项目，无需重新定位 README**。README 已经把它定位成知识库工具。这次客户端要做的是**把这个定位真正落地的入口**——CLI 让"个人知识库"使用起来太重，所以入口空缺，导致用户（我）以为 Neocortex"只是技能成长工具"。

**对外名字 / 视觉品牌** 是另一个问题。Neocortex 这个词偏技术，未来对家庭/普通用户的产品形态可能需要重命名。**不阻塞 v1 开发**，但 v1 上线前要决定。

---

## 5. 解决方案：分两层

### 5.1 `clip` 反馈闭环升级（**复用 `--process`，不是从零造**）

**现状**（精确版）：
- `clip` 默认不调 LLM（零成本路径）
- `clip --process` 已经调用 LLM 产出 `summary / auto_tags / related_concepts / relevance / topic`（`cmd_clip.py:299`）
- 保存后控制台已经打印 summary / related concepts / relevance / topic（`cmd_clip.py:357-369`）
- 已索引到 SQLite（`cmd_clip.py:341`）并 link 到 concept pages（`cmd_clip.py:352`）

**改进**（增量，不重复造）：
1. **把 `--process` 升级为默认路径 + 可配置关闭**（`config.json` 加 `clip_default_process: bool`）
2. **新增结构化返回**：函数级 API 返回 `ClipResult { saved_path, concepts[], related_notes[], cluster_growth, ... }`，CLI 打印基于此返回构造，GUI 直接消费
3. **新增 `related_notes` 字段**：基于现有 SQLite FTS5 + concepts 找 top-K 相关已有笔记（标题 + 路径 + 命中原因），当前 `--process` 只有 `related_concepts`（概念名），没有"具体哪些笔记和你这条相关"
4. **新增 cluster 反馈字段**（**关键：冷启动 vault 必须能看见"长大"，否则反馈感失效**）：
   - `existing_cluster_delta: [{concept, count_before, count_after}]` — 这条 clip 让哪些**已有概念页**的 `evidence_count` +1（来自 `_link_clip_to_concepts:cmd_clip.py:665` 现有逻辑）
   - `new_or_pending_clusters: [concept_name]` — `related_concepts` 中**还没有概念页**的（`concepts/<slug>.md` 不存在），GUI 标记为"新主题"
   - **冷启动场景**（重要）：新 vault 第一条 clip 时 `concepts/` 目录根本不存在（`cmd_clip.py:676-678` 直接 return），`existing_cluster_delta` 必然为空——这时 `new_or_pending_clusters` 提供**播种感**，GUI 显示"播下 N 个新主题，等 `kb compile` 长出来"。没有这一拆分，新用户/新 vault 的前 N 条 clip 看起来都是"什么都没发生"
   - **是否在 clip 时直接生成 stub 概念页让 evidence_count 立刻 0→1**？见 Q14（倾向不做，避免污染概念图）
5. **错误回执（Q11 强调"不能静默失败"）**：当前 `except (ValueError, Exception): pass`（`cmd_clip.py:313`）静默吞——结构化返回必须带：
   - `llm_status: ok | skipped_no_key | skipped_user_opt_out | failed`
   - `llm_error: <message>`（当 status=failed）
   - CLI 输出和 GUI Toast 都要显式展示这个状态，让用户区分"未配置 LLM"vs"LLM 调用失败"vs"用户主动关闭"
   - **默认行为（Q11 决策）**：配置了 LLM key 时 `clip` 默认走 `--process` 即时关联；未配置 key 或 `config.json:clip_default_process=false` → `status=skipped_*` 走零 LLM 路径

→ **核心**：现有 `--process` 已经做了大部分活儿，我们只是**把内部状态产品化**，让它能被 GUI 消费、让用户看见"它实际做了什么"。

### 5.2 多 vault 一等公民（**含旧数据迁移**）

**现状盘点**（精确版）：

| 文件 | 当前路径 | 性质 |
|---|---|---|
| LLM key / provider / model / base_url | `~/.neocortex/config.json` | **账号级**（跨 vault 复用） |
| GitHub token | `~/.neocortex/config.json` | **账号级** |
| 语言 | `~/.neocortex/config.json:output_settings.language` | **账号级**（个人偏好） |
| `notes_dir` | `~/.neocortex/config.json:output_settings.notes_dir`（默认 `~/Documents/Neocortex`） | **vault 级**（每个 vault 独立目录） |
| 技能画像 | `~/.neocortex/profile.json` | **vault 级**（只对启用技能成长模式的 vault 有意义） |
| gap 进度 | `~/.neocortex/gap_progress.json` | **vault 级** |
| 推荐记录 | `~/.neocortex/recommendations.json` | **vault 级** |
| 搜索索引 | `~/.neocortex/neocortex.sqlite` | **vault 级**（按 notes_dir 索引内容） |
| 闪卡 / 验证缓存 / 扫描缓存 | `~/.neocortex/*.json` | **vault 级** |
| 活动日志 | `<notes_dir>/log.md` | **已在 vault 内**，无需迁移 |

**目标目录结构**：

```
~/.neocortex/
├── config.json                    # 账号级：LLM key、provider、language、active_vault
├── vaults/
│   ├── default/                   # vault 级数据
│   │   ├── profile.json
│   │   ├── gap_progress.json
│   │   ├── recommendations.json
│   │   ├── neocortex.sqlite
│   │   ├── scan_cache/
│   │   └── vault.json             # { name, notes_dir, mode: kb|skill-growth, ... }
│   └── kids-edu/
│       ├── neocortex.sqlite
│       └── vault.json
└── server-token                   # §5.4 安全相关
```

**迁移性质：copy + 原子切换，旧数据保留为备份快照**（Q5 决策）

不删除根目录原文件。迁移就是"在 `vaults/default/` 复制一份 + 写 `.migrated_v2` marker + 设置 `active_vault`"。marker 写入即代表切换成功，从此新 CLI / GUI 只看 vault；旧 root 文件成为静态备份快照，用户可以随时手动清理或保留。

**优势**：
- **没有半迁移状态**——marker 写了就是新布局，没写就还是旧布局。下次启动重做 copy 即可，没有"半状态恢复"分支
- **失败安全**：任一步出错 → 不写 marker → 下次启动看到的是旧布局，继续可用，给用户报错让其干预
- **旧 root 是天然备份**：不需要单独 `~/.neocortex.backup-<ts>`（除非用户想升级前再做一次全量备份，可选）
- **新老二进制可以共存一段时间**：旧 CLI 看 root 的快照数据（虽然会逐渐过期，因为新写入只进 vault），过渡期用户可以并行用

**为什么不走 symlink / shim 方案**：Time Machine / iCloud Drive / Dropbox 同步对 symlink 行为不一致，备份恢复后链接可能失效；本方案用"双份数据 + marker 切换"达到了类似的过渡期共存效果，比 symlink 稳。

**迁移流程（idempotent，失败回退旧布局）**：

每次启动按顺序检查：

1. **已完成**：`~/.neocortex/.migrated_v2` 存在 → 系统切到 vault 布局，正常运行
2. **触发迁移**：marker 不存在，且根目录存在 `profile.json` / `gap_progress.json` / `recommendations.json` / `neocortex.sqlite` 任一 → 进入步骤 3；否则按"全新用户"创建空 vault
3. **冲突预检**（Q12）：
   - 若 `~/.neocortex/vaults/default/` 已存在且非空 → **停止迁移**，报错"目标 vault 已存在，请手动处理或重命名"，继续以旧 root 布局运行
   - 若根目录权限异常 / 磁盘空间不足 → 同上，继续旧布局 + 报错
   - 若 `vaults/default/` 不存在 → 创建空目录，进入步骤 4
4. **写 manifest**：`~/.neocortex/.migration_pending` 记录待复制文件列表 + 每个文件源 SHA256 + 目标路径（manifest 仅为本次迁移的工作单，不参与"半状态判定"，因为失败时整个 vaults/default/ 直接抛弃）
5. **逐项 copy + fsync + 校验**：对每个文件 `copy → fsync → 计算目标 SHA256 → 对比 manifest`；任一项校验失败 → 步骤 7 中止
6. **原子提交**：全部校验通过 → `fsync` `vaults/default/` 目录 → 写 `.migrated_v2`（含迁移时间、文件清单、源 SHA256）→ 更新 `config.json:active_vault = "default"` → 删 `.migration_pending`
7. **中止**（任何一步失败）：删除 `vaults/default/` 下本次 copy 的所有文件 → 删 `.migration_pending` → 报错退出，提示"迁移失败，已回退到旧布局，可继续使用旧版本 CLI；请检查错误后重试"
8. **成功后的旧 root**：保留不动。启动时打印一次性提示："已切换到多 vault 结构；旧数据保留在 `~/.neocortex/{profile.json, ...}` 作为静态快照，可保留或手动删除；删除后旧版本 CLI 将不可用。"

**绝不**：
- 用 `os.rename` / `shutil.move` 搬数据（保留旧 root 的前提是从头到尾只 copy）
- 删除根目录原文件（这是用户的选择，不是迁移流程的职责）
- 在没写 `.migrated_v2` 前就更新 `active_vault` 字段
- 跳过 SHA256 校验（磁盘错误悄无声息）
- 半成品状态下尝试"继续上次迁移"——失败就丢弃 `vaults/default/` 重做，简单可靠

**CLI 行为**：
- `--vault <name>` 显式指定（所有命令支持）
- 未指定 → 用 `config.json:active_vault`
- `neocortex vault list / create / switch / delete` 管理子命令
- vault `mode` 字段决定哪些命令可用（kb 模式禁用 `profile scan/learn/probe`，避免对家庭 vault 出现"扫代码"按钮）

**GUI 行为**：
- 主窗口顶部 vault 下拉切换
- 切换 vault = 重新打开会话（清空时间线、关联面板状态）
- 不支持"跨 vault 搜索"（v1 故意收敛，避免儿童教育内容污染个人成长查询）

### 5.3 后端服务化（**真实工程量，不是包装层小改**）

**坦白：这不是"Python 后端 0 改动"，是一次真正的后端化重构**。当前 `cmd_*.py` 把 typer 装饰器、Rich 输出、业务逻辑、LLM 调用混在一起（典型例：`cmd_clip.py:49` 起 200+ 行的 `clip` 函数），不能直接 import 进 FastAPI handler。

**Sprint 0 具体工程**：

1. **新增依赖**（`pyproject.toml`）：
   - `fastapi>=0.115`
   - `uvicorn[standard]>=0.32`
   - `httpx`（已有，CLI 端复用作为 client）
   - `python-multipart`（Share Extension 文件上传场景）

2. **service 层抽出**：
   - 新建 `src/neocortex/services/`
   - `services/clip.py:clip(input, vault, options) -> ClipResult`：纯函数，不调 console、不调 typer.prompt
   - `services/notes.py:list_notes / get_note / search`
   - `services/related.py:related_for(note_id) -> RelatedResult`
   - 当前 `cmd_clip.py` 改成薄壳，调 service 后用 Rich 打印
   - 现有测试要跟随迁移（`tests/test_*` 大部分测的就是 cmd 层混合逻辑）

3. **API schema**：
   - 复用现有 Pydantic models（`Clip / NoteIndex / ...`）
   - 新增 `schemas/api.py`：`ClipRequest / ClipResponse / NoteListResponse / RelatedResponse`
   - OpenAPI 自动生成（FastAPI 自带）

4. **server entry**：
   - `src/neocortex/server/app.py`：FastAPI app 工厂
   - `src/neocortex/server/lifespan.py`：启动时打开 SQLite 连接池、加载 fastembed 模型；关闭时清理
   - `neocortex serve` CLI 命令：起 uvicorn，写 PID 文件 + token 文件

5. **进程生命周期**：
   - PID 文件 `~/.neocortex/server.pid`
   - 健康检查端点 `GET /healthz`（不需要 auth）
   - 优雅退出：SIGTERM → 完成 in-flight 请求 → 关 SQLite → 退出
   - SwiftUI 启动时：检查 PID 是否存活 → 不在则 spawn → 等 healthz 200 → 注入 token

6. **CLI 行为：默认直调 service，server 跑着时可选走 HTTP**（Q7 决策，相比上版反过来）：
   - CLI **默认**直接 import service 层调函数 —— 不依赖 server 是否运行，脚本化稳定，传统命令不受 GUI 进程生命周期影响
   - 若环境变量 `NEOCORTEX_USE_SERVER=1` 或检测到 server.pid 存活且 healthz 200 → 走 HTTP（带 `~/.neocortex/server-token` 的 token）
   - HTTP 调用失败 → 自动 fallback 直调 service
   - 关键：直调和走 HTTP 共用同一份 service 函数，**绝不允许两套代码路径**
   - 好处：日常 `neocortex clip` 等命令永远可用；GUI 用户偶尔在终端跑命令时若 server 在跑也能共享同一进程上下文（避免 fastembed 等重模型重复加载）

7. **测试**：
   - service 层单测
   - API 层用 `httpx.AsyncClient + ASGITransport` 黑盒测
   - 一个 e2e：CLI client → HTTP → service → 文件系统

**预估工作量**：1-2 周纯后端，不含 UI。

### 5.4 v1 安全边界（**Sprint 0 就要，不能拖到移动端阶段**）

**威胁模型**：即使监听 127.0.0.1，浏览器中任意网页可以 fetch `http://127.0.0.1:<port>/...` 探测/写入本地服务。本服务能写 vault、读知识库、持有 LLM 配置——零防护即灾难。

**v1 必须做的（Sprint 0 内嵌在 server 框架）**：

1. **绑定**：严格 `127.0.0.1`，**禁止** `0.0.0.0` 或公开端口
2. **随机端口**：启动时 `socket.bind(('127.0.0.1', 0))` 拿空闲端口，写入 `~/.neocortex/server.port`（避免固定端口被扫）
3. **Bearer Token 认证**：
   - 启动时生成 `secrets.token_urlsafe(32)`，写 `~/.neocortex/server-token`（文件权限 `0600`）
   - 所有 endpoint（除 `/healthz`）强制 `Authorization: Bearer <token>`
   - 无 token / 错 token → `401`，统一不区分（避免 timing/枚举）
   - SwiftUI 启动后读同一文件拿 token；CLI 同
4. **Origin / Host 校验**：
   - 拒绝 `Origin` 不为空且不在白名单的请求（白名单：空、`null`、`tauri://localhost`、未来自定义 scheme）
   - `Host` 必须是 `127.0.0.1:<port>` 或 `localhost:<port>`，其他拒
5. **禁 CORS**：不设 `Access-Control-Allow-Origin`，浏览器跨源访问被默认 SOP 拦
6. **CSRF / DNS Rebinding 防护**：
   - 通过 Host 校验阻断 DNS rebinding（攻击者把恶意域名解析到 127.0.0.1）
   - 状态变更操作（POST/PUT/DELETE）只接受 `Content-Type: application/json`，进一步降低 form-based CSRF
7. **本地日志**：所有 401 / Origin 失败记录到 `~/.neocortex/server.log`，方便排错

**Sprint 4（远程访问 / iPhone）的安全升级**（**不是 v1**）：
- 设备配对（pairing code 在 Mac 显示，iPhone 输入）
- 每设备独立 token + 撤销机制
- TLS（mDNS + 自签证书 / Tailscale）
- 速率限制 / 锁定

---

## 6. 技术架构（推荐：SwiftUI + Python FastAPI）

```
┌─────────────────────────────────────────────────┐
│  Neocortex.app (SwiftUI)                        │
│  ├─ MenuBarExtra (常驻图标)                      │
│  ├─ MainWindow (输入 + 时间线 + 关联 + 阅读)     │
│  ├─ GlobalHotkey (⌥ Space)                      │
│  └─ [v2] ShareExtension (.appex)                │
└──────────────────┬──────────────────────────────┘
                   │ HTTP + WebSocket
                   │ http://127.0.0.1:<random-port>
                   │ Authorization: Bearer <token>
                   │ Host: 127.0.0.1:<port> 校验
┌──────────────────┴──────────────────────────────┐
│  neocortex-server (Python, FastAPI + uvicorn)    │
│                                                  │
│  v1 端点（实线）：                                │
│  ├─ GET  /healthz              （无需 auth）     │
│  ├─ POST /clip                 （即时关联返回）  │
│  ├─ GET  /notes                                  │
│  ├─ GET  /notes/{id}                             │
│  ├─ GET  /search?q=...                           │
│  ├─ GET  /related/{id}                           │
│  └─ WS   /clip-stream          （关联进度推送）  │
│                                                  │
│  v2 端点（虚线，先不实现）：                       │
│  ┊  POST /read                                   │
│  ┊  WS   /read-progress                          │
│  ┊  WS   /ask                  （token 流式）    │
│  ┊  POST /compile / lint / verify                │
│                                                  │
│  内部 → services/ 纯函数层                        │
│      → 现有 clipper / compiler / reader / ...    │
└──────────────────┬──────────────────────────────┘
                   │
        ~/Documents/Neocortex/<vault>/  (Markdown)
        ~/.neocortex/vaults/<vault>/    (db, cache)
        ~/.neocortex/{config.json, server-token, server.port, server.pid}
```

### 为什么 SwiftUI 而不是 pywebview / Tauri / Electron

| 维度 | pywebview | Tauri | Electron | **SwiftUI** |
|---|---|---|---|---|
| 全局快捷键 | pyobjc 拼凑 | 第三方 plugin | electron-globalShortcut | **NSEvent 原生** |
| 菜单栏常驻 | pyobjc 拼凑 | tauri-plugin | electron-tray | **MenuBarExtra 一行** |
| Share Extension | ❌ | ❌ (要 Swift) | ❌ (要 Swift) | **原生支持** |
| 系统通知 | pyobjc | tauri-plugin | electron-notification | **UNNotification 原生** |
| LLM 流式 | JS bridge | WS via sidecar | WS via sidecar | URLSession + WS |
| 体积 | ~200MB | ~150MB | ~300MB | ~150MB |
| 语言数 | 2 (Py+JS) | 3 (Rust+JS+Py) | 2 (JS+Py) | 2 (Swift+Py) |
| 未来 iPhone | ❌ | ❌ | ❌ | **SwiftUI 直接复用** |

→ Mac 单机最痛的"capture 入口"和"全局唤起"上 SwiftUI 优势压倒性。后端 Python **不是** 0 改动，但改动方向正是合理的内部分层（service / api / cli 三层），不属于 SwiftUI 引入的额外成本。

### 进程管理
- App 启动 → 读 `server.pid` 判活 → 不在则 `Process` spawn `neocortex serve` → 轮询 `/healthz` 直到 200 → 读 `server-token` 注入 URLSession → 显示主窗口
- App 退出 → SIGTERM → 等 `/healthz` 不通 → 强 kill 兜底
- Server 崩溃 → app 检测到 healthz 失败 → 自动重启 + Toast 通知
- 也允许 `launchctl` 独立常驻（高级用户），app 检测到已在跑就不重复 spawn

---

## 7. 路线图（粗）

### Sprint 0：地基（**不动 UI**）
1. `clip` 反馈闭环（5.1）：复用 `--process`，加结构化返回 + `related_notes` + `cluster_growth` + `llm_status`
2. 多 vault 支持（5.2）：目录结构调整 + 迁移脚本 + `--vault` 参数 + `vault` 子命令
3. service 层抽出（5.3）：`services/clip.py` 等 + cmd 改薄壳 + 测试迁移
4. FastAPI server v0（5.3）：v1 端点最小集 + lifespan + healthz + PID
5. **v1 安全（5.4）：token + 随机端口 + Origin/Host 校验 + 禁 CORS**（与 4 同时落地，不能解耦）
6. CLI 行为（**与 Q7/§5.3 一致**）：CLI 默认直调 service；`NEOCORTEX_USE_SERVER=1` 或检测到 GUI server 已运行时可走 HTTP（带 `~/.neocortex/server-token`）；HTTP 失败自动 fallback 直调；直调与 HTTP 共用同一份 service 函数，禁止两套代码路径

### Sprint 1：Mac 客户端 v1
7. SwiftUI 主窗口骨架（输入 + 时间线 + WebView）
8. 关联面板 + 搜索
9. MenuBarExtra + 全局快捷键
10. vault 切换 UI
11. Server 进程生命周期（spawn / health / kill）

### Sprint 2：扩展捕获 + 长任务
12. Share Extension（codesign + notarization）
13. v2 端点上线：`POST /read` + 进度 WS、`POST /compile`
14. UI 暴露长任务（进度条 + 取消 + 完成通知）

### Sprint 3：对话和可视化
15. WS `/ask` 流式
16. 概念图 / 主题增长可视化
17. TTS / kb card 内嵌

### Sprint 4：移动 / 远程
18. iPhone capture 端（共用 API）
19. 设备配对 + 每设备 token + 撤销
20. mDNS + 自签 TLS / Tailscale 接入

---

## 8. 决策清单（已锁定，2026-05-20）

| # | 问题 | 决策 |
|---|---|---|
| Q1 | 是否同项目 | ✅ **是**。底层 clip/compile/search/vault 同一套，客户端是入口层不是新内核 |
| Q2 | 对外名字 | ✅ **v1 保留 Neocortex**。仓库/CLI 继续叫 Neocortex；Mac App 用 working name；v1 体验跑通后再定面向普通用户的名字 |
| Q3 | v1 是否含 Share Extension | ✅ **不含**。先用主窗口 + 菜单栏 + 全局快捷键验证反馈闭环。codesign/notarization/系统扩展统一放 v2 |
| Q4 | vault 切换粒度 | ✅ **单 active**。窗口内下拉切换，切换后清空 UI 状态。v1 不做跨 vault 搜索 |
| Q5 | 迁移失败策略 | ✅ **copy + manifest + 原子切换**（不用 move + 回滚）。旧 root 保留为备份快照；失败时继续旧布局并报错，**不进入半迁移状态** |
| Q6 | server 安全 | ✅ **v1 严格 loopback + token + Origin/Host 校验**。Sprint 0 必须落地 |
| Q7 | CLI 是否强制走 server | ✅ **不强制**。CLI 默认直调 service；检测到 GUI server 跑着可优先 HTTP；失败再 fallback 直调。CLI 不受 server 生命周期影响 |
| Q8 | 技能成长模式 | ✅ **默认不启用**。默认 vault 是 kb 模式；profile scan / learn / probe 只在显式开启 skill-growth 的 vault 出现 |
| Q9 | v1 内容类型 | ✅ **文字 + URL + 图片 OCR**，视频不做。图片 OCR 已有路径，覆盖截图/微博/公众号卡片真实场景 |
| Q10 | 重命名方向 | ✅ **偏个人/家庭，不极客向**；命名原则：温暖、可长期积累、支持家庭/孩子，但不能像儿童教育单点产品。**不在 v1 拍最终名字** |
| Q11 | clip 默认 process | ✅ **已实施**（commit TBD）。`AppConfig.clip_default_process=True` 默认开启，配 key 时 `neocortex clip "..."` 自动跑 LLM；`--no-process` 强制关闭；`clip_default_process=false` 全局关闭。`process_clip` 已透传 `_llm_status` / `_llm_error` 防静默失败 |
| Q12 | 迁移触发时机 | ✅ **首次命令启动前检测**；**只自动执行安全迁移**（copy+校验+原子切换）；检测到冲突/目标 vault 已存在/权限异常 → 停止迁移、继续旧布局、明确报错，**不强行改** |
| ~~Q13~~ | ~~one-way vs symlink~~ | 已被 Q5 实质覆盖：不删原 root，用"双份数据 + marker 切换"达到过渡期共存效果 |
| Q14 | clip 时是否生成 stub 概念页（evidence_count 立刻 0→1） | ✅ **否**。clip 阶段只返回 `new_or_pending_clusters` 给 UI 做播种感反馈；正式 `concepts/*.md` 仅由 `kb compile` 生成，避免污染概念图谱和 `kb verify` 结果 |

---

## 9. 立刻可做的最小一步

不论上面怎么定，**§5.1 `clip` 反馈闭环升级**是地基，所有方向都需要它。建议：
1. 我先做这一步（复用 `--process`，加结构化返回 + `related_notes` + `cluster_growth`），CLI 控制台打印
2. 你试用几天，看"看到关联出现"是不是真的解决"看不到效果"的痛
3. 验证通过 → 启动 Sprint 0 剩余项（多 vault + service 层 + server + 安全）
4. 验证不通过 → 重新审视产品方向，省下大量客户端开发投入

这一步**不依赖** §5.2/5.3/5.4 任何一项，完全可以独立做、独立验证。

---

## Changelog

- **v0.6 (2026-05-20)**：第五轮 review 修正（P1 真 bug + P2 默认行为缺口）。
  - P1：`clipper.py:process_clip` 之前在 LLM 异常时静默返回 fallback，导致 cmd_clip 永远显示 `llm_status=ok`，破坏"禁止静默失败"承诺。修法：`process_clip` 返回字典加 `_llm_status` (`ok`/`failed`) + `_llm_error`；cmd_clip 改为 `processed.pop("_llm_status", "ok")` 读取真实状态，不再无条件设 ok
  - P2：Q11 决策"默认开启"实际还没实施。本轮落地：`AppConfig.clip_default_process: bool = True`；`clip` 命令 `--process/--no-process` 三态（None=默认按 config / True=强制开 / False=强制关）；`neocortex clip "..."` 直接触发 LLM 反馈
  - §8 Q11 标注从"决策"升级为"已实施"
  - tests/test_clip.py 新增 8 个针对性测试覆盖 reviewer 指出的 residual gap：`_llm_status` 成功/失败两路、`_compute_new_or_pending` 三种场景、`_link_clip_to_concepts` 返回 delta + 冷启动 + 已引用跳过
- **v0.5 (2026-05-20)**：第四轮 review 修正 + Q14 落定。
  - 文档头：状态从 v0.2 → v0.4 → **v0.5**
  - §7 Sprint 0 第 6 条：CLI 行为表述按 Q7/§5.3 对齐，删除"优先连 server"措辞，改为"默认直调 / 显式开关或 server 在跑才走 HTTP / 失败 fallback"
  - §8 Q14：**否**。clip 不生成 stub 概念页，正式 `concepts/*.md` 只由 `kb compile` 生成。14 个决策全部锁定
- **v0.4 (2026-05-20)**：Q1-Q12 决策落地，机制级修订。
  - §5.1：错误回执部分按 Q11 强化——`llm_status` 细分四态（`ok / skipped_no_key / skipped_user_opt_out / failed`）+ `llm_error` 消息；明确"配 key 默认开启 + 可关闭"行为
  - §5.2：按 Q5/Q12 **彻底重写迁移机制**——从 "one-way + 半状态恢复" 改为 **"copy + 原子切换 + 旧 root 保留为快照"**；删除 9 步算法中的"删原文件"和"半状态恢复"分支；改为 8 步：冲突预检 → manifest → copy+校验 → marker 原子切换 → 失败抛弃 `vaults/default/` 退回旧布局；附"绝不"清单调整
  - §5.3：按 Q7 **反转 CLI 默认行为**——从"优先 server / fallback 直调"改为"默认直调 / 检测到 server 才走 HTTP"；强调 CLI 不受 GUI 生命周期影响
  - §8：12 个决策标记为 ✅ 锁定，Q13 删除（被 Q5 实质覆盖），Q14 仍 ⏳ 待定
- **v0.3 (2026-05-20)**：第三轮 review 修正。
  - §5.1：`cluster_growth` 拆成 `existing_cluster_delta` + `new_or_pending_clusters`，明确处理冷启动 vault `concepts/` 不存在场景（`cmd_clip.py:676-678` 直接 return 导致 evidence_count 0 增长）；引入"播种感"反馈，新主题也能显示为"播下 N 颗等长出来"
  - §5.2：删除假承诺"保留 notes_dir 兼容老 CLI"——单这一项救不了任何老二进制。改为明确 **one-way migration + 自动备份 + 启动提示**，并说明不走 symlink/shim 的原因（Time Machine/iCloud 行为不一）
  - §5.2：迁移流程从粗略 6 步重写为 9 步具体算法——manifest + copy+fsync+SHA256 校验 + 原子 marker（`.migration_in_progress` / `.migrated_v2` 双 marker） + 半状态恢复 + 明确"绝不"清单。从"绝不留半状态"承诺变成可实现的 idempotent 设计
  - §8：新增 Q13（one-way 确认）、Q14（stub 概念页设计）
- **v0.2 (2026-05-20)**：第二轮 review 修正。
  - §3：澄清"完全本地"措辞——本地优先存储 + 用户自带 key，**LLM 调用仍发送到提供商**
  - §4：项目定位改回"AI 驱动的个人知识库工具"（README 原始定位），技能成长降级为增强路径而非主体
  - §5.1：精确描述 `clip --process` 现状（`cmd_clip.py:299/357`），改为"产品化已有 LLM 后处理 + 新增 related_notes/cluster_growth/llm_status"，不是从零造
  - §5.2：详尽多 vault 迁移策略——账号级 vs vault 级分类表 + 目录结构 + 迁移步骤 + 失败回滚 + 老用户兼容
  - §5.3：删掉"Python 后端 0 改动"假话，诚实列出 Sprint 0 真实工程：依赖、service 层、API schema、lifespan、CLI fallback、测试
  - **§5.4 新增**：v1 安全边界（token + 随机端口 + Origin/Host 校验 + 禁 CORS），从 Sprint 4 前移到 Sprint 0
  - §6 架构图：v1 端点实线 / v2 端点虚线明确切分，避免实现时边界漂
  - §7 路线图：Sprint 0 内嵌安全；Sprint 2 才解锁 `/read`、`/compile`；Sprint 4 移动 + 远程
  - §8：新增 Q11（clip 默认 process）、Q12（迁移触发时机）
- **v0.1 (2026-05-20)**：初稿。捋清"为什么要做客户端"、对比市场产品、提出技术方案、罗列未决问题。
