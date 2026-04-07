#!/usr/bin/env python3
"""
ingest_paper.py — Ingest a literature note into the vault.

Maps:
  paper         → literature/papers/<cite_key>.md  + paper-bank/_manifest.json
  concept       → literature/concepts/<concept-slug>.md
  assumption    → literature/assumptions/<assumption-slug>.md
  proof-pattern → literature/proof-patterns/<pattern-slug>.md
  author        → literature/authors/<author-slug>.md

Usage:
  python3 knowledge-maester/scripts/ingest_paper.py \\
    --note PATH_TO_NOTE_MD \\
    [--type paper|concept|assumption|proof-pattern|author] \\
    [--cite-key CITE_KEY] \\
    [--vault-path PATH] \\
    [--paper-bank-path PATH] \\
    [--dry-run]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io

TYPE_TO_DIRECTORY = {
    "paper": "literature/papers",
    "concept": "literature/concepts",
    "assumption": "literature/assumptions",
    "proof-pattern": "literature/proof-patterns",
    "author": "literature/authors",
}

NON_PAPER_IDENTITY_FIELDS = {
    "concept": ("concept_key", "concept", "slug", "id", "title"),
    "assumption": ("assumption_key", "assumption", "slug", "id", "title"),
    "proof-pattern": ("proof_pattern_key", "proof_pattern", "proof-pattern", "slug", "id", "title"),
    "author": ("author_key", "author", "name", "slug", "id", "title"),
}


def ingest_paper(
    cite_key: str,
    note_path: Path,
    vault_path: Path,
    paper_bank_path: Path,
) -> dict:
    content = note_path.read_text(encoding="utf-8")
    fm, body = vault_io.parse_frontmatter(content)
    today = vault_io.today_str()

    # Prefer cite_key from args over frontmatter
    title = fm.get("title", "") or _extract_h1(body) or cite_key
    authors = fm.get("authors", [])
    year = fm.get("year", "")
    canonical_id = fm.get("canonical_id", "") or fm.get("doi", "") or fm.get("arxiv_id", "")
    content_status = fm.get("content_status", "")
    review_status = fm.get("review_status", "draft")
    tags = fm.get("tags", [])

    # Check paper-bank for metadata
    bank_path_rel = f"{cite_key}/"
    bank_meta_path = paper_bank_path / cite_key / "metadata.json"
    bank_meta = {}
    if bank_meta_path.exists():
        import json
        try:
            bank_meta = json.loads(bank_meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    if bank_meta:
        title = bank_meta.get("title", title) or title
        authors = bank_meta.get("authors", authors) or authors
        year = bank_meta.get("year", year) or year
        canonical_id = bank_meta.get("doi", canonical_id) or bank_meta.get("arxiv_id", canonical_id) or canonical_id

    source_type = fm.get("source_type", fm.get("source_format", ""))
    source_path_val = fm.get("source_path", "")

    rel_path = f"literature/papers/{cite_key}.md"

    # Idempotency
    if vault_io.note_exists(vault_path, rel_path):
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        if existing_fm.get("last_updated", "") >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"vault_path": rel_path, "stubs_created": [], "status": "skipped"}

    # Extract sections
    summary = _extract_section(body, "Summary") or _extract_section(body, "Abstract") or ""
    key_claims = _extract_section(body, "Key Claims") or _extract_section(body, "Claims") or ""
    methodology = _extract_section(body, "Methodology") or _extract_section(body, "Methods") or ""
    links_section = _extract_section(body, "Links") or ""

    # Extract cited keys from existing links section
    cited_keys = re.findall(r'\[\[([a-z][a-z0-9]+\d{4}[a-z]*)\]\]', links_section, re.IGNORECASE)

    vault_fm = {
        "type": "paper",
        "title": title,
        "cite_key": cite_key,
        "canonical_id": canonical_id,
        "authors": authors if isinstance(authors, list) else [authors],
        "year": year,
        "date": today,
        "tags": tags,
        "last_updated": today,
        "content_status": content_status,
        "review_status": review_status,
        "bank_path": bank_path_rel,
        "status": "active",
        "schema_version": "2",
        "extraction_confidence": 0.9,
        "validation_status": "pending",
        "source_type": source_type,
        "source_path": source_path_val,
        "source_parse_status": "complete",
        "bibliography_status": "pending",
        "auto_block_hash": "",
    }

    # Build body
    cited_links = " ".join(f"[[{k}]]" for k in cited_keys) if cited_keys else ""
    body_parts = [
        f"# {title}\n",
        "## Summary\n",
        summary or "*No summary provided.*",
        "\n",
        "## Key Claims\n",
        key_claims or "*No key claims extracted.*",
        "\n",
        "## Methodology\n",
        methodology or "*No methodology section.*",
        "\n",
        "## Links\n",
        f"- Related:",
    ]
    if cited_links:
        body_parts.append(f"- Cites: {cited_links}")

    vault_body = "\n".join(body_parts)
    vault_io.write_note(vault_path, rel_path, vault_fm, vault_body)
    print(f"WRITTEN: {rel_path}")

    # Create stubs for cited papers
    stubs_created = []
    for cited_key in cited_keys:
        cited_rel = f"literature/papers/{cited_key}.md"
        if not vault_io.note_exists(vault_path, cited_rel):
            vault_io.create_stub(vault_path, cited_rel, "paper", cited_key)
            stubs_created.append(cited_rel)
            print(f"STUB_CREATED: {cited_rel}")

    # Update paper-bank manifest
    vault_io.upsert_manifest_entry(paper_bank_path, {
        "cite_key": cite_key,
        "title": title,
        "authors": authors if isinstance(authors, list) else [authors],
        "year": str(year),
        "vault_path": rel_path,
        "bank_path": bank_path_rel,
        "date_added": today,
    })
    print(f"MANIFEST_UPDATED: {cite_key}")

    return {"vault_path": rel_path, "stubs_created": stubs_created, "status": "created"}


def ingest_note_type(
    note_type: str,
    note_path: Path,
    vault_path: Path,
    identity_hint: str = "",
) -> dict:
    if note_type == "paper":
        raise ValueError("ingest_note_type only handles non-paper note types")

    content = note_path.read_text(encoding="utf-8")
    fm, body = vault_io.parse_frontmatter(content)
    today = vault_io.today_str()

    slug, title = _resolve_non_paper_identity(note_type, fm, body, note_path, identity_hint)
    rel_path = f"{TYPE_TO_DIRECTORY[note_type]}/{slug}.md"

    if vault_io.note_exists(vault_path, rel_path):
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        if existing_fm.get("last_updated", "") >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"vault_path": rel_path, "stubs_created": [], "status": "skipped"}

    vault_fm = dict(fm) if isinstance(fm, dict) else {}
    vault_fm["type"] = note_type
    vault_fm["title"] = title
    vault_fm["date"] = _as_text(vault_fm.get("date")) or today
    vault_fm["tags"] = _normalize_tags(vault_fm.get("tags"))
    vault_fm["last_updated"] = today
    vault_fm["status"] = _as_text(vault_fm.get("status")) or "active"
    if note_type != "author" and identity_hint and "source_paper" not in vault_fm:
        vault_fm["source_paper"] = identity_hint

    body_text = body.strip()
    if not body_text:
        body_text = "*No content provided.*"
    if not _extract_h1(body_text):
        body_text = f"# {title}\n\n{body_text}"

    vault_io.write_note(vault_path, rel_path, vault_fm, body_text)
    print(f"WRITTEN: {rel_path}")
    return {"vault_path": rel_path, "stubs_created": [], "status": "created"}


def ingest_digest(
    cite_key: str,
    note_path: Path,
    vault_path: Path,
) -> dict:
    content = note_path.read_text(encoding="utf-8")
    fm, body = vault_io.parse_frontmatter(content)
    today = vault_io.today_str()

    title = fm.get("title", "") or _extract_h1(body) or f"Digest: {cite_key}"
    field = fm.get("field", "")
    tags = fm.get("tags", [])

    rel_path = f"literature/digests/{cite_key}-digest.md"
    if vault_io.note_exists(vault_path, rel_path):
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        if existing_fm.get("last_updated", "") >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"vault_path": rel_path, "stubs_created": [], "status": "skipped"}

    one_para = _extract_section(body, "One-Paragraph Summary") or _extract_section(body, "Summary") or ""
    contributions = _extract_section(body, "Key Contributions") or _extract_section(body, "Contributions") or ""
    claims = _extract_section(body, "Claims Worth Tracking") or _extract_section(body, "Claims") or ""
    questions = _extract_section(body, "Open Questions") or _extract_section(body, "Questions") or ""

    vault_fm = {
        "type": "digest",
        "title": title,
        "source_paper": cite_key,
        "cite_key": cite_key,
        "date": today,
        "tags": tags,
        "last_updated": today,
        "field": field,
        "status": "draft",
    }

    body_parts = [
        f"# {title}\n",
        "## One-Paragraph Summary\n",
        one_para or "*No summary provided.*",
        "\n",
        "## Key Contributions\n",
        contributions or "",
        "\n",
        "## Claims Worth Tracking\n",
        claims or "",
        "\n",
        "## Open Questions\n",
        questions or "",
        "\n",
        "## Links\n",
        f"- Paper: [[{cite_key}]]",
        "- Related:",
    ]

    vault_body = "\n".join(body_parts)
    vault_io.write_note(vault_path, rel_path, vault_fm, vault_body)
    print(f"WRITTEN: {rel_path}")

    # Add backlink in paper note if it exists
    paper_rel = f"literature/papers/{cite_key}.md"
    if vault_io.note_exists(vault_path, paper_rel):
        paper_content = (vault_path / paper_rel).read_text(encoding="utf-8")
        digest_link = f"- Digest: [[{cite_key}-digest]]"
        if digest_link not in paper_content:
            if "## Links" in paper_content:
                paper_content = paper_content.replace("## Links\n", f"## Links\n{digest_link}\n", 1)
            else:
                paper_content += f"\n## Links\n{digest_link}\n"
            (vault_path / paper_rel).write_text(paper_content, encoding="utf-8")

    return {"vault_path": rel_path, "stubs_created": [], "status": "created"}


def ingest_field(
    field_name: str,
    note_path: Path,
    vault_path: Path,
) -> dict:
    content = note_path.read_text(encoding="utf-8")
    fm, body = vault_io.parse_frontmatter(content)
    today = vault_io.today_str()

    title = fm.get("title", "") or _extract_h1(body) or field_name
    tags = fm.get("tags", [])
    slug = vault_io.slugify(field_name)
    rel_path = f"literature/fields/{slug}.md"

    if vault_io.note_exists(vault_path, rel_path):
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        if existing_fm.get("last_updated", "") >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"vault_path": rel_path, "stubs_created": [], "status": "skipped"}

    vault_fm = {
        "type": "memory",
        "title": title,
        "date": today,
        "tags": tags,
        "last_updated": today,
        "category": "field-summary",
        "status": "active",
    }

    vault_body = f"# {title}\n\n## Context\n\n## Content\n\n{body.strip()}\n\n## Related\n"
    vault_io.write_note(vault_path, rel_path, vault_fm, vault_body)
    print(f"WRITTEN: {rel_path}")

    return {"vault_path": rel_path, "stubs_created": [], "status": "created"}


def _extract_h1(body: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _extract_section(body: str, heading: str) -> str:
    pattern = re.compile(
        r"^#{1,3}\s+" + re.escape(heading) + r"\s*$",
        re.MULTILINE | re.IGNORECASE
    )
    m = pattern.search(body)
    if not m:
        return ""
    start = m.end()
    next_heading = re.search(r"^#{1,2}\s+", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


def _as_text(value) -> str:
    if isinstance(value, list):
        if not value:
            return ""
        return str(value[0]).strip()
    if value is None:
        return ""
    return str(value).strip()


def _normalize_tags(raw_tags) -> list[str]:
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if str(t).strip()]
    if raw_tags is None:
        return []
    tag = str(raw_tags).strip()
    return [tag] if tag else []


def _resolve_non_paper_identity(
    note_type: str,
    fm: dict,
    body: str,
    note_path: Path,
    identity_hint: str = "",
) -> tuple[str, str]:
    if note_type not in NON_PAPER_IDENTITY_FIELDS:
        raise ValueError(f"Unsupported note type: {note_type}")

    identity_value = ""
    for key in NON_PAPER_IDENTITY_FIELDS[note_type]:
        candidate = _as_text(fm.get(key, ""))
        if candidate:
            identity_value = candidate
            break
    if not identity_value and identity_hint:
        identity_value = identity_hint.strip()
    if not identity_value:
        identity_value = _extract_h1(body) or note_path.stem

    title = _as_text(fm.get("title", "")) or _extract_h1(body) or identity_value
    slug_source = _as_text(fm.get("slug", "")) or identity_value
    slug = vault_io.slugify(slug_source) or vault_io.slugify(note_path.stem) or "note"
    return slug, title.strip()


def main():
    parser = argparse.ArgumentParser(description="Ingest a paper/concept/assumption/proof-pattern/author note into vault")
    parser.add_argument("--cite-key", help="Cite key (required for paper; optional identity hint for non-paper types)")
    parser.add_argument("--note", required=True, help="Path to note markdown file")
    parser.add_argument(
        "--type",
        choices=["paper", "concept", "assumption", "proof-pattern", "author"],
        default="paper",
        help="Note type routing target.",
    )
    parser.add_argument("--vault-path", default=str(vault_io.DEFAULT_VAULT_PATH))
    parser.add_argument("--paper-bank-path", default=str(vault_io.DEFAULT_PAPER_BANK_PATH))
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and show target path without writing.")
    args = parser.parse_args()

    note_path = Path(args.note).expanduser().resolve()
    vault_path = Path(args.vault_path).expanduser()
    paper_bank_path = Path(args.paper_bank_path).expanduser()

    if not note_path.exists():
        print(f"ERROR: Note file not found: {note_path}")
        sys.exit(1)
    if not vault_path.exists():
        print(f"ERROR: Vault not found at {vault_path}. Run preflight_maester.py first.")
        sys.exit(1)

    if args.type == "paper":
        if not args.cite_key:
            print("ERROR: --cite-key required for --type paper")
            sys.exit(1)
        target_path = f"{TYPE_TO_DIRECTORY['paper']}/{args.cite_key}.md"
    else:
        content = note_path.read_text(encoding="utf-8")
        fm, body = vault_io.parse_frontmatter(content)
        slug, _ = _resolve_non_paper_identity(args.type, fm, body, note_path, args.cite_key or "")
        target_path = f"{TYPE_TO_DIRECTORY[args.type]}/{slug}.md"

    if args.dry_run:
        print(f"DRY_RUN: type={args.type}, target={target_path}")
        print("DONE: status=dry-run, stubs=0")
        return

    if args.type == "paper":
        result = ingest_paper(args.cite_key, note_path, vault_path, paper_bank_path)
    else:
        result = ingest_note_type(args.type, note_path, vault_path, args.cite_key or "")

    print(f"DONE: status={result['status']}, stubs={len(result['stubs_created'])}")


if __name__ == "__main__":
    main()
