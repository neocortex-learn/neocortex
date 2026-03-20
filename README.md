# Neocortex

English | [中文](README.zh-CN.md)

> AI-powered developer skill analyzer & personalized learning assistant.
>
> Scan your projects, build your skill profile, learn what matters to **you**.

Neocortex analyzes your actual code — not your resume — to understand what you know, how deep you know it, and what you're missing. Then when you feed it a book, article, or documentation, it delivers personalized notes that skip what you already know and focus on what you need.

## Why Neocortex?

Every developer learns differently. A senior engineer with 3 production-grade real-time messaging systems doesn't need "What is a WebSocket?" — they need "Your Redis Pub/Sub architecture has a dual-write consistency gap, here's how to fix it."

Existing tools fail here:

| Tool | Knows the content | Knows you | Personalized |
|------|:-:|:-:|:-:|
| NotebookLM | Yes | No | No |
| ChatGPT / Claude | Yes | Barely | No |
| Coursera / Udemy | Yes | No | No |
| **Neocortex** | **Yes** | **Yes** | **Yes** |

The secret: Neocortex reads your code to build a real skill profile, then uses it to teach you at exactly the right level — your [Zone of Proximal Development](https://en.wikipedia.org/wiki/Zone_of_proximal_development).

## Quick Start

### Install

```bash
uv pip install neocortex-ai

# Or run directly without installing
uvx neocortex-ai
```

### Initialize

```bash
neocortex init
```

Answer 5 quick questions (role, experience, learning goal, learning style, language). Takes 30 seconds.

### Configure your LLM

```bash
# Use any LLM provider you prefer
neocortex config --provider claude --api-key sk-xxx

# Or use OpenAI
neocortex config --provider openai --api-key sk-xxx

# Or any OpenAI-compatible provider (Kimi, DeepSeek, MiniMax, etc.)
neocortex config --provider openai-compat \
  --api-key sk-xxx \
  --base-url https://api.moonshot.cn/v1 \
  --model moonshot-v1-128k
```

### Scan your projects

```bash
# Scan one or more local projects
neocortex scan ~/projects/my-app ~/projects/my-api

# See your skill profile
neocortex profile
```

Output:

```
 Skill Profile — Updated 2026-03-20
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Languages
  Python        ██████████████████░░  Expert     (85K+ lines, 3 projects)
  TypeScript    ████████████████░░░░  Advanced   (40K+ lines, 2 projects)
  Go            ██████████░░░░░░░░░░  Proficient (3 projects, WebSocket focus)
  Java          ████████████████░░░░  Advanced   (15+ Android apps)

Frameworks & Tools
  FastAPI       ██████████████████░░  Expert
  Tornado       ██████████████████░░  Expert
  React         ████████████████░░░░  Advanced
  React Native  ████████████░░░░░░░░  Proficient
  Android MVVM  ████████████████░░░░  Advanced

Domains
  Real-time Systems   ██████████████████░░  Expert  (3x Redis→Go→WS architecture)
  Payment Integration ██████████████████░░  Expert  (9 providers)
  Database Design     ████████████████░░░░  Advanced (200+ tables)
  Stream Processing   ████████░░░░░░░░░░░░  Basic   (practical, no theory)
  Distributed Systems ██████░░░░░░░░░░░░░░  Basic   (no formal knowledge)
```

### Learn something

```bash
# Feed it a book chapter URL
neocortex read https://ddia.vonng.com/ch8/

# Feed it a local PDF
neocortex read ~/books/system-design.pdf

# Focus on a specific topic
neocortex read https://ddia.vonng.com/ch8/ --focus "transaction isolation"

# Read with a specific question in mind
neocortex read https://some-article.com --question "How does this apply to my payment system?"
```

Neocortex generates a personalized Markdown note:

```
 Note saved: ~/.neocortex/notes/ddia-ch8-transactions.md
 Opening...
```

The note skips what you already know, highlights what's new and relevant, and maps concepts to your actual code and projects.

### Import your AI chat history (optional)

Your past conversations with ChatGPT/Claude reveal what you struggled with — questions you asked = things you weren't sure about. Neocortex extracts these insights to sharpen your skill profile.

```bash
# Import ChatGPT history (Settings → Data Controls → Export)
neocortex import --source chatgpt ~/Downloads/conversations.json

# Import Claude history (Settings → Privacy → Export data)
neocortex import --source claude ~/Downloads/claude-export/
```

Privacy: only structured insights are stored, never raw chat logs. See [Data & Privacy](#data--privacy).

### Set your language

```bash
# Default is English. Switch to Chinese:
neocortex config --language zh

# Switch back to English:
neocortex config --language en
```

This affects CLI messages, note output, and LLM prompts.

### Manage your knowledge base

```bash
# List all notes
neocortex notes

# Search notes
neocortex notes --search "isolation"

# Re-scan projects to update profile
neocortex scan ~/projects/new-project --update

# Export profile as JSON
neocortex profile --export profile.json
```

## How It Works

### 1. Smart Project Scanning

Neocortex doesn't feed your entire codebase to the LLM. It extracts key signals efficiently:

```
Project Directory
    ↓
1. Config Detection     → package.json, requirements.txt, go.mod, build.gradle
2. Code Statistics      → Lines by language, file count, project structure
3. Key File Sampling    → Models, handlers, routes, schemas, tests
4. Architecture Signals → Design patterns, integrations, infrastructure
    ↓
Structured Summary (~2K tokens per project)
    ↓
LLM Analysis → Skill Profile (JSON)
```

This keeps costs low — scanning a project typically costs less than $0.05.

### 2. Skill Profile Model

Your profile captures three dimensions:

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
        "Built Redis Pub/Sub → Go WebSocket → Client architecture 3 times",
        "Implemented Socket.IO v1 and v4 protocols",
        "Room-based broadcasting with multiple namespaces"
      ],
      "gaps": [
        "No formal stream processing theory (event time vs processing time)",
        "No experience with Kafka or similar log-based message brokers"
      ]
    }
  },
  "integrations": {
    "payment": {
      "providers": ["stripe", "paypal", "cardpointe", "authorize.net", "pax"],
      "level": "expert",
      "gaps": ["No idempotency keys in payment flow"]
    }
  }
}
```

### 3. Personalized Reading (Two-Stage Pipeline)

When you feed Neocortex an article or book chapter, it runs a two-stage pipeline:

**Stage 1 — Outline Analysis** (fast, low cost):
1. Fetches and parses the content
2. Extracts chapter/section structure
3. Maps each section against your profile: `✓ skip` / `△ brief` / `★ deep dive`
4. Shows you a personalized outline for confirmation

**Stage 2 — Note Generation**:
5. Generates notes section by section, at your level
6. Uses your projects as reference points for analogies
7. Highlights action items — concrete things to check in your code
8. Saves as Markdown — opens in your preferred editor/viewer

Example: Two developers read the same DDIA chapter on transactions.

**Developer A** (junior, only used SQLite):
> "A transaction groups multiple operations into one atomic unit. Think of it like this: if you're transferring money, you need both the deduction and the addition to succeed, or neither should happen..."

**Developer B** (you, with 9 payment integrations):
> "Your MySQL restaurant project doesn't auto-detect lost updates — unlike PostgreSQL in Cutie. Check your `paymentWrap.py`: if two POS terminals process the same order concurrently without `SELECT FOR UPDATE`, you have a race condition..."

Same content. Completely different output. That's the point.

## Supported LLM Providers

Bring your own API key. Your key stays local in `~/.neocortex/config.json`.

| Provider | Models | Config |
|----------|--------|--------|
| **Anthropic** | Claude Opus, Sonnet, Haiku | `--provider claude` |
| **OpenAI** | GPT-4o, GPT-4.1, o3 | `--provider openai` |
| **Google** | Gemini 2.5 Pro/Flash | `--provider gemini` |
| **OpenAI Compatible** | Kimi, MiniMax, DeepSeek, Qwen, GLM, etc. | `--provider openai-compat --base-url <url>` |

Different models have different context windows. Neocortex automatically adjusts its chunking strategy:

| Context Window | Strategy |
|----------------|----------|
| 1M+ (Gemini, MiniMax) | Single-pass analysis |
| 128K-200K (Claude, GPT-4o, Kimi) | Minimal chunking |
| <128K (DeepSeek, etc.) | Multi-pass with merge |

## Data & Privacy

- **All data stays local.** Profile, notes, and config are stored in `~/.neocortex/`
- **API keys are stored locally.** Never transmitted anywhere except to the LLM provider you chose
- **Your code is not uploaded.** Only structured summaries (config files, stats, key file excerpts) are sent to the LLM for analysis
- **No telemetry.** No tracking, no analytics, no phone-home

```
~/.neocortex/
├── config.json          # LLM provider & API key (encrypted)
├── profile.json         # Your skill profile
└── notes/               # Your knowledge base
    ├── ddia-ch8-transactions.md
    ├── ddia-ch12-stream-processing.md
    └── ...
```

## Roadmap

- [ ] Core CLI framework
- [ ] Multi-LLM provider support
- [ ] Local project scanning
- [ ] Skill profile generation
- [ ] URL content fetching & personalized notes
- [ ] PDF parsing support
- [ ] Chat history import (ChatGPT / Claude) — learn from your past AI conversations
- [ ] GitHub OAuth — scan remote repos directly
- [ ] Profile diff — track skill growth over time
- [ ] Learning path generation — "What should I learn next?"
- [ ] Interactive mode — Q&A with context of your profile
- [ ] Plugin system — community-contributed skill extractors
- [ ] Localization (English, Chinese)

## Contributing

Contributions are welcome! Please open an issue or pull request.

## License

MIT License. See [LICENSE](LICENSE) for details.
