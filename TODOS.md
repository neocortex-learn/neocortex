# TODOS

## 架构改进

### cli.py 拆分
- **优先级**: Medium
- **问题**: cli.py 已达 1900+ 行，扫描/阅读/推荐/卡片全在一个文件
- **方向**: 按命令组拆分为独立模块（scan_cmd.py, read_cmd.py, recommend_cmd.py 等）

### 搜索性能优化
- **优先级**: Medium
- **问题**: semantic_search() 纯 Python 遍历所有向量，O(N) 每次查询
- **方向**: 使用 FAISS 或 SQLite 向量扩展替代纯 Python 相似度计算

### Chat import token 预估
- **优先级**: Low
- **问题**: extract_insights() 按消息数分批而非 token 数，长消息可能溢出上下文
- **方向**: 用 tiktoken 估算 token 数，按 token 预算分批

### 扫描缓存采样限制
- **优先级**: Low
- **问题**: 非 git 项目只采样 50 个源文件 mtime，大项目可能 false cache hit
- **方向**: 增加采样数或改用内容 hash
