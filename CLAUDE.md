# Neocortex 开发规范

## 项目概述
Neocortex 是一个 AI 驱动的开发者技能分析和个性化学习助手。Python CLI 工具。

## 技术栈
- Python 3.10+, Typer + Rich + InquirerPy (CLI), Pydantic (数据模型)
- LLM: anthropic, openai, google-genai SDK
- 内容: httpx, readability-lxml, pymupdf, ebooklib, markdownify
- TTS: edge-tts
- 搜索: SQLite FTS5
- 测试: pytest + pytest-asyncio

## 开发命令
```bash
pip install -e .          # 安装开发版
python -m pytest tests/   # 运行测试
neocortex --help          # 查看 CLI 帮助
```

## 代码规范
- 所有文件使用 `from __future__ import annotations`
- 数据模型用 Pydantic BaseModel（在 models.py 中集中定义）
- LLM 调用都是 async 的，CLI 用 asyncio.run() 包装
- 面向用户的文本通过 i18n.py 的 t() 函数获取
- CLI 命令内部用延迟导入（在函数内 import）
- 测试用 pytest，async 测试用 @pytest.mark.asyncio + AsyncMock

## 目录结构
```
src/neocortex/
├── cli.py          # CLI 入口，所有命令
├── config.py       # 配置、画像、推荐记录、gap 进度读写
├── models.py       # 所有 Pydantic 数据模型
├── i18n.py         # 中英文国际化
├── recommender.py  # 学习路径推荐（结构化上下文 + gap 关联）
├── tracker.py      # 推荐跟踪：阅读 → 匹配推荐 → 更新 gap 状态
├── scan_cache.py   # 扫描结果缓存（按 git HEAD / 文件 mtime）
├── asker.py        # 交互式问答
├── growth.py       # 技能成长追踪
├── tts.py          # 音频输出
├── search.py       # SQLite FTS5 搜索
├── llm/            # LLM 适配层（含 describe_image）
├── scanner/        # 项目扫描（含 gap 同义词规范化）
├── reader/         # 内容阅读 + 笔记生成（URL/PDF/EPUB/图片）
└── importer/       # 聊天记录导入
```

## 核心机制

### 闭环学习
推荐 → 阅读 → 自动匹配推荐 → 更新 gap 状态 → 下次推荐更精准。
- 数据流：`recommend` 生成有序学习路径 → `read` 自动匹配（三级：URL/域名关键词/用户确认）→ gap 状态迁移（gap → learning → known）→ 下次 `recommend` 跳过已完成
- 存储：`~/.neocortex/recommendations.json` + `~/.neocortex/gap_progress.json`

### 学习路径（参考 [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 的渐进式设计）
推荐不再是平铺的独立主题，而是**有序的学习路径**：
- 每条推荐有 `step`（学习顺序）和 `depends_on`（前置主题列表）
- 前置未完成的步骤处于锁定状态，完成后自动解锁下游步骤
- LLM prompt 要求按"基础→进阶"顺序排列，建立知识依赖关系
- `tracker.get_unlocked_recommendations()` 过滤出当前可学的步骤

### Gap 语义去重
`scanner/profile.py` 中的同义词表（`_GAP_SYNONYMS`）将 LLM 输出的不同表述归一化为统一名称。新发现的同义词直接加到表里。

### Token 优化（参考 learn-claude-code 的 Skill 按需加载思路）
`_build_context()` 按域分组展示 gap（减少重复 domain/level 标签），阅读历史只传标题不传完整路径，降低每次 LLM 调用的 token 消耗。

## 注意事项
- Commit message 用中文
- 不要在 commit message 中加 Co-Authored-By
- 新增面向用户的文本必须同时添加中英文 i18n
- LLM 响应可能包含 <think> 标签（推理模型），已在 openai_compat.py 中统一剥离
- gap 名称必须通过 `normalize_gap_name()` 规范化后再存储/比较
- JSON 文件写入使用原子写入（temp file + os.replace），见 `config.py._save_json`
- 推荐必须包含 `step` 和 `depends_on` 字段，保持学习路径的有序性

## 设计参考
- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) — 渐进式学习路径设计、Skill 按需加载、任务依赖图
