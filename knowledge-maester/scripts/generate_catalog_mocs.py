#!/usr/bin/env python3
"""
generate_catalog_mocs.py — Generate per-keyword Markdown catalog (MOC) pages.

Reads from the SQLite literature index and generates Markdown catalog pages
in literature/_catalog/ using a Jinja2 template. Each page has type:moc
frontmatter for memory-retriever MOC detection, a paper listing table,
child/parent links, and stats.

Also generates literature/_catalog/_index.md as a taxonomy overview page.
"""

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Resolve imports — db.py lives next to this script.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import db  # noqa: E402

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Template setup
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------

def _keyword_slug(path: str) -> str:
    """Convert a keyword path like 'point-processes/hawkes' to a catalog filename slug."""
    return path.replace("/", "--")


def _get_all_keywords(conn: Any) -> list[dict]:
    """Return all keywords as dicts."""
    rows = conn.execute(
        "SELECT keyword_id, name, path, parent_id FROM keywords ORDER BY path"
    ).fetchall()
    return [dict(r) for r in rows]


def _get_keyword_by_path(conn: Any, path: str) -> Optional[dict]:
    """Return a single keyword dict by path."""
    row = conn.execute(
        "SELECT keyword_id, name, path, parent_id FROM keywords WHERE path = ?",
        (path,),
    ).fetchone()
    return dict(row) if row else None


def _get_child_keywords(conn: Any, parent_id: int) -> list[dict]:
    """Return direct child keywords of a given parent."""
    rows = conn.execute(
        "SELECT keyword_id, name, path, parent_id FROM keywords WHERE parent_id = ? ORDER BY name",
        (parent_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_parent_keyword(conn: Any, parent_id: Optional[int]) -> Optional[dict]:
    """Return parent keyword dict, or None."""
    if parent_id is None:
        return None
    row = conn.execute(
        "SELECT keyword_id, name, path, parent_id FROM keywords WHERE keyword_id = ?",
        (parent_id,),
    ).fetchone()
    return dict(row) if row else None


def _get_papers_for_keyword(conn: Any, keyword_path: str) -> list[dict]:
    """Get papers assigned to a keyword (including children via materialized path)."""
    return db.get_papers_by_keyword(conn, keyword_path, include_children=True)


def _get_first_author(conn: Any, paper_id: int) -> str:
    """Return the first author's display name for a paper."""
    row = conn.execute(
        """SELECT a.last_name, a.first_name
           FROM authors a
           JOIN paper_authors pa ON pa.author_id = a.author_id
           WHERE pa.paper_id = ?
           ORDER BY pa.order_idx
           LIMIT 1""",
        (paper_id,),
    ).fetchone()
    if row is None:
        return ""
    first = row["first_name"] or ""
    last = row["last_name"] or ""
    if first and last:
        return f"{first} {last}"
    return last or first


def _get_all_authors_for_paper(conn: Any, paper_id: int) -> list[str]:
    """Return all authors for a paper as display names."""
    rows = conn.execute(
        """SELECT a.last_name, a.first_name
           FROM authors a
           JOIN paper_authors pa ON pa.author_id = a.author_id
           WHERE pa.paper_id = ?
           ORDER BY pa.order_idx""",
        (paper_id,),
    ).fetchall()
    authors = []
    for row in rows:
        first = row["first_name"] or ""
        last = row["last_name"] or ""
        if first and last:
            authors.append(f"{first} {last}")
        else:
            authors.append(last or first)
    return authors


def _get_review_status(conn: Any, paper_id: int) -> str:
    """Return review_status from the paper's vault note frontmatter, or 'unknown'."""
    row = conn.execute(
        "SELECT vault_path FROM papers WHERE paper_id = ?", (paper_id,)
    ).fetchone()
    if not row or not row["vault_path"]:
        return "unknown"
    return "indexed"


def _compute_top_authors(conn: Any, papers: list[dict], limit: int = 5) -> list[tuple[str, int]]:
    """Compute the top N authors by paper count across the given papers."""
    counter: Counter = Counter()
    for p in papers:
        authors = _get_all_authors_for_paper(conn, p["paper_id"])
        for a in authors:
            if a:
                counter[a] += 1
    return counter.most_common(limit)


def _count_papers_for_keyword(conn: Any, keyword_path: str) -> int:
    """Count papers for a keyword (including children)."""
    papers = db.get_papers_by_keyword(conn, keyword_path, include_children=True)
    return len(papers)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_keyword_page(
    conn: Any,
    keyword: dict,
    env: Environment,
    today_str: str,
) -> str:
    """Render a single keyword catalog page and return its content."""
    template = env.get_template("keyword-catalog.md.j2")

    papers_raw = _get_papers_for_keyword(conn, keyword["path"])
    children_raw = _get_child_keywords(conn, keyword["keyword_id"])
    parent_raw = _get_parent_keyword(conn, keyword.get("parent_id"))

    # Enrich papers with first_author and review_status
    papers = []
    for p in papers_raw:
        papers.append({
            "cite_key": p["cite_key"],
            "title": p.get("title") or p["cite_key"],
            "year": p.get("year") or "",
            "first_author": _get_first_author(conn, p["paper_id"]),
            "review_status": _get_review_status(conn, p["paper_id"]),
        })

    # Enrich children with paper_count and slug
    children = []
    for c in children_raw:
        children.append({
            "name": c["name"],
            "slug": _keyword_slug(c["path"]),
            "paper_count": _count_papers_for_keyword(conn, c["path"]),
        })

    # Parent info
    parent = None
    if parent_raw:
        parent = {
            "name": parent_raw["name"],
            "slug": _keyword_slug(parent_raw["path"]),
        }

    # Year range
    years = [p["year"] for p in papers if p["year"]]
    year_min = min(years) if years else "—"
    year_max = max(years) if years else "—"

    # Top authors
    top_authors = _compute_top_authors(conn, papers_raw, limit=5)

    return template.render(
        keyword={
            "name": keyword["name"],
            "path": keyword["path"],
        },
        papers=papers,
        children=children,
        parent=parent,
        year_min=year_min,
        year_max=year_max,
        top_authors=top_authors,
        today=today_str,
    )


def render_index_page(
    conn: Any,
    all_keywords: list[dict],
    today_str: str,
) -> str:
    """Render the _index.md taxonomy overview page."""
    # Find top-level keywords (no parent)
    top_level = [k for k in all_keywords if k.get("parent_id") is None]

    stats = db.get_db_stats(conn)

    lines = [
        "---",
        "type: moc",
        'title: "Literature Catalog Index"',
        f'date: "{today_str}"',
        f'last_updated: "{today_str}"',
        "tags: [catalog, auto-generated, index]",
        "status: active",
        "---",
        "",
        "<!-- AUTO-GENERATED: catalog-index. Do not edit between markers. -->",
        "",
        "# Literature Catalog Index",
        "",
        f"**Total papers:** {stats['paper_count']}  |  "
        f"**Keywords:** {stats['keyword_count']}  |  "
        f"**Assignments:** {stats['assignment_count']}",
        "",
        "## Categories",
        "",
    ]

    for kw in top_level:
        slug = _keyword_slug(kw["path"])
        count = _count_papers_for_keyword(conn, kw["path"])
        children = _get_child_keywords(conn, kw["keyword_id"])
        lines.append(f"### [[{slug}|{kw['name']}]] ({count} papers)")
        lines.append("")
        if children:
            for child in children:
                child_slug = _keyword_slug(child["path"])
                child_count = _count_papers_for_keyword(conn, child["path"])
                lines.append(f"- [[{child_slug}|{child['name']}]] ({child_count} papers)")
            lines.append("")

    lines.append("<!-- /AUTO-GENERATED -->")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def generate_keyword_page(
    conn: Any,
    keyword: dict,
    vault_path: Path,
    env: Environment,
    today_str: str,
) -> Path:
    """Generate a single keyword catalog page. Returns the output path."""
    catalog_dir = vault_path / "literature" / "_catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    slug = _keyword_slug(keyword["path"])
    out_path = catalog_dir / f"{slug}.md"

    content = render_keyword_page(conn, keyword, env, today_str)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def generate_index_page(
    conn: Any,
    all_keywords: list[dict],
    vault_path: Path,
    today_str: str,
) -> Path:
    """Generate the _index.md taxonomy overview. Returns the output path."""
    catalog_dir = vault_path / "literature" / "_catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    out_path = catalog_dir / "_index.md"
    content = render_index_page(conn, all_keywords, today_str)
    out_path.write_text(content, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate per-keyword Markdown catalog (MOC) pages from the SQLite literature index."
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=str(Path.home() / "Documents" / "citadel"),
        help="Path to the Obsidian vault root (default: ~/Documents/citadel)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to SQLite database (default: <vault-path>/literature/_index.db)",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="Regenerate only this keyword path (e.g. 'point-processes/hawkes')",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        dest="generate_all",
        help="Regenerate all keyword catalog pages",
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
    if not Path(db_path).exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        print("Run build_taxonomy_db.py first to create the database.", file=sys.stderr)
        sys.exit(1)

    if not args.keyword and not args.generate_all:
        print("ERROR: specify --keyword <path> or --all", file=sys.stderr)
        sys.exit(1)

    conn = db.get_connection(db_path)
    env = _get_jinja_env()
    today_str = date.today().isoformat()

    if args.keyword:
        # Single keyword
        kw = _get_keyword_by_path(conn, args.keyword)
        if kw is None:
            print(f"ERROR: keyword not found: {args.keyword}", file=sys.stderr)
            conn.close()
            sys.exit(1)
        out = generate_keyword_page(conn, kw, vault_path, env, today_str)
        print(f"Generated: {out}")
        # Also regenerate index
        all_kws = _get_all_keywords(conn)
        idx = generate_index_page(conn, all_kws, vault_path, today_str)
        print(f"Generated: {idx}")
    else:
        # All keywords
        all_kws = _get_all_keywords(conn)
        if not all_kws:
            print("No keywords found in database.")
            conn.close()
            return

        count = 0
        for kw in all_kws:
            out = generate_keyword_page(conn, kw, vault_path, env, today_str)
            count += 1
        print(f"Generated {count} keyword catalog pages.")

        idx = generate_index_page(conn, all_kws, vault_path, today_str)
        print(f"Generated index: {idx}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
