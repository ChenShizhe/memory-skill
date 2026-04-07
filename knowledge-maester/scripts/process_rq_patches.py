#!/usr/bin/env python3
"""
Merge rq-patch files into the main reference-queue.md.

Usage:
    python3 process_rq_patches.py [--dry-run] [--help]

Options:
    --dry-run   Parse and report without writing changes or deleting patches.
    --help      Show this help message and exit.

Columns are mapped by header name, so rows with extra columns (authors, venue,
url) in manually added full-schema entries are tolerated correctly.
"""
import argparse
import os
import re
import tempfile
from datetime import datetime

# Configuration
RQ_PATH = os.path.expanduser("~/Documents/citadel/literature/reference-queue.md")
PATCHES_DIR = os.path.expanduser("~/Documents/paper-bank/rq-patches/")
ISSUES_LOG = os.path.join(
    tempfile.gettempdir(),
    f"knowledge-maester-merge-{datetime.now().strftime('%Y-%m-%d')}-issues.md",
)


def log_issue(message):
    timestamp = datetime.now().isoformat()
    with open(ISSUES_LOG, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def parse_markdown_table(content):
    """Parse a markdown table from *content*.

    Column values are mapped to header names by position.  Rows with more
    columns than the header silently drop the extra cells.  Rows with fewer
    columns fill missing positions with an empty string.  A row is only
    flagged malformed (and skipped) when the required fields ``cite_key`` and
    ``title`` are both absent after the header-based mapping.
    """
    lines = [line.strip() for line in content.split("\n") if line.strip() and line.startswith("|")]
    if len(lines) < 2:
        return [], []

    # Read header row to learn column names and their positions
    headers = [h.strip() for h in lines[0].split("|") if h.strip()]

    rows = []
    for line in lines[2:]:  # skip header row (index 0) and separator row (index 1)
        cells = [c.strip() for c in line.split("|") if c.strip()]

        # Map values by header position; extra columns are dropped,
        # missing columns default to "".
        row = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}

        # A row is malformed only when required fields are absent
        if not row.get("cite_key") and not row.get("title"):
            log_issue(f"Skipping malformed row (missing cite_key and title): {line}")
            continue

        rows.append(row)

    return headers, rows


def write_markdown_table(path, headers, rows):
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---" for _ in headers]) + "|")
    for row in rows:
        cells = [row.get(h, "") for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def extract_year_from_cite_key(cite_key):
    match = re.search(r"\d{4}", cite_key)
    return match.group() if match else ""


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing changes or deleting patches.",
    )
    args = parser.parse_args()

    # Initialize issues log
    os.makedirs(os.path.dirname(ISSUES_LOG), exist_ok=True)
    with open(ISSUES_LOG, "w") as f:
        f.write(f"# Knowledge Maester Merge Test Run Issues - {datetime.now().strftime('%Y-%m-%d')}\n\n")

    # Read existing reference queue
    if not os.path.exists(RQ_PATH):
        log_issue("Critical: reference-queue.md missing after pre-flight")
        return 1

    with open(RQ_PATH, "r") as f:
        rq_content = f.read()
    rq_headers, rq_rows = parse_markdown_table(rq_content)
    rq_by_cite = {row["cite_key"]: row for row in rq_rows}
    print(f"Loaded {len(rq_by_cite)} existing entries from reference queue")

    # Process all patch files
    patch_files = [f for f in os.listdir(PATCHES_DIR) if f.endswith("-rq-patch.md")]
    if not patch_files:
        log_issue("No patch files found in rq-patches directory")
        return 0

    processed_patches = []
    added = 0
    updated = 0
    skipped = 0

    for patch_file in patch_files:
        patch_path = os.path.join(PATCHES_DIR, patch_file)
        try:
            with open(patch_path, "r") as f:
                patch_content = f.read()
            patch_headers, patch_rows = parse_markdown_table(patch_content)
            print(f"Processing {patch_file}: {len(patch_rows)} entries")

            for entry in patch_rows:
                status = entry.get("status", "")
                if status == "read":
                    skipped += 1
                    continue
                cite_key = entry.get("cite_key", "")
                if not cite_key:
                    log_issue(f"Skipping entry in {patch_file} with no cite_key")
                    skipped += 1
                    continue

                if cite_key not in rq_by_cite:
                    # Add new entry — honour any extra fields present in the patch row
                    year = entry.get("year", "") or extract_year_from_cite_key(cite_key)
                    new_row = {
                        "id": entry.get("arxiv_id", entry.get("id", "unknown")),
                        "cite_key": cite_key,
                        "title": entry.get("title", ""),
                        "authors": entry.get("authors", ""),
                        "year": year,
                        "venue": entry.get("venue", ""),
                        "url": entry.get("url", ""),
                        "importance_score": entry.get("importance_score", "1"),
                        "sessions_cited": entry.get("sessions_cited", "1"),
                        "status": status,
                        "added_at": entry.get("first_seen", datetime.now().strftime("%Y-%m-%d")),
                        "last_cited_at": entry.get("first_seen", datetime.now().strftime("%Y-%m-%d")),
                    }
                    rq_by_cite[cite_key] = new_row
                    added += 1
                else:
                    # Update existing entry
                    existing = rq_by_cite[cite_key]
                    try:
                        existing["importance_score"] = str(
                            int(existing.get("importance_score", "0"))
                            + int(entry.get("importance_score", "1"))
                        )
                        existing["sessions_cited"] = str(
                            int(existing.get("sessions_cited", "0"))
                            + int(entry.get("sessions_cited", "1"))
                        )
                        existing["last_cited_at"] = entry.get(
                            "first_seen", existing.get("last_cited_at", datetime.now().strftime("%Y-%m-%d"))
                        )
                        updated += 1
                    except ValueError as e:
                        log_issue(f"Failed to update {cite_key} from {patch_file}: invalid number: {e}")
                        skipped += 1
            processed_patches.append(patch_path)
        except Exception as e:
            log_issue(f"Failed to process patch {patch_file}: {str(e)}")
            continue

    if args.dry_run:
        print(
            f"Dry run complete: {len(rq_by_cite)} total entries, "
            f"{added} to add, {updated} to update, {skipped} skipped"
        )
        return 0

    # Write updated reference queue
    updated_rows = list(rq_by_cite.values())
    write_markdown_table(RQ_PATH, rq_headers, updated_rows)
    print(
        f"Write complete: {len(updated_rows)} total entries, "
        f"{added} added, {updated} updated, {skipped} skipped"
    )

    # Delete processed patch files
    for patch_path in processed_patches:
        try:
            os.unlink(patch_path)
            print(f"Deleted processed patch: {patch_path}")
        except Exception as e:
            log_issue(f"Failed to delete patch {patch_path}: {str(e)}")

    # Final log
    log_issue(
        f"Merge complete: {len(updated_rows)} total entries, "
        f"{added} added, {updated} updated, {skipped} skipped, "
        f"{len(processed_patches)} patches processed and deleted"
    )
    return 0


if __name__ == "__main__":
    exit(main())
