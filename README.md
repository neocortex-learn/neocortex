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

### Initialize & Configure

```bash
neocortex profile init                                # First-time setup (30 seconds)
neocortex profile config --provider claude --api-key sk-xxx  # Set LLM provider
```

### Scan & Learn

```bash
neocortex profile scan ~/projects/my-app              # Build skill profile
neocortex profile                                     # View your profile
neocortex read https://ddia.vonng.com/ch8/            # Personalized notes
neocortex learn recommend                             # Learning path
neocortex ask "When should I use Raft vs Paxos?"      # Q&A with profile context
```

## Commands

### Top-Level Commands

| Command | Description |
|---------|-------------|
| `neocortex read <source>` | Read a URL/PDF/EPUB and generate personalized notes |
| `neocortex ask <question>` | Ask a question (or `--chat` for a session) with profile context |
| `neocortex review` | Spaced repetition flashcard review (SM-2) |
| `neocortex clip <source>` | Capture a fragment (tweet, thought, bookmark) to your knowledge base |
| `neocortex inbox` | Manage captured clips (`--process`, `--auto`, `--synthesize`) |
| `neocortex daily` | Daily briefing — resurfaced clips + due reviews |

### `profile` — Profile Management

| Command | Description |
|---------|-------------|
| `neocortex profile` | View your skill profile (`--export`, `--json`, `--edit`) |
| `neocortex profile init` | First-time setup: role, experience, goals, language |
| `neocortex profile config` | Configure LLM provider, API key, and preferences |
| `neocortex profile scan` | Scan local projects or GitHub repos (`--github`, `--update`) |
| `neocortex profile import` | Import ChatGPT/Claude chat history to enrich profile |

### `kb` — Knowledge Base

| Command | Description |
|---------|-------------|
| `neocortex kb notes` | List or search your notes (`--search`) |
| `neocortex kb card` | Generate a visual PNG card from a note |
| `neocortex kb compile` | Compile notes into a linked concept wiki |
| `neocortex kb lint` | Run health checks on your knowledge base (7 checks + `--fix`) |
| `neocortex kb map` | Generate a Mermaid concept map (`--domain`, `--around`) |

### `learn` — Learning Path & Progress

| Command | Description |
|---------|-------------|
| `neocortex learn recommend` | Personalized learning recommendations (`--plan`, `--count`) |
| `neocortex learn opportunities` | Find open source & job opportunities matching your skills |
| `neocortex learn digest` | Generate a learning digest for a time period (`--days`) |

### `discover` — Content Discovery

| Command | Description |
|---------|-------------|
| `neocortex discover explore <url>` | Explore an author's articles and rank by relevance |
| `neocortex discover research <topic>` | Search the web for articles related to your skill gaps |
| `neocortex discover feed` | Manage RSS feeds and discover relevant articles |

For detailed usage of each command, see [docs/COMMANDS.md](docs/COMMANDS.md).

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

### 2. Personalized Reading (Two-Stage Pipeline)

**Stage 1 — Outline Analysis** (fast, low cost):
1. Fetches and parses the content (URL, PDF, EPUB, WeChat articles)
2. Maps each section against your profile: `✓ skip` / `△ brief` / `★ deep dive`
3. Shows you a personalized outline for confirmation

**Stage 2 — Note Generation**:
4. Generates notes at your level with Mermaid diagrams
5. Uses your projects as reference points for analogies
6. Extracts flashcards for spaced repetition
7. Triggers incremental concept compilation

Three reading depths: `--scan` (quick triage), default (standard), `--deep` (8-dimension anatomy).

### 3. Knowledge Compilation

Notes are raw material; concepts are knowledge assets. After each reading:

- **Concept extraction** — LLM identifies concepts from notes
- **Wiki generation** — Each concept gets a dedicated entry with sources, relationships, and open questions
- **Wikilink insertion** — Notes are enriched with `[[concept]]` links (Obsidian-compatible)
- **INDEX.md** — LLM-maintained knowledge map with coverage and mastery levels

### 4. Knowledge Confidence Decay

Based on Hidalgo's research (~50% annual decay rate), concept confidence decays over time. The system resurfaces decaying concepts through reviews, daily briefings, and lint reports.

## Supported LLM Providers

Bring your own API key. Your key stays local in `~/.neocortex/config.json`.

| Provider | Models | Config |
|----------|--------|--------|
| **Anthropic** | Claude Opus, Sonnet, Haiku | `--provider claude` |
| **OpenAI** | GPT-4o, GPT-4.1, o3 | `--provider openai` |
| **Google** | Gemini 2.5 Pro/Flash | `--provider gemini` |
| **OpenAI Compatible** | Kimi, MiniMax, DeepSeek, Qwen, GLM, etc. | `--provider openai-compat --base-url <url>` |

## Data & Privacy

- **All data stays local.** Profile, notes, and config are stored in `~/.neocortex/`
- **User notes are plain Markdown** in `~/Documents/Neocortex/` (configurable via `neocortex profile config --notes-dir`)
- **API keys are stored locally.** Never transmitted anywhere except to the LLM provider you chose
- **Your code is not uploaded.** Only structured summaries are sent to the LLM for analysis
- **No telemetry.** No tracking, no analytics, no phone-home

## Roadmap

- [x] CLI framework (6 top-level commands + 4 subcommand groups)
- [x] Multi-LLM provider support (Claude, OpenAI, Gemini, OpenAI-compat)
- [x] Project scanning (local + GitHub, 12 languages)
- [x] Personalized reading with 3 depth levels (scan/standard/deep)
- [x] Concept compilation + knowledge indexing
- [x] Spaced repetition flashcard review (SM-2)
- [x] Knowledge base health checks (7 lint rules + auto-fix)
- [x] Content discovery (explore, research, RSS feeds)
- [x] Fragment capture (clip, inbox, daily resurfacing)
- [x] Knowledge confidence decay model
- [x] Micro-reflections after reading
- [x] Skill probing & calibration (Socratic Probe)
- [x] Chat history import (ChatGPT / Claude)
- [x] Learning path recommendations + opportunity matching
- [x] Visual concept maps + learning digests
- [x] Audio output / TTS
- [x] Localization (English, Chinese)
- [ ] Plugin system — community-contributed skill extractors
- [ ] Web/App version (student edition)

## Contributing

Contributions are welcome! Please open an issue or pull request.

## License

MIT License. See [LICENSE](LICENSE) for details.
