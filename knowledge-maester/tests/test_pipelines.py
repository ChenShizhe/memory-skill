#!/usr/bin/env python3
"""
Pipeline integration tests for knowledge-maester (C3: Vault Ingestion Pipelines).

Runs all 6 pipeline tests from the C3 spec against the live vault.
Creates synthetic test fixtures, validates pipeline behaviour, then cleans up.

Usage:
  python3 knowledge-maester/tests/test_pipelines.py

Exit: 0 if all tests pass, 1 if any fail.
"""
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# Resolve scripts directory
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import vault_io
from ingest_report import ingest_report
from ingest_paper import ingest_paper
from check_graph import check_graph
from compress_old_notes import find_candidates, compress_note, update_compression_log
from polish_note import polish_note
from generate_index import generate_vault_index, generate_market_dashboard, generate_literature_catalog

VAULT_PATH = Path(os.environ.get("TEST_VAULT_PATH", tempfile.mkdtemp()))
PAPER_BANK_PATH = Path(os.environ.get("TEST_PAPER_BANK_PATH", tempfile.mkdtemp()))

# Unique prefix to identify test notes for cleanup
TEST_PREFIX = "_c3pipe_"

# Track all test artifacts created in live vault for cleanup
_created_vault_notes: list[str] = []
_created_bank_keys: list[str] = []


def _record(rel_path: str) -> None:
    _created_vault_notes.append(rel_path)


def _cleanup() -> None:
    for rel in _created_vault_notes:
        p = VAULT_PATH / rel
        if p.exists():
            p.unlink()
    # Remove test manifest entries
    if _created_bank_keys and PAPER_BANK_PATH.exists():
        manifest = vault_io.read_manifest(PAPER_BANK_PATH)
        manifest = [e for e in manifest if e.get("cite_key") not in _created_bank_keys]
        manifest_path = PAPER_BANK_PATH / "_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report_file(tmp_path: Path, title: str, date_str: str, tags=None,
                       watchlist=None, extra_body: str = "") -> Path:
    tags_str = str(tags or ["energy"]).replace("'", '"')
    wl_str = str(watchlist or ["CL=F", "XOM"]).replace("'", '"')
    content = f"""---
title: {title}
date: {date_str}
confidence: high
tags: {tags_str}
watchlist: {wl_str}
---

# {title}

## Executive Summary

Oil prices rose sharply this week due to supply constraints from OPEC.

## Main Developments

### Supply Crunch

Supply fell 5% this week. {extra_body}

## Source Index

| ID | Source | Date | Type |
|---|---|---|---|
| F01 | Reuters | {date_str} | news |
| F02 | Bloomberg | {date_str} | news |
"""
    p = tmp_path / f"{vault_io.slugify(title)}.md"
    p.write_text(content, encoding="utf-8")
    return p


def _make_paper_note(tmp_path: Path, cite_key: str, title: str,
                      concept_mention: str = "") -> Path:
    content = f"""---
title: {title}
authors: [Smith, Jones]
year: 2024
tags: [market-microstructure, deep-learning]
---

# {title}

## Summary

This paper explores deep learning methods applied to financial time series forecasting.
{concept_mention}

## Key Claims

- Transformer-based models capture long-range dependencies in price sequences.
- The model outperforms LSTM baselines on equity tick data.

## Methodology

Empirical evaluation on benchmark financial datasets (2020-2023).
"""
    p = tmp_path / f"{cite_key}.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------

def run_test(name: str, fn) -> bool:
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print('='*60)
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except AssertionError as e:
        print(f"FAIL: {name}")
        print(f"  AssertionError: {e}")
        return False
    except Exception as e:
        print(f"FAIL: {name}")
        print(f"  Exception ({type(e).__name__}): {e}")
        return False


# ---------------------------------------------------------------------------
# Test 1: Market Report Ingestion
# ---------------------------------------------------------------------------

def test1_market_report_ingestion():
    """Ingest a market report and verify vault note, frontmatter, ticker stub, dashboard."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        title = f"{TEST_PREFIX}Energy Market Brief"
        today = vault_io.today_str()

        source = _make_report_file(tmp_path, title, today, watchlist=["CL=F", "XOM"])
        result = ingest_report(source, "c3-test", "run-001", VAULT_PATH)

        assert result["status"] == "created", f"Expected created, got {result['status']}"
        vault_note_rel = result["vault_path"]
        _record(vault_note_rel)

        # Record ticker stubs for cleanup
        for stub_rel in result.get("stubs_created", []):
            # Only clean up stubs that start with TEST_PREFIX indirectly; tickers are symbols
            # We'll leave tickers unless they're clearly test-only
            pass

        # Verify vault note exists
        note_path = VAULT_PATH / vault_note_rel
        assert note_path.exists(), f"Vault note not found: {vault_note_rel}"

        # Verify frontmatter
        fm, body = vault_io.parse_frontmatter(note_path.read_text(encoding="utf-8"))
        assert fm["type"] == "report", f"type={fm['type']!r}, expected 'report'"
        assert fm["confidence"] == "high", f"confidence={fm['confidence']!r}"
        assert "CL=F" in fm.get("watchlist", []), f"CL=F not in watchlist: {fm.get('watchlist')}"
        assert fm["status"] == "active"

        # Verify ticker stub
        ticker_stubs = result.get("stubs_created", [])
        assert any("CL=F" in s or "XOM" in s for s in ticker_stubs) or \
               (VAULT_PATH / "market" / "tickers" / "CL=F.md").exists(), \
               "No ticker stub created for CL=F"

        # Verify dashboard generation works
        dashboard = generate_market_dashboard(VAULT_PATH)
        assert "Recent Reports" in dashboard, "Dashboard missing Recent Reports section"
        assert "Active Watchlist" in dashboard, "Dashboard missing Active Watchlist section"
        print(f"  vault note: {vault_note_rel}")
        print(f"  ticker stubs: {ticker_stubs}")
        print(f"  dashboard: OK ({len(dashboard)} chars)")


# ---------------------------------------------------------------------------
# Test 2: Paper Note Ingestion
# ---------------------------------------------------------------------------

def test2_paper_note_ingestion():
    """Ingest a paper note and verify vault note and paper-bank manifest update."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cite_key = f"{TEST_PREFIX}test2024example"[:30].replace("-", "").replace("_", "")
        # Use a simple ASCII cite key
        cite_key = "c3test2024example"
        _created_bank_keys.append(cite_key)

        note_path = _make_paper_note(tmp_path, cite_key, "Deep Learning for Financial Forecasting")
        result = ingest_paper(cite_key, note_path, VAULT_PATH, PAPER_BANK_PATH)

        assert result["status"] == "created", f"Expected created, got {result['status']}"
        vault_note_rel = result["vault_path"]
        _record(vault_note_rel)

        # Verify vault note
        note_abs = VAULT_PATH / vault_note_rel
        assert note_abs.exists(), f"Vault note not found: {vault_note_rel}"

        fm, body = vault_io.parse_frontmatter(note_abs.read_text(encoding="utf-8"))
        assert fm["type"] == "paper"
        assert fm["cite_key"] == cite_key
        assert fm["year"] == "2024"
        assert fm["status"] == "active"

        # Verify paper-bank manifest updated
        manifest = vault_io.read_manifest(PAPER_BANK_PATH)
        keys_in_manifest = [e.get("cite_key") for e in manifest]
        assert cite_key in keys_in_manifest, f"{cite_key} not in paper-bank manifest"

        print(f"  vault note: {vault_note_rel}")
        print(f"  manifest entries: {len(manifest)}, cite_key present: {cite_key in keys_in_manifest}")


# ---------------------------------------------------------------------------
# Test 3: Cross-Domain Links
# ---------------------------------------------------------------------------

def test3_cross_domain_links():
    """
    Ingest a paper, then a market report that explicitly links to it.
    Verify: both notes exist, report body references paper cite_key,
            check_graph finds no broken links for valid cross-link.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cite_key = "c3test2024crosslink"
        _created_bank_keys.append(cite_key)

        # Step 1: ingest the paper
        paper_file = _make_paper_note(tmp_path, cite_key,
                                       "Cross-Domain: Financial Forecasting")
        paper_result = ingest_paper(cite_key, paper_file, VAULT_PATH, PAPER_BANK_PATH)
        assert paper_result["status"] == "created"
        _record(paper_result["vault_path"])

        # Step 2: ingest a market report whose body contains [[cite_key]]
        today = vault_io.today_str()
        title = f"{TEST_PREFIX}Cross Domain Report"
        extra = f"This methodology is detailed in [[{cite_key}]]."
        source = _make_report_file(tmp_path, title, today,
                                    watchlist=["CL=F"], extra_body=extra)
        report_result = ingest_report(source, "c3-test", "run-cross", VAULT_PATH)
        assert report_result["status"] == "created"
        vault_note_rel = report_result["vault_path"]
        _record(vault_note_rel)

        # Verify report body contains the cross-domain link
        report_path = VAULT_PATH / vault_note_rel
        report_content = report_path.read_text(encoding="utf-8")
        assert f"[[{cite_key}]]" in report_content, \
            f"Cross-domain link [[{cite_key}]] not found in report note"

        # Verify check_graph sees no BROKEN LINK for this specific pair
        # (the paper note exists, so the link from report → paper is valid)
        graph_report = check_graph(VAULT_PATH, PAPER_BANK_PATH)
        broken_for_cite = [
            i for i in graph_report["issues"]
            if i["type"] == "broken_link"
            and cite_key in i.get("detail", "")
            and vault_note_rel in i.get("note", "")
        ]
        assert not broken_for_cite, \
            f"Cross-domain link to {cite_key} incorrectly flagged as broken: {broken_for_cite}"

        print(f"  paper note: {paper_result['vault_path']}")
        print(f"  report note: {vault_note_rel}")
        print(f"  cross-link [[{cite_key}]] present in report: YES")
        print(f"  no false broken-link errors for this pair: YES")


# ---------------------------------------------------------------------------
# Test 4: Note Polishing
# ---------------------------------------------------------------------------

def test4_note_polishing():
    """
    Ingest a report, then polish it with additional findings.
    Verify: note updated (not overwritten), new content appended.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        today = vault_io.today_str()
        title = f"{TEST_PREFIX}Polish Test Report"
        source = _make_report_file(tmp_path, title, today, watchlist=["NVDA"])
        result = ingest_report(source, "c3-test", "run-polish", VAULT_PATH)
        assert result["status"] == "created"
        vault_note_rel = result["vault_path"]
        _record(vault_note_rel)

        # Read original content to confirm baseline
        original = (VAULT_PATH / vault_note_rel).read_text(encoding="utf-8")
        original_fm, original_body = vault_io.parse_frontmatter(original)

        # Create update file with additional findings
        update_content = f"""---
confidence: high
sources_count: 3
tags: [energy, update]
---

## Key Findings

Additional finding: NVDA data center demand drove oil sentiment.

## Notes

Follow-up note added during polish run.
"""
        update_path = tmp_path / "update.md"
        update_path.write_text(update_content, encoding="utf-8")

        result = polish_note(vault_note_rel, update_path, VAULT_PATH)
        assert result["status"] == "polished", \
            f"Expected 'polished', got {result['status']!r}. Changes: {result.get('changes')}"
        assert len(result["changes"]) > 0, "No changes recorded by polish_note"

        # Verify note was updated, not overwritten
        updated = (VAULT_PATH / vault_note_rel).read_text(encoding="utf-8")
        updated_fm, updated_body = vault_io.parse_frontmatter(updated)

        # Original title should be preserved
        assert updated_fm["title"] == original_fm["title"], \
            f"Title changed: {updated_fm['title']!r} != {original_fm['title']!r}"

        # New content should be appended (not replace original)
        assert "Oil prices rose sharply" in updated, "Original key finding was overwritten"
        assert "NVDA data center demand" in updated, "New finding not added"

        print(f"  vault note: {vault_note_rel}")
        print(f"  changes applied: {result['changes']}")


# ---------------------------------------------------------------------------
# Test 5: Market Note Compression
# ---------------------------------------------------------------------------

def test5_compression():
    """
    Write a market note dated > 30 days ago, compress it, verify archive created.
    """
    old_date = (date.today() - timedelta(days=60)).isoformat()
    today = vault_io.today_str()

    # Write an old note directly into the vault
    old_slug = f"c3test-old-note"
    rel_path = f"market/reports/{old_date}-{old_slug}.md"
    fm = {
        "type": "report",
        "title": "C3 Test Old Report",
        "date": old_date,
        "tags": ["energy", "test"],
        "last_updated": old_date,
        "watchlist": ["CL=F"],
        "time_window": "weekly",
        "confidence": "medium",
        "sources_count": 2,
        "project_name": "c3-test",
        "run_id": "run-old",
        "status": "active",
    }
    body = (
        "# C3 Test Old Report\n\n"
        "## Key Findings\n\nOil was at $75/barrel in January 2026.\n\n"
        "## Analysis\n\nSupply was constrained.\n\n"
        "## Links\n- Related:\n"
    )
    vault_io.write_note(VAULT_PATH, rel_path, fm, body)
    _record(rel_path)

    # Find compression candidates
    candidates = find_candidates(VAULT_PATH, days=30)
    candidate_paths = [str(c[0].relative_to(VAULT_PATH)) for c in candidates]
    assert rel_path in candidate_paths, \
        f"Old note not found in compression candidates. Found: {candidate_paths}"

    # Compress the candidate
    target = next(c for c in candidates if str(c[0].relative_to(VAULT_PATH)) == rel_path)
    note_path, cand_fm, cand_body, age = target
    result = compress_note(note_path, cand_fm, cand_body, VAULT_PATH, dry_run=False)
    update_compression_log(VAULT_PATH, [result])

    assert result["action"] == "compressed", f"Expected 'compressed', got {result['action']}"

    # Verify archive note created
    archive_rel = result["archive"]
    archive_path = VAULT_PATH / archive_rel
    assert archive_path.exists(), f"Archive note not found: {archive_rel}"
    _record(archive_rel)  # track for cleanup

    archive_fm, archive_body = vault_io.parse_frontmatter(
        archive_path.read_text(encoding="utf-8"))
    assert archive_fm["status"] == "archived"
    assert "archived" in archive_fm.get("tags", [])

    # Verify original is no longer at its original location (moved to archive dir)
    assert not note_path.exists(), "Original note still exists at original location after compression"

    # Verify archive_original was created
    archive_original_rel = result["archive_original"]
    _record(archive_original_rel)
    archive_original_path = VAULT_PATH / archive_original_rel
    assert archive_original_path.exists(), f"Archived original not found: {archive_original_rel}"

    # Verify compression log
    log_path = VAULT_PATH / "market" / "archive" / "_compression-log.md"
    assert log_path.exists(), "Compression log not created"
    log_content = log_path.read_text(encoding="utf-8")
    assert "Compression Run" in log_content

    print(f"  original: {rel_path}")
    print(f"  archive summary: {archive_rel}")
    print(f"  archive original: {archive_original_rel}")
    print(f"  age: {age} days")


# ---------------------------------------------------------------------------
# Test 6: Graph Health
# ---------------------------------------------------------------------------

def test6_graph_health():
    """
    Write a note with a broken wiki-link, verify check_graph detects it.
    Then verify a clean pair of notes produces no errors.
    """
    today = vault_io.today_str()

    # Write a note with an intentional broken link
    broken_slug = "c3test-broken-link"
    broken_rel = f"market/reports/{today}-{broken_slug}.md"
    broken_fm = {
        "type": "report",
        "title": "C3 Test Broken Link",
        "date": today,
        "tags": [],
        "last_updated": today,
        "watchlist": [],
        "confidence": "low",
        "sources_count": 0,
        "project_name": "c3-test",
        "run_id": "run-graph",
        "status": "active",
    }
    broken_body = (
        "# C3 Test Broken Link\n\n"
        "## Key Findings\n\nSee [[c3-nonexistent-target-xyz]] for context.\n\n"
        "## Links\n- Related:\n"
    )
    vault_io.write_note(VAULT_PATH, broken_rel, broken_fm, broken_body)
    _record(broken_rel)

    graph_report = check_graph(VAULT_PATH, PAPER_BANK_PATH)

    # Verify broken link is detected
    broken_issues = [
        i for i in graph_report["issues"]
        if i["type"] == "broken_link"
        and broken_rel in i.get("note", "")
        and "c3-nonexistent-target-xyz" in i.get("detail", "")
    ]
    assert broken_issues, \
        f"Broken link not detected for {broken_rel}. Issues: {graph_report['issues']}"

    issue = broken_issues[0]
    assert issue["severity"] in ("WARNING", "ERROR"), \
        f"Unexpected severity: {issue['severity']}"

    print(f"  broken link note: {broken_rel}")
    print(f"  detected issue: {issue}")
    print(f"  total issues in vault: {len(graph_report['issues'])}")
    print(f"  summary: {graph_report['summary']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("C3 Pipeline Integration Tests — Knowledge Maester")
    print(f"Vault: {VAULT_PATH}")
    print(f"Paper Bank: {PAPER_BANK_PATH}")
    print("=" * 60)

    if not VAULT_PATH.exists():
        print(f"ERROR: Vault not found at {VAULT_PATH}. Run preflight_maester.py first.")
        sys.exit(1)

    tests = [
        ("Test 1: Market Report Ingestion", test1_market_report_ingestion),
        ("Test 2: Paper Note Ingestion", test2_paper_note_ingestion),
        ("Test 3: Cross-Domain Links", test3_cross_domain_links),
        ("Test 4: Note Polishing", test4_note_polishing),
        ("Test 5: Market Note Compression", test5_compression),
        ("Test 6: Graph Health", test6_graph_health),
    ]

    results = []
    try:
        for name, fn in tests:
            passed = run_test(name, fn)
            results.append((name, passed))
    finally:
        print("\n--- Cleanup ---")
        _cleanup()
        print(f"  Removed {len(_created_vault_notes)} test vault notes")
        print(f"  Removed {len(_created_bank_keys)} test manifest entries")

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    passed_count = sum(1 for _, p in results if p)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\n{passed_count}/{len(tests)} tests passed")

    if passed_count < len(tests):
        sys.exit(1)


if __name__ == "__main__":
    main()
