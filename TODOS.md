# TODOS

## Bug Fix

### scan_cache.py 缓存失效 + 隐私泄露
- **优先级**: High
- **问题**:
  1. 非 git 项目 `_get_project_hash()` 返回常量 `"unknown"`，缓存永远命中
  2. Python `hash()` 每进程随机化，dirty repo 的缓存跨进程失效
  3. `fetcher.py` Jina fallback 未经用户同意将 URL 发送到第三方服务
- **修复方向**:
  1. 非 git 项目用文件 mtime 的确定性 hash（如 hashlib.md5）
  2. 用 hashlib 替代 `hash()` 确保跨进程一致
  3. Jina fallback 加 opt-in 提示或配置开关
- **Depends on**: 无

## 测试债务

### 补全 scan_cache + fetcher 新功能测试
- **优先级**: Medium
- **内容**: 为 scan_cache、Jina fallback、image fetch、EPUB 读取补充测试
- **Depends on**: scan_cache.py bug fix
