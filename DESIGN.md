# Neocortex — 技术设计文档

## 1. 系统架构

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                     │
│              (typer + rich)                       │
│  scan | import | profile | read | notes | config  │
└──────────┬──────────┬──────────┬────────────────┘
           │          │          │
    ┌──────▼──┐  ┌────▼────┐  ┌──▼───────┐  ┌─▼──────────┐
    │ Scanner │  │ Reader  │  │ Importer │  │   Config    │
    │         │  │         │  │          │  │   Manager   │
    └──────┬──┘  └────┬────┘  └────┬─────┘  └─────────────┘
           │          │            │
    ┌──────▼──────────▼────────────▼─┐
    │     Profile Manager     │
    │  (skill model + gaps)   │
    └──────────┬──────────────┘
               │
    ┌──────────▼──────────────┐
    │     LLM Adapter Layer    │
    │  ┌─────────────────────┐ │
    │  │  Anthropic (Claude) │ │
    │  │  OpenAI (GPT)       │ │
    │  │  Google (Gemini)    │ │
    │  │  OpenAI-Compat      │ │
    │  │  (Kimi/MiniMax/...) │ │
    │  └─────────────────────┘ │
    └──────────────────────────┘
               │
    ┌──────────▼──────────────┐
    │     Local Storage        │
    │  ~/.neocortex/           │
    │  ├── config.json         │
    │  ├── profile.json        │
    │  └── notes/*.md          │
    └──────────────────────────┘
```

## 2. 核心模块设计

### 2.1 CLI Layer (`cli.py`)

框架选型：**Typer**（基于 Click，自动生成帮助文档）+ **Rich**（终端美化）

```python
import typer
from rich.console import Console

app = typer.Typer(help="Neocortex — AI-powered developer learning assistant")
console = Console()

@app.command()
def init():
    """First-time setup: role, experience, goals, language."""

@app.command()
def scan(paths: list[str], update: bool = False):
    """Scan local projects to build/update your skill profile."""

@app.command()
def profile(export: str = None, json: bool = False, edit: bool = False):
    """View, export, or edit your skill profile."""

@app.command()
def read(source: str, focus: str = None, question: str = None):
    """Read a URL/file and generate personalized notes."""

@app.command()
def import_data(source: str, path: str, clear: bool = False):
    """Import chat history (chatgpt/claude) to enrich your profile."""

@app.command()
def notes(search: str = None):
    """List or search your knowledge base."""

@app.command()
def config(provider: str = None, api_key: str = None, base_url: str = None,
           model: str = None, language: str = None):
    """Configure LLM provider, API key, and preferences."""
```

### 2.2 Scanner (`scanner/`)

**职责：** 扫描本地项目，提取结构化信息，生成技能画像。

**关键设计：不把源码直接喂给 LLM。** 先用规则提取，再让 LLM 分析摘要。

```
scanner/
├── __init__.py
├── project.py      # 项目扫描器
├── extractors.py   # 各语言/框架的信息提取器
├── analyzer.py     # LLM 分析，生成技能评估
└── profile.py      # 技能画像管理（读写 profile.json）
```

#### 扫描流程

```
Step 1: 识别项目类型
  - 检测配置文件：package.json, requirements.txt, go.mod, build.gradle,
    Cargo.toml, pom.xml, Gemfile, etc.
  - 确定语言、框架、工具链

Step 2: 统计代码量
  - 按语言统计行数和文件数（排除 node_modules, venv, .git 等）
  - 识别项目规模等级

Step 3: 提取关键文件内容
  - 数据模型/Schema（models.py, schema.prisma, migrations/）
  - 路由/API（urls.py, routes/, handlers/）
  - 配置（docker-compose, nginx.conf, CI/CD）
  - 测试（test 目录的结构和覆盖范围）
  - 每个文件只取前 100 行 + 类/函数签名

Step 4: 架构信号检测
  - 微服务数量（多个独立 server/service 目录）
  - 数据库类型（连接字符串、ORM 配置）
  - 消息队列/缓存（Redis, RabbitMQ, Kafka 配置）
  - 第三方集成（支付、社交、云存储等 SDK）
  - 实时通信（WebSocket, Socket.IO）
  - CI/CD（GitHub Actions, GitLab CI）

Step 5: 打包摘要 → 发给 LLM
  - 将以上信息打包成结构化文本（约 2K tokens/项目）
  - LLM 输出结构化的技能评估 JSON
```

#### 技能评估 Prompt 设计

```
你是一个技术能力评估专家。根据以下项目摘要，评估开发者的技能水平。

项目摘要：
{project_summary}

请输出 JSON 格式的技能评估：
- languages: 语言及熟练度（lines, frameworks, patterns）
- domains: 技术领域及深度（evidence, gaps）
- integrations: 第三方集成经验
- architecture: 架构模式经验

对每项技能评估等级：
- beginner: 简单使用，无复杂场景
- proficient: 有实际项目经验，覆盖常见场景
- advanced: 深度使用，处理过复杂问题
- expert: 大规模生产环境，多项目验证

重要：也要指出可能的知识盲区（gaps），基于项目中缺失的最佳实践。
```

#### 多项目合并

扫描多个项目时，需要合并技能评估：

```python
def merge_profiles(profiles: list[SkillProfile]) -> SkillProfile:
    """
    合并策略：
    - 同一技能取最高等级
    - 代码行数累加
    - evidence 合并去重
    - gaps 取交集（多个项目都缺的才算真的缺）
    - projects 列表合并
    """
```

### 2.3 Importer (`importer/`)

**职责：** 导入用户在 ChatGPT / Claude 等平台的聊天记录，从中提取学习轨迹和知识盲区，补充到用户画像。

灵感来源：[dashhuang/openclaw-chat-history-import](https://github.com/dashhuang/openclaw-chat-history-import)

```
importer/
├── __init__.py
├── chatgpt.py      # ChatGPT conversations.json 解析
├── claude.py       # Claude 导出文件解析
├── extractor.py    # LLM 提取聊天洞察
└── merger.py       # 将洞察合并到 profile
```

#### 为什么聊天记录有价值

代码分析告诉我们"你做过什么"，聊天记录告诉我们"你卡在哪里"：

| 你问 AI 的问题 | 暴露的信息 |
|---------------|-----------|
| "Redis Pub/Sub 怎么保证消息不丢" | 在用 Pub/Sub，但对可靠性不确定 |
| "FastAPI 依赖注入怎么写" | 在学 FastAPI，还在入门 |
| "PostgreSQL 和 MySQL 隔离级别区别" | 知道事务但理解不深 |
| "帮我优化这个 SQL 查询" | SQL 能写但性能优化是弱项 |

**你问过什么 = 你不确定什么。** 这比代码分析更精准地定位知识盲区。

#### 使用方式

```bash
# 导入 ChatGPT 聊天记录
# （从 ChatGPT Settings → Data Controls → Export 获取）
neocortex import --source chatgpt ~/Downloads/conversations.json

# 导入 Claude 聊天记录
# （从 Claude Settings → Privacy → Export data 获取）
neocortex import --source claude ~/Downloads/claude-export/

# 导入后自动分析并更新画像
```

#### 导入流程

```
Step 1: 解析导出文件
  ChatGPT → conversations.json（标准 JSON，包含所有对话）
  Claude  → conversations.json + memories.json + projects.json

Step 2: 提取用户发送的消息
  - 只取用户侧的消息（user role），忽略 AI 回复
  - 按时间排序
  - 过滤过短/无意义的消息（"ok", "好的", "继续"）

Step 3: 分批发送给 LLM 分析
  - 每批约 50 条消息（控制 token 消耗）
  - LLM 提取结构化洞察

Step 4: 合并到 profile.json
  - 与代码分析结果交叉验证
  - 更新 gaps 和 confusion_points
```

#### 提取 Prompt

```
你是一个开发者能力分析专家。以下是一个开发者与 AI 助手的对话历史（仅用户侧消息）。

请分析这些对话，提取以下信息：

1. questions_asked: 用户提出的技术问题，标注主题和难度级别
   - topic: 技术主题（如 redis, fastapi, react, sql）
   - level: 问题体现的水平（beginner/intermediate/advanced）
   - date: 大致日期

2. topics_discussed: 用户讨论过的技术领域

3. confusion_points: 用户明确表示困惑或反复追问的点

4. growth_trajectory: 从对话时间线推断的学习方向
   （例：从前端问题逐渐转向系统设计）

只提取与技术学习相关的内容，忽略闲聊。
输出 JSON 格式。

用户消息：
{user_messages}
```

#### 提取结果数据模型

```json
{
  "chat_insights": {
    "source": "chatgpt",
    "imported_at": "2026-03-20",
    "message_count": 1250,
    "date_range": ["2025-06-01", "2026-03-15"],
    "questions_asked": [
      {
        "topic": "redis_reliability",
        "level": "intermediate",
        "date": "2026-01",
        "summary": "Redis Pub/Sub 消息丢失问题"
      },
      {
        "topic": "transaction_isolation",
        "level": "beginner",
        "date": "2026-03",
        "summary": "MySQL 和 PostgreSQL 隔离级别区别"
      }
    ],
    "topics_discussed": [
      "python", "fastapi", "react_native", "redis",
      "payment_integration", "android", "websocket"
    ],
    "confusion_points": [
      "transaction_isolation",
      "kafka_vs_redis_streams",
      "react_native_navigation"
    ],
    "growth_trajectory": "backend_expert → learning_system_design_and_mobile"
  }
}
```

#### 与代码分析的交叉验证

聊天洞察和代码分析相互补充和验证：

```python
def cross_validate(code_profile: dict, chat_insights: dict) -> dict:
    """
    交叉验证逻辑：

    1. 代码说你是 Expert，聊天记录也没问过相关问题
       → 确认 Expert，置信度高

    2. 代码说你是 Expert，但聊天记录里反复问基础问题
       → 降级为 Advanced，可能是照着教程抄的代码

    3. 代码里没出现过，但聊天记录里频繁讨论
       → 标记为"正在学习"的领域

    4. 代码和聊天都没出现
       → 确认为知识盲区
    """
```

#### 隐私设计

- **不存储原始聊天记录。** 只存提取后的结构化洞察（`chat_insights`）
- 原始文件在分析完成后不做任何拷贝
- 用户可随时删除已导入的洞察：`neocortex import --clear`
- LLM 只看到用户侧消息的摘要，不看 AI 回复

### 2.3.1 社交收藏导入（Future）

除了 AI 聊天记录，用户在社交平台上的收藏/书签也是高价值数据源：

```bash
# 导入 Twitter/X 书签
neocortex import --source twitter-bookmarks ~/Downloads/bookmarks.json

# 导入微博收藏
neocortex import --source weibo-favorites ~/Downloads/weibo-favs.json
```

**为什么收藏数据有价值：**

不同数据源揭示用户的不同面：

| 数据源 | 揭示的信息 | 本质 |
|--------|-----------|------|
| 代码仓库 | 你做过什么 | 能力 |
| AI 聊天记录 | 你卡在哪里 | 盲区 |
| 社交收藏 | 你关注什么 | 兴趣 + 方向 + 价值观 |

收藏行为比发布行为更真实——发推/发微博有社交表演成分，收藏是给自己看的，反映真实兴趣。

**提取内容：**

```json
{
  "social_insights": {
    "source": "twitter_bookmarks",
    "interests": ["ai_education", "product_thinking", "system_design"],
    "thought_leaders_followed": ["howie_serious", "indigox"],
    "recurring_themes": [
      "AI 在教育中的应用",
      "个性化学习",
      "独立开发者产品方向"
    ],
    "career_direction_signals": "从技术执行转向产品思考和教育方向"
  }
}
```

此功能优先级较低，放在 Phase 3。核心价值是让画像从"技术能力"扩展到"兴趣方向和价值取向"，使个性化教学更精准。

### 2.4 Reader (`reader/`)

**职责：** 获取内容 → 分块 → 结合画像生成个性化笔记。

```
reader/
├── __init__.py
├── fetcher.py      # 内容获取（URL, PDF, 本地文件）
├── chunker.py      # 智能分块（按章节/token 限制）
└── teacher.py      # 个性化讲解生成
```

#### 获取策略

```python
class ContentFetcher:
    def fetch(self, source: str) -> Document:
        if source.startswith("http"):
            return self._fetch_url(source)      # httpx + readability
        elif source.endswith(".pdf"):
            return self._fetch_pdf(source)       # PyMuPDF
        elif source.endswith(".md"):
            return self._read_markdown(source)
        elif source.endswith(".epub"):
            return self._read_epub(source)       # ebooklib
        else:
            return self._read_text(source)
```

#### 两阶段生成管道

> 参考来源：[OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) 的大纲→场景两阶段架构。
> OpenMAIC 做了精美的课堂模拟（白板、AI 同学辩论、28 种动作），但完全没有个性化——
> 对每个学生讲的都一样。我们取其管道设计，加上画像驱动的个性化。

```
阶段 1：大纲分析（快，省 token）
  → 读取内容，提取章节结构
  → 对照用户画像，标记每个章节：
      ✓ 已知（跳过或一句话带过）
      △ 需要学（正常讲解）
      ★ 重点学（详细展开，用用户项目做类比）
  → 输出个性化阅读大纲（终端预览）
  → 用户确认或调整后，进入阶段 2

阶段 2：逐章生成笔记
  → 按大纲标记分别处理
  → ✓ 已知：一句话总结
  → △ 需要学：正常讲解 + 原理
  → ★ 重点学：详细展开 + 项目类比 + Action Items
  → 合并输出 Markdown 文件
```

好处：
- 用户先看大纲，确认方向对了再生成，不浪费 token
- 大纲阶段只需要内容结构 + 画像比对，token 消耗很低
- 逐章生成可以做流式输出，用户边看边等

```bash
$ neocortex read https://ddia.vonng.com/ch8/

 Analyzing content...

 Personalized outline for: DDIA Chapter 8 - Transactions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✓  ACID Basics                          skip (you know this)
  ✓  Read Committed                       skip (daily practice)
  △  Snapshot Isolation & MVCC            brief overview
  ★  Lost Updates                         deep dive (your MySQL payment system)
  ★  Write Skew & Phantoms               deep dive (restaurant booking, Cutie wallet)
  △  Serializable Isolation              overview with PostgreSQL focus
  ★  Distributed Transactions            deep dive (your payment flow)

? Proceed with this outline? [Y/n/edit]
```

#### 分块策略

根据 LLM 的上下文窗口动态调整：

```python
def chunk_content(doc: Document, max_tokens: int) -> list[Chunk]:
    """
    1. 尝试按标题/章节自然分块
    2. 如果单块超过 max_tokens，按段落二次分块
    3. 每块带上下文：前一块的摘要 + 当前块内容
    4. 标记块的位置信息（第几章第几节）
    """
```

#### 个性化讲解 Prompt

```
你是一个了解学生的私人导师。

学生的技能画像：
{profile_json}

现在学生在阅读以下内容：
{content_chunk}

{focus_instruction}
{question_instruction}

请生成个性化的学习笔记，要求：

1. 跳过学生已经精通的基础概念，不要浪费篇幅
2. 对学生已有经验的领域，用他做过的项目做类比
   例：如果学生做过 Redis Pub/Sub，讲消息队列时直接用他的架构举例
3. 重点展开学生的知识盲区（profile 中的 gaps）
4. 在笔记末尾给出 Action Items：基于学生的实际项目，给出具体可执行的改进建议
5. 难度控制在学生当前水平 +1~+2 的范围，不要跳太远

输出格式：Markdown，结构清晰，适合日后翻阅。
```

### 2.5 LLM Adapter Layer (`llm/`)

**职责：** 统一接口，屏蔽不同 LLM 提供商的差异。

```
llm/
├── __init__.py
├── base.py             # 抽象基类
├── anthropic.py        # Claude
├── openai_compat.py    # OpenAI + 所有兼容服务
└── google.py           # Gemini
```

#### 统一接口

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        """发送对话请求，返回文本响应"""

    @abstractmethod
    def max_context_tokens(self) -> int:
        """返回模型的最大上下文窗口"""

    @abstractmethod
    def name(self) -> str:
        """返回提供商名称"""
```

#### OpenAI 兼容实现

一个实现覆盖大部分国内模型：

```python
class OpenAICompatProvider(LLMProvider):
    """
    支持所有 OpenAI API 兼容的服务：
    - OpenAI (api.openai.com)
    - Kimi (api.moonshot.cn)
    - DeepSeek (api.deepseek.com)
    - MiniMax (api.minimax.chat)
    - Qwen (dashscope.aliyuncs.com)
    - GLM (open.bigmodel.cn)
    - 任何自定义 base_url
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
```

### 2.6 Config Manager (`config.py`)

```python
# ~/.neocortex/config.json
{
    "provider": "claude",
    "api_key": "<encrypted>",          # AES-256 加密
    "base_url": null,                   # OpenAI-compat 专用
    "model": "claude-sonnet-4-6",       # 可选，默认按 provider 选最优
    "scan_settings": {
        "max_file_lines": 100,          # 每个文件最多取多少行
        "exclude_patterns": [           # 扫描时排除的目录
            "node_modules", "venv", ".git", "dist", "build", "__pycache__"
        ]
    },
    "output_settings": {
        "auto_open": true,              # 生成笔记后自动打开
        "notes_dir": "~/.neocortex/notes",
        "language": "zh"                # 笔记语言：zh / en
    }
}
```

## 3. 用户画像体系

Neocortex 从多个维度理解用户，不只是看代码。

### 3.1 画像数据模型

```python
# ~/.neocortex/profile.json
{
    "skills": { ... },              # 代码分析得出（Section 2.2）
    "chat_insights": { ... },        # 聊天记录分析（Section 2.3）
    "persona": {                     # 首次问卷收集
        "role": "full-stack",
        "experience_years": 6,
        "learning_goal": "system_design",
        "learning_style": "compare_with_known",  # 用已有经验做类比
        "language": "zh"
    },
    "learning_history": {            # 自动追踪
        "topics_read": [
            {
                "source": "https://ddia.vonng.com/ch8/",
                "title": "DDIA - 事务",
                "date": "2026-03-20",
                "focus": "isolation",
                "feedback": "just_right"         # 用户反馈
            }
        ],
        "topic_frequency": {         # 统计主题频率，推断兴趣方向
            "distributed_systems": 3,
            "stream_processing": 2,
            "payment": 1
        }
    },
    "calibration": {                 # 难度校准参数
        "level_offset": 0,           # -2 ~ +2，根据反馈自动调整
        "consecutive_too_easy": 0,
        "consecutive_too_hard": 0
    }
}
```

### 3.2 数据来源

```
┌──────────────────────────────────────────────────────────────────────┐
│                         用户画像（Profile）                           │
├──────────────┬──────────────┬──────────────┬──────────────┬─────────┤
│  代码分析     │  AI 聊天记录  │  学习行为     │  首次问卷     │ 交互反馈 │
│  (你做过什么) │  (你卡在哪里) │  (你在学什么) │  (你想成为谁) │ (难度)  │
├──────────────┼──────────────┼──────────────┼──────────────┼─────────┤
│ neocortex    │ neocortex    │ 每次 read    │ neocortex    │ 每篇笔记│
│ scan         │ import       │ 自动记录     │ init         │ 生成后  │
├──────────────┼──────────────┼──────────────┼──────────────┼─────────┤
│ 技能 + 深度  │ 困惑点       │ 当前关注     │ 角色/目标    │ 难度    │
│ 盲区         │ 学习轨迹     │ 主题频率     │ 学习风格     │ 校准    │
│              │ 兴趣方向     │              │ 语言偏好     │         │
└──────────────┴──────────────┴──────────────┴──────────────┴─────────┘
```

### 3.3 首次使用问卷 (`neocortex init`)

安装后首次运行触发，5 个问题，30 秒完成：

```bash
$ neocortex init

 Let's get to know you.

? Your current role?
  > Backend Engineer / Frontend Engineer / Full-stack Engineer
    Student / Self-taught Developer

? Years of programming experience?
  > 0-1 / 1-3 / 3-5 / 5+

? What's your learning goal right now?
  > System design & architecture
    New language/framework
    Interview prep
    Level up at current job
    Building a side project

? How do you prefer to learn?
  > Explain with real code examples
    Theory first, then practice
    Just tell me what to do
    Compare with things I already know

? Preferred language for notes?
  > English / 中文
```

问卷结果存入 `profile.json` 的 `persona` 字段。用户可随时修改：

```bash
neocortex config --language zh    # 切换笔记语言
neocortex config --language en
```

### 3.4 学习行为追踪（被动收集，零打扰）

每次 `neocortex read` 自动记录：

| 行为 | 自动推断 |
|------|----------|
| 读了 DDIA 事务章节 | 在补分布式系统知识 |
| 用了 `--focus "isolation"` | 对隔离级别特别不确定 |
| 连续读了 3 篇 Kafka 文章 | 在调研消息队列方案 |
| 反复读同一个主题 | 这个领域有难度 |

不需要用户主动提供，系统自动记录到 `profile.json` 的 `learning_history`。

### 3.5 交互反馈（持续校准）

每篇笔记生成后，一个按键的轻量反馈：

```bash
 Note saved: ~/.neocortex/notes/ddia-ch8.md

? How was this note?  [1] Too easy  [2] Just right  [3] Too hard  [4] Skip
```

校准逻辑：

```python
def calibrate(feedback: str, calibration: dict) -> dict:
    if feedback == "too_easy":
        calibration["consecutive_too_easy"] += 1
        calibration["consecutive_too_hard"] = 0
        if calibration["consecutive_too_easy"] >= 2:
            calibration["level_offset"] = min(calibration["level_offset"] + 1, 2)
            calibration["consecutive_too_easy"] = 0
    elif feedback == "too_hard":
        calibration["consecutive_too_hard"] += 1
        calibration["consecutive_too_easy"] = 0
        if calibration["consecutive_too_hard"] >= 2:
            calibration["level_offset"] = max(calibration["level_offset"] - 1, -2)
            calibration["consecutive_too_hard"] = 0
    else:  # just_right
        calibration["consecutive_too_easy"] = 0
        calibration["consecutive_too_hard"] = 0
    return calibration
```

连续 2 次"太简单"→ 自动提升难度；连续 2 次"太难"→ 自动降低。单次波动不调整，避免过度反应。

### 3.6 多语言支持（i18n）

默认英文，支持中文切换。影响范围：

| 组件 | 英文 | 中文 |
|------|------|------|
| CLI 提示信息 | `Scanning project...` | `正在扫描项目...` |
| 技能画像输出 | `Expert` | `精通` |
| 笔记内容 | LLM 用英文 Prompt | LLM 用中文 Prompt |
| 反馈提示 | `How was this note?` | `这篇笔记怎么样？` |

实现方式：Prompt 中注入语言指令，CLI 文本用 dict 映射。

```python
LANG = {
    "en": {
        "scanning": "Scanning project...",
        "note_saved": "Note saved:",
        "feedback_prompt": "How was this note?",
        "too_easy": "Too easy",
        "just_right": "Just right",
        "too_hard": "Too hard",
        "skip": "Skip",
    },
    "zh": {
        "scanning": "正在扫描项目...",
        "note_saved": "笔记已保存：",
        "feedback_prompt": "这篇笔记怎么样？",
        "too_easy": "太简单",
        "just_right": "刚好",
        "too_hard": "太难",
        "skip": "跳过",
    }
}
```

笔记语言通过 Prompt 控制：

```python
language_instruction = {
    "en": "Output the note in English.",
    "zh": "请用中文输出笔记。",
}
```

## 4. 依赖清单

```toml
[project]
name = "neocortex-ai"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    # CLI
    "typer>=0.15.0",
    "rich>=13.0.0",

    # LLM Providers
    "anthropic>=0.52.0",
    "openai>=1.60.0",
    "google-genai>=1.0.0",

    # Content Fetching
    "httpx>=0.28.0",
    "readability-lxml>=0.8.0",       # HTML → 正文提取
    "pymupdf>=1.25.0",               # PDF 解析

    # Utilities
    "tiktoken>=0.8.0",               # Token 计数（OpenAI tokenizer）
    "cryptography>=44.0.0",          # API Key 加密
    "pydantic>=2.0.0",               # 数据模型
]
```

## 5. 关键技术决策

### Q: 为什么不直接把整个项目源码喂给 LLM？

**A:** 成本和效率。一个中等项目可能有 10 万行代码，喂给 Claude 要花 $5+。
而且大部分代码（业务逻辑细节）对技能评估没价值。
用规则先提取关键信息（配置文件、代码统计、架构信号），
压缩到约 2K tokens/项目，成本降到 $0.05 以下，分析质量反而更好。

### Q: 为什么选 Python 而不是 Go 或 Node？

**A:** 这个工具 90% 的工作是跟 LLM 对话，瓶颈是 API 网络延迟（1-10 秒），不是本地执行速度。
在这个前提下，Python 的优势是碾压级的：
1. LLM SDK 生态：anthropic、openai、google-genai 三家官方 SDK 都是 Python-first
2. 文件解析库：PyMuPDF（PDF）、readability-lxml（HTML）、tiktoken（token 计数）都是 Python 库
3. 开发速度：一个人做的项目，用最熟的语言最高效

分发方式用 `uv pip install neocortex-ai` 或 `uvx neocortex-ai`（即用即跑，无需安装）。
uv 比 pip 快 10-100 倍，且自动管理 Python 版本和虚拟环境。

### Q: 为什么用 Typer 而不是 Click？

**A:** Typer 基于 Click，但自动类型推断更方便，且与 Rich 集成好。
CLI 工具的体验很重要，Rich 的表格、进度条、语法高亮能让输出好看很多。

### Q: 为什么 API Key 要加密存储？

**A:** 开源项目用户的 Key 存在本地文件里，如果明文存储，
任何能读取用户 home 目录的程序/脚本都能偷走。AES 加密不是万无一失，
但至少不是裸奔。加密密钥可以用机器指纹（MAC 地址 + hostname hash）。

### Q: 技能画像的评估准确吗？

**A:** 不可能 100% 准确，但够用。关键设计：
1. 画像生成后让用户确认/修正（`neocortex profile --edit`）
2. 多项目扫描时交叉验证（一个项目可能是抄的，三个项目说明是真会）
3. gaps 的判断比 skills 的判断更有价值——"你没做过什么"比"你做过什么"更客观

### Q: 为什么笔记输出为 Markdown 而不是其他格式？

**A:** Markdown 是程序员的通用语。可以用 Obsidian 管理知识库，
可以推到 GitHub 做版本控制，可以用任何编辑器打开。
未来如果需要更丰富的格式，可以加 `--format html` 选项。

## 6. 项目结构

```
neocortex/
├── README.md
├── DESIGN.md               # 本文档
├── LICENSE
├── pyproject.toml
├── src/
│   └── neocortex/
│       ├── __init__.py
│       ├── cli.py           # CLI 入口
│       ├── config.py        # 配置管理
│       ├── scanner/
│       │   ├── __init__.py
│       │   ├── project.py   # 项目扫描
│       │   ├── extractors.py # 信息提取（按语言/框架）
│       │   ├── analyzer.py  # LLM 技能分析
│       │   └── profile.py   # 技能画像 CRUD
│       ├── importer/
│       │   ├── __init__.py
│       │   ├── chatgpt.py   # ChatGPT 导出解析
│       │   ├── claude.py    # Claude 导出解析
│       │   ├── extractor.py # LLM 聊天洞察提取
│       │   └── merger.py    # 洞察合并到画像
│       ├── reader/
│       │   ├── __init__.py
│       │   ├── fetcher.py   # URL/PDF/文件获取
│       │   ├── chunker.py   # 内容分块
│       │   └── teacher.py   # 个性化笔记生成
│       └── llm/
│           ├── __init__.py
│           ├── base.py      # 抽象接口
│           ├── anthropic.py # Claude 适配
│           ├── openai_compat.py # OpenAI 兼容适配
│           └── google.py    # Gemini 适配
└── tests/
    ├── test_scanner.py
    ├── test_reader.py
    └── test_llm.py
```

## 7. 开发路线

### Phase 1: MVP（核心链路跑通）
- [x] CLI 框架 + config 命令
- [x] `neocortex init` 首次问卷（含语言选择）
- [x] 多语言支持（en / zh），CLI 文本 + Prompt 语言切换
- [x] OpenAI-compat LLM 适配（先支持一种，覆盖最多模型）
- [x] 项目扫描器（Python/JS/Go 三种语言）
- [x] 技能画像生成
- [x] URL 内容获取 + 个性化笔记生成
- [x] 笔记反馈 + 难度校准
- [x] 学习行为自动追踪
- [x] Markdown 输出 + 自动打开

### Phase 2: 完善
- [x] Claude + Gemini 适配
- [x] PDF 解析支持
- [x] 聊天记录导入（ChatGPT / Claude）
- [x] 聊天洞察与代码分析交叉验证
- [x] 更多语言的扫描器（Java, Rust, Kotlin, Swift, C#, Ruby, PHP, Dart）
- [x] 画像手动编辑（`neocortex profile --edit`）
- [x] 笔记搜索

### Phase 3: 进阶
- [ ] GitHub OAuth 远程仓库扫描
- [ ] 技能成长追踪（profile diff over time）
- [ ] 学习路径推荐（"What should I learn next?"）
- [ ] 交互式问答模式
- [ ] AI Agent 集成（作为 Claude Code / OpenClaw skill 被调用）
- [ ] 社交收藏导入（Twitter 书签 / 微博收藏）
- [ ] 更多 UI 语言支持
- [ ] 音频输出（TTS，"听课模式"）

### Phase 4: 多模态输出（条件触发）
- [ ] 动画/白板讲解生成（需学生版数据验证需求后再启动）

## 8. 多模态输出策略

> 参考来源：[NotebookLM](https://notebooklm.google.com/)（音频播客）、[OpenMAIC](https://github.com/THU-MAIC/OpenMAIC)（动画白板）

### 8.1 结论：Phase 1 不做，Phase 3 启动音频，Phase 4 视数据决定动画

NotebookLM 能生成音频播客，OpenMAIC 能生成动画白板讲解。但 Neocortex 当前阶段不做多模态输出。

**不急着做的原因：**

1. **核心价值未验证。** Neocortex 的核心是"了解你 → 教你需要的"。个性化引擎还没跑通，多模态是锦上添花
2. **工程量与一人团队不匹配。** TTS 需接外部服务，动画需要渲染引擎，分散精力
3. **CLI 形态不适合。** 当前产品是 CLI + Markdown，音频/动画天然更适合 App/Web

**但长远有价值的原因：**

1. **学生版刚需。** 学生不看 Markdown，但会听音频、看动画。App 形态下多模态是必需品
2. **NotebookLM 验证了需求。** 播客式音频学习有真实受众（通勤、运动等场景）
3. **个性化 + 多模态 = 真壁垒。** NotebookLM 的音频不个性化，OpenMAIC 的动画不个性化。"基于你的画像生成个性化音频/动画讲解"是独一无二的组合

### 8.2 渐进式多模态路线

```
Phase 1 (MVP):   Markdown 笔记（当前）
Phase 2:         学生版 Web/App 上线
Phase 3:         音频输出（TTS，最低成本的多模态扩展）
Phase 4:         动画/白板讲解（需学生版数据验证需求）
```

**为什么音频是最优先的多模态扩展：**

- 实现成本低：个性化笔记文本 → TTS API → 音频文件，管道最短
- 不需要自建模型：接 ElevenLabs / Fish Audio / Edge TTS 即可
- 场景明确：通勤听课、运动听课、睡前复习
- 学生版的"听课模式"可以作为付费差异化功能

```bash
# 开发者版（Phase 3）
neocortex read https://ddia.vonng.com/ch8/ --audio
# → 生成 ~/.neocortex/notes/ddia-ch8.md + ddia-ch8.mp3

# 学生版（App 内）
# 点击"听课模式" → 播放个性化音频讲解
```

**动画为什么排在最后：**

- 工程复杂度高 10 倍：需要白板渲染、图形生成、时间轴同步
- 投入产出不确定：需要学生版积累使用数据后，确认动画对学习效果有显著提升
- 等 AI 视频生成技术成熟后成本会大幅下降

### 8.3 竞品多模态对比

| 产品 | 了解用户 | 文本 | 音频 | 动画 | 个性化 |
|------|:---:|:---:|:---:|:---:|:---:|
| NotebookLM | ❌ | ✅ | ✅ | ❌ | ❌ |
| OpenMAIC | ❌ | ✅ | ❌ | ✅ | ❌ |
| Khan Academy | ❌ | ✅ | ❌ | ✅（人工录制） | ❌ |
| Khanmigo | ❌ | ✅ | ❌ | ❌ | 弱 |
| **Neocortex Phase 1** | **✅** | **✅** | ❌ | ❌ | **✅** |
| **Neocortex Phase 3+** | **✅** | **✅** | **✅** | 待定 | **✅** |

核心差异：**只有 Neocortex 能做到"个性化 × 多模态"的组合。** 其他产品要么有多模态但千人一面，要么有弱个性化但只有文本。

## 9. 存储架构演进

> 参考来源：[OpenClaw Memory](https://docs.openclaw.ai/concepts/memory)、[memsearch](https://github.com/zilliztech/memsearch)、[Local-First RAG with SQLite](https://www.pingcap.com/blog/local-first-rag-using-sqlite-ai-agent-memory-openclaw/)

### 9.1 三阶段演进

**Phase 1（MVP）：纯文件**

```
~/.neocortex/
├── config.json          # LLM 配置
├── profile.json         # 技能画像 + 学习历史 + 校准参数
└── notes/               # Markdown 笔记
```

够用。简单、无依赖、数据完全在用户手里。

**Phase 2：JSON + SQLite 混合搜索**

```
~/.neocortex/
├── config.json
├── profile.json
├── neocortex.sqlite     # 新增：FTS5 全文 + sqlite-vec 向量，混合搜索
└── notes/               # Markdown 依然是源头
```

SQLite 只做索引层，Markdown 是源文件。删掉 .sqlite 重新 `neocortex index` 即可重建。

直接上混合搜索（FTS5 + sqlite-vec），不做"先全文后语义"的递进。原因：
- 用户已经配了 LLM API Key，embedding 零额外配置
- 本地 embedding（ONNX bge-m3）也很成熟，不需要 API Key
- sqlite-vec 只是一个 SQLite 扩展，不是独立服务，不重
- 全文搜索和语义搜索的体验差距是"好用"和"不好用"的区别

新增能力：
- 语义搜索（"并发写入怎么保证一致性" → 找到事务章节笔记）
- 全文搜索（精确关键词匹配）
- 混合排名（BM25 + 向量余弦相似度加权融合）
- 读新内容时自动关联历史笔记
- 画像评估的依据追溯

### 9.2 为什么 MVP 不上 SQLite

- MVP 阶段笔记数量少（<20 篇），遍历文件就够了
- 减少依赖，降低安装门槛
- 先验证核心价值（个性化讲解），再优化搜索体验

### 9.3 为什么选 SQLite 而不是其他方案

OpenClaw 生态验证了 SQLite 做本地 AI 记忆存储的可行性：

| 方案 | 优点 | 缺点 | 适合 Neocortex？ |
|------|------|------|:---:|
| **SQLite + FTS5 + sqlite-vec** | 单文件、全文+语义搜索、零服务依赖 | 需加载扩展 | Phase 2 ✅ |
| **memsearch (Milvus)** | 开箱即用、混合搜索 | 依赖重 | ❌ 太重 |
| **Chroma** | 向量搜索好用 | 额外进程 | ❌ 违背单文件原则 |
| **PostgreSQL** | 功能全 | 需要运行服务 | ❌ 违背本地优先 |
| **纯 JSON** | 最简单 | 搜索差、规模上限低 | Phase 1 ✅ |

核心原则：**Markdown 是源头，SQLite 只是索引。** 数据永远是人可读、git 友好的。

### 9.4 渐进式检索（参考 claude-mem）

> 参考来源：[claude-mem](https://github.com/thedotmack/claude-mem) 的三层检索设计

claude-mem 搜索记忆时用三层渐进式检索，实现 10 倍 token 节省：

```
Layer 1: search       → 紧凑索引（~50-100 tokens）→ 先看有没有相关的
Layer 2: timeline     → 时间线上下文            → 确认具体是哪些
Layer 3: get_details  → 完整内容（~500-1000 tokens）→ 拿到细节
```

Neocortex 的 `read` 两阶段管道已经体现了这个思路（大纲→详细笔记），
在笔记搜索中也应该采用类似策略：

```bash
# Layer 1：搜索标题和摘要（快，省 token）
neocortex notes --search "事务隔离"
# → ddia-ch8-transactions.md (2026-03-20) — 丢失更新、写偏差、分布式事务

# Layer 2：查看某篇笔记的大纲
neocortex notes --outline ddia-ch8-transactions.md
# → 显示标题结构和关键要点

# Layer 3：打开完整内容
neocortex notes --open ddia-ch8-transactions.md
```

### 9.5 潜在数据源扩展

claude-mem 记录了用户在 Claude Code 里的所有操作历史。
如果用户同时安装了 claude-mem 和 Neocortex，claude-mem 的数据可以作为额外的画像来源：

```bash
# Future: 从 claude-mem 导入 AI 编程行为数据
neocortex import --source claude-mem ~/.claude-mem/data/
```

这比导入聊天记录更精准——它记录的是你实际的编程行为，而不只是对话。
优先级低，放在 Phase 3 之后。

## 10. CLI 设计参考

> 参考来源：[Obsidian CLI](https://obsidian.md/cli)、[Notion CLI (4ier)](https://github.com/4ier/notion-cli)

### 10.1 从 Obsidian CLI 和 Notion CLI 学到的

| 设计点 | 它们怎么做 | Neocortex 应用 |
|--------|-----------|---------------|
| **输出自动适配** | 终端交互时彩色表格，管道/脚本时自动输出 JSON | `neocortex profile` 终端美观展示，`--json` 给脚本用 |
| **Markdown 双向** | 读出为 Markdown，写入也支持 Markdown | 笔记输出 Markdown，将来支持导入 Markdown 更新画像 |
| **AI Agent 友好** | Notion CLI 专门为 AI Agent 设计了 JSON 输出 + 标准退出码 | Neocortex 可作为 Claude Code / OpenClaw 的 skill 被调用 |
| **URL 和本地路径双格式** | 支持直接粘贴链接，也支持本地 ID | `neocortex read` 同时支持 URL 和本地文件路径 |

### 10.2 输出模式设计

```python
import sys

def output(data: dict, human_format: callable):
    """
    TTY 检测：
    - 终端交互 → 调用 human_format 做彩色/表格输出
    - 管道/脚本 → 输出 JSON
    """
    if sys.stdout.isatty():
        human_format(data)
    else:
        import json
        print(json.dumps(data, ensure_ascii=False, indent=2))
```

所有命令都支持 `--json` 强制 JSON 输出：

```bash
# 终端使用 → 好看的表格
neocortex profile

# 脚本/AI Agent 使用 → JSON
neocortex profile --json

# 管道使用 → 自动 JSON
neocortex profile | jq '.skills.python'
```

### 10.3 AI Agent 集成设计（Future）

Neocortex 可以被 Claude Code、OpenClaw 等 AI Agent 作为 skill 调用。
当用户在 Claude Code 里写代码时，Claude Code 可以查询用户画像，给出更个性化的建议。

```bash
# Claude Code 调用 Neocortex 查询用户画像
neocortex profile --json | jq '.skills'

# Claude Code 调用 Neocortex 为用户读文章
neocortex read https://some-article.com --json --question "跟我的项目有什么关系"
```

场景示例：

```
用户在 Claude Code 里："帮我设计一个消息队列方案"

Claude Code 调用 neocortex profile --json
→ 发现用户 real_time_systems: expert，但 stream_processing_theory: basic

Claude Code 的回答就会跳过 Pub/Sub 基础，
直接讲 Kafka vs Redis Streams 的架构对比，
因为它知道用户已经做过 3 次 Redis Pub/Sub 架构。
```

这让 Neocortex 从一个独立 CLI 工具，变成整个 AI 开发生态的一部分。

### 10.4 与知识库工具的定位区分

Obsidian / Notion 等知识库工具开放 CLI 后，理论上也能做个性化学习。
但它们本质上是 **存储和组织工具**，Neocortex 是 **理解和教学工具**：

```
Obsidian / Notion               Neocortex
━━━━━━━━━━━━━━━━                ━━━━━━━━━━━━━━

存储笔记          ✅              不做
组织知识库        ✅              不做
搜索笔记          ✅              不做
理解用户能力      ❌              ✅  ← 核心差异
分析知识盲区      ❌              ✅
个性化教学        ❌              ✅
难度校准          ❌              ✅
```

Neocortex 生成的笔记可以存进 Obsidian/Notion，两者是互补关系，不是竞争关系。
将来甚至可以做 Obsidian 插件，把 Neocortex 的个性化能力嵌入 Obsidian 的生态里。
