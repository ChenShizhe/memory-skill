#!/usr/bin/env python3
"""
build_taxonomy_db.py — Populate/rebuild the SQLite literature index from Markdown.

Scans vault paper notes, loads taxonomy.yaml and synonym_map.json,
and populates the SQLite database.  Supports incremental (content-hash skip)
and full-rebuild modes.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Resolve imports — db.py and vault_io.py live next to this script in the
# knowledge-maester/scripts/ directory.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import db  # noqa: E402
try:
    import vault_io  # noqa: E402
except ImportError:
    vault_io = None  # graceful: allow running without vault_io for testing

# ---------------------------------------------------------------------------
# YAML loading (uses pyyaml if available, else a minimal fallback)
# ---------------------------------------------------------------------------

try:
    import yaml as _yaml

    def _load_yaml(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return _yaml.safe_load(f)
except ImportError:
    _yaml = None

    def _load_yaml(path: Path) -> Any:
        raise RuntimeError(
            f"pyyaml is required to load {path}. Install with: pip install pyyaml"
        )


# ---------------------------------------------------------------------------
# Frontmatter parsing — prefer vault_io, fallback to a minimal parser
# ---------------------------------------------------------------------------

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if vault_io is not None:
        return vault_io.parse_frontmatter(content)
    # Minimal fallback
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")
    fm = _parse_yaml_subset(fm_text)
    return fm, body


def _parse_yaml_subset(text: str) -> dict:
    """Minimal YAML key-value parser (no nesting, supports inline/block lists)."""
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        if line.startswith("  - ") or line.startswith("- "):
            i += 1
            continue
        colon_pos = line.find(":")
        if colon_pos == -1:
            i += 1
            continue
        key = line[:colon_pos].strip()
        value_str = line[colon_pos + 1:].strip()
        if value_str == "" or value_str == "[]":
            items = []
            j = i + 1
            while j < len(lines) and (
                lines[j].startswith("  - ") or lines[j].startswith("- ")
            ):
                item = lines[j].strip().lstrip("- ").strip()
                items.append(item)
                j += 1
            if items:
                result[key] = items
                i = j
                continue
            result[key] = [] if value_str == "[]" else ""
        else:
            if value_str.startswith("[") and value_str.endswith("]"):
                inner = value_str[1:-1]
                items = [
                    x.strip().strip('"').strip("'")
                    for x in inner.split(",")
                    if x.strip()
                ]
                result[key] = items
            else:
                v = value_str.strip('"').strip("'")
                result[key] = v
        i += 1
    return result


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------

def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Author parsing helpers
# ---------------------------------------------------------------------------

_AUTHOR_AFFILIATION_RE = re.compile(r"\s*\(.*?\)\s*$")


def _parse_author_name(raw: str) -> tuple[str, str]:
    """Parse 'First Last (Affiliation)' → (last_name, first_name)."""
    name = _AUTHOR_AFFILIATION_RE.sub("", raw).strip()
    parts = name.rsplit(None, 1)
    if len(parts) == 2:
        return parts[1], parts[0]
    return name, ""


def _extract_body_authors(body: str) -> list[str]:
    """Try to extract authors from the body (e.g., '**Authors:** A, B  **Year:** 2021')."""
    m = re.search(r"\*\*Authors?:\*\*\s*(.+?)(?:\s{2,}|\n)", body)
    if m:
        raw = m.group(1).strip()
        return [a.strip() for a in raw.split(",") if a.strip()]
    return []


# ---------------------------------------------------------------------------
# Taxonomy loading
# ---------------------------------------------------------------------------

def _walk_taxonomy(
    node: dict,
    parent_path: str = "",
    parent_id: Optional[int] = None,
    conn: Any = None,
) -> int:
    """Recursively walk taxonomy.yaml nodes and upsert keywords.

    Expected node format:
        name: "Topic Name"
        path: "parent/topic-name"   (optional — derived from parent_path + slugified name if absent)
        children:
          - name: ...
            children: ...

    Returns the count of keywords inserted/updated.
    """
    name = node.get("name", "")
    path = node.get("path", "")
    if not path:
        slug = name.lower().replace(" ", "-")
        path = f"{parent_path}/{slug}" if parent_path else slug

    kid = db.upsert_keyword(conn, name, path, parent_id)
    count = 1

    for child in node.get("children", []):
        count += _walk_taxonomy(child, path, kid, conn)
    return count


def load_taxonomy(conn: Any, taxonomy_path: Path) -> int:
    """Load taxonomy.yaml and populate the keywords table. Returns keyword count."""
    data = _load_yaml(taxonomy_path)
    if data is None:
        return 0
    count = 0
    # taxonomy.yaml can be a single root dict or a list of root nodes
    nodes = data if isinstance(data, list) else data.get("taxonomy", data.get("categories", data.get("keywords", [data])))
    if isinstance(nodes, dict):
        nodes = [nodes]
    for node in nodes:
        count += _walk_taxonomy(node, "", None, conn)
    return count


# ---------------------------------------------------------------------------
# Synonym map loading
# ---------------------------------------------------------------------------

def load_synonym_map(conn: Any, synonym_path: Path) -> int:
    """Load synonym_map.json and populate keyword_aliases table. Returns alias count.

    Expected format (v1):
        { "mappings": { "<alias>": { "canonical": "<keyword-path>", "source": "<provenance>" } } }

    Also supports flat format:
        { "<alias>": "<keyword-path>" }
    """
    with open(synonym_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    mappings = data.get("mappings", data) if isinstance(data, dict) else {}
    count = 0

    for alias, value in mappings.items():
        if isinstance(value, dict):
            canonical = value.get("canonical", "")
            source = value.get("source", "synonym_map")
        else:
            canonical = str(value)
            source = "synonym_map"

        if not canonical:
            continue

        # Find the keyword_id for the canonical path
        row = conn.execute(
            "SELECT keyword_id FROM keywords WHERE path = ?", (canonical,)
        ).fetchone()
        if row is None:
            # Try case-insensitive match
            row = conn.execute(
                "SELECT keyword_id FROM keywords WHERE LOWER(path) = LOWER(?)",
                (canonical,),
            ).fetchone()
        if row is None:
            print(f"  WARN: synonym '{alias}' → '{canonical}' — keyword path not found, skipping")
            continue

        keyword_id = row["keyword_id"]
        conn.execute(
            """INSERT INTO keyword_aliases (alias, keyword_id, source)
               VALUES (?, ?, ?)
               ON CONFLICT(alias, keyword_id) DO UPDATE SET source = excluded.source""",
            (alias, keyword_id, source),
        )
        count += 1

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Paper scanning
# ---------------------------------------------------------------------------

def _upsert_authors(conn: Any, paper_id: int, authors_raw: list[str]) -> None:
    """Upsert authors and link to paper via paper_authors."""
    # Clear old author links for this paper
    conn.execute("DELETE FROM paper_authors WHERE paper_id = ?", (paper_id,))

    for idx, raw_name in enumerate(authors_raw):
        last_name, first_name = _parse_author_name(raw_name)
        if not last_name:
            continue

        # Find or insert author
        row = conn.execute(
            "SELECT author_id FROM authors WHERE last_name = ? AND first_name = ?",
            (last_name, first_name),
        ).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO authors (last_name, first_name) VALUES (?, ?)",
                (last_name, first_name),
            )
            author_id = cur.lastrowid
        else:
            author_id = row["author_id"]

        conn.execute(
            """INSERT OR IGNORE INTO paper_authors (paper_id, author_id, order_idx)
               VALUES (?, ?, ?)""",
            (paper_id, author_id, idx),
        )


def _resolve_keyword(conn: Any, raw_kw: str) -> Optional[int]:
    """Resolve a raw keyword to a keyword_id via alias table or direct path match."""
    # Try alias lookup first
    row = conn.execute(
        "SELECT keyword_id FROM keyword_aliases WHERE alias = ?", (raw_kw.lower(),)
    ).fetchone()
    if row:
        return row["keyword_id"]

    # Try direct path match
    row = conn.execute(
        "SELECT keyword_id FROM keywords WHERE LOWER(path) = LOWER(?)", (raw_kw,)
    ).fetchone()
    if row:
        return row["keyword_id"]

    # Try name match
    row = conn.execute(
        "SELECT keyword_id FROM keywords WHERE LOWER(name) = LOWER(?)", (raw_kw,)
    ).fetchone()
    if row:
        return row["keyword_id"]

    return None


def scan_papers(
    conn: Any,
    vault_path: Path,
    incremental: bool = False,
) -> dict[str, int]:
    """Scan literature/papers/*.md and populate DB. Returns stats dict."""
    papers_dir = vault_path / "literature" / "papers"
    if not papers_dir.exists():
        print(f"  WARN: papers directory not found: {papers_dir}")
        return {"added": 0, "updated": 0, "skipped": 0}

    md_files = sorted(papers_dir.glob("*.md"))
    added = 0
    updated = 0
    skipped = 0

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        chash = _content_hash(content)
        fm, body = _parse_frontmatter(content)

        cite_key = fm.get("cite_key", md_file.stem)
        vault_rel = str(md_file.relative_to(vault_path))

        # Incremental: skip if hash matches
        if incremental:
            row = conn.execute(
                "SELECT content_hash FROM papers WHERE cite_key = ?", (cite_key,)
            ).fetchone()
            if row and row["content_hash"] == chash:
                skipped += 1
                continue

        # Check if paper already exists
        existing = conn.execute(
            "SELECT paper_id FROM papers WHERE cite_key = ?", (cite_key,)
        ).fetchone()
        is_new = existing is None

        # Extract year (handle string or int)
        year_raw = fm.get("year", "")
        try:
            year = int(str(year_raw).strip()) if year_raw else None
        except (ValueError, TypeError):
            year = None

        # Extract title from frontmatter or first heading
        title = fm.get("title", "")
        if not title:
            # Try first H1 heading in body
            m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if m:
                title = m.group(1).strip()

        # Extract abstract — use frontmatter if available, else skip
        abstract = fm.get("abstract", "")

        paper_dict = {
            "cite_key": cite_key,
            "title": title,
            "year": year,
            "abstract": abstract,
            "doi": fm.get("doi", ""),
            "venue": fm.get("venue", fm.get("journal", "")),
            "vault_path": vault_rel,
            "content_hash": chash,
        }
        paper_id = db.upsert_paper(conn, paper_dict)

        # Authors
        authors_raw = fm.get("authors", [])
        if isinstance(authors_raw, str):
            authors_raw = [a.strip() for a in authors_raw.split(",") if a.strip()]
        if not authors_raw:
            authors_raw = _extract_body_authors(body)
        if authors_raw:
            _upsert_authors(conn, paper_id, authors_raw)

        # Keywords — try to resolve against taxonomy
        keywords_raw = fm.get("keywords", fm.get("controlled_keywords", []))
        if isinstance(keywords_raw, str):
            keywords_raw = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        if keywords_raw:
            # Clear existing keyword assignments for this paper
            conn.execute(
                "DELETE FROM paper_keywords WHERE paper_id = ?", (paper_id,)
            )
            for i, raw_kw in enumerate(keywords_raw):
                kid = _resolve_keyword(conn, raw_kw)
                if kid is not None:
                    conn.execute(
                        """INSERT OR IGNORE INTO paper_keywords
                           (paper_id, keyword_id, is_primary)
                           VALUES (?, ?, ?)""",
                        (paper_id, kid, 1 if i == 0 else 0),
                    )

        conn.commit()

        if is_new:
            added += 1
        else:
            updated += 1

    return {"added": added, "updated": updated, "skipped": skipped}


# ---------------------------------------------------------------------------
# Claims import
# ---------------------------------------------------------------------------

def import_claims(conn: Any, vault_path: Path) -> int:
    """Import claims from literature/claims/*.json. Returns count of claims imported."""
    claims_dir = vault_path / "literature" / "claims"
    if not claims_dir.exists():
        print(f"  WARN: claims directory not found: {claims_dir}")
        return 0

    json_files = sorted(claims_dir.glob("*.json"))
    total = 0

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: failed to parse {jf.name}: {e}")
            continue

        cite_key = data.get("cite_key", jf.stem)
        claims = data.get("claims", [])
        if not claims:
            continue

        # Find the paper_id
        row = conn.execute(
            "SELECT paper_id FROM papers WHERE cite_key = ?", (cite_key,)
        ).fetchone()
        if row is None:
            # Paper not in DB yet — skip claims for now
            continue
        paper_id = row["paper_id"]

        # Clear existing claims for this paper (idempotent rebuild)
        conn.execute("DELETE FROM claims WHERE paper_id = ?", (paper_id,))

        for claim in claims:
            statement = claim.get("statement", claim.get("claim_text", ""))
            if not statement:
                continue
            claim_type = claim.get("claim_type", "")
            section = ""
            anchor = claim.get("source_anchor", {})
            if isinstance(anchor, dict):
                section = anchor.get("locator", "")
            confidence_raw = anchor.get("confidence", "") if isinstance(anchor, dict) else ""
            confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
            if isinstance(confidence_raw, (int, float)):
                confidence = float(confidence_raw)
            else:
                confidence = confidence_map.get(str(confidence_raw).lower(), None)

            conn.execute(
                """INSERT INTO claims (paper_id, claim_text, claim_type, section, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (paper_id, statement, claim_type, section, confidence),
            )
            total += 1

        conn.commit()

    return total


# ---------------------------------------------------------------------------
# Orphan cleanup
# ---------------------------------------------------------------------------

def cleanup_orphans(conn: Any, vault_path: Path) -> int:
    """Remove DB rows for papers whose vault_path no longer exists on disk.
    Returns count of removed papers."""
    rows = conn.execute("SELECT paper_id, vault_path FROM papers").fetchall()
    removed = 0
    for row in rows:
        vp = row["vault_path"]
        if vp and not (vault_path / vp).exists():
            conn.execute("DELETE FROM papers WHERE paper_id = ?", (row["paper_id"],))
            removed += 1
    conn.commit()
    return removed


# ---------------------------------------------------------------------------
# Full rebuild — drop and recreate all tables
# ---------------------------------------------------------------------------

def _drop_all_tables(conn: Any) -> None:
    """Drop all tables so they can be recreated cleanly."""
    # Drop triggers first
    for trigger in ("papers_ai", "papers_ad", "papers_au"):
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    # Drop FTS virtual table
    conn.execute("DROP TABLE IF EXISTS papers_fts")
    # Drop tables in dependency order
    for table in (
        "claims",
        "citations",
        "keyword_aliases",
        "paper_keywords",
        "paper_authors",
        "keywords",
        "authors",
        "papers",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build/rebuild the literature SQLite index from Markdown files."
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=str(Path.home() / "Documents" / "citadel"),
        help="Path to the Obsidian vault root (default: ~/Documents/citadel)",
    )
    parser.add_argument(
        "--taxonomy",
        type=str,
        default=None,
        help="Path to taxonomy.yaml (default: <vault-path>/taxonomy.yaml)",
    )
    parser.add_argument(
        "--synonym-map",
        type=str,
        default=None,
        help="Path to synonym_map.json (default: <vault-path>/synonym_map.json)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        default=False,
        help="Skip files whose content hash matches the DB (default mode)",
    )
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        default=False,
        help="Drop and recreate all tables before populating",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to SQLite database (default: <vault-path>/literature/_index.db)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_cli()
    args = parser.parse_args(argv)

    vault_path = Path(args.vault_path).expanduser().resolve()
    if not vault_path.exists():
        print(f"ERROR: vault path does not exist: {vault_path}", file=sys.stderr)
        sys.exit(1)

    db_path = args.db_path or str(vault_path / "literature" / db.DEFAULT_DB_NAME)
    taxonomy_path = Path(args.taxonomy) if args.taxonomy else (vault_path / "taxonomy.yaml")
    synonym_path = Path(args.synonym_map) if args.synonym_map else (vault_path / "synonym_map.json")

    # Ensure parent directory for DB exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"Vault:     {vault_path}")
    print(f"Database:  {db_path}")
    print(f"Taxonomy:  {taxonomy_path} {'(exists)' if taxonomy_path.exists() else '(not found)'}")
    print(f"Synonyms:  {synonym_path} {'(exists)' if synonym_path.exists() else '(not found)'}")
    print()

    # Full rebuild: drop everything first
    if args.full_rebuild:
        print("=== FULL REBUILD: dropping all tables ===")
        conn = db.get_connection(db_path)
        _drop_all_tables(conn)
        conn.close()

    # Init DB (creates tables if not exist)
    conn = db.init_db(db_path)

    # 1. Load taxonomy
    kw_count = 0
    if taxonomy_path.exists():
        print("Loading taxonomy...")
        kw_count = load_taxonomy(conn, taxonomy_path)
        print(f"  Keywords loaded: {kw_count}")
    else:
        print("Taxonomy file not found — skipping keyword population.")

    # 2. Load synonym map
    alias_count = 0
    if synonym_path.exists():
        print("Loading synonym map...")
        alias_count = load_synonym_map(conn, synonym_path)
        print(f"  Aliases loaded: {alias_count}")
    else:
        print("Synonym map not found — skipping alias population.")

    # 3. Scan papers
    print("Scanning papers...")
    stats = scan_papers(conn, vault_path, incremental=args.incremental)
    print(f"  Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}")

    # 4. Import claims
    print("Importing claims...")
    claims_count = import_claims(conn, vault_path)
    print(f"  Claims imported: {claims_count}")

    # 5. Orphan cleanup
    print("Cleaning orphans...")
    orphans = cleanup_orphans(conn, vault_path)
    print(f"  Orphan papers removed: {orphans}")

    # 6. Rebuild FTS5
    print("Rebuilding FTS5 index...")
    db.rebuild_fts(conn)

    # Summary
    final_stats = db.get_db_stats(conn)
    print()
    print("=== Summary ===")
    print(f"  Papers in DB:      {final_stats['paper_count']}")
    print(f"  Keywords in DB:    {final_stats['keyword_count']}")
    print(f"  Assignments in DB: {final_stats['assignment_count']}")
    print(f"  Claims imported:   {claims_count}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
