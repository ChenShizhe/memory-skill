# Setup Guide

This guide walks through setting up memory-skill on a fresh machine. It is written for both human users and AI agents (Claude Code, Codex, etc.).

## Prerequisites

| Requirement | Check command | Notes |
|-------------|--------------|-------|
| Python 3.12+ | `python3 --version` | macOS: `brew install python@3.12`. Windows: download from python.org |
| Claude Code CLI | `claude --version` | Or any agent runtime that supports SKILL.md instructions |
| Git | `git --version` | For cloning this repo |

### Optional

| Dependency | What it enables | Install |
|------------|----------------|---------|
| Obsidian | Knowledge vault browsing (knowledge-maester) | [obsidian.md](https://obsidian.md) |

## Step 1: Clone the repo

```bash
git clone https://github.com/ChenShizhe/memory-skill.git
cd memory-skill
```

## Step 2: Create the directory structure

The memory system uses two storage layers. Create them:

```bash
# Personal memory (required)
mkdir -p ~/Documents/memory

# Knowledge vault (optional, for knowledge-maester)
mkdir -p ~/Documents/citadel

# Experience inbox (for experience-logger)
mkdir -p ~/Documents/experiences
```

**Windows equivalent:**
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Documents\memory"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Documents\citadel"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Documents\experiences"
```

## Step 3: Bootstrap personal memory

Run the bootstrap script to create core identity files:

```bash
python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/
```

This creates:
- `~/Documents/memory/AGENTS.md` — operating procedures
- `~/Documents/memory/SOUL.md` — quality standards
- `~/Documents/memory/IDENTITY.md` — system identity
- `~/Documents/memory/USER.md` — user profile (edit this to describe yourself)
- `~/Documents/memory/long-term/`, `short-term/`, `archive/` directories
- `~/Documents/memory/catalog.md` — memory index

**Done signal:** You should see `Bootstrap complete` in the output and `~/Documents/memory/AGENTS.md` should exist.

## Step 4: Install the skills

Copy skill folders to your agent's skill directory:

```bash
# For Claude Code personal skills:
SKILL_DIR=~/.claude/skills
mkdir -p "$SKILL_DIR"

cp -R memory-retriever "$SKILL_DIR/memory-retriever"
cp -R experience-logger "$SKILL_DIR/experience-logger"
cp -R memory-manager "$SKILL_DIR/memory-manager"
cp -R knowledge-maester "$SKILL_DIR/knowledge-maester"
```

## Step 5: Verify

```bash
# 1. Check bootstrap output exists
ls ~/Documents/memory/AGENTS.md && echo "OK: Memory bootstrapped"

# 2. Run unit tests (pytest)
python3 -m pytest knowledge-maester/tests/ -q

# 3. Run integration tests (direct execution — skip gracefully on fresh install)
python3 memory-retriever/test_memory_retriever.py
python3 experience-logger/test_experience_logger.py
python3 memory-manager/test_memory_manager.py
```

**Done signal:** pytest reports 0 failures for knowledge-maester. Each integration test prints "passed" or "SKIP" (expected on a fresh install with an empty vault).

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OBSIDIAN_CLI_PATH` | `/Applications/Obsidian.app/Contents/MacOS/obsidian` (macOS) | Path to Obsidian binary. Set this on Windows/Linux. |

## Cross-Platform Notes

- **macOS:** Works out of the box with Homebrew Python.
- **Windows:** Use `%USERPROFILE%\Documents\memory` instead of `~/Documents/memory`. The Obsidian path must be updated via `OBSIDIAN_CLI_PATH`. Shell scripts in knowledge-maester require Git Bash or WSL.
- **Linux:** Same as macOS but set `OBSIDIAN_CLI_PATH` to your Obsidian AppImage/binary path.

## What to do next

1. Edit `~/Documents/memory/USER.md` to describe yourself — this shapes how agents interact with you.
2. Start a Claude Code session and ask it to use `memory-retriever` — it should load your identity files.
3. At the end of a session, ask it to use `experience-logger` to record what happened.
