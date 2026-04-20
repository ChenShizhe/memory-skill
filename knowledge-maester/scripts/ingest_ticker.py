#!/usr/bin/env python3
"""
ingest_ticker.py — Ingest a specialist-produced ticker profile into the Citadel vault.

Ticker profiles use a two-layer structure:
  - Static `## Fundamentals` section (business description, segments, customers,
    geography, management, competitors)
  - Append-only `## Thesis updates` section, with dated three-layer blocks
    (YAML brief + low-level evidence block + high-level thesis-update block)

Modes:
  --mode create         Create a new full profile from a markdown source that
                        contains the full two-layer structure. Preserves the
                        AUTO-GENERATED Appearances section from an existing
                        note when --overwrite is used.
  --mode append-thesis  Append a new dated thesis block to an existing
                        profile's `## Thesis updates` section. Validates that
                        the block carries the required three-layer structure.

Maps: subagent-outputs/<slug>.md (specialist brief)
   -> citadel/market/tickers/<SYMBOL>.md

Usage:
  python3 knowledge-maester/scripts/ingest_ticker.py \\
    --mode create --source PATH_TO_PROFILE_MD --ticker SYMBOL \\
    [--vault-path PATH] [--overwrite]

  python3 knowledge-maester/scripts/ingest_ticker.py \\
    --mode append-thesis --source PATH_TO_THESIS_BLOCK_MD --ticker SYMBOL \\
    [--vault-path PATH]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io


THESIS_BLOCK_HEADER_RE = re.compile(r"^###\s+\d{4}-\d{2}-\d{2}\s+—", re.MULTILINE)
LOW_LEVEL_HEADER_RE = re.compile(r"^####\s+Low-level block", re.MULTILINE)
HIGH_LEVEL_HEADER_RE = re.compile(r"^####\s+High-level block", re.MULTILINE)
YAML_FENCE_RE = re.compile(r"^```yaml\s*$", re.MULTILINE)


def _validate_thesis_block(block_text: str) -> None:
    """Raise ValueError if a thesis block is missing any required layer."""
    if not THESIS_BLOCK_HEADER_RE.search(block_text):
        raise ValueError(
            "Thesis block missing dated heading (expected `### YYYY-MM-DD — <trigger>`)"
        )
    if not YAML_FENCE_RE.search(block_text):
        raise ValueError("Thesis block missing YAML brief (expected a ```yaml code fence)")
    if not LOW_LEVEL_HEADER_RE.search(block_text):
        raise ValueError(
            "Thesis block missing `#### Low-level block` section — required by the "
            "three-layer spec"
        )
    if not HIGH_LEVEL_HEADER_RE.search(block_text):
        raise ValueError(
            "Thesis block missing `#### High-level block` section — required by the "
            "three-layer spec"
        )


def _validate_profile_body(body: str) -> None:
    """Raise ValueError if a full profile body is missing required sections."""
    if not re.search(r"^##\s+Fundamentals\s*$", body, re.MULTILINE):
        raise ValueError("Profile missing `## Fundamentals` section")
    if not re.search(r"^##\s+Thesis updates\s*$", body, re.MULTILINE):
        raise ValueError("Profile missing `## Thesis updates` section")
    # Validate at least one thesis block exists and follows the three-layer spec
    thesis_match = re.search(
        r"^##\s+Thesis updates\s*$(.*?)(?=^##\s+|<!-- AUTO-GENERATED -->|\Z)",
        body, re.MULTILINE | re.DOTALL
    )
    if thesis_match:
        thesis_section = thesis_match.group(1)
        if THESIS_BLOCK_HEADER_RE.search(thesis_section):
            _validate_thesis_block(thesis_section)


def _extract_appearances_section(content: str) -> str:
    """Extract the AUTO-GENERATED Appearances block from an existing profile."""
    match = re.search(
        r"<!-- AUTO-GENERATED -->.*?<!-- /AUTO-GENERATED -->",
        content, re.DOTALL
    )
    return match.group(0) if match else ""


def ingest_ticker_create(
    source_path: Path,
    ticker: str,
    vault_path: Path,
    overwrite: bool = False,
) -> dict:
    """
    Create a new ticker profile from a specialist-produced source file.
    Returns result dict with keys: vault_path, status.
    """
    ticker = ticker.upper()
    today = vault_io.today_str()
    rel_path = f"market/tickers/{ticker}.md"
    abs_path = vault_path / rel_path

    content = source_path.read_text(encoding="utf-8")
    fm, body = vault_io.parse_frontmatter(content)

    # Validate frontmatter
    symbol_in_fm = str(fm.get("symbol", "")).upper()
    if symbol_in_fm and symbol_in_fm != ticker:
        raise ValueError(
            f"Source frontmatter symbol '{symbol_in_fm}' does not match "
            f"--ticker '{ticker}'"
        )

    # Validate body structure
    _validate_profile_body(body)

    # Idempotency / overwrite logic
    existing_appearances = ""
    if abs_path.exists():
        if not overwrite:
            existing_fm, _ = vault_io.read_note(vault_path, rel_path)
            existing_updated = existing_fm.get("last_updated", "")
            if existing_updated >= today:
                print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
                return {"vault_path": rel_path, "status": "skipped"}
        existing_appearances = _extract_appearances_section(
            abs_path.read_text(encoding="utf-8")
        )

    # Normalize frontmatter
    vault_fm = dict(fm)
    vault_fm["type"] = "ticker"
    vault_fm["symbol"] = ticker
    if not vault_fm.get("title"):
        vault_fm["title"] = vault_fm.get("name", ticker)
    if not vault_fm.get("date"):
        vault_fm["date"] = today
    vault_fm["last_updated"] = today
    if "status" not in vault_fm:
        vault_fm["status"] = "active"
    if "tags" not in vault_fm:
        vault_fm["tags"] = []

    # Compose body: append existing AUTO-GENERATED Appearances if present and not
    # already in source body
    body_out = body.rstrip()
    if existing_appearances and "<!-- AUTO-GENERATED -->" not in body_out:
        body_out = body_out + "\n\n" + existing_appearances + "\n"
    elif "<!-- AUTO-GENERATED -->" not in body_out:
        # Add an empty Appearances scaffold so ingest_report.py can populate it
        body_out = (
            body_out
            + "\n\n<!-- AUTO-GENERATED -->\n## Appearances\n\n<!-- /AUTO-GENERATED -->\n"
        )

    vault_io.write_note(vault_path, rel_path, vault_fm, body_out)
    print(f"WRITTEN: {rel_path}")
    return {"vault_path": rel_path, "status": "created"}


def ingest_ticker_append_thesis(
    source_path: Path,
    ticker: str,
    vault_path: Path,
) -> dict:
    """
    Append a new dated thesis block to an existing ticker profile.
    Returns result dict with keys: vault_path, status.
    """
    ticker = ticker.upper()
    rel_path = f"market/tickers/{ticker}.md"
    abs_path = vault_path / rel_path

    if not abs_path.exists():
        raise FileNotFoundError(
            f"Profile not found: {abs_path}. Run --mode create first."
        )

    # Read source thesis block (frontmatter optional; body contains the block)
    source_content = source_path.read_text(encoding="utf-8")
    _, block_text = vault_io.parse_frontmatter(source_content)
    block_text = block_text.strip()

    _validate_thesis_block(block_text)

    # Read existing profile
    existing_content = abs_path.read_text(encoding="utf-8")
    existing_fm, existing_body = vault_io.parse_frontmatter(existing_content)

    # Locate `## Thesis updates` section end (next `##` heading or AUTO-GENERATED)
    thesis_header_match = re.search(
        r"^##\s+Thesis updates\s*$", existing_body, re.MULTILINE
    )
    if not thesis_header_match:
        raise ValueError(
            f"Profile missing `## Thesis updates` section: {abs_path}"
        )

    section_start = thesis_header_match.end()
    # Find next `## heading` or AUTO-GENERATED marker after the thesis section
    next_marker = re.search(
        r"(^##\s+|<!--\s*AUTO-GENERATED\s*-->)",
        existing_body[section_start:],
        re.MULTILINE,
    )
    if next_marker:
        insert_pos = section_start + next_marker.start()
        new_body = (
            existing_body[:insert_pos].rstrip()
            + "\n\n"
            + block_text
            + "\n\n"
            + existing_body[insert_pos:]
        )
    else:
        new_body = existing_body.rstrip() + "\n\n" + block_text + "\n"

    # Bump last_updated
    today = vault_io.today_str()
    existing_fm["last_updated"] = today

    vault_io.write_note(vault_path, rel_path, existing_fm, new_body)
    print(f"APPENDED: {rel_path}")
    return {"vault_path": rel_path, "status": "appended"}


def main():
    parser = argparse.ArgumentParser(
        description="Ingest a ticker profile or thesis-update block into the Citadel vault"
    )
    parser.add_argument("--mode", required=True, choices=["create", "append-thesis"])
    parser.add_argument("--source", required=True, help="Path to source markdown")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., GEV)")
    parser.add_argument("--vault-path", default=str(vault_io.DEFAULT_VAULT_PATH))
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="For --mode create: overwrite existing profile while preserving the "
        "AUTO-GENERATED Appearances section.",
    )
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    vault_path = Path(args.vault_path).expanduser()

    if not source_path.exists():
        print(f"ERROR: Source file not found: {source_path}")
        sys.exit(1)
    if not vault_path.exists():
        print(f"ERROR: Vault not found at {vault_path}. Run preflight_maester.py first.")
        sys.exit(1)

    try:
        if args.mode == "create":
            result = ingest_ticker_create(
                source_path, args.ticker, vault_path, overwrite=args.overwrite
            )
        elif args.mode == "append-thesis":
            result = ingest_ticker_append_thesis(source_path, args.ticker, vault_path)
        else:
            parser.error(f"Unknown mode: {args.mode}")
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"DONE: status={result['status']}")


if __name__ == "__main__":
    main()
