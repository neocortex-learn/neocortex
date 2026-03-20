# Neocortex

> AI 驱动的开发者技能分析与个性化学习助手。
>
> 扫描你的项目，构建技能画像，只学你**需要的**。

[English](README.md) | 中文

Neocortex 通过分析你的实际代码（而不是简历）来了解你会什么、有多深、缺什么。当你丢给它一本书、一篇文章或一份文档时，它会生成个性化的学习笔记——跳过你已经懂的，专注你需要补的。

## 为什么做 Neocortex？

每个开发者的学习需求都不一样。一个做过 3 套实时消息系统的高级工程师不需要听"WebSocket 是什么"——他需要的是"你的 Redis Pub/Sub 架构有双写一致性问题，该怎么修"。

现有工具都做不到这一点：

| 工具 | 懂内容 | 懂你 | 个性化 |
|------|:------:|:----:|:------:|
| NotebookLM | 是 | 否 | 否 |
| ChatGPT / Claude | 是 | 一点点 | 否 |
| Coursera / Udemy | 是 | 否 | 否 |
| **Neocortex** | **是** | **是** | **是** |

核心原理：Neocortex 通过分析你的代码构建真实的技能画像，然后在你的[最近发展区](https://zh.wikipedia.org/wiki/%E8%BF%91%E4%BE%A7%E5%8F%91%E5%B1%95%E5%8C%BA%E9%97%B4)内精准教学。

## 快速开始

### 安装

```bash
uv pip install neocortex-ai

# 或者直接运行，无需安装
uvx neocortex-ai
```

### 初始化

```bash
neocortex init
```

回答 5 个简短问题（角色、经验、学习目标、学习风格、语言偏好），30 秒搞定。

### 配置 LLM

```bash
# 使用 Claude
neocortex config --provider claude --api-key sk-xxx

# 使用 OpenAI
neocortex config --provider openai --api-key sk-xxx

# 使用 OpenAI 兼容的服务（Kimi、DeepSeek、MiniMax 等）
neocortex config --provider openai-compat \
  --api-key sk-xxx \
  --base-url https://api.moonshot.cn/v1 \
  --model moonshot-v1-128k
```

### 扫描你的项目

```bash
# 扫描一个或多个本地项目
neocortex scan ~/projects/my-app ~/projects/my-api

# 查看技能画像
neocortex profile
```

输出示例：

```
 技能画像 — 更新于 2026-03-20
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

编程语言
  Python        ██████████████████░░  精通     (85K+ 行, 3 个项目)
  TypeScript    ████████████████░░░░  熟练     (40K+ 行, 2 个项目)
  Go            ██████████░░░░░░░░░░  掌握     (3 个项目, WebSocket 方向)
  Java          ████████████████░░░░  熟练     (15+ 个 Android 应用)

框架与工具
  FastAPI       ██████████████████░░  精通
  Tornado       ██████████████████░░  精通
  React         ████████████████░░░░  熟练
  React Native  ████████████░░░░░░░░  掌握
  Android MVVM  ████████████████░░░░  熟练

领域能力
  实时系统       ██████████████████░░  精通  (3 套 Redis→Go→WS 架构)
  支付集成       ██████████████████░░  精通  (9 种支付方式)
  数据库设计     ████████████████░░░░  熟练  (200+ 张表)
  流处理         ████████░░░░░░░░░░░░  基础  (有实践, 缺理论)
  分布式系统     ██████░░░░░░░░░░░░░░  基础  (无系统性知识)
```

### 开始学习

```bash
# 丢一个书章节的 URL
neocortex read https://ddia.vonng.com/ch8/

# 丢一个本地 PDF
neocortex read ~/books/system-design.pdf

# 聚焦某个主题
neocortex read https://ddia.vonng.com/ch8/ --focus "事务隔离级别"

# 带着问题读
neocortex read https://some-article.com --question "这跟我的支付系统有什么关系？"
```

Neocortex 生成个性化的 Markdown 笔记：

```
 笔记已保存：~/.neocortex/notes/ddia-ch8-事务.md
 正在打开...
```

笔记会跳过你已经懂的，重点讲你需要学的，并用你实际做过的项目做类比。

### 导入 AI 聊天记录（可选）

你跟 ChatGPT/Claude 聊过的内容暴露了你的知识盲区——你问过的问题 = 你不确定的东西。Neocortex 提取这些洞察来让你的画像更精准。

```bash
# 导入 ChatGPT 记录（设置 → 数据控制 → 导出）
neocortex import --source chatgpt ~/Downloads/conversations.json

# 导入 Claude 记录（设置 → 隐私 → 导出数据）
neocortex import --source claude ~/Downloads/claude-export/
```

隐私：只存储结构化洞察，不保存原始聊天记录。详见[数据与隐私](#数据与隐私)。

### 设置语言

```bash
# 默认英文，切换为中文：
neocortex config --language zh

# 切换回英文：
neocortex config --language en
```

影响 CLI 提示信息、笔记输出和 LLM Prompt。

### 管理知识库

```bash
# 列出所有笔记
neocortex notes

# 搜索笔记
neocortex notes --search "隔离级别"

# 重新扫描项目更新画像
neocortex scan ~/projects/new-project --update

# 导出画像为 JSON
neocortex profile --export profile.json
```

## 工作原理

### 1. 智能项目扫描

Neocortex 不会把你的整个代码库喂给 LLM，而是高效提取关键信号：

```
项目目录
    ↓
1. 配置检测     → package.json, requirements.txt, go.mod, build.gradle
2. 代码统计     → 按语言统计行数、文件数、项目结构
3. 关键文件采样 → 模型、处理器、路由、Schema、测试
4. 架构信号     → 设计模式、第三方集成、基础设施
    ↓
结构化摘要（每个项目约 2K tokens）
    ↓
LLM 分析 → 技能画像（JSON）
```

成本很低——扫描一个项目通常不到 $0.05。

### 2. 技能画像模型

画像从三个维度刻画你的能力：

```json
{
  "languages": {
    "python": {
      "level": "expert",
      "lines": 85000,
      "frameworks": ["fastapi", "tornado", "celery"],
      "patterns": ["async/await", "middleware", "connection pooling"],
      "projects": ["cutie-server", "restaurant-server", "liveblog"]
    }
  },
  "domains": {
    "real_time_systems": {
      "level": "expert",
      "evidence": [
        "在 3 个项目中构建了 Redis Pub/Sub → Go WebSocket → Client 架构",
        "实现了 Socket.IO v1 和 v4 协议",
        "多命名空间的 Room-based 广播"
      ],
      "gaps": [
        "缺少流处理的理论知识（事件时间 vs 处理时间）",
        "没用过 Kafka 等基于日志的消息代理"
      ]
    }
  },
  "integrations": {
    "payment": {
      "providers": ["stripe", "paypal", "cardpointe", "authorize.net", "pax"],
      "level": "expert",
      "gaps": ["支付流程中缺少幂等 ID"]
    }
  }
}
```

### 3. 个性化阅读（两阶段管道）

当你丢给 Neocortex 一篇文章或书的章节时，它会运行两阶段管道：

**阶段 1 — 大纲分析**（快速，低成本）：
1. 获取并解析内容
2. 提取章节结构
3. 对照你的画像标记每个章节：`✓ 跳过` / `△ 简要` / `★ 重点`
4. 展示个性化大纲，等你确认

**阶段 2 — 笔记生成**：
5. 逐章生成笔记，在你的水平上讲
6. 用你做过的项目做类比
7. 列出 Action Items——你代码里具体该检查什么
8. 保存为 Markdown——用你喜欢的编辑器打开

举例：两个开发者读同一本 DDIA 事务章节。

**开发者 A**（初级，只用过 SQLite）：
> "事务把多个操作打包成一个原子单元。可以这样理解：转账时，扣款和加款必须同时成功，否则都不发生……"

**开发者 B**（你，集成过 9 种支付方式）：
> "你的 restaurant 项目用的 MySQL 不会自动检测丢失更新——PostgreSQL 在 Cutie 里会。检查你的 `paymentWrap.py`：如果两个 POS 终端同时处理同一订单且没加 `SELECT FOR UPDATE`，就有竞态条件……"

同一份内容。完全不同的输出。这就是个性化的意义。

## 支持的 LLM 提供商

自带 API Key，Key 只存在本地 `~/.neocortex/config.json`。

| 提供商 | 模型 | 配置 |
|--------|------|------|
| **Anthropic** | Claude Opus, Sonnet, Haiku | `--provider claude` |
| **OpenAI** | GPT-4o, GPT-4.1, o3 | `--provider openai` |
| **Google** | Gemini 2.5 Pro/Flash | `--provider gemini` |
| **OpenAI 兼容** | Kimi、MiniMax、DeepSeek、通义、GLM 等 | `--provider openai-compat --base-url <url>` |

不同模型的上下文窗口不同，Neocortex 自动调整分块策略：

| 上下文窗口 | 策略 |
|-----------|------|
| 1M+（Gemini、MiniMax） | 单次分析 |
| 128K-200K（Claude、GPT-4o、Kimi） | 最小分块 |
| <128K（DeepSeek 等） | 多次分析 + 合并 |

## 数据与隐私

- **所有数据留在本地。** 画像、笔记、配置都存在 `~/.neocortex/`
- **API Key 本地存储。** 只发送给你选择的 LLM 提供商
- **代码不会上传。** 只有结构化摘要（配置文件、统计信息、关键文件片段）会发给 LLM 分析
- **无遥测。** 不追踪、不分析、不回传

```
~/.neocortex/
├── config.json          # LLM 配置与 API Key（加密）
├── profile.json         # 技能画像
└── notes/               # 知识库
    ├── ddia-ch8-事务.md
    ├── ddia-ch12-流处理.md
    └── ...
```

## 路线图

- [ ] CLI 核心框架
- [ ] 多 LLM 提供商支持
- [ ] 本地项目扫描
- [ ] 技能画像生成
- [ ] URL 内容获取与个性化笔记
- [ ] PDF 解析支持
- [ ] 聊天记录导入（ChatGPT / Claude）——从你的 AI 对话历史中学习
- [ ] GitHub OAuth——直接扫描远程仓库
- [ ] 画像变化追踪——看到技能成长轨迹
- [ ] 学习路径推荐——"我下一步该学什么？"
- [ ] 交互式问答——带着你的画像上下文提问
- [ ] 插件系统——社区贡献的技能提取器
- [ ] 多语言支持（English、中文）

## 贡献

欢迎贡献！请提交 Issue 或 Pull Request。

## 许可证

MIT License. 详见 [LICENSE](LICENSE)。
