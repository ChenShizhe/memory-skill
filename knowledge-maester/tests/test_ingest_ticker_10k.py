"""
Unit tests for 10-K-mode summary ingestion via ingest_ticker.py --mode append-thesis.

Covers proposal 02 (knowledge-maester-improvement/02-10k-summary-ingestion.md):
  - 10-K input detection via frontmatter `mode: 10k`
  - Validation of required sections, ticker match, fiscal_year present
  - Synthesis of three-layer thesis block from 14-section summary
  - Idempotency via cite_key dedup
  - Empty Textual-Analysis Flags tolerated (null-emit, no abort)
  - --seed-predictions / --seed-credibility flag plumbing
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import vault_io
import ingest_ticker

FIXTURES = Path(__file__).parent / "fixtures"


def _bootstrap_minimal_profile(vault_path: Path, ticker: str) -> Path:
    """Write a minimal EXMP profile so append-thesis has a target."""
    rel_path = f"market/tickers/{ticker}.md"
    fm = {
        "type": "ticker",
        "title": f"{ticker} placeholder",
        "symbol": ticker,
        "name": "Example Industrial Corporation",
        "sector": "industrials",
        "exchange": "NYSE",
        "date": "2026-04-26",
        "tags": [],
        "last_updated": "2026-04-26",
        "watchlist": [],
        "status": "active",
        "owner_specialist": "test-fixture",
    }
    body = (
        "## Fundamentals\n\n"
        "### Business description\n\nPlaceholder.\n\n"
        "## Thesis updates\n\n"
        "### 2026-04-26 — bootstrap (test-fixture)\n\n"
        "```yaml\n"
        f"ticker: {ticker}\n"
        "brief_date: 2026-04-26\n"
        "brief_trigger: bootstrap\n"
        "thesis_state: intact\n"
        "```\n\n"
        "#### Low-level block — what the inputs say\n\n"
        "Bootstrap placeholder.\n\n"
        "#### High-level block — how this updates the thesis\n\n"
        "Bootstrap placeholder.\n\n"
        "<!-- AUTO-GENERATED -->\n## Appearances\n\n<!-- /AUTO-GENERATED -->\n"
    )
    return vault_io.write_note(vault_path, rel_path, fm, body)


def _copy_fixture(tmp_root: Path, with_claims: bool = True) -> Path:
    """Mirror the EXMP fixture into a paper-reader-style layout under tmp_root."""
    papers_dir = tmp_root / "papers"
    claims_dir = tmp_root / "claims"
    papers_dir.mkdir(parents=True, exist_ok=True)
    claims_dir.mkdir(parents=True, exist_ok=True)
    summary_dst = papers_dir / "EXMP_10k_FY2024.md"
    shutil.copy(FIXTURES / "EXMP_10k_FY2024.md", summary_dst)
    if with_claims:
        shutil.copy(
            FIXTURES / "EXMP_10k_FY2024.json",
            claims_dir / "EXMP_10k_FY2024.json",
        )
    return summary_dst


class Test10kIngestion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        self.vault_path = self.tmp_root / "citadel"
        self.vault_path.mkdir(parents=True)
        self.source_vault_root = self.tmp_root / "paper-reader-vault"
        self.source_vault_root.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_happy_path_appends_block(self):
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root)

        result = ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
        )
        self.assertEqual(result["status"], "appended")

        profile = (self.vault_path / "market/tickers/EXMP.md").read_text(encoding="utf-8")
        # Synthesized header is present
        self.assertIn("### 2025-02-14 — 10-K filing FY2024 (paper-reader-10k)", profile)
        # YAML brief carries cite_key, ticker, segments
        self.assertIn("cite_key: EXMP_10k_FY2024", profile)
        self.assertIn("ticker: EXMP", profile)
        self.assertIn("segments:", profile)
        self.assertIn("Industrial Components", profile)
        # Three-layer scaffold preserved
        self.assertIn("#### Low-level block", profile)
        self.assertIn("#### High-level block", profile)
        # Inline cite_key markers
        self.assertIn("[cite_key: EXMP_10k_FY2024, Item 7]", profile)
        # Bootstrap thesis block was preserved
        self.assertIn("### 2026-04-26 — bootstrap (test-fixture)", profile)
        # AUTO-GENERATED Appearances section preserved
        self.assertIn("<!-- AUTO-GENERATED -->", profile)
        self.assertIn("## Appearances", profile)

    def test_idempotency_via_cite_key(self):
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root)
        ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
        )
        # Second run should detect the cite_key and skip
        result2 = ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
        )
        self.assertEqual(result2["status"], "skipped")
        # Profile only has one synthesized block
        profile = (self.vault_path / "market/tickers/EXMP.md").read_text(encoding="utf-8")
        self.assertEqual(profile.count("(paper-reader-10k)"), 1)

    def test_ticker_mismatch_aborts(self):
        _bootstrap_minimal_profile(self.vault_path, "WRONG")
        source = _copy_fixture(self.source_vault_root)
        # Source frontmatter has ticker EXMP; --ticker WRONG should error
        with self.assertRaises(ValueError) as ctx:
            ingest_ticker.ingest_ticker_append_thesis(
                source_path=source,
                ticker="WRONG",
                vault_path=self.vault_path,
                source_vault_root=self.source_vault_root,
            )
        self.assertIn("does not match", str(ctx.exception))

    def test_missing_required_section_aborts(self):
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root)
        # Mutilate the source: drop the `## Open Questions` section
        text = source.read_text(encoding="utf-8")
        mutilated = text.replace("## Open Questions\n", "## Open Questions REMOVED\n")
        source.write_text(mutilated, encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            ingest_ticker.ingest_ticker_append_thesis(
                source_path=source,
                ticker="EXMP",
                vault_path=self.vault_path,
                source_vault_root=self.source_vault_root,
            )
        self.assertIn("Open Questions", str(ctx.exception))

    def test_empty_textual_analysis_emits_null(self):
        # The fixture ships with an italicized placeholder textual-analysis section.
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root)
        ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
        )
        profile = (self.vault_path / "market/tickers/EXMP.md").read_text(encoding="utf-8")
        self.assertIn("textual_analysis: ~", profile)
        # And the high-level synthesis omits the empty Textual-Analysis Flags section
        # (no `**Textual-Analysis Flags.**` paragraph in the high-level block).
        # Find the high-level block boundary:
        hl_idx = profile.index("#### High-level block")
        hl_block = profile[hl_idx:]
        self.assertNotIn("**Textual-Analysis Flags.**", hl_block)

    def test_missing_profile_errors(self):
        # No bootstrap profile written; append-thesis should error
        source = _copy_fixture(self.source_vault_root)
        with self.assertRaises(FileNotFoundError):
            ingest_ticker.ingest_ticker_append_thesis(
                source_path=source,
                ticker="EXMP",
                vault_path=self.vault_path,
                source_vault_root=self.source_vault_root,
            )

    def test_seed_predictions_writes_entry(self):
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root)
        ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
            seed_predictions=True,
        )
        pred_dir = self.vault_path / "predictions"
        self.assertTrue(pred_dir.exists())
        entries = list(pred_dir.glob("*.md"))
        self.assertEqual(len(entries), 1, f"expected 1 prediction entry, got {entries}")
        content = entries[0].read_text(encoding="utf-8")
        self.assertIn("source_cite_key: EXMP_10k_FY2024", content)
        self.assertIn("FY2025 consolidated revenue growth", content)
        # check_date should be guidance horizon (2025-12-31) + 30 days
        self.assertIn("check_date: 2026-01-30", content)

    def test_seed_predictions_default_off(self):
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root)
        ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
        )
        pred_dir = self.vault_path / "predictions"
        self.assertFalse(pred_dir.exists())

    def test_seed_credibility_writes_log(self):
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root)
        ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
            seed_credibility=True,
        )
        log_path = self.vault_path / "reference" / "credibility-log.md"
        self.assertTrue(log_path.exists())
        content = log_path.read_text(encoding="utf-8")
        self.assertIn("EXMP_management_2024", content)

    def test_claims_sidecar_optional(self):
        # Without sidecar copy, ingestion should still succeed (sidecar is optional).
        _bootstrap_minimal_profile(self.vault_path, "EXMP")
        source = _copy_fixture(self.source_vault_root, with_claims=False)
        result = ingest_ticker.ingest_ticker_append_thesis(
            source_path=source,
            ticker="EXMP",
            vault_path=self.vault_path,
            source_vault_root=self.source_vault_root,
        )
        self.assertEqual(result["status"], "appended")


class Test10kSynthesisHelpers(unittest.TestCase):
    """Cover helper functions directly so failures localize cleanly."""

    def test_parse_segments_table(self):
        section = (
            "| Segment | Revenue ($M) | Margin (%) | YoY Change (%) |\n"
            "|---|---|---|---|\n"
            "| Industrial Components | 2,140 | 18.2 | 9.1 |\n"
            "| Aftermarket Services | 740 | 24.6 | 4.4 |\n"
            "| **Consolidated** | **3,290** | **18.4** | **6.2** |\n"
        )
        segments = ingest_ticker._parse_segments_table(section)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["name"], "Industrial Components")
        self.assertEqual(segments[0]["revenue"], "2140")
        self.assertEqual(segments[1]["name"], "Aftermarket Services")

    def test_is_textual_analysis_empty_placeholder(self):
        self.assertTrue(ingest_ticker._is_textual_analysis_empty(
            "_(Section reserved for paper-reader textual-analysis screening.)_"
        ))
        self.assertTrue(ingest_ticker._is_textual_analysis_empty(""))

    def test_is_textual_analysis_empty_populated(self):
        self.assertFalse(ingest_ticker._is_textual_analysis_empty(
            "LM Negative density 0.0234, YoY delta +0.0042, CMN cosine 0.81. Flagged: Item 7A."
        ))

    def test_cite_key_already_present(self):
        body = "stuff\ncite_key: EXMP_10k_FY2024\nstuff"
        self.assertTrue(ingest_ticker._cite_key_already_present(body, "EXMP_10k_FY2024"))
        self.assertFalse(ingest_ticker._cite_key_already_present(body, "EXMP_10k_FY2023"))


if __name__ == "__main__":
    unittest.main()
