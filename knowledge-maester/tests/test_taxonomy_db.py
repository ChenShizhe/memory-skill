"""
Unit tests for foundation scripts: db.py, build_taxonomy_db.py,
normalize_keywords.py, and generate_catalog_mocs.py.

All tests use in-memory or temp-file SQLite databases — no vault side effects.
No external dependencies beyond sqlite3, jinja2, pyyaml.

Run:
  cd knowledge-maester && python3 -m pytest tests/test_taxonomy_db.py -v
"""

import json
import sqlite3
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Add scripts dir to path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import db
import build_taxonomy_db
import normalize_keywords
import generate_catalog_mocs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_in_memory_db() -> sqlite3.Connection:
    """Create a fully-initialized in-memory database."""
    return db.init_db(":memory:")


def _seed_papers(conn: sqlite3.Connection, count: int = 5) -> list[int]:
    """Insert `count` test papers and return their paper_ids."""
    ids = []
    for i in range(1, count + 1):
        pid = db.upsert_paper(conn, {
            "cite_key": f"author{i:02d}paper",
            "title": f"Paper Title {i}",
            "year": 2020 + i,
            "abstract": f"Abstract about topic {i} with important research findings",
            "doi": f"10.1234/test.{i}",
            "venue": f"Venue {i}",
            "vault_path": f"literature/papers/author{i:02d}paper.md",
            "content_hash": f"hash{i:032d}",
        })
        ids.append(pid)
    return ids


def _seed_keywords(conn: sqlite3.Connection) -> dict[str, int]:
    """Insert a small keyword hierarchy and return path->keyword_id map."""
    root_id = db.upsert_keyword(conn, "Point Processes", "point-processes")
    hawkes_id = db.upsert_keyword(conn, "Hawkes", "point-processes/hawkes", root_id)
    neural_id = db.upsert_keyword(conn, "Neural", "point-processes/neural", root_id)
    ml_id = db.upsert_keyword(conn, "Machine Learning", "machine-learning")
    return {
        "point-processes": root_id,
        "point-processes/hawkes": hawkes_id,
        "point-processes/neural": neural_id,
        "machine-learning": ml_id,
    }


# ---------------------------------------------------------------------------
# 1. test_schema_creation
# ---------------------------------------------------------------------------

class TestSchemaCreation(unittest.TestCase):
    """init_db creates all expected tables, indexes, and FTS virtual table."""

    def test_schema_creation(self):
        conn = _make_in_memory_db()

        expected_tables = {
            "papers", "authors", "paper_authors", "keywords",
            "paper_keywords", "keyword_aliases", "citations", "claims",
        }

        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        tables = {r[0] for r in rows}

        for t in expected_tables:
            self.assertIn(t, tables, f"Table {t} missing from schema")

        # FTS5 virtual table
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'papers_fts'"
        ).fetchall()
        self.assertEqual(len(rows), 1, "papers_fts virtual table missing")

        # Triggers
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        trigger_names = {r[0] for r in rows}
        for t in ("papers_ai", "papers_ad", "papers_au"):
            self.assertIn(t, trigger_names, f"Trigger {t} missing")

        conn.close()


# ---------------------------------------------------------------------------
# 2. test_paper_upsert
# ---------------------------------------------------------------------------

class TestPaperUpsert(unittest.TestCase):
    """Insert and update a paper via upsert_paper; idempotency check."""

    def test_paper_upsert(self):
        conn = _make_in_memory_db()

        paper = {
            "cite_key": "smith2024deep",
            "title": "Deep Learning for Sequences",
            "year": 2024,
            "abstract": "We study deep learning.",
            "doi": "10.1234/dl.2024",
            "venue": "NeurIPS",
            "vault_path": "literature/papers/smith2024deep.md",
            "content_hash": "abc123",
        }

        # Insert
        pid1 = db.upsert_paper(conn, paper)
        self.assertIsNotNone(pid1)
        self.assertEqual(
            db.get_db_stats(conn)["paper_count"], 1
        )

        # Update same cite_key
        paper["title"] = "Updated Title"
        pid2 = db.upsert_paper(conn, paper)
        self.assertEqual(pid1, pid2, "upsert should return same paper_id on update")

        row = conn.execute(
            "SELECT title FROM papers WHERE paper_id = ?", (pid1,)
        ).fetchone()
        self.assertEqual(row["title"], "Updated Title")

        # Count should still be 1 (idempotent)
        self.assertEqual(db.get_db_stats(conn)["paper_count"], 1)

        conn.close()


# ---------------------------------------------------------------------------
# 3. test_keyword_materialized_path
# ---------------------------------------------------------------------------

class TestKeywordMaterializedPath(unittest.TestCase):
    """Subtree query via materialized path LIKE prefix returns correct papers."""

    def test_keyword_materialized_path(self):
        conn = _make_in_memory_db()
        pids = _seed_papers(conn, 3)
        kws = _seed_keywords(conn)

        # Assign paper 1 to hawkes (child), paper 2 to neural (child), paper 3 to root
        db.assign_keyword(conn, "author01paper", "point-processes/hawkes", is_primary=True)
        db.assign_keyword(conn, "author02paper", "point-processes/neural", is_primary=True)
        db.assign_keyword(conn, "author03paper", "point-processes", is_primary=True)

        # Query root with include_children=True should return all 3
        results = db.get_papers_by_keyword(conn, "point-processes", include_children=True)
        cite_keys = {r["cite_key"] for r in results}
        self.assertEqual(cite_keys, {"author01paper", "author02paper", "author03paper"})

        # Query hawkes subtree should return only paper 1
        results = db.get_papers_by_keyword(conn, "point-processes/hawkes", include_children=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["cite_key"], "author01paper")

        # Query root with include_children=False should return only paper 3
        results = db.get_papers_by_keyword(conn, "point-processes", include_children=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["cite_key"], "author03paper")

        conn.close()


# ---------------------------------------------------------------------------
# 4. test_fts5_search
# ---------------------------------------------------------------------------

class TestFTS5Search(unittest.TestCase):
    """Full-text search returns ranked results."""

    def test_fts5_search(self):
        conn = _make_in_memory_db()

        # Insert papers with distinct content for FTS
        db.upsert_paper(conn, {
            "cite_key": "hawkes2024",
            "title": "Hawkes Processes for Event Streams",
            "year": 2024,
            "abstract": "This paper studies Hawkes processes and self-exciting point processes.",
            "vault_path": "literature/papers/hawkes2024.md",
            "content_hash": "h1",
        })
        db.upsert_paper(conn, {
            "cite_key": "neural2024",
            "title": "Neural Network Architectures",
            "year": 2024,
            "abstract": "We propose novel transformer architectures for language modeling.",
            "vault_path": "literature/papers/neural2024.md",
            "content_hash": "h2",
        })
        db.upsert_paper(conn, {
            "cite_key": "finance2024",
            "title": "Financial Time Series Analysis",
            "year": 2024,
            "abstract": "Analysis of high-frequency financial data using point processes.",
            "vault_path": "literature/papers/finance2024.md",
            "content_hash": "h3",
        })

        # Search for "hawkes" should return hawkes2024 first
        results = db.query_fts(conn, "hawkes")
        self.assertGreater(len(results), 0, "FTS should return at least one result")
        self.assertEqual(results[0]["cite_key"], "hawkes2024")

        # Search for "point processes" should match hawkes and finance papers
        results = db.query_fts(conn, "point processes")
        cite_keys = {r["cite_key"] for r in results}
        self.assertIn("hawkes2024", cite_keys)
        self.assertIn("finance2024", cite_keys)

        # Search for "transformer" should match only neural2024
        results = db.query_fts(conn, "transformer")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["cite_key"], "neural2024")

        conn.close()


# ---------------------------------------------------------------------------
# 5. test_content_hash_skip
# ---------------------------------------------------------------------------

class TestContentHashSkip(unittest.TestCase):
    """Incremental build skips files whose content hash matches the DB."""

    def test_content_hash_skip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            papers_dir = vault / "literature" / "papers"
            papers_dir.mkdir(parents=True)

            # Write a paper file
            md = textwrap.dedent("""\
                ---
                cite_key: test2024skip
                title: Skip Test Paper
                year: 2024
                ---

                Body content here.
            """)
            (papers_dir / "test2024skip.md").write_text(md, encoding="utf-8")

            # First scan: paper should be added
            conn = _make_in_memory_db()
            stats = build_taxonomy_db.scan_papers(conn, vault, incremental=False)
            self.assertEqual(stats["added"], 1)
            self.assertEqual(stats["skipped"], 0)

            # Second scan with incremental=True: should skip (hash unchanged)
            stats = build_taxonomy_db.scan_papers(conn, vault, incremental=True)
            self.assertEqual(stats["added"], 0)
            self.assertEqual(stats["skipped"], 1)

            # Modify the file content
            (papers_dir / "test2024skip.md").write_text(
                md + "\nExtra content appended.", encoding="utf-8"
            )

            # Third scan with incremental=True: should process (hash changed)
            stats = build_taxonomy_db.scan_papers(conn, vault, incremental=True)
            self.assertEqual(stats["skipped"], 0)
            self.assertEqual(stats["updated"], 1)

            conn.close()


# ---------------------------------------------------------------------------
# 6. test_orphan_cleanup
# ---------------------------------------------------------------------------

class TestOrphanCleanup(unittest.TestCase):
    """Papers whose vault_path no longer exists on disk are removed."""

    def test_orphan_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            papers_dir = vault / "literature" / "papers"
            papers_dir.mkdir(parents=True)

            conn = _make_in_memory_db()

            # Insert papers pointing to files that exist and one that doesn't
            (papers_dir / "real.md").write_text("---\ntitle: Real\n---\n", encoding="utf-8")
            db.upsert_paper(conn, {
                "cite_key": "real",
                "title": "Real Paper",
                "vault_path": "literature/papers/real.md",
                "content_hash": "r1",
            })
            db.upsert_paper(conn, {
                "cite_key": "ghost",
                "title": "Ghost Paper",
                "vault_path": "literature/papers/ghost.md",
                "content_hash": "g1",
            })

            self.assertEqual(db.get_db_stats(conn)["paper_count"], 2)

            removed = build_taxonomy_db.cleanup_orphans(conn, vault)
            self.assertEqual(removed, 1)
            self.assertEqual(db.get_db_stats(conn)["paper_count"], 1)

            # The remaining paper should be "real"
            row = conn.execute("SELECT cite_key FROM papers").fetchone()
            self.assertEqual(row["cite_key"], "real")

            conn.close()


# ---------------------------------------------------------------------------
# 7. test_normalize_known_synonym
# ---------------------------------------------------------------------------

class TestNormalizeKnownSynonym(unittest.TestCase):
    """Stage 2 resolves a known alias to its canonical term."""

    def test_normalize_known_synonym(self):
        synonym_map = {
            "hawkes process": "point-processes/hawkes",
            "self-exciting process": "point-processes/hawkes",
        }
        taxonomy_terms = {
            "point-processes",
            "point-processes/hawkes",
            "machine-learning",
        }

        # "Hawkes Process" after normalization becomes "hawkes process" → resolves
        normalized = normalize_keywords.normalize_string("Hawkes Process")
        result = normalize_keywords.resolve_keyword(normalized, synonym_map, taxonomy_terms)
        self.assertEqual(result, "point-processes/hawkes")

        # "self-exciting process" → resolves via synonym map
        normalized = normalize_keywords.normalize_string("Self-Exciting Process")
        result = normalize_keywords.resolve_keyword(normalized, synonym_map, taxonomy_terms)
        self.assertEqual(result, "point-processes/hawkes")


# ---------------------------------------------------------------------------
# 8. test_normalize_unknown_keyword
# ---------------------------------------------------------------------------

class TestNormalizeUnknownKeyword(unittest.TestCase):
    """Stage 3 produces a pending_terms entry for unmatched keywords."""

    def test_normalize_unknown_keyword(self):
        synonym_map = {"hawkes process": "point-processes/hawkes"}
        taxonomy_terms = {"point-processes", "point-processes/hawkes"}

        # Unknown keyword
        normalized = normalize_keywords.normalize_string("spectral estimation of hawkes")
        result = normalize_keywords.resolve_keyword(normalized, synonym_map, taxonomy_terms)
        self.assertIsNone(result, "Unknown keyword should not resolve")

        # Build pending entry
        entry = normalize_keywords.build_pending_entry(
            raw_keyword="spectral estimation of hawkes",
            cite_key="bonnet2024spectral",
        )
        self.assertEqual(entry["raw_keyword"], "spectral estimation of hawkes")
        self.assertEqual(entry["paper"], "bonnet2024spectral")
        self.assertEqual(entry["status"], "pending")
        self.assertIsNone(entry["suggested_canonical"])

    def test_pending_terms_file_written(self):
        """write_pending_terms writes entries and deduplicates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "pending_terms.yaml"
            entries = [
                normalize_keywords.build_pending_entry("unknown kw", "paper1"),
                normalize_keywords.build_pending_entry("another kw", "paper2"),
            ]
            normalize_keywords.write_pending_terms(entries, out_path)
            self.assertTrue(out_path.exists())

            # Write again with duplicate — should not duplicate
            normalize_keywords.write_pending_terms(entries, out_path)
            import yaml
            data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
            self.assertEqual(len(data), 2, "Duplicate entries should be deduplicated")


# ---------------------------------------------------------------------------
# 9. test_string_normalization
# ---------------------------------------------------------------------------

class TestStringNormalization(unittest.TestCase):
    """Edge cases: hyphens, plurals, case, whitespace, acronyms."""

    def test_lowercase(self):
        self.assertEqual(
            normalize_keywords.normalize_string("HAWKES PROCESS"),
            "hawkes process",
        )

    def test_strip_whitespace(self):
        self.assertEqual(
            normalize_keywords.normalize_string("  point processes  "),
            "point process",
        )

    def test_hyphen_normalization(self):
        # "self exciting" → "self-exciting" (common hyphen prefix)
        result = normalize_keywords.normalize_string("self exciting")
        self.assertEqual(result, "self-exciting")

    def test_already_hyphenated(self):
        result = normalize_keywords.normalize_string("self-exciting")
        self.assertEqual(result, "self-exciting")

    def test_plural_collapse(self):
        # "hawkes processes" → "hawkes process" (via exception or plural rule)
        result = normalize_keywords.normalize_string("hawkes processes")
        self.assertEqual(result, "hawkes process")

    def test_plural_ies(self):
        result = normalize_keywords.normalize_string("strategies")
        self.assertEqual(result, "strategy")

    def test_known_acronym_expansion(self):
        result = normalize_keywords.normalize_string("MLE")
        self.assertEqual(result, "maximum likelihood estimation")

    def test_unicode_dashes(self):
        # En-dash (\u2013) should be normalized to ASCII hyphen
        result = normalize_keywords.normalize_string("non\u2013parametric")
        self.assertEqual(result, "non-parametric")

    def test_collapse_multiple_spaces(self):
        result = normalize_keywords.normalize_string("point   processes")
        self.assertEqual(result, "point process")

    def test_preserved_words(self):
        # Words in the exception list should not be depluralized
        result = normalize_keywords.normalize_string("statistics")
        self.assertEqual(result, "statistics")

        result = normalize_keywords.normalize_string("dynamics")
        self.assertEqual(result, "dynamics")


# ---------------------------------------------------------------------------
# 10. test_catalog_moc_generation
# ---------------------------------------------------------------------------

class TestCatalogMocGeneration(unittest.TestCase):
    """Template renders valid Markdown with correct data."""

    def test_catalog_moc_generation(self):
        conn = _make_in_memory_db()
        pids = _seed_papers(conn, 3)
        kws = _seed_keywords(conn)

        # Assign papers to keywords
        db.assign_keyword(conn, "author01paper", "point-processes/hawkes")
        db.assign_keyword(conn, "author02paper", "point-processes/neural")
        db.assign_keyword(conn, "author03paper", "point-processes")

        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            catalog_dir = vault / "literature" / "_catalog"

            env = generate_catalog_mocs._get_jinja_env()
            today_str = "2026-04-13"

            # Get all keywords and generate pages
            all_kws = generate_catalog_mocs._get_all_keywords(conn)
            self.assertTrue(len(all_kws) >= 3, "Should have at least 3 keywords")

            for kw in all_kws:
                generate_catalog_mocs.generate_keyword_page(conn, kw, vault, env, today_str)

            # Generate index
            generate_catalog_mocs.generate_index_page(conn, all_kws, vault, today_str)

            # Verify files were created
            self.assertTrue(catalog_dir.exists())
            md_files = list(catalog_dir.glob("*.md"))
            # Should have one page per keyword + _index.md
            self.assertGreaterEqual(len(md_files), 4, "Expected at least 4 catalog files")

            # Check that the hawkes page contains the assigned paper
            hawkes_slug = generate_catalog_mocs._keyword_slug("point-processes/hawkes")
            hawkes_page = catalog_dir / f"{hawkes_slug}.md"
            self.assertTrue(hawkes_page.exists(), f"{hawkes_slug}.md should exist")
            content = hawkes_page.read_text(encoding="utf-8")
            self.assertIn("author01paper", content)
            self.assertIn("Paper Title 1", content)

            # Index page should exist
            index_page = catalog_dir / "_index.md"
            self.assertTrue(index_page.exists())
            index_content = index_page.read_text(encoding="utf-8")
            self.assertIn("Literature Catalog Index", index_content)

        conn.close()


# ---------------------------------------------------------------------------
# 11. test_catalog_moc_idempotent
# ---------------------------------------------------------------------------

class TestCatalogMocIdempotent(unittest.TestCase):
    """Regeneration produces identical output."""

    def test_catalog_moc_idempotent(self):
        conn = _make_in_memory_db()
        _seed_papers(conn, 2)
        kws = _seed_keywords(conn)

        db.assign_keyword(conn, "author01paper", "point-processes/hawkes")
        db.assign_keyword(conn, "author02paper", "point-processes")

        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            env = generate_catalog_mocs._get_jinja_env()
            today_str = "2026-04-13"

            all_kws = generate_catalog_mocs._get_all_keywords(conn)

            # First generation
            for kw in all_kws:
                generate_catalog_mocs.generate_keyword_page(conn, kw, vault, env, today_str)
            generate_catalog_mocs.generate_index_page(conn, all_kws, vault, today_str)

            catalog_dir = vault / "literature" / "_catalog"
            first_pass = {}
            for f in sorted(catalog_dir.glob("*.md")):
                first_pass[f.name] = f.read_text(encoding="utf-8")

            # Second generation (regenerate over the same files)
            for kw in all_kws:
                generate_catalog_mocs.generate_keyword_page(conn, kw, vault, env, today_str)
            generate_catalog_mocs.generate_index_page(conn, all_kws, vault, today_str)

            second_pass = {}
            for f in sorted(catalog_dir.glob("*.md")):
                second_pass[f.name] = f.read_text(encoding="utf-8")

            self.assertEqual(first_pass.keys(), second_pass.keys())
            for name in first_pass:
                self.assertEqual(
                    first_pass[name], second_pass[name],
                    f"File {name} differs between runs — not idempotent",
                )

        conn.close()


# ---------------------------------------------------------------------------
# 12. test_moc_frontmatter
# ---------------------------------------------------------------------------

class TestMocFrontmatter(unittest.TestCase):
    """Generated catalog pages have type: moc in frontmatter."""

    def test_moc_frontmatter(self):
        conn = _make_in_memory_db()
        _seed_papers(conn, 2)
        kws = _seed_keywords(conn)

        db.assign_keyword(conn, "author01paper", "point-processes/hawkes")

        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            env = generate_catalog_mocs._get_jinja_env()
            today_str = "2026-04-13"

            kw = generate_catalog_mocs._get_keyword_by_path(conn, "point-processes/hawkes")
            generate_catalog_mocs.generate_keyword_page(conn, kw, vault, env, today_str)

            slug = generate_catalog_mocs._keyword_slug("point-processes/hawkes")
            page_path = vault / "literature" / "_catalog" / f"{slug}.md"
            self.assertTrue(page_path.exists())

            content = page_path.read_text(encoding="utf-8")

            # Parse frontmatter
            self.assertTrue(content.startswith("---"), "Page should start with frontmatter")
            end = content.find("\n---", 3)
            self.assertGreater(end, 0, "Should have closing frontmatter delimiter")
            fm_text = content[3:end]

            # Validate required frontmatter fields
            self.assertIn("type: moc", fm_text)
            self.assertIn("taxonomy_path:", fm_text)
            self.assertIn("paper_count:", fm_text)
            self.assertIn("date:", fm_text)
            self.assertIn("last_updated:", fm_text)
            self.assertIn("status: active", fm_text)
            self.assertIn("tags:", fm_text)

        conn.close()

    def test_index_page_frontmatter(self):
        """The _index.md page also has type: moc in frontmatter."""
        conn = _make_in_memory_db()
        kws = _seed_keywords(conn)

        with tempfile.TemporaryDirectory() as tmpdir:
            vault = Path(tmpdir)
            today_str = "2026-04-13"
            all_kws = generate_catalog_mocs._get_all_keywords(conn)
            generate_catalog_mocs.generate_index_page(conn, all_kws, vault, today_str)

            index_path = vault / "literature" / "_catalog" / "_index.md"
            self.assertTrue(index_path.exists())
            content = index_path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("---"))
            end = content.find("\n---", 3)
            fm_text = content[3:end]
            self.assertIn("type: moc", fm_text)

        conn.close()


if __name__ == "__main__":
    unittest.main()
