#!/usr/bin/env python3
"""
ingest_analysis.py — Ingest a market-thinker analysis into the vault.

Maps: <workspace>/analysis.md → citadel/market/analysis/YYYY-MM-DD-<slug>.md

Usage:
  python3 knowledge-maester/scripts/ingest_analysis.py \\
    --source PATH_TO_ANALYSIS_MD \\
    [--vault-path PATH]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io


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


def ingest_analysis(source_path: Path, vault_path: Path) -> dict:
    content = source_path.read_text(encoding="utf-8")
    fm, body = vault_io.parse_frontmatter(content)
    today = vault_io.today_str()

    title = fm.get("title", "") or _extract_h1(body) or source_path.stem
    confidence = fm.get("confidence", "medium")
    tags = fm.get("tags", [])
    related_tickers = fm.get("related_tickers", [])
    if isinstance(related_tickers, str):
        related_tickers = [t.strip() for t in related_tickers.split(",") if t.strip()]
    related_reports = fm.get("related_reports", [])
    if isinstance(related_reports, str):
        related_reports = [r.strip() for r in related_reports.split(",") if r.strip()]

    # Extract additional tickers from body
    body_tickers = vault_io.extract_tickers(body)
    all_tickers = list(dict.fromkeys(related_tickers + body_tickers))

    analysis_date = fm.get("date") or today
    slug = vault_io.slugify(title)
    rel_path = f"market/analysis/{analysis_date}-{slug}.md"

    # Idempotency
    if vault_io.note_exists(vault_path, rel_path):
        existing_fm, _ = vault_io.read_note(vault_path, rel_path)
        if existing_fm.get("last_updated", "") >= today:
            print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
            return {"vault_path": rel_path, "stubs_created": [], "status": "skipped"}

    # Extract sections
    context = _extract_section(body, "Context") or _extract_section(body, "Background") or ""
    analysis_body = _extract_section(body, "Analysis") or ""
    reasoning_chain = _extract_section(body, "Reasoning Chain") or _extract_section(body, "Reasoning") or ""
    predictions = _extract_section(body, "Predictions") or _extract_section(body, "Forecast") or ""
    conclusion = _extract_section(body, "Conclusion") or ""
    sources_section = _extract_section(body, "Sources") or ""

    vault_fm = {
        "type": "analysis",
        "title": title,
        "date": analysis_date,
        "tags": tags,
        "last_updated": today,
        "related_tickers": all_tickers,
        "related_reports": related_reports,
        "confidence": confidence,
        "status": "draft",
    }

    # Wiki-links for tickers and related reports
    ticker_links = " ".join(f"[[{t}]]" for t in all_tickers) if all_tickers else ""
    report_links = " ".join(f"[[{r}]]" for r in related_reports) if related_reports else ""

    body_parts = [f"# {title}\n"]

    if context:
        body_parts.extend(["## Context\n", context, "\n"])

    if analysis_body:
        body_parts.extend(["## Analysis\n", analysis_body, "\n"])

    body_parts.append("## Reasoning Chain\n")
    body_parts.append("<!-- AUTO-GENERATED -->")
    if reasoning_chain:
        body_parts.append(reasoning_chain)
    body_parts.append("<!-- /AUTO-GENERATED -->")
    body_parts.append("\n")

    if predictions:
        body_parts.extend(["## Predictions\n", predictions, "\n"])
    else:
        body_parts.append("## Predictions\n\n")

    if conclusion:
        body_parts.extend(["## Conclusion\n", conclusion, "\n"])

    if sources_section:
        body_parts.extend(["## Sources\n", sources_section, "\n"])

    body_parts.append("## Links\n")
    if ticker_links:
        body_parts.append(f"- Tickers: {ticker_links}")
    if report_links:
        body_parts.append(f"- Reports: {report_links}")
    body_parts.append("- Related:")

    vault_body = "\n".join(body_parts)
    vault_io.write_note(vault_path, rel_path, vault_fm, vault_body)
    print(f"WRITTEN: {rel_path}")

    # Create ticker stubs
    stubs_created = []
    for symbol in all_tickers:
        _, created = vault_io.ensure_ticker_stub(vault_path, symbol)
        if created:
            stubs_created.append(f"market/tickers/{symbol}.md")
            print(f"STUB_CREATED: market/tickers/{symbol}.md")

    # Add backlinks in referenced report notes
    for report_ref in related_reports:
        report_note = vault_io.find_note_by_stem(vault_path, report_ref)
        if report_note:
            report_content = report_note.read_text(encoding="utf-8")
            analysis_link = f"- Analysis: [[{analysis_date}-{slug}]]"
            if analysis_link not in report_content:
                if "## Links" in report_content:
                    report_content = report_content.replace("## Links\n", f"## Links\n{analysis_link}\n", 1)
                    report_note.write_text(report_content, encoding="utf-8")

    return {"vault_path": rel_path, "stubs_created": stubs_created, "status": "created"}


def _extract_h1(body: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else ""


def main():
    parser = argparse.ArgumentParser(description="Ingest a market-thinker analysis into vault")
    parser.add_argument("--source", required=True, help="Path to analysis markdown file")
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

    result = ingest_analysis(source_path, vault_path)
    print(f"DONE: status={result['status']}, stubs={len(result['stubs_created'])}")


if __name__ == "__main__":
    main()
