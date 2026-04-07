#!/usr/bin/env python3
"""
generate_memory_catalog.py — regenerate memories/catalog.md from memory note frontmatter.

Usage:
  python3 knowledge-maester/scripts/generate_memory_catalog.py \
    [--vault-path PATH]   # default: ~/Documents/memory/
    [--output PATH]       # default: <vault-path>/catalog.md
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io

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


def _extract_manual_entries(existing_catalog: str) -> str:
    """
    Preserve the manual section verbatim.

    Preferred order is "Generated" then "Manual". If the file is malformed and has
    Manual before Generated, preserve the text between the matched Manual heading
    and the first Generated heading.
    """
    manual_matches = list(re.finditer(r"^##\s+Manual Entries\s*$", existing_catalog, flags=re.MULTILINE))
    if not manual_matches:
        return ""

    generated_matches = list(re.finditer(r"^##\s+Generated Entries\s*$", existing_catalog, flags=re.MULTILINE))
    generated_positions = [match.start() for match in generated_matches]

    if generated_positions:
        last_generated_pos = max(generated_positions)
        manual_after_generated = [m for m in manual_matches if m.start() > last_generated_pos]
        if manual_after_generated:
            selected = manual_after_generated[-1]
            return existing_catalog[selected.end():]

        first_generated_pos = min(generated_positions)
        manual_before_generated = [m for m in manual_matches if m.start() < first_generated_pos]
        if manual_before_generated:
            selected = manual_before_generated[-1]
            return existing_catalog[selected.end():first_generated_pos]

    return existing_catalog[manual_matches[-1].end():]


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
    lines = [
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
    return "\n".join(lines)


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


def generate_catalog(vault_path: Path, output_path: Path | None = None) -> int:
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault path does not exist: {vault_path}")

    output_path = output_path or (vault_path / "catalog.md")

    existing_catalog_path = vault_path / "catalog.md"
    existing_catalog = ""
    if existing_catalog_path.exists():
        existing_catalog = existing_catalog_path.read_text(encoding="utf-8", errors="replace")

    manual_section = _extract_manual_entries(existing_catalog)

    long_term, short_term, hubs = _scan_memory_notes(vault_path)
    operational = _scan_operational_notes(vault_path)

    generated_entries = CORE_IDENTITY_ENTRIES + long_term + short_term + hubs + operational

    rendered_entries = "\n\n".join(_render_entry(entry) for entry in generated_entries)

    output = (
        "# Searchable Memory Catalog\n\n"
        "This catalog tracks all searchable central memory that `memory-retriever` may use.\n\n"
        "## Generated Entries\n\n"
        f"{rendered_entries}\n\n"
        "## Manual Entries\n"
        f"{manual_section}"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")

    return len(generated_entries)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate memories/catalog.md from memory notes")
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
        help="Output path (default: <vault-path>/catalog.md)",
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

    destination = output_path if output_path else (vault_path / "catalog.md")
    print(f"CATALOG_GENERATED: {entry_count} entries -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
