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
from datetime import date as _date_cls, datetime as _datetime_cls
from pathlib import Path

DIRECTORIES = [
    "proposals",
    "proposals/resolved",
    "long-term",
    "short-term",
    "archive",
    "workflow-templates",
    "workflow-templates/_shared",
    "catalog-shards",
]

# ---------------------------------------------------------------------------
# Capacity-signal thresholds
# ---------------------------------------------------------------------------

MISC_SOFT_THRESHOLD = 15
CATALOG_PHASE2_THRESHOLD = 500
PROPOSAL_REVIEW_THRESHOLD = 10

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


# ---------------------------------------------------------------------------
# Tag synonym normalization
# ---------------------------------------------------------------------------
#
# SYNONYMS maps surface-form tags that have appeared in real cards to canonical
# tags that the routing rules already recognize. Pattern: Rasa entity-synonyms /
# SpamAssassin / Hugo taxonomy. Applied via `normalize_tags()` before rule
# evaluation, so the rule bodies stay narrow and new vocabulary misses become
# one-line dict additions instead of edits across multiple rule blocks.
#
# Original tags are preserved on the card; this map only extends the rule-match
# set. Each entry includes the date added and the motivating slug so the file
# is self-documenting.
SYNONYMS: dict[str, str] = {
    # 2026-05-01 — review-* hyphenated variants surfaced by misc drain
    # (anchor-string-verification-for-review-comments,
    # non-lead-author-manuscript-comment-style, review-voice-constructive-by-default,
    # review-writing-workflow-patterns, bibtex-per-field-verification-from-canonical-source).
    # All review-* variants canonicalize to `review` (writing-style topic) since
    # the source cards are about review-comment/manuscript-comment style, not
    # paper-reading workflow. paper-review specifically: the misc-drain cards
    # tagged paper-review (e.g. anchor-string-verification-for-review-comments,
    # non-lead-author-manuscript-comment-style) are about writing review
    # comments on a paper, not about reading papers.
    "academic-review": "review",
    "manuscript-review": "manuscript",
    "paper-review": "review",
    "review-style": "review",
    "review-writing": "review",
    "writing-voice": "writing",
}


def normalize_tags(tags) -> set[str]:
    """Return a lowercase tag set extended via the SYNONYMS map.

    Pure function. Input may be a list, a single string, or already a set.
    Output is the union of (a) original lowercased tags and (b) canonical
    forms produced by looking each tag up in SYNONYMS. Original tags are
    always preserved so rules that match them directly still fire.
    """
    if isinstance(tags, (list, tuple, set)):
        base = {str(t).strip().lower() for t in tags if str(t).strip()}
    elif isinstance(tags, str):
        base = {tags.strip().lower()} if tags.strip() else set()
    else:
        base = set()
    extensions = {SYNONYMS[t] for t in base if t in SYNONYMS}
    return base | extensions


def route_card_with_index(frontmatter: dict) -> tuple[str, int]:
    """Return ``(shard_filename, rule_index)`` for the given frontmatter.

    Same routing ladder as :func:`route_card`; the index identifies which
    rule fired (1-based, matching the comment-numbered rules below). Used by
    the test suite to assert both the destination shard and the firing rule
    in a single check, which makes precedence executable rather than merely
    documented (DroolsAssert / DMN ``Unique`` hit-policy pattern).
    """
    path = str(frontmatter.get("path", "")).strip()
    type_ = str(frontmatter.get("type", "")).strip()
    slug = str(frontmatter.get("slug", "")).strip()
    projects = _as_list(frontmatter.get("projects"))
    topics_l = normalize_tags(frontmatter.get("topics"))

    # === Block 1: Identity, type, and project rules (most specific) ===

    # 1. Core identity paths
    if path in CORE_IDENTITY_PATHS:
        return ("core-identity.md", 1)
    # 2. workflow_template
    if type_ == "workflow_template":
        return ("workflow-templates.md", 2)
    # 3. role_profile
    if type_ == "role_profile":
        return ("roles.md", 3)
    # 4. hub
    if type_ == "hub":
        return ("hubs.md", 4)
    # 5. sole graduated project
    if len(projects) == 1 and projects[0] in GRADUATED_PROJECTS:
        return (f"project-{projects[0]}.md", 5)
    # 6. sole below-threshold project
    if len(projects) == 1:
        return ("project-continuity.md", 6)

    # === Block 2a: Slug-prefix matches (most specific by-name routing) ===
    #
    # Slug starting with a domain-specific prefix is a strong by-name claim.
    # Routing by prefix runs before any topic-based rule so that, e.g.,
    # `ralph-testing-patterns` (slug ralph-) lands in skill-ops even if its
    # topics also include words that other topical rules now match.

    # 7. paper-reading slug-prefix
    if (slug.startswith("paper-reader-") or slug.startswith("paper-discovery-")
            or slug.startswith("paper-review-")):
        return ("paper-reading.md", 7)
    # 8. memory-system slug-prefix
    if (slug.startswith("memory-") or slug.startswith("catalog-")
            or slug.startswith("experience-logger-")
            or slug.startswith("knowledge-maester-")):
        return ("memory-system.md", 8)
    # 9. market-ops slug-prefix
    if slug.startswith("market-") or slug.startswith("portfolio-"):
        return ("market-ops.md", 9)
    # 13. skill-ops slug-prefix
    if slug.startswith("ralph-") or slug.startswith("skill-"):
        return ("skill-ops.md", 13)

    # === Block 2b: Structural matches (path / project-prefix) ===
    #
    # Path or project-prefix matches are nearly as specific as slug-prefix
    # but apply to fewer rules. Run after slug-prefix and before any topical
    # match.

    # 8. memory-system path
    if path == "memories/manager-ledger.md":
        return ("memory-system.md", 8)
    # 8. memory-system project-prefix
    if any(p.startswith("memory-manager") for p in projects):
        return ("memory-system.md", 8)
    # 9. market-ops project-prefix (US-Iran*)
    if any(p.lower().startswith("us-iran") for p in projects):
        return ("market-ops.md", 9)

    # === Block 2c: Topical matches and slug-substring matches ===
    #
    # Topic-based rules and looser slug-substring matches. Order within
    # this block matters: writing-style precedes session-ops (writing
    # patterns belong with writing patterns even when about workflow
    # documents). Substring slug matches (e.g. ``"session-" in slug``)
    # live here, not in Block 2a, because substring is less specific than
    # prefix and is correctly beaten by an earlier writing-topic match.

    # 7. paper-reading topics
    if topics_l & {"paper-reading", "paper-reader",
                   "reading-strategy", "industry-reports"}:
        return ("paper-reading.md", 7)
    # 8. memory-system topics
    if topics_l & {"memory-ingestion", "retrieval", "catalog",
                   "memory-manager", "operations", "ingestion-ledger"}:
        return ("memory-system.md", 8)
    # 9. market-ops topics
    if topics_l & {"market-watcher", "portfolio", "ticker",
                   "provider-orchestration", "report-validation",
                   "evidence-synthesis", "geopolitics", "market-risk", "us-iran"}:
        return ("market-ops.md", 9)
    # 10. tooling-ops slug-substring
    if "credential" in slug or "broker" in slug or "git-" in slug:
        return ("tooling-ops.md", 10)
    # 10. tooling-ops topics
    if topics_l & {"credential-broker", "env-vars", "secret-handling", "git",
                   "obsidian", "knowledge-graph", "vault-operations",
                   "model-routing", "provider-selection", "capability-map",
                   "pandoc", "latex", "mathjax",
                   "deliverable-tooling", "reproducibility"}:
        return ("tooling-ops.md", 10)
    # 11. writing-style topics (precedes session-ops by design)
    writing_topics = {"writing", "manuscript", "review", "academic-writing",
                      "documentation-design", "deliverable-design", "user-facing",
                      "citations", "bibtex", "reference-management"}
    if topics_l & writing_topics:
        return ("writing-style.md", 11)
    # 12. session-ops slug-substring
    if "research-meeting-" in slug or "session-" in slug:
        return ("session-ops.md", 12)
    # 12. session-ops topics
    if topics_l & {"research-meeting", "session-handoff",
                   "decision-making", "rule-enforcement", "evaluation",
                   "documentation-pattern", "subagent-delegation",
                   "verification", "research-process",
                   "planning", "workflow-governance",
                   "project-kickoff", "personal-productivity"}:
        return ("session-ops.md", 12)
    # 13. skill-ops topics
    if topics_l & {"skill-design", "skill-testing", "skill-onboarding",
                   "strangler-fig",
                   "agent-architecture", "modularity", "resilience"}:
        return ("skill-ops.md", 13)
    # 14. agent-ops topics
    if topics_l & {"agent-ops", "preflight", "paper-trail", "safety"}:
        return ("agent-ops.md", 14)

    # === Block 3: Fallback ===

    # 15. misc
    return ("misc.md", 15)


def route_card(frontmatter: dict) -> str:
    """Return the target shard filename (e.g. ``core-identity.md``).

    Implements the routing ladder documented in memory-manager/SKILL.md
    (Shard Routing section). First-match-wins.

    Precedence policy (source-order, three tiers, the second tier split
    into three sub-blocks by specificity):

    1. **Identity, type, and project rules — most specific.** Run first so
       that core-identity files, special card types (workflow_template,
       role_profile, hub), and sole-project routing claim their cards before
       any topical rule sees them.
    2a. **Slug-prefix matches.** A slug starting with `paper-reader-`,
       `memory-`, `market-`, `ralph-`, etc. is a strong by-name claim.
       Routes the card before any topic rule sees it, so e.g.
       ``ralph-testing-patterns`` lands in skill-ops even when its topics
       also overlap session-ops.
    2b. **Structural matches.** Path equality and project-name prefix
       checks. Specific but narrower than slug-prefix.
    2c. **Topical matches and slug-substring matches.** Topic-based rules
       and looser slug-substring matches (e.g. ``"session-" in slug``).
       Order within this block matters: writing-style precedes session-ops
       (writing patterns belong with writing patterns even when about
       workflow documents).
    3. **Fallback.** No safety-net rule. Cards that no topical rule claims
       fall through to misc; the manager files a ROUTE-* proposal so the
       miss is visible.

    Tag matching uses :func:`normalize_tags` so hyphenated synonyms (e.g.
    ``manuscript-review`` → ``manuscript``) extend the rule-match set
    without requiring per-rule synonym lists.

    The ladder body lives in :func:`route_card_with_index`; this function
    is a thin wrapper that drops the rule-index field for callers that want
    just the shard name.
    """
    shard, _index = route_card_with_index(frontmatter)
    return shard


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
    r"(- card_count:[^\n]*\n)"
    r"(- last_updated:[^\n]*)",
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


# ---------------------------------------------------------------------------
# Route-proposal filing
# ---------------------------------------------------------------------------


_ROUTE_PROPOSAL_TEMPLATE = """\
# Proposed Route: {slug}

- created_at: {created_at}
- proposal_type: route_ambiguous_card
- card_slug: {slug}
- card_path: {card_path}
- current_shard: catalog-shards/misc.md
- source_experience: {source_experience}
- reason: Routing rules produced no match; card defaulted to misc.

## Routing signals

- type: {type_}
- topics: {topics}
- projects: {projects}

## Candidate shards

The manager's shortlist of plausible shards with rationale per shard:

{candidate_lines}

## User decision

<!-- Check exactly one option above during an interactive memory-manager run. The manager reads this block and acts. -->
"""


def _format_candidate_line(shard: str, rationale: str) -> str:
    if shard == "__new_shard__":
        return f"- [ ] propose new shard: {rationale}"
    if shard == "__confirm_misc__":
        return "- [ ] confirm misc (no clear shard; card stays in misc pending periodic review)"
    return f"- [ ] catalog-shards/{shard} — {rationale}"


def file_route_proposal(
    card: dict,
    candidates: list[tuple[str, str]],
    *,
    proposals_dir: Path,
    now: _datetime_cls | None = None,
) -> Path:
    """Write ``memories/proposals/ROUTE-<slug>-<date>.md`` for an ambiguous card.

    ``card`` is the card frontmatter plus at least ``slug`` and ``card_path``
    (the destination of the note body) and optional ``source_experience``.
    ``candidates`` is a list of ``(shard_name, rationale)`` tuples; use the
    sentinel shard name ``"__new_shard__"`` for a "propose new shard" line and
    ``"__confirm_misc__"`` for the explicit confirm-misc option. The function
    always appends a final ``confirm misc`` line if one is not already present
    in ``candidates``.
    """
    proposals_dir.mkdir(parents=True, exist_ok=True)
    now_dt = now or _datetime_cls.now().astimezone()
    slug = str(card.get("slug", "")).strip()
    if not slug:
        raise ValueError("card must include a non-empty 'slug'")
    date_str = now_dt.date().isoformat()
    target = proposals_dir / f"ROUTE-{slug}-{date_str}.md"

    # Ensure confirm-misc sentinel is present.
    has_confirm = any(s == "__confirm_misc__" for s, _ in candidates)
    full_candidates = list(candidates)
    if not has_confirm:
        full_candidates.append(("__confirm_misc__", ""))

    candidate_lines = "\n".join(
        _format_candidate_line(s, r) for s, r in full_candidates
    )

    type_ = str(card.get("type", "")).strip()
    topics = _as_list(card.get("topics"))
    projects = _as_list(card.get("projects"))

    body = _ROUTE_PROPOSAL_TEMPLATE.format(
        slug=slug,
        created_at=now_dt.isoformat(timespec="seconds"),
        card_path=str(card.get("card_path", f"memories/long-term/{slug}.md")),
        source_experience=str(card.get("source_experience", "unknown")),
        type_=type_ or "(unspecified)",
        topics=", ".join(topics) if topics else "(none)",
        projects=", ".join(projects) if projects else "(none)",
        candidate_lines=candidate_lines,
    )
    target.write_text(body, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Route-candidate diagnostic pass
# ---------------------------------------------------------------------------


# Approximate topic signatures for each shard. Used by ``generate_route_candidates``
# to produce a "near match" shortlist for cards that routed to misc. Keep these
# in rough parity with the ladder in ``route_card`` but intentionally looser
# (single-topic overlap is enough to surface a shard as a candidate).
_SHARD_TOPIC_SIGNATURES: dict[str, set[str]] = {
    "paper-reading.md": {"paper-reading", "paper-reader", "paper-discovery", "paper-review"},
    "memory-system.md": {"memory-ingestion", "retrieval", "catalog", "memory", "experience-logger", "knowledge-maester"},
    "market-ops.md": {"market-watcher", "portfolio", "ticker", "market"},
    "tooling-ops.md": {"credential-broker", "env-vars", "secret-handling", "git"},
    "session-ops.md": {"research-meeting", "session-handoff", "session-continuity"},
    "skill-ops.md": {"skill-design", "skill-testing", "skill-onboarding", "strangler-fig", "skill"},
    "agent-ops.md": {"agent-ops", "preflight", "paper-trail", "safety"},
    "writing-style.md": {"writing", "manuscript", "review", "academic-writing"},
}


_SHARD_RATIONALES: dict[str, str] = {
    "paper-reading.md": "partial topic overlap with paper-reading shard",
    "memory-system.md": "partial topic overlap with memory-system shard",
    "market-ops.md": "partial topic overlap with market-ops shard",
    "tooling-ops.md": "partial topic overlap with tooling-ops shard",
    "session-ops.md": "partial topic overlap with session-ops shard",
    "skill-ops.md": "partial topic overlap with skill-ops shard",
    "agent-ops.md": "partial topic overlap with agent-ops shard",
    "writing-style.md": "partial topic overlap with writing-style shard",
}


def generate_route_candidates(frontmatter: dict) -> list[tuple[str, str]]:
    """Return up to 3 plausible shards (and rationales) for a misc-routed card.

    The routing ladder in ``route_card`` is first-match-wins; a ``misc`` result
    means no rule fired cleanly. For each topic-signature shard above, compute
    overlap with the card's topics and surface the top matches. Returns an
    empty list when no overlap exists (caller should still include a confirm
    misc line via the template).
    """
    topics = _as_list(frontmatter.get("topics"))
    topics_l = {t.lower() for t in topics}
    if not topics_l:
        return []

    scored: list[tuple[int, str]] = []
    for shard, sig in _SHARD_TOPIC_SIGNATURES.items():
        overlap = len(topics_l & sig)
        if overlap > 0:
            scored.append((overlap, shard))
    scored.sort(key=lambda t: (-t[0], t[1]))

    return [(shard, _SHARD_RATIONALES[shard]) for _, shard in scored[:3]]


# ---------------------------------------------------------------------------
# Capacity-signal emission
# ---------------------------------------------------------------------------


_LEDGER_SIGNAL_RE = re.compile(
    r"^- signal_last_emitted_(misc|catalog|proposals):\s*(\d+)\s*$",
    re.MULTILINE,
)


def _parse_last_emitted(ledger_text: str) -> dict[str, int]:
    out = {"misc": 0, "catalog": 0, "proposals": 0}
    for m in _LEDGER_SIGNAL_RE.finditer(ledger_text):
        out[m.group(1)] = int(m.group(2))
    return out


def _update_last_emitted(ledger_text: str, updates: dict[str, int]) -> str:
    """Return ``ledger_text`` with ``signal_last_emitted_*`` fields updated.

    The fields live in a ``## Capacity Signal State`` section at the end of the
    ledger; if the section is absent it is appended.
    """
    # Remove existing lines.
    new_text = _LEDGER_SIGNAL_RE.sub("", ledger_text)
    # Collapse any blank-line runs left behind.
    new_text = re.sub(r"\n{3,}", "\n\n", new_text).rstrip() + "\n"

    section_header = "## Capacity Signal State"
    lines = [
        f"- signal_last_emitted_misc: {updates.get('misc', 0)}",
        f"- signal_last_emitted_catalog: {updates.get('catalog', 0)}",
        f"- signal_last_emitted_proposals: {updates.get('proposals', 0)}",
    ]
    if section_header in new_text:
        # Replace the section's body.
        before, _, _ = new_text.partition(section_header)
        new_text = (
            before.rstrip()
            + "\n\n"
            + section_header
            + "\n\n"
            + "\n".join(lines)
            + "\n"
        )
    else:
        new_text = (
            new_text.rstrip()
            + "\n\n"
            + section_header
            + "\n\n"
            + "\n".join(lines)
            + "\n"
        )
    return new_text


def check_and_emit_capacity_signals(
    memory_root: Path,
    *,
    misc_card_count: int | None = None,
    total_card_count: int | None = None,
    pending_proposal_count: int | None = None,
    write_ledger: bool = True,
) -> list[str]:
    """Return capacity-signal lines for thresholds that transited upward.

    Counts may be supplied explicitly (for tests and dry runs); when omitted
    they are computed from the vault on disk. When ``write_ledger`` is True,
    the ledger's "last emitted at count" fields are refreshed so the same
    threshold is not re-emitted on the next ingestion.
    """
    shards_dir = memory_root / "catalog-shards"
    proposals_dir = memory_root / "proposals"

    if misc_card_count is None:
        misc_path = shards_dir / "misc.md"
        if misc_path.exists():
            misc_text = misc_path.read_text(encoding="utf-8")
            misc_card_count = sum(
                1 for m in _SLUG_HEADING_RE.finditer(misc_text)
                if m.group(1).strip() not in ("Generated Entries", "Manual Entries")
            )
        else:
            misc_card_count = 0

    if total_card_count is None:
        total_card_count = 0
        if shards_dir.exists():
            for shard_file in shards_dir.glob("*.md"):
                shard_text = shard_file.read_text(encoding="utf-8")
                total_card_count += sum(
                    1 for m in _SLUG_HEADING_RE.finditer(shard_text)
                    if m.group(1).strip() not in ("Generated Entries", "Manual Entries")
                )

    if pending_proposal_count is None:
        if proposals_dir.exists():
            pending_proposal_count = sum(
                1 for p in proposals_dir.glob("*.md") if not p.name.startswith(".")
            )
        else:
            pending_proposal_count = 0

    ledger_path = memory_root / "manager-ledger.md"
    ledger_text = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
    last_emitted = _parse_last_emitted(ledger_text)

    signals: list[str] = []
    new_state = dict(last_emitted)

    # Misc threshold: emit when crossing upward from below the threshold.
    if misc_card_count >= MISC_SOFT_THRESHOLD and last_emitted["misc"] < MISC_SOFT_THRESHOLD:
        signals.append(
            f"[SIGNAL] misc-shard at {misc_card_count} cards — "
            f"consider a maintenance review to re-home or archive."
        )
        new_state["misc"] = misc_card_count
    elif misc_card_count < MISC_SOFT_THRESHOLD:
        new_state["misc"] = misc_card_count

    # Phase-2 catalog threshold.
    if total_card_count >= CATALOG_PHASE2_THRESHOLD and last_emitted["catalog"] < CATALOG_PHASE2_THRESHOLD:
        signals.append(
            f"[SIGNAL] catalog at {total_card_count} cards — "
            f"consider Phase 2 (derived frontmatter query index; see "
            f"memory-retriever-improvement project for design)."
        )
        new_state["catalog"] = total_card_count
    elif total_card_count < CATALOG_PHASE2_THRESHOLD:
        new_state["catalog"] = total_card_count

    # Proposal review threshold.
    if pending_proposal_count >= PROPOSAL_REVIEW_THRESHOLD and last_emitted["proposals"] < PROPOSAL_REVIEW_THRESHOLD:
        signals.append(
            f"[SIGNAL] {pending_proposal_count} proposals pending — "
            f"run memory-manager in approval_mode to resolve."
        )
        new_state["proposals"] = pending_proposal_count
    elif pending_proposal_count < PROPOSAL_REVIEW_THRESHOLD:
        new_state["proposals"] = pending_proposal_count

    if write_ledger and (signals or new_state != last_emitted):
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_text = ledger_text or "# Memory Manager Ledger\n"
        ledger_path.write_text(_update_last_emitted(ledger_text, new_state), encoding="utf-8")

    return signals


# ---------------------------------------------------------------------------
# Route-proposal maintenance processing
# ---------------------------------------------------------------------------


_CHECKED_BOX_RE = re.compile(r"^- \[[xX]\] (.+)$", re.MULTILINE)


def _parse_route_proposal(text: str) -> dict:
    """Return {slug, card_path, chosen} for a ROUTE proposal file.

    ``chosen`` is one of:
      - ``{"kind": "shard", "shard": "<name>.md"}``
      - ``{"kind": "new_shard", "name": "<name>"}``
      - ``{"kind": "confirm_misc"}``
      - ``None`` if no checkbox is checked.
    """
    slug = ""
    card_path = ""
    for m in re.finditer(r"^- card_slug:\s*(\S+)", text, re.MULTILINE):
        slug = m.group(1).strip()
        break
    for m in re.finditer(r"^- card_path:\s*(\S+)", text, re.MULTILINE):
        card_path = m.group(1).strip()
        break

    chosen = None
    checked = _CHECKED_BOX_RE.search(text)
    if checked:
        payload = checked.group(1).strip()
        if payload.startswith("catalog-shards/"):
            shard = payload.split(" ", 1)[0][len("catalog-shards/"):]
            chosen = {"kind": "shard", "shard": shard}
        elif payload.startswith("propose new shard:"):
            name = payload[len("propose new shard:"):].split("—", 1)[0].strip()
            chosen = {"kind": "new_shard", "name": name}
        elif payload.startswith("confirm misc"):
            chosen = {"kind": "confirm_misc"}
    return {"slug": slug, "card_path": card_path, "chosen": chosen}


def _move_card_between_shards(
    shards_dir: Path,
    slug: str,
    source_shard: str,
    dest_shard: str,
) -> None:
    """Remove the ``## <slug>`` block from ``source_shard`` and append to ``dest_shard``."""
    source_path = shards_dir / source_shard
    if not source_path.exists():
        return
    content = source_path.read_text(encoding="utf-8")
    header, generated, manual = _split_shard(content)

    # Find and extract the slug entry.
    matches = list(_SLUG_HEADING_RE.finditer(generated))
    entry_text = None
    new_generated_parts = []
    last = 0
    for i, m in enumerate(matches):
        s = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(generated)
        if s == slug:
            entry_text = generated[start:end]
            new_generated_parts.append(generated[last:start])
            last = end
    new_generated_parts.append(generated[last:])
    new_generated = "".join(new_generated_parts)

    # Write source back.
    source_new = header + "## Generated Entries" + new_generated + "## Manual Entries" + manual
    source_path.write_text(source_new.rstrip() + "\n", encoding="utf-8")

    if entry_text is None:
        return

    # Append to destination shard.
    write_entry_to_shard(shards_dir, dest_shard, slug, entry_text)


def _create_empty_shard(
    memory_root: Path,
    shard_filename: str,
    description_placeholder: str = "TODO: describe shard purpose",
) -> None:
    """Create an empty shard file and add a minimal block to ``catalog-index.md``."""
    shards_dir = memory_root / "catalog-shards"
    shard_path = shards_dir / shard_filename
    if not shard_path.exists():
        shard_path.write_text(
            SHARD_HEADER_TEMPLATE.format(name=shard_filename[:-3]),
            encoding="utf-8",
        )

    index_path = memory_root / "catalog-index.md"
    if not index_path.exists():
        return
    index_text = index_path.read_text(encoding="utf-8")
    block_name = shard_filename[:-3]
    if f"### {block_name}\n" in index_text:
        return
    new_block = (
        f"\n### {block_name}\n"
        f"- path: catalog-shards/{shard_filename}\n"
        f"- description: {description_placeholder}\n"
        f"- stable_tags: []\n"
        f"- card_count: 0\n"
        f"- last_updated: \n"
    )
    index_path.write_text(index_text.rstrip() + "\n" + new_block, encoding="utf-8")


def process_route_proposals(
    memory_root: Path,
    *,
    interactive: bool = True,
    user_choice: "callable | None" = None,
) -> list[dict]:
    """Process pending ROUTE-* proposals under ``memories/proposals/``.

    ``user_choice`` is a callable ``(proposal_path, parsed) -> dict`` that
    returns the same ``chosen`` shape as ``_parse_route_proposal``. If
    omitted and ``interactive=True``, the function reads the checked box from
    the proposal file itself (i.e. the user has already edited the proposal
    file to check one option). If no box is checked, the proposal is skipped
    and reported.

    Returns a list of per-proposal result dicts.
    """
    proposals_dir = memory_root / "proposals"
    resolved_root = proposals_dir / "resolved"
    shards_dir = memory_root / "catalog-shards"
    if not proposals_dir.exists():
        return []

    proposal_files = sorted(
        [p for p in proposals_dir.glob("ROUTE-*.md") if p.is_file()]
    )
    results: list[dict] = []
    for path in proposal_files:
        text = path.read_text(encoding="utf-8")
        parsed = _parse_route_proposal(text)
        if user_choice is not None:
            chosen = user_choice(path, parsed)
        else:
            chosen = parsed["chosen"]
        slug = parsed["slug"]
        if chosen is None or not slug:
            results.append({"path": str(path), "slug": slug, "action": "skipped", "reason": "no checked option or missing slug"})
            continue

        action = None
        if chosen["kind"] == "shard":
            dest = chosen["shard"]
            _move_card_between_shards(shards_dir, slug, "misc.md", dest)
            update_index_for_shard(memory_root, "misc.md")
            update_index_for_shard(memory_root, dest)
            action = f"moved_to:{dest}"
        elif chosen["kind"] == "new_shard":
            new_name = chosen["name"]
            if not new_name.endswith(".md"):
                new_name = new_name + ".md"
            _create_empty_shard(memory_root, new_name)
            _move_card_between_shards(shards_dir, slug, "misc.md", new_name)
            update_index_for_shard(memory_root, "misc.md")
            update_index_for_shard(memory_root, new_name)
            action = f"moved_to_new_shard:{new_name}"
        elif chosen["kind"] == "confirm_misc":
            action = "confirmed_misc"

        # Move proposal file to resolved/YYYY-MM/
        yyyy_mm = _datetime_cls.now().strftime("%Y-%m")
        resolved_dir = resolved_root / yyyy_mm
        resolved_dir.mkdir(parents=True, exist_ok=True)
        resolution_note = f"\n\n- resolution: {action}\n"
        path.write_text(text.rstrip() + resolution_note, encoding="utf-8")
        target = resolved_dir / path.name
        path.rename(target)

        results.append({"path": str(target), "slug": slug, "action": action})

    return results


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
