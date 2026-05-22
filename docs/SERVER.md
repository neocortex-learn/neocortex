# Neocortex 本地 HTTP Server

> 由 `neocortex serve` 启动的 FastAPI 进程，绑定 `127.0.0.1`，供本机 GUI 客户端
> （SwiftUI / 未来 Tauri）调用。设计文档历史背景：CLIENT_PROPOSAL.md v0.7 Sprint 0。

---

## 1. 启动与服务发现

```bash
neocortex serve                # 随机端口
neocortex serve --port 8765    # 固定端口
neocortex serve --show-token   # 启动时打印 Bearer token
```

启动后 `~/.neocortex/` 下出现三个 runtime 文件：

| 文件 | 内容 | 权限 |
|---|---|---|
| `server.pid` | 当前进程 PID | 0644 |
| `server.port` | 绑定的端口（int） | 0644 |
| `server-token` | Bearer token（44 字节 urlsafe） | **0600**（从 `os.open` 首次 syscall 即 0600） |

GUI 客户端读这三个文件做服务发现。进程退出时（SIGINT/SIGTERM/atexit）
自动清理（`runtime.cleanup_runtime()`）。重启时若发现旧 PID 不在了，先 cleanup
再 provision，避免半新半旧的 token / port 混搭。

`is_server_alive()` 用 `os.kill(pid, 0)` 做存活检测，CLI 后续 fallback 可用。

---

## 2. 安全模型（4 层防御 + 不挂 CORS）

威胁假设：

- 同一台机器上的恶意网页 / 其他本地账户探测 `127.0.0.1`
- DNS rebinding 把 `evil.com` 解析到 `127.0.0.1`
- 表单驱动的 CSRF（非 JS 也能跨域 POST）

防御栈（`server/security.py`，全部叠加）：

1. **Bearer Token**：随机 32 字节 urlsafe，每次启动重新生成；`Authorization: Bearer <token>`，
   `secrets.compare_digest` 比对。
2. **Host 严格匹配**：只接受 `127.0.0.1:<port>` 或 `localhost:<port>`。打掉 DNS rebinding。
3. **Origin 白名单**：`null`（file://）+ `tauri://localhost`。SwiftUI URLSession 通常不带
   Origin → 允许；浏览器带其他 Origin → 403。
4. **Content-Type 强制**：变更方法（POST/PUT/PATCH/DELETE）必须 `application/json`，
   打掉表单 CSRF。

**不挂 CORS**：浏览器 SOP 自然把跨域 fetch 挡掉，加 `Access-Control-Allow-Origin`
反而是降级。出于同样原因，Swagger UI / OpenAPI 默认禁用（`docs_url=None` 等）。

**WebSocket**：Starlette 的 BaseHTTPMiddleware 不拦 `websocket` ASGI scope，所以
WS 路由必须自己跑 `validate_ws_handshake()`，做 host/origin/token 三件套
（token 优先从 `Authorization` 头取，浏览器无法设 WS 自定义 header 时退到 `?token=` 查询参数）。
失败时用 close code 1008 退出。

---

## 3. Routes 总览

所有 `/api/*` 路由都需要 Bearer token；`/healthz` 例外。

| Method | Path | Request | Response | Service |
|---|---|---|---|---|
| GET | `/healthz` | — | `{"status":"ok"}` | — |
| GET | `/api/version` | — | `{"version":"x.y"}` | smoke test |
| POST | `/api/clip` | `{source, process?}` | `ClipResult` | `services.clip.clip_text` |
| POST | `/api/read` | `{source, focus?}` | `ReadResult`（同步阻塞 30s–3min） | `services.read.read_url` |
| WS | `/api/read/ws` | 首条 JSON `{source, focus?}`，后续推 progress 事件 | `{type:progress, phase, ...}` / `{type:done, result}` / `{type:error}` | 同上 + `on_progress` 回调 |
| POST | `/api/notes/delete` | `{file_path}` | `DeleteNoteResponse` | `services.notes.delete_note` |
| GET | `/api/search?q=...&limit=...&type=...` | query | `SearchResponse` | `search.py` FTS5 |
| POST | `/api/ask` | `{question, save?}` | `AskResult` | `services.ask.ask_question` |
| GET | `/api/daily` | — | `DailyBriefing` | `services.daily.build_briefing` |
| POST | `/api/daily/surface` | `{clip_id, action}` | `SurfaceUpdate` | `services.daily.mark_surfaced` |
| GET | `/api/map?domain=...&around=...` | query | `ConceptMap`（含 Mermaid 源） | `services.visualize.build_concept_map` |

> 注意：删除笔记走的是 `POST /api/notes/delete`，**不是** `DELETE /api/notes`。
> 这是为了和 4 层安全里的"变更方法强制 JSON body"规则配合。

`POST /api/clip` 的语义：**fetch hard-fail 不算协议错误**，返回 200 + `aborted=true`。
设计原因：HTTP 请求本身合法，是上游内容拿不到 — 这是业务状态，不是协议错误。

---

## 4. WebSocket 协议（/api/read/ws）

```
Client ──握手──> Server   （Authorization: Bearer ... 或 ?token=...）
Client ──{"source":"https://...","focus":null}──> Server
Server ──{"type":"progress","phase":"fetch","..."}──> Client
Server ──{"type":"progress","phase":"outline","..."}──> Client
Server ──{"type":"progress","phase":"chunk","done":3,"total":8}──> Client
...
Server ──{"type":"done","result":{...ReadResult...}}──> Client
Server ──close 1000──> Client
```

错误：

- 握手 host/origin/token 任一失败：close 1008
- 请求体解析失败：发 `{type:error}` + close 1003
- read pipeline 抛异常：发 `{type:error,message}` + close 1011

客户端断开（client_alive=False）时，server 端 `on_progress` 静默 skip 余下事件，
不阻塞 `read_url` 本身的执行（背景任务最终会写入笔记目录）。

---

## 5. 去重（dedup.py）

`services/clip.py` 和 `services/read.py` 在调 LLM 前用 `dedup.find_existing()`
查重，命中则返回已有笔记 + `reused=True`。

**规范化规则**（`dedup.normalize_source_url`）：

- 去 `utm_*` / `fbclid` / `gclid` / `ref` / `source` / `spm` / `share*` 等追踪参数
- 去末尾斜杠、fragment、域名小写
- **微信文章保留 `mid/idx/sn/chksm/__biz`**（这些才是真 ID，去掉会撞车）
- 纯文本 / `source: manual` → 返回 None（退出去重，重 clip 成本低）

匹配方式：先查 SQLite `NoteIndex.note_sources`，回退到 FS 扫描笔记 frontmatter。

**已知局限**：CLI 路径 `cmd_clip.py` / `cmd_read.py` 不走 services，**不去重**。
commit 33a3884 的描述"clip/read 自动去重"实际只覆盖 HTTP 路径。CLI 何时收敛
到 services 见 services/__init__.py 头部注释。

---

## 6. 客户端集成示例

### curl 测试

```bash
PORT=$(cat ~/.neocortex/server.port)
TOKEN=$(cat ~/.neocortex/server-token)

# 健康检测
curl http://127.0.0.1:$PORT/healthz

# 版本（smoke test，验证 token 工作）
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:$PORT/api/version

# Clip 一条推文
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"source":"https://x.com/karpathy/status/123"}' \
  http://127.0.0.1:$PORT/api/clip

# Daily briefing
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:$PORT/api/daily
```

### WebSocket（Python wscat 替代）

```python
import asyncio, json, websockets

async def main():
    token = open("~/.neocortex/server-token").read().strip()
    port = open("~/.neocortex/server.port").read().strip()
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/api/read/ws",
        additional_headers={"Authorization": f"Bearer {token}"},
    ) as ws:
        await ws.send(json.dumps({"source": "https://example.com/article"}))
        async for raw in ws:
            msg = json.loads(raw)
            print(msg["type"], msg.get("phase", ""))
            if msg["type"] in ("done", "error"):
                break

asyncio.run(main())
```

---

## 7. 测试覆盖

- `tests/test_server.py` — 安全中间件 + 各 route 端到端（含 WS 进度流、runtime 文件生命周期）
- `tests/test_dedup.py` — URL 规范化 + 查重

---

## 8. 未做 / 未来

- **CLI 收敛到 services**：当前 CLI 直接调引擎，不去重也不走服务层。计划在 GUI
  稳定后切换，让两条入口共享同一组路径。
- **远程访问**：明确不支持。绑死 `127.0.0.1`，鉴权和安全设计都假设单机。
  需要远端用 SSH 隧道或 Tailscale，不要改 host。
- **多用户 / 多 vault**：当前 process 全局共享 `~/.neocortex/`，
  没有 per-user / per-workspace 隔离。
- **OpenAPI 暴露**：默认全关。开发调试需要 Swagger UI 时在 `server/app.py` 临时打开。
