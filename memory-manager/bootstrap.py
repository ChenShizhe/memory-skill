#!/usr/bin/env python3
"""Bootstrap a personal memory directory structure.

Usage:
    python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/
    python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/ --dry-run
    python3 memory-manager/bootstrap.py --memory-root ~/Documents/memory/ --force

Also provides the canonical ``route_card`` routing function consumed by
memory-manager ingestion and (optionally, via import) by knowledge-maester's
catalog regenerator.
"""

import argparse
import re
import sys
from datetime import date as _date_cls
from pathlib import Path

DIRECTORIES = [
    "proposals",
    "long-term",
    "short-term",
    "archive",
    "workflow-templates",
    "workflow-templates/_shared",
    "catalog-shards",
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

PLACEHOLDER_CATALOG_INDEX = """\
# Memory Catalog Index

This file is the top-level manifest of the searchable memory. memory-retriever reads this first to decide which shards to open in a session. memory-manager keeps `card_count` and `last_updated` in sync with shard contents on every ingestion; `description` and `stable_tags` are hand-edited and stable.

## Registered projects

<!-- Comma-separated list of project names that currently have, or may grow into, their own shard. Update by hand when a new project is added. -->



## Shards

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
    "catalog-index.md": PLACEHOLDER_CATALOG_INDEX,
    "archive-catalog.md": PLACEHOLDER_ARCHIVE_CATALOG,
    "manager-ledger.md": PLACEHOLDER_LEDGER,
    "provider-quotas.md": PLACEHOLDER_QUOTAS,
}


# ---------------------------------------------------------------------------
# Shard routing
# ---------------------------------------------------------------------------

CORE_IDENTITY_PATHS = {
    "memories/AGENTS.md",
    "memories/SOUL.md",
    "memories/IDENTITY.md",
    "memories/USER.md",
}


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            if not inner:
                return []
            return [x.strip() for x in inner.split(",") if x.strip()]
        return [v] if v else []
    return []


# Projects that have graduated to their own shard. Keep in sync with
# memories/catalog-index.md "Registered projects" entries whose card count
# reached the graduation threshold (>= 5 sole-project cards). Hand-maintained.
GRADUATED_PROJECTS: set[str] = {
    "coordination",
    "git-integration",
    "learning-by-doing",
    "memory-manager-v0",
    "paper-reader-improvement",
    "research-meeting",
    "skill-publication",
}


def route_card(frontmatter: dict) -> str:
    """Return the target shard filename (e.g. ``core-identity.md``).

    Implements the routing ladder documented in memory-manager/SKILL.md
    (Shard Routing section). First-match-wins.
    """
    path = str(frontmatter.get("path", "")).strip()
    type_ = str(frontmatter.get("type", "")).strip()
    slug = str(frontmatter.get("slug", "")).strip()
    projects = _as_list(frontmatter.get("projects"))
    topics = _as_list(frontmatter.get("topics"))
    topics_l = {t.lower() for t in topics}

    # 1. Core identity paths
    if path in CORE_IDENTITY_PATHS:
        return "core-identity.md"
    # 2. workflow_template
    if type_ == "workflow_template":
        return "workflow-templates.md"
    # 3. role_profile
    if type_ == "role_profile":
        return "roles.md"
    # 4. hub
    if type_ == "hub":
        return "hubs.md"
    # 5. sole graduated project
    if len(projects) == 1 and projects[0] in GRADUATED_PROJECTS:
        return f"project-{projects[0]}.md"
    # 6. sole below-threshold project
    if len(projects) == 1:
        return "project-continuity.md"
    # 7. paper-reading
    if (slug.startswith("paper-reader-") or slug.startswith("paper-discovery-")
            or slug.startswith("paper-review-")):
        return "paper-reading.md"
    if "paper-reading" in topics_l or "paper-reader" in topics_l:
        return "paper-reading.md"
    # 8. memory-system
    if (slug.startswith("memory-") or slug.startswith("catalog-")
            or slug.startswith("experience-logger-")
            or slug.startswith("knowledge-maester-")):
        return "memory-system.md"
    if "memory-ingestion" in topics_l or "retrieval" in topics_l or "catalog" in topics_l:
        return "memory-system.md"
    # 9. market-ops
    if slug.startswith("market-") or slug.startswith("portfolio-"):
        return "market-ops.md"
    if "market-watcher" in topics_l or "portfolio" in topics_l or "ticker" in topics_l:
        return "market-ops.md"
    # 10. tooling-ops
    if "credential" in slug or "broker" in slug or "git-" in slug:
        return "tooling-ops.md"
    if ("credential-broker" in topics_l or "env-vars" in topics_l
            or "secret-handling" in topics_l or "git" in topics_l):
        return "tooling-ops.md"
    # 11. session-ops
    if "research-meeting-" in slug or "session-" in slug:
        return "session-ops.md"
    if "research-meeting" in topics_l or "session-handoff" in topics_l:
        return "session-ops.md"
    # 12. skill-ops
    if slug.startswith("ralph-") or slug.startswith("skill-"):
        return "skill-ops.md"
    if ("skill-design" in topics_l or "skill-testing" in topics_l
            or "skill-onboarding" in topics_l or "strangler-fig" in topics_l):
        return "skill-ops.md"
    # 13. agent-ops
    if ("agent-ops" in topics_l or "preflight" in topics_l
            or "paper-trail" in topics_l or "safety" in topics_l):
        return "agent-ops.md"
    # 14. writing-style
    writing_topics = {"writing", "manuscript", "review", "academic-writing"}
    has_writing_topic = bool(topics_l & writing_topics)
    if has_writing_topic:
        return "writing-style.md"
    if type_ in {"user_preference", "user-preference"} and has_writing_topic:
        return "writing-style.md"
    # 15. misc
    return "misc.md"


# ---------------------------------------------------------------------------
# Shard file I/O
# ---------------------------------------------------------------------------

SHARD_HEADER_TEMPLATE = """# Catalog Shard — {name}

Searchable memory cards routed to this shard. See `../catalog-index.md` for the shard manifest. `generate_memory_catalog.py` rewrites the `## Generated Entries` subsection on regeneration; the `## Manual Entries` subsection is preserved verbatim. memory-manager writes generated entries at ingestion time; hand-edit only the Manual Entries subsection.

## Generated Entries

## Manual Entries
"""


_SLUG_HEADING_RE = re.compile(r"^## ([^\n]+)$", re.MULTILINE)


_GENERATED_HEADING_RE = re.compile(r"^## Generated Entries\s*$", re.MULTILINE)
_MANUAL_HEADING_RE = re.compile(r"^## Manual Entries\s*$", re.MULTILINE)


def _split_shard(content: str) -> tuple[str, str, str]:
    """Return (header, generated_section, manual_section) as raw strings.

    Each section string is everything after its heading up to the next
    top-level heading (`## Manual Entries` for generated, end-of-file for
    manual). Headers are preserved literally in the returned ``header``.

    Matches real markdown headings only (a line that starts with ``## ...``),
    not mentions of the subsection name embedded in prose or inline code.
    """
    gen_matches = list(_GENERATED_HEADING_RE.finditer(content))
    man_matches = list(_MANUAL_HEADING_RE.finditer(content))
    if not gen_matches or not man_matches:
        raise ValueError("shard file missing required subsections")
    gen = gen_matches[-1]
    man_candidates = [m for m in man_matches if m.start() > gen.start()]
    if not man_candidates:
        raise ValueError("shard file has Manual Entries before Generated Entries")
    man = man_candidates[-1]
    header = content[: gen.start()]
    generated = content[gen.end(): man.start()]
    manual = content[man.end():]
    return header, generated, manual


def _format_entries_block(entries: list[str]) -> str:
    """Join entry raw texts with a trailing newline."""
    if not entries:
        return "\n"
    return "\n" + "".join(entries).rstrip("\n") + "\n\n"


def write_entry_to_shard(
    shards_dir: Path,
    shard_name: str,
    slug: str,
    entry_markdown: str,
    subsection: str = "Generated Entries",
) -> None:
    """Append or replace ``entry_markdown`` in the specified shard subsection.

    - ``shards_dir``: path to ``memories/catalog-shards/``.
    - ``shard_name``: filename like ``"core-identity.md"``.
    - ``slug``: the slug whose ``## <slug>`` block is being written.
    - ``entry_markdown``: the raw markdown block starting with ``## <slug>`` and
      ending with a trailing blank line.
    - ``subsection``: ``"Generated Entries"`` (default) or ``"Manual Entries"``.
      Ingestion never writes to Manual automatically.
    """
    shard_path = shards_dir / shard_name
    if not shard_path.exists():
        shard_path.write_text(
            SHARD_HEADER_TEMPLATE.format(name=shard_name[:-3]),
            encoding="utf-8",
        )

    content = shard_path.read_text(encoding="utf-8")
    header, generated, manual = _split_shard(content)

    def _split_entries(block: str) -> list[tuple[str, str]]:
        matches = list(_SLUG_HEADING_RE.finditer(block))
        out = []
        for i, m in enumerate(matches):
            s = m.group(1).strip()
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
            out.append((s, block[start:end]))
        return out

    entry_markdown = entry_markdown.rstrip("\n") + "\n\n"

    if subsection == "Generated Entries":
        entries = _split_entries(generated)
        entries = [(s, r) for s, r in entries if s != slug]
        entries.append((slug, entry_markdown))
        generated_body = _format_entries_block([r for _, r in entries])
        new = header + "## Generated Entries\n" + generated_body + "## Manual Entries" + manual
    elif subsection == "Manual Entries":
        entries = _split_entries(manual)
        entries = [(s, r) for s, r in entries if s != slug]
        entries.append((slug, entry_markdown))
        manual_body = _format_entries_block([r for _, r in entries])
        new = header + "## Generated Entries" + generated + "## Manual Entries\n" + manual_body
    else:
        raise ValueError(f"unknown subsection: {subsection}")

    shard_path.write_text(new.rstrip() + "\n", encoding="utf-8")


_INDEX_BLOCK_RE = re.compile(
    r"(### (?P<name>[A-Za-z0-9_-]+)\n"
    r"(?:-[^\n]*\n)*?)"
    r"(- card_count:\s*[^\n]*\n)"
    r"(- last_updated:\s*[^\n]*)",
    re.MULTILINE,
)


def update_index_for_shard(memory_root: Path, shard_name: str) -> None:
    """Recompute ``card_count`` and ``last_updated`` for ``shard_name`` in the index.

    - ``memory_root``: the memory vault root (e.g. ``~/Documents/memory/``).
    - ``shard_name``: filename like ``"core-identity.md"``.

    Only the two fields are rewritten. ``description`` and ``stable_tags`` are
    never touched.
    """
    index_path = memory_root / "catalog-index.md"
    shard_path = memory_root / "catalog-shards" / shard_name
    if not index_path.exists() or not shard_path.exists():
        return

    shard_content = shard_path.read_text(encoding="utf-8")
    slugs = [
        m.group(1).strip()
        for m in _SLUG_HEADING_RE.finditer(shard_content)
        if m.group(1).strip() not in ("Generated Entries", "Manual Entries")
    ]
    card_count = len(slugs)

    last_updated = ""
    for m in re.finditer(r"^- updated:\s*(\S+)", shard_content, re.MULTILINE):
        val = m.group(1).strip()
        if val > last_updated:
            last_updated = val

    index_content = index_path.read_text(encoding="utf-8")
    target_block_name = shard_name[:-3]

    def _replace(match: re.Match) -> str:
        if match.group("name") != target_block_name:
            return match.group(0)
        return (
            match.group(1)
            + f"- card_count: {card_count}\n"
            + f"- last_updated: {last_updated}"
        )

    new_index = _INDEX_BLOCK_RE.sub(_replace, index_content)
    index_path.write_text(new_index, encoding="utf-8")


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
        print(
            "     This produces a fresh sharded layout: `catalog-index.md` (manifest)"
            " plus per-topic files under `catalog-shards/`."
        )

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
