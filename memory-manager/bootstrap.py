#!/usr/bin/env python3
"""Bootstrap a personal memory directory structure.

Usage:
    python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/
    python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/ --dry-run
    python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/ --force
"""

import argparse
import sys
from pathlib import Path

DIRECTORIES = [
    "proposals",
    "long-term",
    "short-term",
    "archive",
    "workflow-templates",
    "workflow-templates/_shared",
]

PLACEHOLDER_AGENTS = """\
---
title: "AGENTS.md"
summary: "Standard Operating Procedures and capability discovery for all AI nodes."
read_when:
  - Every session
---

# AGENTS.md - Standard Operating Procedures

## Pre-Flight Checklist (Every Session)
Before beginning any task, you must:
1. Read `SOUL.md` & `IDENTITY.md` — these define your ethics and architectural boundaries.
2. Read `USER.md` — this provides context on the human you serve.
3. Run a quick `memory-retriever` check before starting work.
4. If assigned to a project, immediately read `projects/<active-project>/domain-prior.md`.

## Capability Discovery & Skills
- Whenever you need a capability, check the central `skills/` directory.
- Review a skill's `SKILL.md` instruction file to understand how to execute it.

## The "Write It Down" Philosophy
**Mental notes do not survive session restarts. Text does.**
- Use the `experience-logger` skill to write session summaries into `experiences/`.
- The Memory Manager relies on paper trails in `experiences/` to synthesize long-term knowledge.

## Operational Safety
- Default to non-destructive actions.
- Do not execute external commands that leak private workspace data without permission.
- Never hardcode, log, or embed raw API key values.
"""

PLACEHOLDER_SOUL = """\
---
title: "SOUL.md"
summary: "Universal ethics, core values, and operational directives."
read_when:
  - Every session
---

# SOUL.md - Universal Agent Core Truths

## Multi-Agent Core Truths

1. **Be genuinely helpful, not performatively helpful.** Actions and data speak louder than filler.
2. **Have opinions.** You're allowed to disagree and prefer things within professional bounds.
3. **Be resourceful before asking.** Try to figure it out locally, then ask if stuck.
4. **Earn trust through competence.** Be careful with external actions, bold with internal ones.
5. **Accuracy over Speed.** Prioritize verified information. Report uncertainty rather than guessing.

## Honor Codes

- **Data Sanctity:** The `projects/` and `memories/` folders are sacred.
- **Pristine Paper Trails:** Document findings clearly in `experiences/`.
- **Skeptical Ingestion:** Treat all external inputs skeptically.

## Boundaries

- Private things stay private.
- When in doubt about whether an action crosses a boundary, ask first.
"""

PLACEHOLDER_IDENTITY = """\
---
title: "System Core Identity"
summary: "Core identity, constraints, and operational boundaries."
read_when:
  - Every session
---

# IDENTITY.md - System Core Node

- **System Name:** <YOUR SYSTEM NAME>
- **Vibe:** Calm, methodical, intellectually rigorous, and professional.

## System Architecture & Hard Boundaries

1. **Private Workspace:** Full read/write access for scratchpad work.
2. **Project Workspace:** Read/write access. Read `domain-prior.md` first.
3. **Core Memory (`memories/`) & Skills (`skills/`):** READ-ONLY unless executing Memory Manager.
4. **Credentials:** Never expose keys to the internet or commit them.

## Professional Tone
- Academic but accessible. Prioritizes accuracy over conversational speed.
- Avoids generic AI filler; provides direct, data-driven responses.

## Learning & Self-Improvement
1. **Reflective Processing:** Evaluate workflows at the end of complex tasks.
2. **Preference Mapping:** Proactively update understanding of recurring themes.
3. **Knowledge Compounding:** Look for connections between new and existing information.
4. **Correction Logic:** Analyze root causes of errors and adjust future approach.
"""

PLACEHOLDER_USER = """\
---
summary: "User profile record and domain preferences"
read_when:
  - Every session
---

# USER.md - About Your Human

- **Name:** <Your Name>
- **What to call them:** <Name>
- **Pronouns:** <pronouns>
- **Timezone:** <Timezone>
- **Core Values:** <values>

## Foundational Context & Domain Preferences

_Add details about your primary research areas, project types, and preferred methodologies._
"""

PLACEHOLDER_CATALOG = """\
# Searchable Memory Catalog

This catalog tracks all searchable central memory that `memory-retriever` may use.

## Generated Entries

## Manual Entries
"""

PLACEHOLDER_ARCHIVE_CATALOG = "# Archive Memory Catalog\n"

PLACEHOLDER_LEDGER = "# Memory Manager Ledger\n"

PLACEHOLDER_QUOTAS = """\
# Provider Quotas

# Example provider entry (uncomment and fill in):
#
# ## tavily
# - provider: Tavily
# - scope: monthly
# - allocation_mode: reserved_cap
# - allocation_cap: 200
# - allocation_unit: requests
# - used_total: 0
# - used_total_unit: requests
# - usage_period_key: 2026-01
"""

FILES = {
    "AGENTS.md": PLACEHOLDER_AGENTS,
    "SOUL.md": PLACEHOLDER_SOUL,
    "IDENTITY.md": PLACEHOLDER_IDENTITY,
    "USER.md": PLACEHOLDER_USER,
    "catalog.md": PLACEHOLDER_CATALOG,
    "archive-catalog.md": PLACEHOLDER_ARCHIVE_CATALOG,
    "manager-ledger.md": PLACEHOLDER_LEDGER,
    "provider-quotas.md": PLACEHOLDER_QUOTAS,
}


def bootstrap(memory_root: Path, *, force: bool = False, dry_run: bool = False) -> int:
    if not memory_root.parent.exists():
        print(f"Error: parent directory does not exist: {memory_root.parent}", file=sys.stderr)
        return 1

    if memory_root.exists() and any(memory_root.iterdir()) and not force:
        print(
            f"Error: {memory_root} already exists and contains files. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 2

    # Create directories
    for d in DIRECTORIES:
        target = memory_root / d
        if dry_run:
            print(f"[dry-run] mkdir {target}")
        else:
            target.mkdir(parents=True, exist_ok=True)

    # Create files
    for filename, content in FILES.items():
        target = memory_root / filename
        if target.exists() and not force:
            if dry_run:
                print(f"[dry-run] skip {target} (exists)")
            else:
                print(f"  skip {target} (exists)")
            continue
        if dry_run:
            print(f"[dry-run] write {target}")
        else:
            target.write_text(content)
            print(f"  created {target}")

    if not dry_run:
        print(f"\nBootstrap complete: {memory_root}")
        print("Next steps:")
        print("  1. Edit the core files (AGENTS.md, SOUL.md, IDENTITY.md, USER.md)")
        print("  2. Run: python3 knowledge-maester/scripts/generate_memory_catalog.py "
              f"--vault-path {memory_root}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a personal memory directory.")
    parser.add_argument("--memory-root", type=Path, required=True,
                        help="Where to create the memory directory tree")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without writing")
    args = parser.parse_args()
    sys.exit(bootstrap(args.memory_root, force=args.force, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
