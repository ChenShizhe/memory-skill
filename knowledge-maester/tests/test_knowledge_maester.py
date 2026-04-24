"""
Unit tests for knowledge-maester scripts.

Run from workspace root:
  python3 -m pytest knowledge-maester/tests/ -v
  # or
  python3 knowledge-maester/tests/test_knowledge_maester.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts dir to path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import vault_io
from ingest_report import ingest_report, _strip_url_column
from ingest_paper import ingest_paper, ingest_digest, ingest_field
from ingest_reference import ingest_reference
from check_graph import check_graph, collect_notes
from validate_vault import validate_vault
from generate_index import generate_vault_index, generate_market_dashboard


# ---------------------------------------------------------------------------
# vault_io tests
# ---------------------------------------------------------------------------

class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(vault_io.slugify("Energy Market Brief"), "energy-market-brief")

    def test_special_chars(self):
        self.assertEqual(vault_io.slugify("AI/ML & Data — 2026"), "ai-ml-data-2026")

    def test_max_length(self):
        long = "a" * 100
        self.assertLessEqual(len(vault_io.slugify(long)), 60)

    def test_em_dash(self):
        self.assertEqual(vault_io.slugify("Energy Market Brief — March 2026"), "energy-market-brief-march-2026")


class TestParseFrontmatter(unittest.TestCase):
    def test_basic_frontmatter(self):
        content = "---\ntype: report\ntitle: Test\n---\n\n# Body"
        fm, body = vault_io.parse_frontmatter(content)
        self.assertEqual(fm["type"], "report")
        self.assertEqual(fm["title"], "Test")
        self.assertIn("Body", body)

    def test_list_field(self):
        content = "---\ntags:\n  - market\n  - energy\n---\n\nbody"
        fm, body = vault_io.parse_frontmatter(content)
        self.assertEqual(fm["tags"], ["market", "energy"])

    def test_inline_list(self):
        content = "---\nwatchlist: [NVDA, AMD]\n---\n\nbody"
        fm, body = vault_io.parse_frontmatter(content)
        self.assertEqual(fm["watchlist"], ["NVDA", "AMD"])

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nbody"
        fm, body = vault_io.parse_frontmatter(content)
        self.assertEqual(fm, {})
        self.assertIn("Just a heading", body)

    def test_render_roundtrip(self):
        fm = {"type": "report", "title": "Test", "tags": ["a", "b"], "sources_count": "5"}
        rendered = vault_io.render_frontmatter(fm)
        re_parsed = vault_io._parse_yaml_subset(rendered)
        self.assertEqual(re_parsed["type"], "report")
        self.assertEqual(re_parsed["tags"], ["a", "b"])


class TestExtractTickers(unittest.TestCase):
    def test_basic_tickers(self):
        text = "NVDA and AMD are up. The US economy is fine."
        tickers = vault_io.extract_tickers(text)
        self.assertIn("NVDA", tickers)
        self.assertIn("AMD", tickers)
        self.assertNotIn("US", tickers)  # excluded

    def test_futures(self):
        tickers = vault_io.extract_tickers("CL=F and BZ=F moved today.")
        self.assertIn("CL=F", tickers)

    def test_exclusions(self):
        text = "The GDP and CPI data came in hot. THE Fed reacted."
        tickers = vault_io.extract_tickers(text)
        self.assertNotIn("GDP", tickers)
        self.assertNotIn("THE", tickers)


class TestExtractWikiLinks(unittest.TestCase):
    def test_basic(self):
        text = "See [[energy-report]] and [[NVDA]] for details."
        links = vault_io.extract_wiki_links(text)
        self.assertIn("energy-report", links)
        self.assertIn("NVDA", links)

    def test_empty(self):
        self.assertEqual(vault_io.extract_wiki_links("no links here"), [])


class TestToday(unittest.TestCase):
    def test_format(self):
        import re
        self.assertRegex(vault_io.today_str(), r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Ingest report tests (using temp vault)
# ---------------------------------------------------------------------------

def _make_temp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "citadel"
    for d in ["market/reports", "market/tickers", "market/analysis", "market/archive",
               "literature/papers", "literature/digests", "literature/fields",
               "literature/surveys", "reference", "templates", "zotero"]:
        (vault / d).mkdir(parents=True)
    (vault / "_index.md").write_text("---\ntype: index\ntitle: Index\n---\n", encoding="utf-8")
    # Deploy minimal templates
    (vault / "templates" / "report.md").write_text("---\ntype: report\n---\n", encoding="utf-8")
    return vault


def _make_temp_paper_bank(tmp_path: Path) -> Path:
    pb = tmp_path / "paper-bank"
    pb.mkdir()
    (pb / "_manifest.json").write_text("[]", encoding="utf-8")
    return pb


class TestIngestReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _make_temp_vault(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_report(self, content: str) -> Path:
        p = self.tmp_path / "final-report.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_basic_ingest(self):
        report_content = """---
title: Energy Market Brief
date: 2026-03-14
confidence: high
tags: [energy]
watchlist: [CL=F, XOM]
---

# Energy Market Brief

## Executive Summary

Oil prices rose sharply.

## Main Developments

### Supply Crunch

Supply fell 5% this week.

## Source Index

| ID | Source | Date | Type |
|---|---|---|---|
| F01 | Reuters | 2026-03-14 | news |
| F02 | Bloomberg | 2026-03-14 | news |
"""
        source = self._make_report(report_content)
        result = ingest_report(source, "test-project", "run-001", self.vault)

        self.assertEqual(result["status"], "created")
        note_path = self.vault / result["vault_path"]
        self.assertTrue(note_path.exists())

        # Check frontmatter
        content = note_path.read_text(encoding="utf-8")
        fm, body = vault_io.parse_frontmatter(content)
        self.assertEqual(fm["type"], "report")
        self.assertEqual(fm["confidence"], "high")
        self.assertIn("CL=F", fm.get("watchlist", []))

    def test_idempotency(self):
        report_content = "---\ntitle: Test\ndate: 2026-03-14\n---\n# Test\n"
        source = self._make_report(report_content)
        result1 = ingest_report(source, "proj", "run1", self.vault)
        result2 = ingest_report(source, "proj", "run1", self.vault)
        self.assertEqual(result1["status"], "created")
        self.assertEqual(result2["status"], "skipped")

    def test_ticker_stub_created(self):
        report_content = "---\ntitle: NVDA Brief\ndate: 2026-03-14\nwatchlist: [NVDA]\n---\n# NVDA Brief\n## Executive Summary\nNVDA surged.\n"
        source = self._make_report(report_content)
        result = ingest_report(source, "proj", "run1", self.vault)
        ticker_path = self.vault / "market" / "tickers" / "NVDA.md"
        self.assertTrue(ticker_path.exists())
        self.assertIn("market/tickers/NVDA.md", result["stubs_created"])

    def test_strip_url_column(self):
        table = "| ID | Source | URL | Date |\n|---|---|---|---|\n| F01 | Reuters | https://example.com | 2026-03-14 |"
        stripped = _strip_url_column(table)
        self.assertNotIn("URL", stripped)
        self.assertNotIn("https://", stripped)
        self.assertIn("Reuters", stripped)


# ---------------------------------------------------------------------------
# Ingest reference tests
# ---------------------------------------------------------------------------

class TestIngestReference(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _make_temp_vault(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_source(self, content: str) -> Path:
        source_path = self.tmp_path / "reference-source.md"
        source_path.write_text(content, encoding="utf-8")
        return source_path

    def test_basic_ingest_with_fallback_body(self):
        source = self._make_source(
            """# Source

This describes market-watcher usage in plain language.
"""
        )
        result = ingest_reference(
            source_path=source,
            title="Market Watcher Capability",
            tags=["my-system", "reference"],
            category="tool-capability",
            vault_path=self.vault,
        )

        self.assertEqual(result["status"], "created")
        note_path = self.vault / "reference" / "market-watcher-capability.md"
        self.assertTrue(note_path.exists())

        fm, body = vault_io.parse_frontmatter(note_path.read_text(encoding="utf-8"))
        self.assertEqual(fm["type"], "memory")
        self.assertEqual(fm["title"], "Market Watcher Capability")
        self.assertEqual(fm["category"], "tool-capability")
        self.assertEqual(fm["status"], "active")
        self.assertEqual(fm["tags"], ["my-system", "reference"])

        self.assertIn("## Context", body)
        self.assertIn("## Content", body)
        self.assertIn("## Related", body)
        self.assertIn("[[market-watcher|market-watcher]]", body)

    def test_idempotency(self):
        source = self._make_source(
            """## Content

Credential Broker connects requests to tools.
"""
        )
        result1 = ingest_reference(
            source_path=source,
            title="Credential Broker",
            tags=[],
            category="tool-capability",
            vault_path=self.vault,
        )
        result2 = ingest_reference(
            source_path=source,
            title="Credential Broker",
            tags=[],
            category="tool-capability",
            vault_path=self.vault,
        )
        self.assertEqual(result1["status"], "created")
        self.assertEqual(result2["status"], "skipped")

    def test_balanced_linking_skips_protected_spans(self):
        source = self._make_source(
            """## Content

Knowledge Maester works with market-watcher.
Keep `market-watcher` literal.
Existing [[already-linked]] should stay.
Reference https://example.com/Knowledge-Maester for docs.
"""
        )
        result = ingest_reference(
            source_path=source,
            title="Reference Primer",
            tags=[],
            category="workflow",
            vault_path=self.vault,
        )
        self.assertEqual(result["status"], "created")

        note_path = self.vault / result["vault_path"]
        content = note_path.read_text(encoding="utf-8")

        self.assertIn("[[knowledge-maester|Knowledge Maester]]", content)
        self.assertIn("[[market-watcher|market-watcher]]", content)
        self.assertIn("`market-watcher`", content)
        self.assertIn("[[already-linked]]", content)
        self.assertIn("https://example.com/Knowledge-Maester", content)

    def test_stub_creation_includes_memory_category_and_no_self_stub(self):
        source = self._make_source(
            """## Context

Knowledge Maester maintains graph integrity.

## Content

Credential Broker connects to market-watcher.
"""
        )
        result = ingest_reference(
            source_path=source,
            title="Knowledge Maester",
            tags=["my-system"],
            category="tool-capability",
            vault_path=self.vault,
        )

        self.assertEqual(result["status"], "created")
        self.assertNotIn("reference/knowledge-maester.md", result["stubs_created"])
        self.assertIn("reference/credential-broker.md", result["stubs_created"])
        self.assertIn("reference/market-watcher.md", result["stubs_created"])

        for stub_rel in result["stubs_created"]:
            stub_fm, stub_body = vault_io.read_note(self.vault, stub_rel)
            self.assertEqual(stub_fm["type"], "memory")
            self.assertEqual(stub_fm["category"], "tool-capability")
            self.assertIn("Stub — no content yet.", stub_body)


# ---------------------------------------------------------------------------
# Ingest paper tests
# ---------------------------------------------------------------------------

class TestIngestPaper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _make_temp_vault(self.tmp_path)
        self.paper_bank = _make_temp_paper_bank(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_paper_ingest(self):
        note_content = """---
title: Neural Architecture Search Methods
authors: [Smith, Jones, Lee]
year: 2024
tags: [neural-architecture, search-methods]
---

# Neural Architecture Search Methods

## Summary

This paper surveys neural architecture search methods for efficient model design.

## Key Claims

- Differentiable search reduces compute cost by an order of magnitude.

## Methodology

Empirical evaluation on standard benchmarks.
"""
        note_path = self.tmp_path / "note.md"
        note_path.write_text(note_content, encoding="utf-8")

        result = ingest_paper("smith2024neural", note_path, self.vault, self.paper_bank)
        self.assertEqual(result["status"], "created")

        vault_note = self.vault / "literature" / "papers" / "smith2024neural.md"
        self.assertTrue(vault_note.exists())

        content = vault_note.read_text(encoding="utf-8")
        fm, body = vault_io.parse_frontmatter(content)
        self.assertEqual(fm["cite_key"], "smith2024neural")
        self.assertEqual(fm["year"], "2024")

        # Check manifest updated
        manifest = vault_io.read_manifest(self.paper_bank)
        keys = [e["cite_key"] for e in manifest]
        self.assertIn("smith2024neural", keys)

    def test_digest_ingest(self):
        note_content = """---
title: Digest of Neural Architecture Search Paper
field: neural-architecture-search
---

# Digest of Neural Architecture Search Paper

## One-Paragraph Summary

The paper provides...

## Key Contributions

- Differentiable search framework for architecture design.

## Claims Worth Tracking

- Search cost scales linearly with network depth.

## Open Questions

- Does it generalize to vision transformers?
"""
        note_path = self.tmp_path / "digest.md"
        note_path.write_text(note_content, encoding="utf-8")

        result = ingest_digest("smith2024neural", note_path, self.vault)
        self.assertEqual(result["status"], "created")

        digest_path = self.vault / "literature" / "digests" / "smith2024neural-digest.md"
        self.assertTrue(digest_path.exists())


# ---------------------------------------------------------------------------
# check_graph.py tests
# ---------------------------------------------------------------------------

class TestCheckGraph(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _make_temp_vault(self.tmp_path)
        self.paper_bank = _make_temp_paper_bank(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_note(self, rel_path: str, fm: dict, body: str):
        vault_io.write_note(self.vault, rel_path, fm, body)

    def _base_fm(self, note_type: str = "memory", title: str = "Test") -> dict:
        return {
            "type": note_type, "title": title, "date": "2026-03-14",
            "tags": [], "last_updated": "2026-03-14", "status": "active",
        }

    def _memory_base_fm(self, note_type: str = "workflow", title: str = "Test") -> dict:
        return {
            "type": note_type, "title": title, "date": "2026-03-14",
            "last_updated": "2026-03-14", "status": "active",
            "layer": "long-term", "topics": ["memory-system"], "projects": ["memories-obsidianization"],
        }

    def test_broken_link_detected(self):
        self._write_note(
            "market/reports/2026-03-14-test.md",
            {**self._base_fm("report", "Test Report"),
             "watchlist": [], "confidence": "medium", "sources_count": 1,
             "project_name": "p", "run_id": "r"},
            "# Test\n\n## Key Findings\nSee [[nonexistent-note]].\n"
        )
        report = check_graph(self.vault, self.paper_bank)
        issue_types = [i["type"] for i in report["issues"]]
        self.assertIn("broken_link", issue_types)

    def test_orphan_note_detected(self):
        self._write_note(
            "market/reports/2026-03-14-isolated.md",
            {**self._base_fm("report", "Isolated"),
             "watchlist": [], "confidence": "medium", "sources_count": 0,
             "project_name": "p", "run_id": "r"},
            "# Isolated\n\n## Key Findings\nNo links here.\n"
        )
        report = check_graph(self.vault, self.paper_bank)
        issue_types = [i["type"] for i in report["issues"]]
        self.assertIn("orphan_note", issue_types)

    def test_missing_frontmatter_detected(self):
        note_path = self.vault / "market" / "reports" / "bare.md"
        note_path.write_text("# A note with no frontmatter\n\nContent.", encoding="utf-8")
        report = check_graph(self.vault, self.paper_bank)
        issue_types = [i["type"] for i in report["issues"]]
        self.assertIn("missing_frontmatter", issue_types)

    def test_duplicate_cite_key(self):
        for name in ("paper-a.md", "paper-b.md"):
            self._write_note(
                f"literature/papers/{name}",
                {**self._base_fm("paper", name),
                 "cite_key": "smith2020test", "review_status": "draft",
                 "bank_path": "", "canonical_id": "", "authors": [], "year": "2020",
                 "content_status": ""},
                "# Paper\n\n## Summary\nSame cite key.\n"
            )
        report = check_graph(self.vault, self.paper_bank)
        issue_types = [i["type"] for i in report["issues"]]
        self.assertIn("duplicate_cite_key", issue_types)

    def test_clean_vault_no_errors(self):
        # Write two linked notes
        self._write_note(
            "market/reports/2026-03-14-linked.md",
            {**self._base_fm("report", "Linked Report"),
             "watchlist": [], "confidence": "medium", "sources_count": 1,
             "project_name": "p", "run_id": "r"},
            "# Linked Report\n\n## Key Findings\nSee [[2026-03-14-other]].\n"
        )
        self._write_note(
            "market/reports/2026-03-14-other.md",
            {**self._base_fm("report", "Other Report"),
             "watchlist": [], "confidence": "medium", "sources_count": 1,
             "project_name": "p", "run_id": "r"},
            "# Other Report\n\n## Key Findings\nSee [[2026-03-14-linked]].\n"
        )
        report = check_graph(self.vault, self.paper_bank)
        errors = [i for i in report["issues"] if i["severity"] == "ERROR"]
        self.assertEqual(errors, [])

    def test_memory_schema_accepts_memory_types(self):
        memory_vault = self.tmp_path / "memories"
        memory_vault.mkdir()

        vault_io.write_note(
            memory_vault,
            "long-term/workflow-memory-evolution.md",
            self._memory_base_fm("workflow", "Memory Evolution"),
            "# Memory Evolution\n\n## Summary\nTracks ingestion.\n\n## Guidance\n- Keep links fresh.\n\n## Related\n- [[decision-linking-policy]]\n"
        )
        vault_io.write_note(
            memory_vault,
            "long-term/decision-linking-policy.md",
            self._memory_base_fm("decision", "Linking Policy"),
            "# Linking Policy\n\n## Summary\nDefines links.\n\n## Guidance\n- Use topic anchors.\n"
        )
        report = check_graph(memory_vault, self.paper_bank, schema="memory")
        errors = [i for i in report["issues"] if i["severity"] == "ERROR"]
        self.assertEqual(errors, [])

    def test_memory_schema_includes_hub_prefixed_notes(self):
        memory_vault = self.tmp_path / "memories"
        memory_vault.mkdir()

        vault_io.write_note(
            memory_vault,
            "long-term/_hub-memory-system.md",
            self._memory_base_fm("hub", "Topic Hub: Memory System"),
            "# Topic Hub: Memory System\n\n## Summary\nHub note.\n\n## Guidance\n- Collect related notes.\n"
        )
        notes = collect_notes(memory_vault, schema="memory")
        stems = {n.stem for n in notes}
        self.assertIn("_hub-memory-system", stems)

    def test_memory_schema_skips_core_identity_files(self):
        memory_vault = self.tmp_path / "memories"
        memory_vault.mkdir()

        identity = memory_vault / "AGENTS.md"
        identity.write_text("# Agent Identity\n\nNo frontmatter here.\n", encoding="utf-8")
        notes = collect_notes(memory_vault, schema="memory")
        note_names = {n.name for n in notes}
        self.assertNotIn("AGENTS.md", note_names)

    def test_memory_schema_skips_catalog_and_shards(self):
        memory_vault = self.tmp_path / "memories"
        memory_vault.mkdir()

        (memory_vault / "catalog.md").write_text(
            "# Searchable Memory Catalog\n\n## Generated Entries\n",
            encoding="utf-8",
        )
        (memory_vault / "catalog-index.md").write_text(
            "# Memory Catalog Index\n\n## Shards\n",
            encoding="utf-8",
        )
        shards_dir = memory_vault / "catalog-shards"
        shards_dir.mkdir()
        (shards_dir / "core-identity.md").write_text(
            "# Catalog Shard — core-identity\n\n## Generated Entries\n\n## Manual Entries\n",
            encoding="utf-8",
        )
        (shards_dir / "misc.md").write_text(
            "# Catalog Shard — misc\n\n## Generated Entries\n\n## Manual Entries\n",
            encoding="utf-8",
        )
        vault_io.write_note(
            memory_vault,
            "long-term/memory-note.md",
            self._memory_base_fm("workflow", "Memory Note"),
            "# Memory Note\n\n## Summary\nLinked note.\n\n## Guidance\n- Keep the vault valid.\n",
        )

        notes = collect_notes(memory_vault, schema="memory")
        note_names = {n.name for n in notes}
        self.assertNotIn("catalog.md", note_names)
        self.assertNotIn("catalog-index.md", note_names)
        # Shards are excluded via directory skip.
        shard_paths = [n for n in notes if "catalog-shards" in str(n)]
        self.assertEqual(shard_paths, [])

        report = check_graph(memory_vault, self.paper_bank, schema="memory")
        errors = [i for i in report["issues"] if i["severity"] == "ERROR"]
        self.assertEqual(errors, [])

    def test_memory_schema_skips_duplicate_cite_key_and_manifest_drift(self):
        memory_vault = self.tmp_path / "memories"
        memory_vault.mkdir()

        for name in ("paper-a.md", "paper-b.md"):
            vault_io.write_note(
                memory_vault,
                f"long-term/{name}",
                {**self._memory_base_fm("reference", name), "cite_key": "testkey2024shared"},
                "# Ref\n\n## Summary\nShared cite key.\n\n## Guidance\n- Not a paper-bank artifact.\n"
            )
        (self.paper_bank / "_manifest.json").write_text(
            json.dumps([{"cite_key": "manifest_only_key"}]),
            encoding="utf-8"
        )
        report = check_graph(memory_vault, self.paper_bank, schema="memory")
        issue_types = [i["type"] for i in report["issues"]]
        self.assertNotIn("duplicate_cite_key", issue_types)
        self.assertNotIn("manifest_drift", issue_types)


# ---------------------------------------------------------------------------
# validate_vault.py tests
# ---------------------------------------------------------------------------

class TestValidateVault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _make_temp_vault(self.tmp_path)
        self.paper_bank = _make_temp_paper_bank(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_paper_passes(self):
        vault_io.write_note(
            self.vault, "literature/papers/smith2020test.md",
            {
                "type": "paper", "title": "Test Paper", "cite_key": "smith2020test",
                "canonical_id": "", "authors": ["Smith"], "year": "2020",
                "date": "2026-03-14", "tags": [], "last_updated": "2026-03-14",
                "content_status": "full-text", "review_status": "reviewed",
                "bank_path": "smith2020test/", "status": "active",
            },
            "# Test Paper\n\n## Summary\nA great paper.\n\n## Key Claims\nClaim.\n\n## Methodology\nRCT.\n"
        )
        report = validate_vault(self.vault, self.paper_bank)
        errors = [i for i in report["issues"] if i["severity"] == "ERROR"]
        self.assertEqual(errors, [])

    def test_invalid_type_fails(self):
        vault_io.write_note(
            self.vault, "market/reports/2026-03-14-bad.md",
            {
                "type": "badtype", "title": "Bad", "date": "2026-03-14",
                "tags": [], "last_updated": "2026-03-14", "status": "active",
            },
            "# Bad\n"
        )
        report = validate_vault(self.vault, self.paper_bank)
        self.assertFalse(report["summary"]["passed"])


# ---------------------------------------------------------------------------
# generate_index.py tests
# ---------------------------------------------------------------------------

class TestGenerateIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _make_temp_vault(self.tmp_path)
        self.paper_bank = _make_temp_paper_bank(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_vault_index_contains_sections(self):
        content = generate_vault_index(self.vault)
        self.assertIn("Market Intelligence", content)
        self.assertIn("Literature", content)
        self.assertIn("type: index", content)

    def test_dashboard_contains_tables(self):
        content = generate_market_dashboard(self.vault)
        self.assertIn("Recent Reports", content)
        self.assertIn("Active Watchlist", content)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
