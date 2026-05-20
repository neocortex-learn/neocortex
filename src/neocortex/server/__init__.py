"""Local HTTP server for Neocortex GUI / programmatic clients.

Per CLIENT_PROPOSAL.md §5.4 (v0.6 安全决策):
    - 严格 loopback (127.0.0.1)
    - 随机端口 (避免被扫)
    - Bearer Token + Origin/Host 校验
    - 禁 CORS
    - DNS rebinding 防护（Host 头严格匹配）

Server entry: ``neocortex serve``. SwiftUI / future clients read
``~/.neocortex/server.{port,token}`` to discover the running instance.
"""
