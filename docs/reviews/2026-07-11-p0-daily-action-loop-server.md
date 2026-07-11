# P0 Daily Action Loop Server 契约验收

> 日期：2026-07-11
> Package：`P0-DAILY-ACTION-LOOP`
> Task：`P0-CONTRACT-SERVER`
> Worker commit：`cc994cf`
> Merge commit：`3ac9c95`
> 证据标签：`local`；Mac/安装态/真实使用仍为 `blocked`。

## 结果

已接受并合并 server 端 P0 契约：

- `/api/daily` 默认只返回最多 3 条到期且尚未判断的 Inbox，另返回截断前总数、继续读 1 条和 Top of Mind。
- `/api/inbox` 返回未判断内容。
- `/api/inbox/action` 支持 keep/skip/later/master/undo，`action_id` 重放无重复副作用。
- keep/skip/later/master 分别落为 reference/archived/later/promoted；reference 不再主动浮现。
- undo 必须指定目标动作；同一 clip 存在后续已应用动作时拒绝旧撤销。
- Inbox 写入使用 SQLite pending/applied 绝对快照、跨进程锁和原文件路径原子覆盖。
- `/api/top-of-mind` 支持读取/整体设置最多 3 个主题；Today 使用确定、可解释的规则排序。

## 审查

- 改动仅涉及任务允许的 server models/services/routes/tests/docs。
- 未修改真实 `vault/`、`data/` 或 Mac 仓库。
- Daily 原有字段保留，新增字段有默认值，旧客户端可继续解码已有字段。
- 精确文件路径更新避免手工改名后的 clip 被重新保存成副本。
- pending intent 在“事件已写/文件未写”和“文件已写/事件未完成”两个崩溃窗口均有回归测试。
- Top of Mind 第一版只匹配 title/summary/topic/tags/related concepts，没有引入推荐模型。

## 验证

- Focused：25 passed。
- Worker full：1145 passed, 5 skipped。
- Orchestrator full：1145 passed, 5 skipped，2 个既有依赖弃用 warning。
- Ruff：通过。
- `git diff --check`、`git diff --cached --check`：通过。
- `codex-orchestrator` PR reviewer 和 merge-readiness：本地路径/diff 检查通过；人工协调者复核 self-review 与 evidence boundary 后接受。

## 未完成与下一步

- `blocked`：Mac Codable/ServerClient、Today 默认主界面、Inbox 四动作 UI、Top of Mind 编辑、导航降噪、真实鼠标和安装态证明。
- `blocked`：七天使用率、十分钟完成度、长期行为指标。
- 下一任务应从总纲和 P0 package spec 继续 `P0-MAC-TODAY`，不得提前启动 P1/P2。
