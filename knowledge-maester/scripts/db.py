"""
SQLite database module for the literature organization system.

Defines the full schema (papers, authors, paper_authors, keywords, paper_keywords,
keyword_aliases, citations, claims, papers_fts) and provides CRUD operations,
FTS5 search, and materialized-path subtree queries.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


DEFAULT_DB_NAME = "_index.db"


def _default_db_path() -> str:
    return str(Path.home() / "Documents" / "citadel" / "literature" / DEFAULT_DB_NAME)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a connection with row_factory set to sqlite3.Row."""
    if db_path is None:
        db_path = _default_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    cite_key     TEXT    UNIQUE NOT NULL,
    title        TEXT,
    year         INTEGER,
    abstract     TEXT,
    doi          TEXT,
    venue        TEXT,
    vault_path   TEXT,
    content_hash TEXT,
    date_added   TEXT,
    date_modified TEXT
);

CREATE TABLE IF NOT EXISTS authors (
    author_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name  TEXT NOT NULL,
    first_name TEXT
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id  INTEGER NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES authors(author_id) ON DELETE CASCADE,
    order_idx INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS keywords (
    keyword_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    path       TEXT    UNIQUE NOT NULL,
    parent_id  INTEGER REFERENCES keywords(keyword_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS paper_keywords (
    paper_id   INTEGER NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    keyword_id INTEGER NOT NULL REFERENCES keywords(keyword_id) ON DELETE CASCADE,
    is_primary INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (paper_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS keyword_aliases (
    alias      TEXT    NOT NULL,
    keyword_id INTEGER NOT NULL REFERENCES keywords(keyword_id) ON DELETE CASCADE,
    source     TEXT,
    PRIMARY KEY (alias, keyword_id)
);

CREATE TABLE IF NOT EXISTS citations (
    citing_id INTEGER NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    cited_id  INTEGER NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    context   TEXT,
    PRIMARY KEY (citing_id, cited_id)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id   INTEGER NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    claim_text TEXT    NOT NULL,
    claim_type TEXT,
    section    TEXT,
    confidence REAL
);
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_papers_cite_key     ON papers(cite_key);
CREATE INDEX IF NOT EXISTS idx_papers_year          ON papers(year);
CREATE INDEX IF NOT EXISTS idx_authors_last_name    ON authors(last_name);
CREATE INDEX IF NOT EXISTS idx_keywords_path        ON keywords(path);
CREATE INDEX IF NOT EXISTS idx_keywords_parent_id   ON keywords(parent_id);
CREATE INDEX IF NOT EXISTS idx_paper_keywords_kid   ON paper_keywords(keyword_id);
CREATE INDEX IF NOT EXISTS idx_keyword_aliases_alias ON keyword_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_claims_paper_id      ON claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_citations_cited_id   ON citations(cited_id);
"""

_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts
    USING fts5(title, abstract, content=papers, content_rowid=paper_id);
"""

_FTS_TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(rowid, title, abstract)
    VALUES (new.paper_id, new.title, new.abstract);
END;

CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
    VALUES ('delete', old.paper_id, old.title, old.abstract);
END;

CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
    VALUES ('delete', old.paper_id, old.title, old.abstract);
    INSERT INTO papers_fts(rowid, title, abstract)
    VALUES (new.paper_id, new.title, new.abstract);
END;
"""


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create all tables, indexes, and FTS5 virtual table. Returns the connection."""
    conn = get_connection(db_path)
    conn.executescript(_TABLES_SQL)
    conn.executescript(_INDEXES_SQL)
    conn.executescript(_FTS_SQL)
    conn.executescript(_FTS_TRIGGERS_SQL)
    return conn


# ---------------------------------------------------------------------------
# Paper CRUD
# ---------------------------------------------------------------------------

def upsert_paper(db: sqlite3.Connection, paper_dict: dict[str, Any]) -> int:
    """Insert or update a paper by cite_key. Returns the paper_id.

    Idempotent: running twice with the same data produces no change.
    """
    cite_key = paper_dict["cite_key"]
    now = datetime.utcnow().isoformat()

    row = db.execute(
        "SELECT paper_id FROM papers WHERE cite_key = ?", (cite_key,)
    ).fetchone()

    if row is None:
        cur = db.execute(
            """INSERT INTO papers (cite_key, title, year, abstract, doi, venue,
                                   vault_path, content_hash, date_added, date_modified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cite_key,
                paper_dict.get("title"),
                paper_dict.get("year"),
                paper_dict.get("abstract"),
                paper_dict.get("doi"),
                paper_dict.get("venue"),
                paper_dict.get("vault_path"),
                paper_dict.get("content_hash"),
                now,
                now,
            ),
        )
        db.commit()
        return cur.lastrowid
    else:
        paper_id = row["paper_id"]
        db.execute(
            """UPDATE papers
               SET title = ?, year = ?, abstract = ?, doi = ?, venue = ?,
                   vault_path = ?, content_hash = ?, date_modified = ?
               WHERE paper_id = ?""",
            (
                paper_dict.get("title"),
                paper_dict.get("year"),
                paper_dict.get("abstract"),
                paper_dict.get("doi"),
                paper_dict.get("venue"),
                paper_dict.get("vault_path"),
                paper_dict.get("content_hash"),
                now,
                paper_id,
            ),
        )
        db.commit()
        return paper_id


# ---------------------------------------------------------------------------
# Keyword CRUD
# ---------------------------------------------------------------------------

def upsert_keyword(
    db: sqlite3.Connection,
    name: str,
    path: str,
    parent_id: Optional[int] = None,
) -> int:
    """Insert or update a keyword by path. Returns the keyword_id."""
    row = db.execute(
        "SELECT keyword_id FROM keywords WHERE path = ?", (path,)
    ).fetchone()

    if row is None:
        cur = db.execute(
            "INSERT INTO keywords (name, path, parent_id) VALUES (?, ?, ?)",
            (name, path, parent_id),
        )
        db.commit()
        return cur.lastrowid
    else:
        keyword_id = row["keyword_id"]
        db.execute(
            "UPDATE keywords SET name = ?, parent_id = ? WHERE keyword_id = ?",
            (name, parent_id, keyword_id),
        )
        db.commit()
        return keyword_id


def assign_keyword(
    db: sqlite3.Connection,
    cite_key: str,
    keyword_path: str,
    is_primary: bool = False,
) -> None:
    """Assign a keyword to a paper by cite_key and keyword path."""
    paper_row = db.execute(
        "SELECT paper_id FROM papers WHERE cite_key = ?", (cite_key,)
    ).fetchone()
    if paper_row is None:
        raise ValueError(f"Paper not found: {cite_key}")

    kw_row = db.execute(
        "SELECT keyword_id FROM keywords WHERE path = ?", (keyword_path,)
    ).fetchone()
    if kw_row is None:
        raise ValueError(f"Keyword not found: {keyword_path}")

    db.execute(
        """INSERT INTO paper_keywords (paper_id, keyword_id, is_primary)
           VALUES (?, ?, ?)
           ON CONFLICT(paper_id, keyword_id)
           DO UPDATE SET is_primary = excluded.is_primary""",
        (paper_row["paper_id"], kw_row["keyword_id"], int(is_primary)),
    )
    db.commit()


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------

def query_fts(
    db: sqlite3.Connection,
    query_text: str,
    filters: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Full-text search over papers_fts with optional metadata filters.

    Supported filters: year, venue, keyword_path.
    Returns a list of paper dicts ordered by FTS5 rank.
    """
    if filters is None:
        filters = {}

    params: list[Any] = [query_text]
    joins = ""
    where_clauses = ""

    if "keyword_path" in filters:
        joins += (
            " JOIN paper_keywords pk ON pk.paper_id = p.paper_id"
            " JOIN keywords k ON k.keyword_id = pk.keyword_id"
        )
        where_clauses += " AND k.path LIKE ?"
        params.append(filters["keyword_path"].rstrip("/") + "%")

    if "year" in filters:
        where_clauses += " AND p.year = ?"
        params.append(filters["year"])

    if "venue" in filters:
        where_clauses += " AND p.venue = ?"
        params.append(filters["venue"])

    sql = f"""
        SELECT p.paper_id, p.cite_key, p.title, p.year, p.abstract,
               p.doi, p.venue, p.vault_path,
               rank
        FROM papers_fts
        JOIN papers p ON p.paper_id = papers_fts.rowid
        {joins}
        WHERE papers_fts MATCH ?
        {where_clauses}
        ORDER BY rank
    """

    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Keyword-based queries (materialized path)
# ---------------------------------------------------------------------------

def get_papers_by_keyword(
    db: sqlite3.Connection,
    keyword_path: str,
    include_children: bool = True,
) -> list[dict[str, Any]]:
    """Get papers assigned to a keyword. When include_children is True, uses
    materialized path LIKE prefix to include papers in all child keywords."""
    if include_children:
        # Materialized path subtree query: path LIKE 'parent/path%'
        path_prefix = keyword_path.rstrip("/") + "/%"
        exact_path = keyword_path
        sql = """
            SELECT DISTINCT p.paper_id, p.cite_key, p.title, p.year,
                   p.abstract, p.doi, p.venue, p.vault_path
            FROM papers p
            JOIN paper_keywords pk ON pk.paper_id = p.paper_id
            JOIN keywords k ON k.keyword_id = pk.keyword_id
            WHERE k.path = ? OR k.path LIKE ?
            ORDER BY p.year DESC, p.title
        """
        rows = db.execute(sql, (exact_path, path_prefix)).fetchall()
    else:
        sql = """
            SELECT p.paper_id, p.cite_key, p.title, p.year,
                   p.abstract, p.doi, p.venue, p.vault_path
            FROM papers p
            JOIN paper_keywords pk ON pk.paper_id = p.paper_id
            JOIN keywords k ON k.keyword_id = pk.keyword_id
            WHERE k.path = ?
            ORDER BY p.year DESC, p.title
        """
        rows = db.execute(sql, (keyword_path,)).fetchall()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# FTS rebuild
# ---------------------------------------------------------------------------

def rebuild_fts(db: sqlite3.Connection) -> None:
    """Rebuild the FTS5 index from scratch."""
    db.execute("INSERT INTO papers_fts(papers_fts) VALUES ('rebuild')")
    db.commit()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_db_stats(db: sqlite3.Connection) -> dict[str, int]:
    """Return paper count, keyword count, and assignment count."""
    paper_count = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    keyword_count = db.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
    assignment_count = db.execute("SELECT COUNT(*) FROM paper_keywords").fetchone()[0]
    return {
        "paper_count": paper_count,
        "keyword_count": keyword_count,
        "assignment_count": assignment_count,
    }
