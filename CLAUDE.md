# Neocortex 开发规范

## 项目概述
Neocortex 是一个 AI 驱动的开发者技能分析和个性化学习助手。Python CLI 工具。

## 技术栈
- Python 3.10+, Typer + Rich (CLI), Pydantic (数据模型)
- LLM: anthropic, openai, google-genai SDK
- 内容: httpx, readability-lxml, pymupdf
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
├── config.py       # 配置和画像读写
├── models.py       # 所有 Pydantic 数据模型
├── i18n.py         # 中英文国际化
├── recommender.py  # 学习路径推荐
├── asker.py        # 交互式问答
├── growth.py       # 技能成长追踪
├── tts.py          # 音频输出
├── search.py       # SQLite FTS5 搜索
├── llm/            # LLM 适配层
├── scanner/        # 项目扫描
├── reader/         # 内容阅读 + 笔记生成
└── importer/       # 聊天记录导入
```

## 注意事项
- Commit message 用中文
- 不要在 commit message 中加 Co-Authored-By
- 新增面向用户的文本必须同时添加中英文 i18n
- LLM 响应可能包含 <think> 标签（推理模型），已在 openai_compat.py 中统一剥离
