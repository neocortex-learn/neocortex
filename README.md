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
neocortex config --provider claude --api-key sk-xxx
```

### Scan & Learn

```bash
neocortex scan ~/projects/my-app          # Build skill profile
neocortex profile                          # View your profile
neocortex read https://ddia.vonng.com/ch8/ # Personalized notes
neocortex recommend                        # Learning path
neocortex ask "When should I use Raft vs Paxos?"  # Q&A
```

## Commands

### `neocortex init`

First-time setup — role, experience, learning goal, learning style, language.

```bash
neocortex init
```

Interactive prompts walk you through 5 questions. Takes 30 seconds.

### `neocortex config`

Configure LLM provider, API key, GitHub token, and preferences. Run without options to view current config.

```bash
# Set LLM provider
neocortex config --provider claude --api-key sk-xxx

# OpenAI-compatible providers (Kimi, DeepSeek, MiniMax, etc.)
neocortex config --provider openai-compat \
  --api-key sk-xxx \
  --base-url https://api.moonshot.cn/v1 \
  --model moonshot-v1-128k

# Set GitHub token (needed for --github scanning)
neocortex config --github-token ghp_xxx

# Switch output language
neocortex config --language zh
```

**Options:** `--provider`, `--api-key`, `--base-url`, `--model`, `--github-token`, `--language`

### `neocortex scan`

Scan local projects or GitHub repos to build/update your skill profile.

```bash
# Scan local projects
neocortex scan ~/projects/my-app ~/projects/my-api

# Update existing profile (merge, don't replace)
neocortex scan ~/projects/new-project --update

# Scan GitHub repos (requires --github-token in config)
neocortex scan --github octocat           # All repos for a user
neocortex scan --github octocat/my-repo   # Single repo
```

**Options:** `--github <user or user/repo>`, `--update`

### `neocortex profile`

View, export, or edit your skill profile.

```bash
# View profile in terminal
neocortex profile

# Export as JSON
neocortex profile --export profile.json

# Output as JSON to stdout (for piping)
neocortex profile --json

# Open profile.json in your $EDITOR
neocortex profile --edit
```

**Options:** `--export <path>`, `--json`, `--edit`

Example output:

```
 Skill Profile — Updated 2026-03-20
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Languages
  Python        ██████████████████░░  Expert     (85K+ lines, 3 projects)
  TypeScript    ████████████████░░░░  Advanced   (40K+ lines, 2 projects)
  Go            ██████████░░░░░░░░░░  Proficient (3 projects, WebSocket focus)

Domains
  Real-time Systems   ██████████████████░░  Expert  (3x Redis→Go→WS architecture)
  Payment Integration ██████████████████░░  Expert  (9 providers)
```

### `neocortex read`

Read a URL, PDF, or file and generate personalized notes based on your skill profile.

```bash
# Read a web page
neocortex read https://ddia.vonng.com/ch8/

# Read a local PDF
neocortex read ~/books/system-design.pdf

# Focus on a specific topic
neocortex read https://ddia.vonng.com/ch8/ --focus "transaction isolation"

# Read with a question in mind
neocortex read https://some-article.com --question "How does this apply to my payment system?"

# Generate audio version alongside the notes
neocortex read https://some-article.com --audio
```

**Options:** `--focus <topic>`, `--question <text>`, `--audio`

Neocortex shows a personalized outline first (skip/brief/deep dive per section), then generates notes that skip what you know and focus on what matters to you.

### `neocortex import`

Import ChatGPT or Claude chat history to enrich your skill profile. Questions you asked reveal knowledge gaps.

```bash
# Import ChatGPT export (Settings → Data Controls → Export)
neocortex import --source chatgpt ~/Downloads/conversations.json

# Import Claude export (Settings → Privacy → Export data)
neocortex import --source claude ~/Downloads/claude-export/

# Clear previously imported insights
neocortex import --clear
```

**Options:** `--source <chatgpt|claude>`, `--clear`

Privacy: only structured insights are stored, never raw chat logs. See [Data & Privacy](#data--privacy).

### `neocortex notes`

List or search your knowledge base.

```bash
# List all notes (sorted by date)
neocortex notes

# Search notes by keyword
neocortex notes --search "isolation"
```

**Options:** `--search <query>`

### `neocortex recommend`

Get personalized learning path recommendations based on your skill profile and gaps.

```bash
# Get 5 recommendations (default)
neocortex recommend

# Get more recommendations
neocortex recommend --count 10

# Output as JSON
neocortex recommend --json
```

**Options:** `--count <n>`, `--json`

Each recommendation includes a topic, why it matters for you, expected benefit, and suggested resources.

### `neocortex ask`

Ask any question with your skill profile as context. The answer is tailored to your level and references your actual projects.

```bash
neocortex ask "When should I use Raft vs Paxos?"
neocortex ask "How do I add idempotency to my payment flow?"
```

The response is rendered as Markdown in your terminal.

### `neocortex growth`

Track how your skills evolve over time. Each `scan` creates a snapshot; `growth` compares them.

```bash
# View growth summary
neocortex growth

# Output as JSON
neocortex growth --json
```

**Options:** `--json`

Shows new languages learned, skill level-ups, new domains, closed knowledge gaps, and line/project/note counts over time.

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

- [x] Core CLI framework (10 commands)
- [x] Multi-LLM provider support (Claude, OpenAI, Gemini, OpenAI-compat)
- [x] Local project scanning (Python, JS/TS, Go, Java, Kotlin, Swift, Rust, Ruby, PHP, C/C++, C#, Dart)
- [x] Skill profile generation
- [x] URL content fetching & personalized notes
- [x] PDF parsing support
- [x] Chat history import (ChatGPT / Claude)
- [x] GitHub remote repo scanning (`neocortex scan --github`)
- [x] Skill growth tracking (`neocortex growth`)
- [x] Learning path recommendations (`neocortex recommend`)
- [x] Interactive Q&A with profile context (`neocortex ask`)
- [x] Audio output / TTS (`neocortex read --audio`)
- [x] Localization (English, Chinese)
- [x] AI Agent integration (Claude Code commands)
- [ ] Plugin system — community-contributed skill extractors
- [ ] Web/App version (student edition)

## Contributing

Contributions are welcome! Please open an issue or pull request.

## License

MIT License. See [LICENSE](LICENSE) for details.
