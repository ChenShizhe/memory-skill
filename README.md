# memory-skill

Four skills for persistent memory across AI agent sessions. Built as model-agnostic markdown instructions that any LLM agent runtime can follow.

## Quick Start (new machine)

```bash
git clone https://github.com/ChenShizhe/memory-skill.git
cd memory-skill
mkdir -p ~/Documents/memory ~/Documents/citadel ~/Documents/experiences
python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/
```

**Done:** `~/Documents/memory/AGENTS.md` exists. See [SETUP.md](SETUP.md) for the full walkthrough including cross-platform notes and verification.

## Usage Example

```
You: "Remember that the deploy target for project X is us-east-1."
  --> experience-logger writes a log to experiences/

You: "Ingest recent experiences."
  --> memory-manager reads experiences/, writes a searchable note to memories/

(Next session) You: "Set up the deploy pipeline for project X."
  --> memory-retriever loads the us-east-1 note into the agent's context automatically
```

## Skills

| Skill | Purpose | Reads | Writes |
|-------|---------|-------|--------|
| **memory-retriever** | Load relevant memory at session start or mid-session | `memories/`, `citadel/` (read-only) | project `memory/` (trace files) |
| **experience-logger** | Record session outcomes for later ingestion | (none) | `experiences/` |
| **memory-manager** | Ingest experience logs into searchable long-term memory | `experiences/`, `memories/` | `memories/` |
| **knowledge-maester** | Ingest papers, reports, and analyses into a knowledge vault | source artifacts | `citadel/`, `paper-bank/` |

## Architecture

The system uses two complementary storage layers:

### Personal Memory (`~/Documents/memory/`)

Core identity files loaded every session:
- `AGENTS.md` — operating procedures and pre-flight checklist
- `SOUL.md` — ethics and quality standards
- `IDENTITY.md` — system identity and workspace boundaries
- `USER.md` — user profile and preferences

Plus searchable memory managed by memory-manager:
- `long-term/` and `short-term/` — atomic notes indexed via `catalog-index.md` (manifest) and per-topic files under `catalog-shards/`
- `workflow-templates/` — learned workflow patterns
- `archive/` — retired memory (not actively searched)

### Knowledge Vault (`~/Documents/citadel/`)

An Obsidian vault for structured knowledge:
- Market intelligence (reports, analyses, ticker notes)
- Literature (paper notes, digests, field summaries)
- Reference material (tool notes, system references)

### Data Flow

```
experience-logger --> experiences/
                          |
                    memory-manager --> memories/ (long-term, short-term)
                          |                |
                          |         memory-retriever --> expanded instruction
                          |
                    knowledge-maester --> citadel/ (vault notes)
```

## Setup

### Prerequisites

- Python 3.12+
- [Obsidian](https://obsidian.md/) desktop app (optional, for knowledge-maester vault operations). See also [Obsidian CLI](https://obsidian.md/cli)

### First-Time Setup

Bootstrap a personal memory directory:

```bash
python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/
```

This creates the directory structure and placeholder core files. Personalize the core files, then build the initial catalog:

```bash
python3 knowledge-maester/scripts/generate_memory_catalog.py --vault-path ~/Documents/memory/
```

### Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `OBSIDIAN_CLI_PATH` | `/Applications/Obsidian.app/Contents/MacOS/obsidian` | Path to Obsidian CLI binary |

## Running Tests

Tests are a mix of unit tests (knowledge-maester) and integration tests (the other three skills). Integration tests use custom assertion functions and must be run directly — they are not pytest-discoverable.

```bash
# Unit tests (pytest)
python3 -m pytest knowledge-maester/tests/ -q

# Integration tests (direct execution — skip gracefully if workspace is not configured)
python3 memory-retriever/test_memory_retriever.py
python3 experience-logger/test_experience_logger.py
python3 memory-manager/test_memory_manager.py
```

## License

MIT
