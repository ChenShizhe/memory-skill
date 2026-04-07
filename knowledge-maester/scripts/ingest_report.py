#!/usr/bin/env python3
"""
ingest_report.py — Ingest a market-watcher final report into the Citadel vault.

Maps: projects/<name>/market-watcher/<run-id>/final-report.md
   → citadel/market/reports/YYYY-MM-DD-<slug>.md

Usage:
  python3 knowledge-maester/scripts/ingest_report.py \\
    --source PATH_TO_REPORT_MD \\
    --project-name NAME \\
    --run-id RUN_ID \\
    [--vault-path PATH]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io


def _extract_section(body: str, heading: str) -> str:
    """Extract content under a markdown heading (## or ###)."""
    pattern = re.compile(
        r"^#{1,3}\s+" + re.escape(heading) + r"\s*$",
        re.MULTILINE | re.IGNORECASE
    )
    m = pattern.search(body)
    if not m:
        return ""
    start = m.end()
    # Find next heading of same or higher level
    next_heading = re.search(r"^#{1,2}\s+", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


def _count_source_index_rows(body: str) -> int:
    """Count rows in a markdown Source Index table."""
    section = _extract_section(body, "Source Index")
    if not section:
        return 0
    rows = [l for l in section.splitlines() if l.strip().startswith("|") and "---" not in l]
    # Subtract header row
    return max(0, len(rows) - 1)


def ingest_report(
    source_path: Path,
    project_name: str,
    run_id: str,
    vault_path: Path,
) -> dict:
    """
    Ingest a report. Returns a result dict with keys:
      - vault_path (str): relative path of written note
      - stubs_created (list[str])
      - status (str): 'created' | 'skipped'
    """
    content = source_path.read_text(encoding="utf-8")
    fm, body = vault_io.parse_frontmatter(content)

    today = vault_io.today_str()

    # --- Derive title ---
    title = fm.get("title", "")
    if not title:
        h1 = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = h1.group(1).strip() if h1 else source_path.stem

    # --- Derive date from source or today ---
    report_date = fm.get("date") or fm.get("report_date") or today

    # --- Build slug and vault path ---
    slug = vault_io.slugify(title)
    rel_path = f"market/reports/{report_date}-{slug}.md"

    # --- Idempotency check ---
    abs_path = vault_path / rel_path
    if abs_path.exists():
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        existing_updated = existing_fm.get("last_updated", "")
        if existing_updated >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"vault_path": rel_path, "stubs_created": [], "status": "skipped"}

    # --- Extract tickers ---
    tickers = vault_io.extract_tickers(body)
    # Also use watchlist from source frontmatter if present
    source_watchlist = fm.get("watchlist", [])
    if isinstance(source_watchlist, str):
        source_watchlist = [w.strip() for w in source_watchlist.split(",") if w.strip()]
    all_tickers = list(dict.fromkeys(source_watchlist + tickers))  # preserve order, dedupe

    # --- Extract sections ---
    exec_summary = _extract_section(body, "Executive Summary")
    main_developments = _extract_section(body, "Main Developments")
    market_dashboard = _extract_section(body, "Market Dashboard")
    if not market_dashboard:
        market_dashboard = _extract_section(body, "Market Dashboard & Tracking")
    risks = _extract_section(body, "Risks and Counterarguments")
    if not risks:
        risks = _extract_section(body, "Risks")
    source_index_section = _extract_section(body, "Source Index")
    sources_count = _count_source_index_rows(body)

    confidence = fm.get("confidence", "medium")
    time_window = fm.get("time_window", "")

    # --- Build frontmatter ---
    vault_fm = {
        "type": "report",
        "title": title,
        "date": report_date,
        "tags": fm.get("tags", []),
        "last_updated": today,
        "watchlist": all_tickers,
        "time_window": time_window,
        "confidence": confidence,
        "sources_count": sources_count,
        "project_name": project_name,
        "run_id": run_id,
        "status": "active",
    }

    # --- Build body ---
    # Generate wiki-links for tickers mentioned in body
    wiki_links_str = " ".join(f"[[{t}]]" for t in all_tickers) if all_tickers else ""

    body_parts = [f"# {title}\n"]

    body_parts.append("## Key Findings\n")
    body_parts.append(exec_summary or "*No executive summary found in source.*")
    body_parts.append("\n")

    body_parts.append("## Analysis\n")
    body_parts.append(main_developments or "*No main developments section found in source.*")
    body_parts.append("\n")

    if market_dashboard:
        body_parts.append("## Market Dashboard\n")
        body_parts.append(market_dashboard)
        body_parts.append("\n")

    if risks:
        body_parts.append("## Risks and Counterarguments\n")
        body_parts.append(risks)
        body_parts.append("\n")

    body_parts.append("## Source Index\n")
    if source_index_section:
        # Strip URL column from source index if present (markdown table column with URLs)
        body_parts.append(_strip_url_column(source_index_section))
    else:
        body_parts.append("| ID | Source | Date | Type |\n|---|---|---|---|")
    body_parts.append("\n")

    body_parts.append("## Links\n")
    if wiki_links_str:
        body_parts.append(f"- Tickers: {wiki_links_str}")
    body_parts.append("- Related:")

    vault_body = "\n".join(body_parts)

    # --- Write vault note ---
    vault_io.write_note(vault_path, rel_path, vault_fm, vault_body)
    print(f"WRITTEN: {rel_path}")

    # --- Create ticker stubs and add backlinks ---
    stubs_created = []
    for symbol in all_tickers:
        _, created = vault_io.ensure_ticker_stub(vault_path, symbol)
        if created:
            stubs_created.append(f"market/tickers/{symbol}.md")
            print(f"STUB_CREATED: market/tickers/{symbol}.md")
        vault_io.add_ticker_appearance(vault_path, symbol, f"{report_date}-{slug}")

    return {
        "vault_path": rel_path,
        "stubs_created": stubs_created,
        "status": "created",
    }


def _strip_url_column(table_text: str) -> str:
    """Remove a URL column from a markdown table if present."""
    lines = table_text.splitlines()
    result = []
    url_col_idx = None
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            result.append(line)
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if i == 0:
            # Find URL column
            for idx, cell in enumerate(cells):
                if cell.lower() in ("url", "link", "source url"):
                    url_col_idx = idx
                    break
        if url_col_idx is not None:
            cells.pop(url_col_idx)
        result.append("| " + " | ".join(cells) + " |")
    return "\n".join(result)


def main():
    parser = argparse.ArgumentParser(description="Ingest a market-watcher report into vault")
    parser.add_argument("--source", required=True, help="Path to final-report.md")
    parser.add_argument("--project-name", required=True, help="Source project name")
    parser.add_argument("--run-id", required=True, help="Source run ID")
    parser.add_argument("--vault-path", default=str(vault_io.DEFAULT_VAULT_PATH))
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    vault_path = Path(args.vault_path).expanduser()

    if not source_path.exists():
        print(f"ERROR: Source file not found: {source_path}")
        sys.exit(1)
    if not vault_path.exists():
        print(f"ERROR: Vault not found at {vault_path}. Run preflight_maester.py first.")
        sys.exit(1)

    result = ingest_report(source_path, args.project_name, args.run_id, vault_path)
    print(f"DONE: status={result['status']}, stubs={len(result['stubs_created'])}")


if __name__ == "__main__":
    main()
