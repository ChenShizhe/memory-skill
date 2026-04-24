#!/usr/bin/env python3
"""
generate_memory_catalog.py — regenerate the sharded memory catalog.

The sharded layout replaces the historical flat `memories/catalog.md`:
  - `<vault-path>/catalog-index.md`  — thin manifest of shards.
  - `<vault-path>/catalog-shards/<shard>.md` — per-topic shards with a
    `## Generated Entries` subsection (auto-managed) and a
    `## Manual Entries` subsection (preserved verbatim).

Usage:
  python3 knowledge-maester/scripts/generate_memory_catalog.py \
    [--vault-path PATH]   # default: ~/Documents/memory/
    [--output PATH]       # default: <vault-path>/catalog-index.md
                          # shard files are written to <vault-path>/catalog-shards/
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io

# Import the canonical router from memory-manager/bootstrap.py. Fall back to a
# local duplicate if the cross-package import is awkward.
try:
    _mm_dir = Path(__file__).resolve().parents[2] / "memory-manager"
    sys.path.insert(0, str(_mm_dir))
    from bootstrap import route_card as _route_card_canonical  # type: ignore
    route_card = _route_card_canonical
except Exception:  # pragma: no cover - fallback path
    # TODO(consolidate-route-card): keep this fallback in lockstep with the
    # memory-manager implementation until cross-package imports are stable.
    _GRADUATED_PROJECTS = {
        "coordination",
        "git-integration",
        "learning-by-doing",
        "memory-manager-v0",
        "paper-reader-improvement",
        "research-meeting",
        "skill-publication",
    }
    _CORE_IDENTITY_PATHS = {
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

    def route_card(frontmatter: dict) -> str:  # type: ignore[no-redef]
        path = str(frontmatter.get("path", "")).strip()
        type_ = str(frontmatter.get("type", "")).strip()
        slug = str(frontmatter.get("slug", "")).strip()
        projects = _as_list(frontmatter.get("projects"))
        topics = _as_list(frontmatter.get("topics"))
        topics_l = {t.lower() for t in topics}
        if path in _CORE_IDENTITY_PATHS:
            return "core-identity.md"
        if type_ == "workflow_template":
            return "workflow-templates.md"
        if type_ == "role_profile":
            return "roles.md"
        if type_ == "hub":
            return "hubs.md"
        if len(projects) == 1 and projects[0] in _GRADUATED_PROJECTS:
            return f"project-{projects[0]}.md"
        if len(projects) == 1:
            return "project-continuity.md"
        if (slug.startswith("paper-reader-") or slug.startswith("paper-discovery-")
                or slug.startswith("paper-review-")):
            return "paper-reading.md"
        if "paper-reading" in topics_l or "paper-reader" in topics_l:
            return "paper-reading.md"
        if (slug.startswith("memory-") or slug.startswith("catalog-")
                or slug.startswith("experience-logger-")
                or slug.startswith("knowledge-maester-")):
            return "memory-system.md"
        if "memory-ingestion" in topics_l or "retrieval" in topics_l or "catalog" in topics_l:
            return "memory-system.md"
        if slug.startswith("market-") or slug.startswith("portfolio-"):
            return "market-ops.md"
        if "market-watcher" in topics_l or "portfolio" in topics_l or "ticker" in topics_l:
            return "market-ops.md"
        if "credential" in slug or "broker" in slug or "git-" in slug:
            return "tooling-ops.md"
        if ("credential-broker" in topics_l or "env-vars" in topics_l
                or "secret-handling" in topics_l or "git" in topics_l):
            return "tooling-ops.md"
        if "research-meeting-" in slug or "session-" in slug:
            return "session-ops.md"
        if "research-meeting" in topics_l or "session-handoff" in topics_l:
            return "session-ops.md"
        if slug.startswith("ralph-") or slug.startswith("skill-"):
            return "skill-ops.md"
        if ("skill-design" in topics_l or "skill-testing" in topics_l
                or "skill-onboarding" in topics_l or "strangler-fig" in topics_l):
            return "skill-ops.md"
        if ("agent-ops" in topics_l or "preflight" in topics_l
                or "paper-trail" in topics_l or "safety" in topics_l):
            return "agent-ops.md"
        writing_topics = {"writing", "manuscript", "review", "academic-writing"}
        has_writing_topic = bool(topics_l & writing_topics)
        if has_writing_topic:
            return "writing-style.md"
        if type_ in {"user_preference", "user-preference"} and has_writing_topic:
            return "writing-style.md"
        return "misc.md"


DEFAULT_MEMORY_VAULT_PATH = Path.home() / "Documents" / "memory"

CORE_IDENTITY_ENTRIES = [
    {
        "slug": "agents-core-protocol",
        "path": "memories/AGENTS.md",
        "layer": "long-term",
        "title": "Agent Operating Protocol",
        "type": "workflow",
        "topics": ["agent-ops", "preflight", "skills", "paper-trail", "safety", "credentials", "env-vars"],
        "projects": ["example-project"],
        "summary": "Core session startup and operating procedures for all agents, including required pre-flight reads, skill discovery, default-skill mirror freshness checks, paper-trail expectations, two-tier credential access rules, and safe operating rules.",
        "retrieval_hints": "Use when the task depends on mandatory session startup behavior, skill discovery order, paper-trail requirements, credential access paths (env var vs broker), or safe non-destructive operation.",
        "priority": "high",
        "updated": "2026-03-11",
        "token_cost_estimate": "320",
    },
    {
        "slug": "soul-core-principles",
        "path": "memories/SOUL.md",
        "layer": "long-term",
        "title": "Core Operating Principles",
        "type": "operating_principle",
        "topics": ["ethics", "behavior", "quality", "privacy", "accuracy"],
        "projects": ["example-project"],
        "summary": "Universal agent principles covering helpfulness without filler, resourcefulness before asking, accuracy-first behavior, privacy boundaries, and team-readable paper trails.",
        "retrieval_hints": "Use when execution style, privacy boundaries, verification standards, or cross-agent operating principles materially affect the task.",
        "priority": "high",
        "updated": "2026-03-03",
        "token_cost_estimate": "220",
    },
    {
        "slug": "identity-core-boundaries",
        "path": "memories/IDENTITY.md",
        "layer": "long-term",
        "title": "System Identity And Boundaries",
        "type": "system_identity",
        "topics": ["identity", "architecture", "boundaries", "workspace", "credentials", "env-vars"],
        "projects": ["example-project"],
        "summary": "Core system identity and architectural boundaries for the system, including workspace responsibilities, read-only zones, two-tier credential handling (env vars for low-risk, broker for high-risk), and skill-onboarding constraints.",
        "retrieval_hints": "Use when the task depends on system role, workspace boundaries, skill onboarding, or credential and filesystem constraints.",
        "priority": "high",
        "updated": "2026-03-11",
        "token_cost_estimate": "260",
    },
    {
        "slug": "user-core-profile",
        "path": "memories/USER.md",
        "layer": "long-term",
        "title": "User Core Profile",
        "type": "user-preference",
        "topics": ["user-profile", "preferences", "collaboration-style", "timezone"],
        "projects": ["example-project"],
        "summary": "Core profile for the human collaborator, including stable preferences, communication expectations, and foundational context that should shape assistant behavior.",
        "retrieval_hints": "Use when tailoring tone, depth, and prioritization to the user's profile, values, or collaboration preferences.",
        "priority": "high",
        "updated": "2026-03-15",
        "token_cost_estimate": "180",
    },
]

OPERATIONAL_FILES = [
    "manager-ledger.md",
    "provider-quotas.md",
    "archive-catalog.md",
]


SHARD_HEADER_TEMPLATE = """# Catalog Shard — {name}

Searchable memory cards routed to this shard. See `../catalog-index.md` for the shard manifest. `generate_memory_catalog.py` rewrites the `## Generated Entries` subsection on regeneration; the `## Manual Entries` subsection is preserved verbatim. memory-manager writes generated entries at ingestion time; hand-edit only the Manual Entries subsection.

## Generated Entries

## Manual Entries
"""


_GENERATED_HEADING_RE = re.compile(r"^## Generated Entries\s*$", re.MULTILINE)
_MANUAL_HEADING_RE = re.compile(r"^## Manual Entries\s*$", re.MULTILINE)
_SLUG_HEADING_RE = re.compile(r"^## ([^\n]+)$", re.MULTILINE)


def _split_shard(content: str) -> tuple[str, str, str]:
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


def _extract_summary_first_paragraph(body: str) -> str:
    summary_match = re.search(r"^##\s+Summary\s*$", body, flags=re.MULTILINE | re.IGNORECASE)
    if not summary_match:
        return ""
    start = summary_match.end()
    next_h2 = re.search(r"^##\s+", body[start:], flags=re.MULTILINE)
    end = start + next_h2.start() if next_h2 else len(body)
    summary_section = body[start:end].strip()
    if not summary_section:
        return ""
    paragraphs = re.split(r"\n\s*\n", summary_section)
    for paragraph in paragraphs:
        text = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if text:
            return text
    return ""


def _to_rel_path_from_parent(vault_path: Path, note_path: Path) -> str:
    rel = note_path.relative_to(vault_path.parent)
    return rel.as_posix()


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []


def _build_entry(vault_path: Path, note_path: Path, frontmatter: dict, body: str) -> dict:
    stem = note_path.stem
    return {
        "slug": stem,
        "path": _to_rel_path_from_parent(vault_path, note_path),
        "layer": str(frontmatter.get("layer", "")).strip(),
        "title": str(frontmatter.get("title", "")).strip(),
        "type": str(frontmatter.get("type", "")).strip(),
        "topics": _as_list(frontmatter.get("topics")),
        "projects": _as_list(frontmatter.get("projects")),
        "summary": _extract_summary_first_paragraph(body),
        "retrieval_hints": str(frontmatter.get("retrieval_hints", "")).strip(),
        "priority": str(frontmatter.get("priority", "")).strip(),
        "updated": str(frontmatter.get("last_updated", "")).strip(),
        "token_cost_estimate": str(frontmatter.get("token_cost_estimate", "")).strip(),
    }


def _format_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return f"[{', '.join(values)}]"


def _render_entry(entry: dict) -> str:
    return "\n".join(
        [
            f"## {entry['slug']}",
            "",
            f"- path: {entry.get('path', '')}",
            f"- layer: {entry.get('layer', '')}",
            f"- title: {entry.get('title', '')}",
            f"- type: {entry.get('type', '')}",
            f"- topics: {_format_list(entry.get('topics', []))}",
            f"- projects: {_format_list(entry.get('projects', []))}",
            f"- summary: {entry.get('summary', '')}",
            f"- retrieval_hints: {entry.get('retrieval_hints', '')}",
            f"- priority: {entry.get('priority', '')}",
            f"- updated: {entry.get('updated', '')}",
            f"- token_cost_estimate: {entry.get('token_cost_estimate', '')}",
        ]
    )


def _scan_memory_notes(vault_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    long_term: list[dict] = []
    short_term: list[dict] = []
    hubs: list[dict] = []

    for layer in ("long-term", "short-term"):
        note_dir = vault_path / layer
        if not note_dir.exists():
            continue
        for note_path in sorted(note_dir.glob("*.md")):
            stem = note_path.stem
            if stem.startswith("_template") or stem.startswith("_hub-template"):
                continue
            content = note_path.read_text(encoding="utf-8", errors="replace")
            frontmatter, body = vault_io.parse_frontmatter(content)
            entry = _build_entry(vault_path, note_path, frontmatter, body)
            is_hub = entry.get("type") == "hub" or stem.startswith("_hub-")
            if is_hub:
                hubs.append(entry)
            elif layer == "long-term":
                long_term.append(entry)
            else:
                short_term.append(entry)

    long_term.sort(key=lambda item: item["slug"])
    short_term.sort(key=lambda item: item["slug"])
    hubs.sort(key=lambda item: item["slug"])
    return long_term, short_term, hubs


def _scan_operational_notes(vault_path: Path) -> list[dict]:
    operational: list[dict] = []
    for filename in OPERATIONAL_FILES:
        note_path = vault_path / filename
        if not note_path.exists():
            continue
        content = note_path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = vault_io.parse_frontmatter(content)
        if not frontmatter:
            continue
        operational.append(_build_entry(vault_path, note_path, frontmatter, body))
    operational.sort(key=lambda item: item["slug"])
    return operational


def _read_existing_manual(shard_path: Path) -> str:
    """Return the raw Manual Entries body of an existing shard, or ``""``.

    On malformed files, returns an empty string rather than raising.
    """
    if not shard_path.exists():
        return ""
    try:
        _, _, manual = _split_shard(shard_path.read_text(encoding="utf-8"))
    except ValueError:
        return ""
    return manual


def _write_shard(
    shard_path: Path,
    shard_name: str,
    generated_entries: list[dict],
    manual_body: str,
) -> None:
    if generated_entries:
        generated_body = "\n\n" + "\n\n".join(_render_entry(e) for e in generated_entries) + "\n"
    else:
        generated_body = "\n"
    header = SHARD_HEADER_TEMPLATE.split("## Generated Entries", 1)[0]
    body = (
        header
        + "## Generated Entries\n"
        + generated_body
        + "\n## Manual Entries"
        + (manual_body if manual_body else "\n")
    )
    # Ensure the file ends with exactly one trailing newline.
    body = body.rstrip() + "\n"
    shard_path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

DEFAULT_SHARD_DESCRIPTIONS = {
    "core-identity": "Core agent protocol, operating principles, system identity, user profile. Baseline for any session; load when no other shard clearly applies.",
    "agent-ops": "Agent preflight checks, paper-trail requirements, safety rules, credential access policies. Load when the task depends on startup behavior, skill discovery order, or credential handling.",
    "skill-ops": "Generic skill design, testing, packaging, versioning, onboarding patterns. Load when editing a skill, planning a skill-level change, or handling strangler-fig migrations.",
    "workflow-templates": "Stored canonical workflow patterns. Load when the task matches a recognizable workflow type.",
    "memory-system": "memory-retriever, memory-manager, catalog maintenance, experience-logger internals. Load when the task touches central memory, retrieval, or ingestion.",
    "paper-reading": "paper-reader dispatch, pipeline, vault integration, citadel patterns. Load when the task involves reading or processing academic papers.",
    "tooling-ops": "Credential broker, environment variables, git integration, external-tool access. Load when the task involves secrets, API access, or cross-repo git work.",
    "session-ops": "Session conduct, session handoffs, continuity between sessions. Load when the task is a research-meeting session or involves session bookkeeping.",
    "writing-style": "User writing-style feedback for manuscripts, reviews, assumption blocks, citations, plain-English norms. Load when producing polished prose, reviews, or manuscript content.",
    "hubs": "Topic-cluster hubs that index groups of related long-term notes. Load when the retriever's hub-shortcut logic fires.",
    "roles": "Role-specialist profiles for multi-agent sessions. Load only in multi-agent mode.",
    "market-ops": "market-watcher skill, portfolio management, ticker conventions. Load when the task involves market data or portfolio analysis.",
    "project-continuity": "Continuity cards for projects that have not yet earned their own shard.",
    "misc": "Quarantine for cards with ambiguous or unestablished routing. Drains via periodic maintenance runs; never the permanent home for any card.",
}

DEFAULT_SHARD_TAGS = {
    "core-identity": ["agent-ops", "identity", "user-profile", "core"],
    "agent-ops": ["preflight", "paper-trail", "safety", "credentials", "agent-ops"],
    "skill-ops": ["skill-design", "skill-testing", "skill-onboarding", "versioning", "strangler-fig"],
    "workflow-templates": ["workflow-template", "automation-template"],
    "memory-system": ["memory-ingestion", "retrieval", "catalog", "experience-logger"],
    "paper-reading": ["paper-reader", "paper-discovery", "paper-review", "vault", "citadel"],
    "tooling-ops": ["credential-broker", "env-vars", "secret-handling", "git"],
    "session-ops": ["research-meeting", "session-handoff", "session-continuity"],
    "writing-style": ["writing", "manuscript", "review", "academic-writing", "user-preference"],
    "hubs": ["hub", "topic-cluster"],
    "roles": ["role-profile", "specialist", "multi-agent"],
    "market-ops": ["market-watcher", "portfolio", "ticker"],
    "project-continuity": ["project-continuity"],
    "misc": ["misc", "uncategorized"],
}


_INDEX_BLOCK_RE = re.compile(
    r"(### (?P<name>[A-Za-z0-9_-]+)\n"
    r"(?:- (?:path|description|stable_tags|card_count|last_updated):[^\n]*\n?)+)",
    re.MULTILINE,
)


def _parse_existing_index(index_path: Path) -> dict[str, dict]:
    """Return name -> {path, description, stable_tags, card_count, last_updated}.

    Empty dict when no index exists.
    """
    if not index_path.exists():
        return {}
    text = index_path.read_text(encoding="utf-8")
    blocks: dict[str, dict] = {}
    for m in _INDEX_BLOCK_RE.finditer(text):
        name = m.group("name")
        block = m.group(0)
        fields: dict[str, str] = {}
        for fm in re.finditer(r"^- (\w+):\s*(.*)$", block, re.MULTILINE):
            fields[fm.group(1)] = fm.group(2).strip()
        blocks[name] = fields
    return blocks


def _write_index(index_path: Path, shard_info: dict[str, dict]) -> None:
    lines = [
        "# Memory Catalog Index",
        "",
        "This file is the top-level manifest of the searchable memory. memory-retriever reads this first to decide which shards to open in a session. memory-manager keeps `card_count` and `last_updated` in sync with shard contents on every ingestion; `description` and `stable_tags` are hand-edited and stable.",
        "",
        "## Registered projects",
        "",
        "<!-- Comma-separated list of project names that currently have, or may grow into, their own shard. Update by hand when a new project is added. -->",
        "",
        "## Shards",
        "",
    ]
    canonical_order = [
        "core-identity",
        "agent-ops",
        "skill-ops",
        "workflow-templates",
        "memory-system",
        "paper-reading",
        "tooling-ops",
        "session-ops",
        "writing-style",
        "hubs",
        "roles",
        "market-ops",
        "project-continuity",
    ]
    ordered = [n for n in canonical_order if n in shard_info]
    project_names = sorted(
        n for n in shard_info
        if n.startswith("project-") and n != "project-continuity"
    )
    other_names = sorted(
        n for n in shard_info
        if n not in canonical_order and not n.startswith("project-") and n != "misc"
    )
    ordered.extend(project_names)
    ordered.extend(other_names)
    if "misc" in shard_info:
        ordered.append("misc")

    for name in ordered:
        info = shard_info[name]
        tags_str = "[" + ", ".join(info.get("stable_tags", [])) + "]"
        lines.extend([
            f"### {name}",
            f"- path: catalog-shards/{name}.md",
            f"- description: {info.get('description', '')}",
            f"- stable_tags: {tags_str}",
            f"- card_count: {info.get('card_count', 0)}",
            f"- last_updated: {info.get('last_updated', '')}",
            "",
        ])
    index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_catalog(vault_path: Path, output_path: Path | None = None) -> int:
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault path does not exist: {vault_path}")

    output_path = output_path or (vault_path / "catalog-index.md")
    shards_dir = vault_path / "catalog-shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    # Collect entries.
    long_term, short_term, hubs_list = _scan_memory_notes(vault_path)
    operational = _scan_operational_notes(vault_path)
    all_generated: list[dict] = CORE_IDENTITY_ENTRIES + long_term + short_term + hubs_list + operational

    # Route each entry.
    by_shard: dict[str, list[dict]] = {}
    for entry in all_generated:
        shard = route_card(entry)
        by_shard.setdefault(shard, []).append(entry)

    # Read existing index to preserve description/stable_tags.
    existing_index = _parse_existing_index(output_path)

    # Write every routed shard, preserving existing Manual content.
    # Also preserve existing shards that had no new routed entries (so Manual
    # survives regeneration even when the shard becomes empty of Generated).
    existing_shards = {p.name for p in shards_dir.glob("*.md")}
    all_shard_names = set(by_shard.keys()) | existing_shards

    shard_info: dict[str, dict] = {}
    for shard_name in sorted(all_shard_names):
        shard_path = shards_dir / shard_name
        existing_manual = _read_existing_manual(shard_path)
        generated = by_shard.get(shard_name, [])
        _write_shard(shard_path, shard_name, generated, existing_manual)

        # Count slugs across both sections, excluding the section headings.
        shard_text = shard_path.read_text(encoding="utf-8")
        slugs = [
            m.group(1).strip()
            for m in _SLUG_HEADING_RE.finditer(shard_text)
            if m.group(1).strip() not in ("Generated Entries", "Manual Entries")
        ]
        card_count = len(slugs)
        last_updated = ""
        for m in re.finditer(r"^- updated:\s*(\S+)", shard_text, re.MULTILINE):
            val = m.group(1).strip()
            if val > last_updated:
                last_updated = val

        base = shard_name[:-3]
        existing = existing_index.get(base, {})
        stable_tags_raw = existing.get("stable_tags", "")
        if stable_tags_raw.startswith("[") and stable_tags_raw.endswith("]"):
            stable_tags = [
                t.strip() for t in stable_tags_raw[1:-1].split(",") if t.strip()
            ]
        else:
            stable_tags = DEFAULT_SHARD_TAGS.get(base, [])
        description = existing.get("description") or DEFAULT_SHARD_DESCRIPTIONS.get(
            base, ""
        )
        shard_info[base] = {
            "description": description,
            "stable_tags": stable_tags,
            "card_count": card_count,
            "last_updated": last_updated,
        }

    _write_index(output_path, shard_info)

    return len(all_generated)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Regenerate the sharded memory catalog (catalog-index.md + catalog-shards/)",
    )
    parser.add_argument(
        "--vault-path",
        type=Path,
        default=DEFAULT_MEMORY_VAULT_PATH,
        help="Path to memory vault (default: ~/Documents/memory)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output index path (default: <vault-path>/catalog-index.md). "
             "Shards are written alongside under <vault-path>/catalog-shards/.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    vault_path = args.vault_path.expanduser().resolve()
    output_path = args.output.expanduser().resolve() if args.output else None

    if not vault_path.exists():
        print(f"ERROR: vault path does not exist: {vault_path}")
        return 1

    try:
        entry_count = generate_catalog(vault_path=vault_path, output_path=output_path)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    destination = output_path if output_path else (vault_path / "catalog-index.md")
    print(f"CATALOG_GENERATED: {entry_count} entries -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
