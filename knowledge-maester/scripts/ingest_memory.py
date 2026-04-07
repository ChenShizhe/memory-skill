#!/usr/bin/env python3
"""
ingest_memory.py — Ingest or update memory notes in an Obsidian-style memory vault.

Usage:
  # Create a new memory note
  python3 knowledge-maester/scripts/ingest_memory.py \
    --source PATH \
    --title "Title" \
    --type workflow \
    --layer long-term \
    --topics "topic-1,topic-2" \
    --projects "project-1" \
    --priority high \
    [--vault-path PATH] \
    [--related "slug1,slug2"] \
    [--retrieval-hints "text"] \
    [--token-cost-estimate N]

  # Update an existing memory note
  python3 knowledge-maester/scripts/ingest_memory.py \
    --update \
    --note-path long-term/example-note.md \
    --source PATH \
    [--vault-path PATH]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io

DEFAULT_MEMORY_VAULT_PATH = Path.home() / "Documents" / "memory"

VALID_MEMORY_TYPES = {
    "workflow",
    "decision",
    "project-pattern",
    "reference",
    "continuity",
    "user-preference",
    "hub",
    "operational",
}
VALID_LAYERS = {"long-term", "short-term"}
VALID_PRIORITIES = {"high", "medium", "low"}


def _extract_section(body: str, heading: str) -> str:
    pattern = re.compile(
        r"^##\s+" + re.escape(heading) + r"\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(body)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


def _extract_h1(body: str) -> str:
    match = re.search(r"^\s*#\s+(.+?)\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _first_paragraph(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return ""
    paragraphs = re.split(r"\n\s*\n", stripped)
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith("#") for line in lines):
            continue
        return "\n".join(lines).strip()
    return ""


def _extract_list_items(text: str) -> list[str]:
    if not text.strip():
        return []
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+?)\s*$", line)
        if match:
            value = match.group(1).strip()
            if value:
                items.append(value)
            continue
        if items and line.strip():
            items[-1] = f"{items[-1]} {line.strip()}"
    return _dedupe_ordered(items)


def _parse_csv(value: str) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in value.split(",")]
    return _dedupe_ordered([part for part in parts if part])


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return _dedupe_ordered([str(v).strip() for v in value if str(v).strip()])
    if isinstance(value, str):
        return _parse_csv(value)
    return []


def _dedupe_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_wikilink_target(raw_target: str) -> str:
    candidate = raw_target.strip()
    if candidate.startswith("[[") and candidate.endswith("]]"):
        candidate = candidate[2:-2].strip()
    candidate = candidate.split("|", 1)[0].split("#", 1)[0].strip()
    if not candidate:
        return ""
    candidate = candidate.split("/")[-1].strip()
    if candidate.lower().startswith("_hub-"):
        suffix = candidate[5:]
        normalized_suffix = vault_io.slugify(suffix)
        return f"_hub-{normalized_suffix}" if normalized_suffix else "_hub-"
    slug = vault_io.slugify(candidate)
    return slug


def _extract_related_slugs_from_text(text: str) -> list[str]:
    links = vault_io.extract_wiki_links(text or "")
    slugs = []
    for link in links:
        normalized = _normalize_wikilink_target(link)
        if normalized:
            slugs.append(normalized)
    return _dedupe_ordered(slugs)


def _guidance_points_from_source(source_fm: dict, source_body: str) -> list[str]:
    guidance_section = _extract_section(source_body, "Guidance")
    if guidance_section:
        points = _extract_list_items(guidance_section)
        if points:
            return points
        first = _first_paragraph(guidance_section)
        return [first] if first else []

    fm_guidance = source_fm.get("guidance")
    if isinstance(fm_guidance, list):
        return _dedupe_ordered([str(item).strip() for item in fm_guidance if str(item).strip()])
    if isinstance(fm_guidance, str) and fm_guidance.strip():
        return [fm_guidance.strip()]
    return []


def _render_guidance(points: list[str]) -> str:
    if not points:
        return ""
    return "\n".join(f"- {point}" for point in points)


def _render_related(slugs: list[str]) -> str:
    if not slugs:
        return ""
    return "\n".join(f"- [[{slug}]]" for slug in slugs)


def _compose_memory_body(title: str, summary: str, guidance_points: list[str], related_slugs: list[str]) -> str:
    summary_text = summary.strip()
    guidance_text = _render_guidance(guidance_points)
    related_text = _render_related(related_slugs)
    return (
        f"# {title}\n\n"
        "## Summary\n\n"
        f"{summary_text}\n\n"
        "## Guidance\n\n"
        f"{guidance_text}\n\n"
        "## Related\n\n"
        f"{related_text}\n"
    )


def _replace_or_add_section(body: str, heading: str, content: str) -> str:
    section_pattern = re.compile(
        r"(^##\s+" + re.escape(heading) + r"\s*$)(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    replacement = f"## {heading}\n\n{content.strip()}\n\n"
    match = section_pattern.search(body)
    if match:
        return section_pattern.sub(replacement, body, count=1)
    return body.rstrip() + f"\n\n## {heading}\n\n{content.strip()}\n"


def _has_substring_duplicate(candidate: str, existing: list[str]) -> bool:
    for item in existing:
        if candidate in item or item in candidate:
            return True
    return False


def _create_missing_related_stubs(
    vault_path: Path,
    layer: str,
    note_slug: str,
    related_slugs: list[str],
) -> list[str]:
    stubs_created: list[str] = []
    for related_slug in related_slugs:
        if not related_slug or related_slug == note_slug:
            continue
        if vault_io.find_note_by_stem(vault_path, related_slug):
            continue
        stub_rel_path = f"{layer}/{related_slug}.md"
        if vault_io.note_exists(vault_path, stub_rel_path):
            continue
        title = related_slug.replace("-", " ").title()
        vault_io.create_stub(vault_path, stub_rel_path, "reference", title)
        stubs_created.append(stub_rel_path)
        print(f"STUB_CREATED: {stub_rel_path}")
    return stubs_created


def create_memory_note(
    source_path: Path,
    title: str,
    note_type: str,
    layer: str,
    topics: list[str],
    projects: list[str],
    priority: str,
    vault_path: Path,
    related: list[str] | None = None,
    retrieval_hints: str | None = None,
    token_cost_estimate: int | None = None,
) -> dict:
    source_content = source_path.read_text(encoding="utf-8")
    source_fm, source_body = vault_io.parse_frontmatter(source_content)
    today = vault_io.today_str()

    slug = vault_io.slugify(title)
    rel_path = f"{layer}/{slug}.md"

    if vault_io.note_exists(vault_path, rel_path):
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        if str(existing_fm.get("last_updated", "")) >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"status": "skipped", "vault_path": rel_path, "stubs_created": []}

    summary = _extract_section(source_body, "Summary") or _first_paragraph(source_body)
    guidance_points = _guidance_points_from_source(source_fm, source_body)
    related_slugs = _dedupe_ordered((related or []) + _extract_related_slugs_from_text(source_body))

    source_projects = _coerce_list(source_fm.get("source_projects")) or projects
    token_cost = token_cost_estimate
    if token_cost is None:
        try:
            source_token_cost = source_fm.get("token_cost_estimate")
            token_cost = int(source_token_cost) if source_token_cost is not None and str(source_token_cost) != "" else None
        except (TypeError, ValueError):
            token_cost = None

    memory_fm = {
        "title": title,
        "type": note_type,
        "layer": layer,
        "topics": topics,
        "projects": projects,
        "source_projects": source_projects,
        "status": "active",
        "date": today,
        "last_updated": today,
        "priority": priority,
        "token_cost_estimate": token_cost if token_cost is not None else "",
        "retrieval_hints": retrieval_hints or source_fm.get("retrieval_hints", ""),
    }

    body = _compose_memory_body(title, summary, guidance_points, related_slugs)
    vault_io.write_note(vault_path, rel_path, memory_fm, body)

    stubs_created = _create_missing_related_stubs(vault_path, layer, slug, related_slugs)
    print(f"NOTE_CREATED: {rel_path}")
    return {"status": "created", "vault_path": rel_path, "stubs_created": stubs_created}


def update_memory_note(
    note_path: str,
    source_path: Path,
    vault_path: Path,
) -> dict:
    existing_fm, existing_body = vault_io.read_note(vault_path, note_path)
    source_content = source_path.read_text(encoding="utf-8")
    source_fm, source_body = vault_io.parse_frontmatter(source_content)

    today = vault_io.today_str()
    note_layer = str(existing_fm.get("layer", Path(note_path).parts[0] if "/" in note_path else "long-term"))
    note_slug = Path(note_path).stem
    note_title = str(existing_fm.get("title") or _extract_h1(existing_body) or note_slug.replace("-", " ").title())

    source_summary = _extract_section(source_body, "Summary")
    merged_body = existing_body
    if source_summary:
        merged_body = _replace_or_add_section(merged_body, "Summary", source_summary)

    existing_guidance_section = _extract_section(merged_body, "Guidance")
    existing_guidance_points = _extract_list_items(existing_guidance_section)
    source_guidance_points = _guidance_points_from_source(source_fm, source_body)
    merged_guidance_points = list(existing_guidance_points)
    for point in source_guidance_points:
        if not _has_substring_duplicate(point, merged_guidance_points):
            merged_guidance_points.append(point)
    merged_body = _replace_or_add_section(merged_body, "Guidance", _render_guidance(merged_guidance_points))

    existing_related_slugs = _extract_related_slugs_from_text(_extract_section(merged_body, "Related"))
    source_related_section = _extract_section(source_body, "Related")
    source_related_slugs = _extract_related_slugs_from_text(source_related_section or source_body)
    merged_related_slugs = _dedupe_ordered(existing_related_slugs + source_related_slugs)
    merged_body = _replace_or_add_section(merged_body, "Related", _render_related(merged_related_slugs))

    existing_fm["title"] = note_title
    existing_fm["last_updated"] = today

    source_topics = _coerce_list(source_fm.get("topics"))
    if source_topics:
        existing_fm["topics"] = _dedupe_ordered(_coerce_list(existing_fm.get("topics")) + source_topics)

    source_projects = _coerce_list(source_fm.get("projects"))
    if source_projects:
        existing_fm["projects"] = _dedupe_ordered(_coerce_list(existing_fm.get("projects")) + source_projects)

    source_priority = source_fm.get("priority")
    if source_priority:
        existing_fm["priority"] = str(source_priority).strip()

    vault_io.write_note(vault_path, note_path, existing_fm, merged_body)
    stubs_created = _create_missing_related_stubs(vault_path, note_layer, note_slug, merged_related_slugs)
    print(f"NOTE_UPDATED: {note_path}")
    return {"status": "updated", "vault_path": note_path, "stubs_created": stubs_created}


def _validate_create_args(args) -> tuple[list[str], list[str], list[str]]:
    if args.type not in VALID_MEMORY_TYPES:
        raise ValueError(f"Invalid --type: {args.type}. Allowed: {sorted(VALID_MEMORY_TYPES)}")
    if args.layer not in VALID_LAYERS:
        raise ValueError(f"Invalid --layer: {args.layer}. Allowed: {sorted(VALID_LAYERS)}")
    if args.priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid --priority: {args.priority}. Allowed: {sorted(VALID_PRIORITIES)}")

    topics = _parse_csv(args.topics)
    projects = _parse_csv(args.projects)
    related = _parse_csv(args.related or "")

    if not args.title:
        raise ValueError("--title is required in create mode")
    if not topics:
        raise ValueError("--topics must contain at least one value in create mode")
    if not projects:
        raise ValueError("--projects must contain at least one value in create mode")

    return topics, projects, related


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update memory notes in the memory vault")
    parser.add_argument("--source", required=True, help="Path to source markdown")
    parser.add_argument("--vault-path", default=str(DEFAULT_MEMORY_VAULT_PATH))
    parser.add_argument("--update", action="store_true", help="Use update mode")
    parser.add_argument("--note-path", help="Vault-relative note path in update mode")

    # Create-mode fields
    parser.add_argument("--title", help="Note title (create mode)")
    parser.add_argument("--type", dest="type", help="Memory note type (create mode)")
    parser.add_argument("--layer", help="Memory layer (create mode)")
    parser.add_argument("--topics", default="", help="Comma-separated topics")
    parser.add_argument("--projects", default="", help="Comma-separated projects")
    parser.add_argument("--priority", help="Priority (high|medium|low)")
    parser.add_argument("--related", default="", help="Comma-separated related slugs")
    parser.add_argument("--retrieval-hints", default="", help="Retrieval hint text")
    parser.add_argument("--token-cost-estimate", type=int, default=None, help="Estimated retrieval token cost")
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    vault_path = Path(args.vault_path).expanduser()

    try:
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        if not vault_path.exists():
            raise FileNotFoundError(f"Vault path not found: {vault_path}")

        if args.update:
            if not args.note_path:
                raise ValueError("--note-path is required in update mode")
            update_memory_note(args.note_path, source_path, vault_path)
            return

        required = ["title", "type", "layer", "priority"]
        missing = [field for field in required if not getattr(args, field)]
        if missing:
            raise ValueError(f"Missing required create-mode args: {', '.join('--' + m for m in missing)}")

        topics, projects, related = _validate_create_args(args)
        create_memory_note(
            source_path=source_path,
            title=args.title,
            note_type=args.type,
            layer=args.layer,
            topics=topics,
            projects=projects,
            priority=args.priority,
            vault_path=vault_path,
            related=related,
            retrieval_hints=args.retrieval_hints,
            token_cost_estimate=args.token_cost_estimate,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
