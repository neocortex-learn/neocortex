# Neocortex

English | [中文](README.zh-CN.md)

> AI-powered personal knowledge base for developers.
>
> Clip anything, compile into concepts, find it when you need it.

Neocortex manages your knowledge like a code repository — with intake, compilation, indexing, and health checks. Save tweets, articles, and ideas with zero friction. The LLM compiles them into a linked concept graph. When you need something, search or ask — it finds what you saved.

Inspired by Karpathy's ["LLM Knowledge Bases"](https://karpathy.ai/) workflow: raw materials → compiled knowledge → searchable output.

## Why Neocortex?

Your bookmarks, saved tweets, and read-later lists are graveyards. You save things and never find them again.

Neocortex fixes this with a three-layer architecture:

```
clip (save anything)  →  compile (LLM organizes)  →  search/ask (find it)
```

It also understands **you** — scan your projects to build a skill profile, then get personalized notes that skip what you already know.

| Tool | Saves easily | Organizes automatically | Finds when needed | Knows you |
|------|:-:|:-:|:-:|:-:|
| Pocket / Instapaper | Yes | No | Barely | No |
| Obsidian | Manual | Manual | Plugin | No |
| NotebookLM | No | Yes | Yes | No |
| **Neocortex** | **Yes** | **Yes** | **Yes** | **Yes** |

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

### Save & Search (lightweight path)

```bash
neocortex clip https://x.com/karpathy/status/123      # Save a tweet — zero LLM cost
neocortex clip "Redis Pub/Sub has ordering guarantees" # Save a thought
neocortex kb compile                                   # Compile into concept graph
neocortex search "redis pub/sub"                       # Find it instantly
neocortex ask "What did I save about message ordering?" # AI answers from your KB
```

### Scan & Learn (deep mode)

```bash
neocortex profile scan ~/projects/my-app              # Build skill profile
neocortex read https://ddia.vonng.com/ch8/            # Personalized deep notes
neocortex learn recommend                             # Learning path with probes
```

## Commands

### Top-Level Commands

| Command | Description |
|---------|-------------|
| `neocortex clip <source>` | Save anything — URL, tweet, thought, bookmark (zero LLM by default, `--process` for AI tagging) |
| `neocortex search <query>` | Search across all notes, clips, concepts, and insights |
| `neocortex ask <question>` | Ask a question — AI answers using your knowledge base (or `--chat` for a session) |
| `neocortex read <source>` | Deep reading — URL/PDF/EPUB personalized notes with Mermaid diagrams |
| `neocortex review` | Spaced repetition flashcard review (SM-2) |
| `neocortex inbox` | Manage captured clips (`--process`, `--auto`, `--synthesize`) |
| `neocortex daily` | Daily briefing — resurfaced clips + due reviews + compile reminders |

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
| `neocortex kb compile` | Compile notes into a linked concept wiki (`--verify` to verify after) |
| `neocortex kb verify` | Verify concept entries are faithful to source notes (`--fix`/`--trend`/`--depth deep`) |
| `neocortex kb lint` | Run health checks on your knowledge base (8 checks + `--fix`) |
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

### 1. Three-Layer Knowledge Architecture

Like a code repository with source, build, and output:

```
~/Documents/Neocortex/          (your knowledge vault)
├── clips/                      ← Raw intake (tweets, bookmarks, thoughts)
├── general/                    ← Deep notes from `read`
├── concepts/                   ← Compiled knowledge (auto-generated wiki)
├── insights/                   ← Saved Q&A from `ask`
├── INDEX.md                    ← Auto-maintained knowledge map
└── .search.db                  ← FTS5 + vector search index
```

### 2. Lightweight Path: Clip → Compile → Search

**Clip** (zero friction): Save anything — URLs, tweets, thoughts. No LLM cost by default.

**Compile** (`kb compile`): LLM batch-processes your clips and notes — extracts concepts, builds wiki entries, updates the search index. Run it when you've accumulated a few items.

**Search/Ask**: `search` does full-text + semantic hybrid search across everything. `ask` automatically searches your knowledge base and injects relevant context into the AI's response.

### 3. Deep Path: Read → Probe → Review

For content you want to deeply understand:

**Read** generates personalized notes at your level — maps each section against your skill profile (`skip` / `brief` / `deep`), embeds Mermaid diagrams, uses your projects as analogies.

**Probe** verifies real understanding with four question types (edge cases, error detection, design tradeoffs, behavior prediction). Gap status only advances through verification — reading alone doesn't count as "learned."

**Review** uses SM-2 spaced repetition with interleaved flashcards.

### 4. Smart Project Scanning

Neocortex extracts key signals from your codebase efficiently (~2K tokens per project, <$0.05):

```
Config detection → Code statistics → Key file sampling → Architecture signals
    ↓
LLM Analysis → Skill Profile (level + confidence per skill)
```

### 5. Knowledge Confidence Decay

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

**Knowledge Base (lightweight path)**
- [x] Zero-LLM clip capture (tweets, URLs, thoughts)
- [x] Hybrid search (FTS5 + vector) across all content types
- [x] Standalone `search` command
- [x] Dynamic knowledge-base context in `ask`/`chat`
- [x] Concept compilation + knowledge indexing
- [x] Knowledge base health checks (8 lint rules + auto-fix)
- [x] Fidelity verification (FACTScore + Hermes independent review)
- [x] Daily briefing with clip resurfacing + compile reminders
- [x] Knowledge confidence decay (Hidalgo model)

**Deep Learning (opt-in)**
- [x] Personalized reading with 3 depth levels (scan/standard/deep)
- [x] Socratic Probe — 4 question types aligned with Bloom's taxonomy
- [x] Metacognition calibration (predict vs actual)
- [x] Gap verification gates (reading alone ≠ learned)
- [x] Spaced repetition flashcard review (SM-2)
- [x] Learning path recommendations + opportunity matching

**Infrastructure**
- [x] CLI framework (7 top-level commands + 4 subcommand groups)
- [x] Multi-LLM provider support (Claude, OpenAI, Gemini, OpenAI-compat)
- [x] Project scanning (local + GitHub, 12 languages)
- [x] Content discovery (explore, research, RSS feeds)
- [x] Chat history import (ChatGPT / Claude)
- [x] Visual concept maps + learning digests
- [x] Audio output / TTS
- [x] Localization (English, Chinese)
- [ ] Plugin system — community-contributed skill extractors
- [ ] Web/App version

## Contributing

Contributions are welcome! Please open an issue or pull request.

## License

MIT License. See [LICENSE](LICENSE) for details.
