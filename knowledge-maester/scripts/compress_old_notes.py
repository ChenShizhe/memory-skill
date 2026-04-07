#!/usr/bin/env python3
"""
compress_old_notes.py — Summarize aged market notes and move to archive.

Only compresses market/reports/ and market/analysis/ notes older than --days.
Never compresses literature/ notes.

Usage:
  python3 knowledge-maester/scripts/compress_old_notes.py \\
    [--days 30] \\
    [--dry-run] \\
    [--vault-path PATH]
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io

COMPRESSIBLE_DIRS = ["market/reports", "market/analysis"]


def find_candidates(vault_path: Path, days: int) -> list[tuple[Path, dict, str]]:
    """
    Return list of (note_path, frontmatter, body) tuples for notes eligible for compression.
    """
    today = date.today()
    candidates = []

    for rel_dir in COMPRESSIBLE_DIRS:
        dir_path = vault_path / rel_dir
        if not dir_path.exists():
            continue
        for md_file in dir_path.glob("*.md"):
            if md_file.stem.startswith("_"):
                continue
            content = md_file.read_text(encoding="utf-8", errors="replace")
            fm, body = vault_io.parse_frontmatter(content)

            status = fm.get("status", "active")
            if status == "archived":
                continue

            last_updated_str = fm.get("last_updated") or fm.get("date", "")
            last_updated = vault_io.parse_iso_date(last_updated_str)
            if not last_updated:
                continue

            age_days = (today - last_updated).days
            if age_days >= days:
                candidates.append((md_file, fm, body, age_days))

    return candidates


def _extract_durable_content(fm: dict, body: str) -> str:
    """Extract durable lessons, key findings, and data points from a note."""
    sections = []

    for heading in ("Key Findings", "Analysis", "Predictions", "Confirmed Predictions",
                    "Conclusion", "Durable Findings"):
        section = _extract_section(body, heading)
        if section:
            sections.append(f"### {heading}\n\n{section}")

    # Extract any explicit data points (numbers, %, prices)
    data_lines = []
    for line in body.splitlines():
        if re.search(r"\b\d+\.?\d*[%$¥€]\b|\$\d+|\b\d{1,3},\d{3}\b", line):
            clean = line.strip().lstrip("-").strip()
            if clean and len(clean) > 10:
                data_lines.append(f"- {clean}")
    if data_lines[:10]:
        sections.append("### Historical Data Points\n\n" + "\n".join(data_lines[:10]))

    return "\n\n".join(sections) if sections else "*No durable content extracted.*"


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


def compress_note(note_path: Path, fm: dict, body: str, vault_path: Path, dry_run: bool) -> dict:
    """
    Create archive copy, update original status, return result dict.
    """
    today_str = vault_io.today_str()
    original_slug = note_path.stem
    archive_slug = f"{original_slug}-archive"
    original_rel = str(note_path.relative_to(vault_path))
    archive_rel = f"market/archive/{archive_slug}.md"

    original_title = fm.get("title", original_slug)
    original_date = fm.get("date", "")
    time_window = fm.get("time_window", "")
    tags = fm.get("tags", [])
    if isinstance(tags, list):
        archive_tags = tags + ["archived"]
    else:
        archive_tags = [tags, "archived"]

    durable_content = _extract_durable_content(fm, body)

    # Build archive frontmatter
    archive_fm = {
        "type": fm.get("type", "report"),
        "title": f"[Archive] {original_title}",
        "date": original_date,
        "tags": archive_tags,
        "last_updated": today_str,
        "watchlist": fm.get("watchlist", []),
        "archived_from": original_rel,
        "archive_date": today_str,
        "status": "archived",
    }
    if fm.get("confidence"):
        archive_fm["confidence"] = fm["confidence"]
    if fm.get("sources_count"):
        archive_fm["sources_count"] = fm["sources_count"]

    # Build archive body
    time_note = f"Original covered {time_window}." if time_window else ""
    archive_body = f"""# [Archive] {original_title}

*Archived from [[{original_slug}]] on {today_str}. {time_note}*

{durable_content}

## Links
- Original: [[{original_slug}]]
- Related:
"""

    if dry_run:
        return {
            "action": "would_compress",
            "original": original_rel,
            "archive": archive_rel,
            "durable_content_chars": len(durable_content),
        }

    # Write archive copy
    vault_io.write_note(vault_path, archive_rel, archive_fm, archive_body)
    print(f"ARCHIVE_WRITTEN: {archive_rel}")

    # Update original: set status=archived, move to archive dir
    updated_fm = dict(fm)
    updated_fm["status"] = "archived"
    updated_fm["last_updated"] = today_str

    archive_original_rel = f"market/archive/{original_slug}.md"
    vault_io.write_note(vault_path, archive_original_rel, updated_fm, body)
    print(f"ORIGINAL_MOVED: {original_rel} -> {archive_original_rel}")

    # Delete original from its current location
    note_path.unlink()

    # Update ticker backlinks
    watchlist = fm.get("watchlist", [])
    if isinstance(watchlist, str):
        watchlist = [w.strip() for w in watchlist.split(",") if w.strip()]
    for symbol in watchlist:
        ticker_path = vault_path / f"market/tickers/{symbol}.md"
        if ticker_path.exists():
            content = ticker_path.read_text(encoding="utf-8")
            # Replace old link with archive link
            content = content.replace(f"[[{original_slug}]]", f"[[{original_slug}]] → [[{archive_slug}]]")
            ticker_path.write_text(content, encoding="utf-8")

    return {
        "action": "compressed",
        "original": original_rel,
        "archive": archive_rel,
        "archive_original": archive_original_rel,
    }


def update_compression_log(vault_path: Path, results: list[dict]) -> None:
    """Append entry to market/archive/_compression-log.md."""
    log_path = vault_path / "market" / "archive" / "_compression-log.md"
    today_str = vault_io.today_str()

    compressed = [r for r in results if r.get("action") == "compressed"]
    entry_lines = [
        f"\n## {today_str} Compression Run",
        f"- Compressed: {len(compressed)} notes",
        "- Notes:",
    ]
    for r in compressed:
        entry_lines.append(f"  - {r['original']} → {r['archive']}")

    entry = "\n".join(entry_lines) + "\n"

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        log_path.write_text(existing + entry, encoding="utf-8")
    else:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"# Compression Log\n{entry}", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compress aged market notes to archive")
    parser.add_argument("--days", type=int, default=30, help="Age threshold in days (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying files")
    parser.add_argument("--vault-path", default=str(vault_io.DEFAULT_VAULT_PATH))
    args = parser.parse_args()

    vault_path = Path(args.vault_path).expanduser()
    if not vault_path.exists():
        print(f"ERROR: Vault not found at {vault_path}")
        sys.exit(1)

    candidates = find_candidates(vault_path, args.days)

    if not candidates:
        print(f"No notes older than {args.days} days found. Nothing to compress.")
        sys.exit(0)

    print(f"Found {len(candidates)} compression candidate(s) (threshold: {args.days} days):")
    for note_path, fm, body, age in candidates:
        print(f"  [{age}d] {note_path.relative_to(vault_path)} — {fm.get('title', '?')}")

    if args.dry_run:
        print("\n[DRY RUN] No files modified.")
        results = []
        for note_path, fm, body, age in candidates:
            r = compress_note(note_path, fm, body, vault_path, dry_run=True)
            results.append(r)
        for r in results:
            print(f"  WOULD_COMPRESS: {r['original']} → {r['archive']}")
        sys.exit(0)

    results = []
    for note_path, fm, body, age in candidates:
        r = compress_note(note_path, fm, body, vault_path, dry_run=False)
        results.append(r)

    update_compression_log(vault_path, results)
    compressed = sum(1 for r in results if r.get("action") == "compressed")
    print(f"\nDONE: {compressed} note(s) compressed.")


if __name__ == "__main__":
    main()
