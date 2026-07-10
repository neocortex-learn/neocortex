# 2026-07-10 复习闭环（Slices 0–2）三方异模型 Review

- 范围：server + mac 两 repo 的未提交 diff（review service / HTTP API+事件 / AppKit 面板）
- 模型：Codex（GPT，stdin 模式）、Pi（DeepSeek V4 Pro）、Kimi（K2.7 Code），同一对抗式 prompt + 背景不变量
- 来源标注：C=Codex，P=Pi，K=Kimi；多家同报 = 高可信

## Findings 与处置

| # | 级别 | 发现 | 来源 | 处置 |
|---|---|---|---|---|
| 1 | P1 | concept 名可构造路径逃逸，boost 会改写 vault 外文件；SQLite 恢复重放同样危险 | C | ✅ 修复：`_safe_concept_path()` 在 compute 与 apply 两端校验（拒绝绝对路径/`..`/分隔符/点开头 + `relative_to` 双保险）；测试 `TestConceptPathEscape` |
| 2 | P1 | `apply_outcome` 重写整文件时静默丢弃无法解析的条目（容错读取变破坏性写回） | C+K | ✅ 修复：只对目标卡 dict 合并 SCHEDULE_FIELDS，其余条目（含坏条目、未知字段）原样保留；测试 `TestApplyPreservesUnknownEntries` |
| 3 | P1 | compiler/cmd_read 的 `save_flashcards` 绕过 flock，整文件覆写可吃掉并发复习进度；compiler 读-改-写窗口无锁且同样丢坏条目 | P | ✅ 修复：`config.save_flashcards` 内部取同一把 `review_write_lock`；compiler relationship 批次读-改-写整体持锁 + 原样保留原始条目（`atomic_save_raw`）；测试 `TestSaveFlashcardsLocking` |
| 4 | P2 | 崩溃恢复会用旧 boost 绝对值覆盖期间其他写者（CLI/compiler）更新的 confidence | C+P | ✅ 修复：boost 快照增加 `before_confidence`，apply 三态判断（==before 应用 / ==目标 跳过 / 其他 保留新值）；测试 `TestBoostConflictDetection` |
| 5 | P2 | Mac 端 409（stale event）被当网络错误：pending 永不清除、按钮禁用、重试永远同一个必然失败的 event_id → 面板死锁 | C | ✅ 修复：4xx 明确拒绝走 `abandonPending()`（清 pending、跳过该卡、不计数），仅 transport/5xx 保留 pending 重试；测试 `testAbandonPending*` |
| 6 | P2 | restore 不校验卡片确实 suspended：对已评分卡发 restore 可把已完成 session 错误重开 | K | ✅ 修复：restore 前置校验，非 suspended 返回 409；测试 `test_restore_requires_suspended_card` |
| 7 | P2 | 恢复 after 分支重放 apply 造成多余 concept 写 | P | ⚖️ 有意保留重放：崩溃可能落在"卡片已写、boost 未写"窗口，重放可补 boost；#4 的三态应用已消除覆盖风险（代码注释说明） |
| 8 | P2 | `resolve_source_path` 的全 vault rglob 在锁内执行，大 vault 长时间阻塞所有写者 | K | ✅ 修复：source 解析（只读）移出 `review_write_lock` |
| 9 | P3 | Swift 端不校验 server 返回的 source_path（纵深防御） | K | ✅ 修复：openSource 拒绝绝对路径/`..` |
| 10 | P3 | `refreshDueCount` 无 coalescing，快速开菜单会并发请求、UI 可能乱序；impression 每次菜单打开都记一条 | K | 📝 记录不修：impression 按曝光记录是有意设计；乱序窗口极小且下次刷新自愈 |
| 11 | P3 | `services/daily.py` due count 吞所有异常返回 0（可观测性） | K | 📝 记录不修：沿用 daily briefing 既有容错模式，失败不应挂掉整个简报 |
| 12 | P3 | 每请求新建 `ReviewEventStore` 重跑 `CREATE TABLE IF NOT EXISTS`（低效） | K | 📝 记录不修：本地单用户负载可忽略，SQLite busy timeout=10s 兜底 |

## 三家均确认无问题的部分（Pi 明确背书）

- pending/applied 状态机 + 绝对值快照设计与三路恢复分支（before/after/stale）
- event_id 幂等（PRIMARY KEY + response_json 重放）
- flock 获取点覆盖完整（本次 review 后 save_flashcards 也已纳入）
- quality 0/1/2 折叠为 Again 的决策及其哨兵测试

## 修复后门禁

- server：`pytest tests/ -q` → **1104 passed, 5 skipped**（review 前 1096，+8 回归锁定测试）
- mac：xcodegen + Debug build + test → **55 tests, 0 failures**（+2）
