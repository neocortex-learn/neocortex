# 2026-07-10 自用复习闭环验收复核

## 结论

**源码与自动化门禁通过；正式 30 天试运行仍需安装当前 Mac build，并完成一次人工真实鼠标 smoke。**

本轮复核不是只确认原实现测试为绿；发现并修复了会影响试运行指标或跨仓库上线的可靠性问题。外部桌面自动化未作为最终 UI 证据，避免把工具侧状态误写成产品证据。

## 本轮确认并修复

| 严重度 | 问题 | 修复与锁定 |
|---|---|---|
| P1 | session 创建响应超时后重试会新增 abandoned session，污染开始率 | session body 增加稳定 `request_id`；SQLite 唯一索引 + 原响应重放；Mac controller 生命周期内复用同一 key；服务端一版兼容未升级的已安装客户端 |
| P1 | pending event 持久化绝对卡片路径，整个 Neocortex 目录移动后无法恢复 | 只存 `.flashcards` 内单文件引用；apply 重新做逃逸校验；兼容旧绝对路径时只取 basename 并映射到当前 layout |
| P1 | Mac 把所有 4xx 都当成“跳过当前卡”，可能显示完成但 server 未完成 | 仅明确 `superseded` 冲突跳过；401/404/422 和其他 409 只清 pending、保留当前卡 |
| P1 | stale grade/suspend 未计入原 session 终态 | stale 事件刷新 session；终态重算同时读取 applied/stale，避免 UI/server 完成态分叉 |
| P2 | 新生成卡仍只存源笔记 basename，同名文件会歧义 | 新卡保存 vault-relative `source_note`，旧卡继续走唯一 basename 兼容解析 |
| P2 | 同一 `event_id` 可被串用于不同 action/session/card | 重放前绑定三元组校验，不一致返回 409 |
| P2 | 测试传入自定义 `today` 时 summary 与 reviewer 使用不同日期 | `today` 贯通默认/Hard queue 计算并加回归测试 |

## 验证证据

- Server 全量：`1113 passed, 5 skipped`；仅 2 条既有依赖弃用 warning。
- Mac 全量：`57 tests, 0 failures`，`** TEST SUCCEEDED **`。
- Mac Debug build：`** BUILD SUCCEEDED **`。
- 隔离运行时端到端（临时 data/vault，由 Mac App 拉起当前 server）：
  - daily due = impression due = session due = 2；
  - impression 前后 `review_sessions` 均为 0；
  - 同一 `request_id` 两次响应完全一致，session 表只有 1 行；
  - suspend → restore → Good/Easy 完成，session `completed_at` 已写；
  - 同一 grade `event_id` 重放响应一致，未重复推进。
- 真实数据保护：真实四个 flashcard JSON 的 SHA-256 与验收前完全一致；真实 `review_sessions=0`、`review_events=11`，时间范围仍为 `2026-07-10T17:16:13..17:40:08`。

## 试运行前剩余门禁

1. 安装当前源码构建的 Mac App；当前 `/Applications/NeocortexApp.app` 是上一版二进制，服务端已保留一版兼容，但它不具备 session 创建重试幂等。
2. 人工真实鼠标完成一次：菜单栏入口 → 翻面 → 四档任一评分 → suspend/undo → 打开源笔记。
3. 记录 `pilot_started_at`，30/60 天复盘只统计该时间之后的记录。真实 DB 已有 11 条开发/验收 impression，必须从试运行分母排除，不能删除后假装不存在。

