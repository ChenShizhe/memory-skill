#!/usr/bin/env python3
"""
ingest_reference.py — Ingest a reference/capability note into the vault.

Maps: <workspace>/reference-note.md → citadel/reference/<slug>.md

Usage:
  python3 knowledge-maester/scripts/ingest_reference.py \\
    --source PATH_TO_SOURCE_MD \\
    --title "Human-Readable Title" \\
    --tags my-system,tool-name \\
    --category tool-capability \\
    [--vault-path PATH]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io

# Protect existing syntax that should not be rewritten.
PROTECTED_SPAN_PATTERN = re.compile(
    r"(```[\s\S]*?```|`[^`\n]*`|\[\[[^\[\]]+\]\]|https?://[^\s)\]]+)"
)

# Balanced entity detection:
# - Hyphenated names (e.g. market-watcher, knowledge-maester)
# - Title-case/acronym multi-word names (e.g. Knowledge Maester, LLM Digestion)
TITLE_ENTITY_PATTERN = re.compile(
    r"\b((?:[A-Z][a-z0-9]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z0-9]+|[A-Z]{2,}))+)\b"
)
HYPHEN_ENTITY_PATTERN = re.compile(r"\b([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)\b")

TITLE_STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of",
    "on", "or", "the", "to", "with", "without", "vs", "via",
}
TITLE_PHRASE_STOPWORDS = {
    "key findings", "main developments", "market dashboard", "source index",
    "risks and counterarguments", "open questions", "one paragraph summary",
    "related reports", "related notes", "related links",
}
HYPHEN_STOPWORDS = {
    "auto-generated", "tool-capability", "last_updated", "run-id",
    "project-name", "wiki-links",
}


def _extract_section(body: str, heading: str) -> str:
    pattern = re.compile(
        r"^#{1,3}\s+" + re.escape(heading) + r"\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(body)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^#{1,2}\s+", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


def _strip_h1(body: str) -> str:
    return re.sub(r"^\s*#\s+.*?$", "", body, count=1, flags=re.MULTILINE).strip()


def _parse_tags(tags_raw: str) -> list[str]:
    if not tags_raw.strip():
        return []
    seen = set()
    tags = []
    for part in tags_raw.split(","):
        tag = part.strip()
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def _should_link_entity(entity_text: str, entity_kind: str) -> bool:
    normalized = entity_text.strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if entity_kind == "title":
        if lowered in TITLE_PHRASE_STOPWORDS:
            return False
        words = [w.lower() for w in normalized.split()]
        if len(words) < 2:
            return False
        if all(w in TITLE_STOPWORDS for w in words):
            return False
    else:
        if lowered in HYPHEN_STOPWORDS:
            return False

    return True


def _collect_entity_matches(segment: str, current_slug: str) -> list[tuple[int, int, str, str]]:
    candidates = []

    for match in TITLE_ENTITY_PATTERN.finditer(segment):
        raw = match.group(1)
        if not _should_link_entity(raw, "title"):
            continue
        slug = vault_io.slugify(raw)
        if not slug or slug == current_slug:
            continue
        candidates.append((match.start(1), match.end(1), raw, slug, 0))

    for match in HYPHEN_ENTITY_PATTERN.finditer(segment):
        raw = match.group(1)
        if not _should_link_entity(raw, "hyphen"):
            continue
        slug = vault_io.slugify(raw)
        if not slug or slug == current_slug:
            continue
        candidates.append((match.start(1), match.end(1), raw, slug, 1))

    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[4]))

    selected = []
    cursor = -1
    for start, end, raw, slug, _priority in candidates:
        if start < cursor:
            continue
        selected.append((start, end, raw, slug))
        cursor = end
    return selected


def _link_segment(segment: str, current_slug: str) -> tuple[str, dict[str, str]]:
    matches = _collect_entity_matches(segment, current_slug)
    if not matches:
        return segment, {}

    linked = []
    entity_titles: dict[str, str] = {}
    cursor = 0

    for start, end, raw, slug in matches:
        linked.append(segment[cursor:start])
        linked.append(f"[[{slug}|{raw}]]")
        entity_titles.setdefault(slug, raw)
        cursor = end

    linked.append(segment[cursor:])
    return "".join(linked), entity_titles


def _link_entities(text: str, current_slug: str) -> tuple[str, dict[str, str]]:
    if not text:
        return "", {}

    transformed_parts = []
    entity_titles: dict[str, str] = {}
    cursor = 0

    for match in PROTECTED_SPAN_PATTERN.finditer(text):
        plain_chunk = text[cursor:match.start()]
        linked_chunk, chunk_entities = _link_segment(plain_chunk, current_slug)
        transformed_parts.append(linked_chunk)
        transformed_parts.append(match.group(0))
        for slug, title in chunk_entities.items():
            entity_titles.setdefault(slug, title)
        cursor = match.end()

    tail = text[cursor:]
    linked_tail, tail_entities = _link_segment(tail, current_slug)
    transformed_parts.append(linked_tail)
    for slug, title in tail_entities.items():
        entity_titles.setdefault(slug, title)

    return "".join(transformed_parts), entity_titles


def ingest_reference(
    source_path: Path,
    title: str,
    tags: list[str],
    category: str,
    vault_path: Path,
) -> dict:
    content = source_path.read_text(encoding="utf-8")
    _source_fm, body = vault_io.parse_frontmatter(content)
    today = vault_io.today_str()

    slug = vault_io.slugify(title)
    rel_path = f"reference/{slug}.md"

    # Idempotency
    if vault_io.note_exists(vault_path, rel_path):
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        if existing_fm.get("last_updated", "") >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"vault_path": rel_path, "stubs_created": [], "status": "skipped"}

    context = _extract_section(body, "Context")
    content_section = _extract_section(body, "Content")
    related = _extract_section(body, "Related")

    # Fallback: if source has no structured sections, put all source body in Content.
    if not (context or content_section or related):
        content_section = _strip_h1(body)

    linked_context, context_entities = _link_entities(context, slug)
    linked_content, content_entities = _link_entities(content_section, slug)
    linked_related, related_entities = _link_entities(related, slug)

    linked_entities: dict[str, str] = {}
    for mapping in (context_entities, content_entities, related_entities):
        for entity_slug, display_name in mapping.items():
            linked_entities.setdefault(entity_slug, display_name)

    vault_fm = {
        "type": "memory",
        "title": title,
        "date": today,
        "tags": tags,
        "last_updated": today,
        "status": "active",
        "category": category,
    }

    vault_body = (
        f"# {title}\n\n"
        "## Context\n\n"
        f"{linked_context}\n\n"
        "## Content\n\n"
        f"{linked_content}\n\n"
        "## Related\n\n"
        f"{linked_related}\n"
    )

    vault_io.write_note(vault_path, rel_path, vault_fm, vault_body)
    print(f"WRITTEN: {rel_path}")

    stubs_created = []
    for entity_slug, display_name in linked_entities.items():
        if entity_slug == slug:
            continue
        if vault_io.find_note_by_stem(vault_path, entity_slug):
            continue
        stub_rel = f"reference/{entity_slug}.md"
        if vault_io.note_exists(vault_path, stub_rel):
            continue
        vault_io.create_stub(vault_path, stub_rel, "memory", display_name)
        stubs_created.append(stub_rel)
        print(f"STUB_CREATED: {stub_rel}")

    return {"vault_path": rel_path, "stubs_created": stubs_created, "status": "created"}


def main():
    parser = argparse.ArgumentParser(description="Ingest a reference note into vault")
    parser.add_argument("--source", required=True, help="Path to source markdown")
    parser.add_argument("--title", required=True, help="Note title for the target memory note")
    parser.add_argument("--tags", default="", help="Comma-separated tags (optional)")
    parser.add_argument("--category", required=True, help="Memory category (e.g. tool-capability)")
    parser.add_argument("--vault-path", default=str(vault_io.DEFAULT_VAULT_PATH))
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    vault_path = Path(args.vault_path).expanduser()
    tags = _parse_tags(args.tags)

    if not source_path.exists():
        print(f"ERROR: Source file not found: {source_path}")
        sys.exit(1)
    if not vault_path.exists():
        print(f"ERROR: Vault not found at {vault_path}. Run preflight_maester.py first.")
        sys.exit(1)

    result = ingest_reference(
        source_path=source_path,
        title=args.title,
        tags=tags,
        category=args.category,
        vault_path=vault_path,
    )
    print(f"DONE: status={result['status']}, stubs={len(result['stubs_created'])}")


if __name__ == "__main__":
    main()
