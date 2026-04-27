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
                        profile's `## Thesis updates` section. Accepts two
                        input shapes:
                          (a) hand-drafted three-layer thesis-block markdown
                              (the original specialist-brief input)
                          (b) paper-reader 10-K-mode summary, detected via
                              frontmatter `mode: 10k`. The script synthesizes
                              a thesis block from the 14-section summary and
                              its companion claims sidecar, then appends.

Maps: subagent-outputs/<slug>.md (specialist brief)            -> citadel/market/tickers/<SYMBOL>.md
   or paper-reader/papers/<cite_key>.md (10-K-mode summary)    -> citadel/market/tickers/<SYMBOL>.md

Usage:
  python3 knowledge-maester/scripts/ingest_ticker.py \\
    --mode create --source PATH_TO_PROFILE_MD --ticker SYMBOL \\
    [--vault-path PATH] [--overwrite]

  python3 knowledge-maester/scripts/ingest_ticker.py \\
    --mode append-thesis --source PATH_TO_THESIS_BLOCK_MD --ticker SYMBOL \\
    [--vault-path PATH] [--source-vault-root PATH] \\
    [--seed-predictions] [--seed-credibility]
"""
import argparse
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import vault_io


THESIS_BLOCK_HEADER_RE = re.compile(r"^###\s+\d{4}-\d{2}-\d{2}\s+—", re.MULTILINE)
LOW_LEVEL_HEADER_RE = re.compile(r"^####\s+Low-level block", re.MULTILINE)
HIGH_LEVEL_HEADER_RE = re.compile(r"^####\s+High-level block", re.MULTILINE)
YAML_FENCE_RE = re.compile(r"^```yaml\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# 10-K-mode input support (proposal 02)
# ---------------------------------------------------------------------------

REQUIRED_10K_SECTIONS = [
    "Company Snapshot",
    "Business and Segments",
    "Priority Risk Factors",
    "MD&A Synthesis",
    "Segment Performance",
    "Financial Position",
    "Cash Flow Quality",
    "Notes Highlights",
    "Controls and Governance",
    "Non-GAAP and KPI Reconciliation",
    "Evolving-Topic Coverage",
    "Textual-Analysis Flags",
    "Forward-Looking Statements",
    "Open Questions",
]

# Section-to-Item attribution for inline cite-key markers in the synthesized
# low-level block. Items derived from paper-reader proposal 07 §"Pipeline flow".
LOW_LEVEL_10K_SECTIONS = [
    ("Business and Segments", "1"),
    ("Priority Risk Factors", "1A"),
    ("MD&A Synthesis", "7"),
    ("Segment Performance", "7"),
    ("Financial Position", "8"),
    ("Cash Flow Quality", "8"),
    ("Notes Highlights", "8"),
    ("Controls and Governance", "9A"),
    ("Non-GAAP and KPI Reconciliation", "7"),
]

HIGH_LEVEL_10K_SECTIONS = [
    ("Company Snapshot", "1"),
    ("Evolving-Topic Coverage", "1/1A/1C/7"),
    ("Textual-Analysis Flags", "1A/7/7A"),
    ("Forward-Looking Statements", "7"),
    ("Open Questions", "cross-ref"),
]


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

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


def _validate_10k_summary(fm: dict, body: str, ticker: str) -> None:
    """Validate that a paper-reader 10-K-mode summary is conformant for ingestion."""
    if fm.get("mode") != "10k":
        raise ValueError(
            f"Source frontmatter mode is not '10k' (got {fm.get('mode')!r})"
        )
    fm_ticker = str(fm.get("ticker", "")).upper()
    if fm_ticker and fm_ticker != ticker:
        raise ValueError(
            f"Source frontmatter ticker '{fm_ticker}' does not match "
            f"--ticker '{ticker}'"
        )
    if not fm.get("fiscal_year"):
        raise ValueError("Source frontmatter missing 'fiscal_year'")
    if not fm.get("cite_key"):
        raise ValueError("Source frontmatter missing 'cite_key'")
    missing = []
    for heading in REQUIRED_10K_SECTIONS:
        pattern = re.compile(
            rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE
        )
        if not pattern.search(body):
            missing.append(heading)
    if missing:
        raise ValueError(
            f"Source body missing required 10-K summary sections: {missing}"
        )


# ---------------------------------------------------------------------------
# Section + sidecar helpers
# ---------------------------------------------------------------------------

def _extract_section(body: str, heading: str) -> str:
    """Extract the body text of an `## H2` section identified by heading text."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(body)
    if not m:
        return ""
    return m.group(1).strip()


def _resolve_claims_path(
    source_path: Path,
    source_vault_root: Optional[Path],
    cite_key: str,
) -> Optional[Path]:
    """
    Probe candidate locations for the claims sidecar produced by paper-reader
    10-K mode. Real paper-reader output: <vault-root>/[literature/]claims/<cite_key>.json.
    """
    candidates = []
    if source_vault_root is not None:
        candidates.extend([
            source_vault_root / "literature" / "claims" / f"{cite_key}.json",
            source_vault_root / "claims" / f"{cite_key}.json",
        ])
    parent = source_path.parent
    if parent.name == "papers":
        candidates.append(parent.parent / "claims" / f"{cite_key}.json")
    grandparent = parent.parent if parent.parent != parent else None
    if grandparent is not None and grandparent.name == "literature":
        candidates.append(grandparent / "claims" / f"{cite_key}.json")
    # Also probe the source file's sibling for hand-crafted fixtures
    candidates.append(source_path.parent / f"{cite_key}.json")
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_claims_sidecar(claims_path: Optional[Path]) -> Optional[dict]:
    if claims_path is None:
        return None
    try:
        return json.loads(claims_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: claims sidecar at {claims_path} could not be loaded: {e}")
        return None


# ---------------------------------------------------------------------------
# Synthesis helpers
# ---------------------------------------------------------------------------

def _parse_segments_table(section_text: str) -> Optional[list]:
    """Best-effort parse of the Segment Performance markdown pipe table."""
    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if re.match(r"^\|\s*[-:]+\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        rows.append(cells)
    if len(rows) < 2:
        return None
    data_rows = rows[1:]  # skip header row
    segments = []
    for row in data_rows:
        first_cell_clean = row[0].replace("*", "").strip().lower()
        if "consolidated" in first_cell_clean or first_cell_clean.startswith("total"):
            continue
        segments.append({
            "name": row[0].replace("*", "").strip(),
            "revenue": row[1].replace(",", "").replace("*", "").replace("$", "").strip(),
            "margin": row[2].replace("*", "").strip(),
            "yoy_change": row[3].replace("*", "").strip(),
        })
    return segments if segments else None


def _is_textual_analysis_empty(section_text: str) -> bool:
    """Detect MVP-placeholder textual-analysis section (italicized note only)."""
    text = section_text.strip()
    if not text:
        return True
    if "reserved for paper-reader textual-analysis screening" in text.lower():
        return True
    if "T-009" in text:
        return True
    # Italicized-only placeholder (single italic block, no quantitative content)
    italic_only = (
        (text.startswith("_") and text.endswith("_"))
        or (text.startswith("*") and text.endswith("*"))
    )
    if italic_only and not re.search(r"\d+\.\d+", text):
        return True
    return False


def _format_yaml_segments(segments: Optional[list]) -> str:
    if not segments:
        return "segments: ~"
    lines = ["segments:"]
    for seg in segments:
        lines.append(f"  - name: \"{seg['name']}\"")
        lines.append(f"    revenue: \"{seg['revenue']}\"")
        lines.append(f"    margin: \"{seg['margin']}\"")
        lines.append(f"    yoy_change: \"{seg['yoy_change']}\"")
    return "\n".join(lines)


def _format_yaml_block_scalar(key: str, content: str, indent: int = 2) -> str:
    """Render a YAML block-scalar entry: 'key: |\\n  line1\\n  line2'."""
    if not content.strip():
        return f"{key}: ~"
    pad = " " * indent
    indented = "\n".join(f"{pad}{ln}" for ln in content.splitlines())
    return f"{key}: |\n{indented}"


def _synthesize_10k_thesis_block(
    fm: dict,
    body: str,
    claims_data: Optional[dict],
    source_path: Path,
) -> str:
    """
    Build a three-layer thesis block from a paper-reader 10-K-mode summary.
    Output passes _validate_thesis_block.
    """
    cite_key = fm.get("cite_key", "")
    ticker = str(fm.get("ticker", "")).upper()
    filed = fm.get("filed", vault_io.today_str())
    fiscal_year = fm.get("fiscal_year", "")

    header = f"### {filed} — 10-K filing FY{fiscal_year} (paper-reader-10k)"

    seg_section = _extract_section(body, "Segment Performance")
    segments = _parse_segments_table(seg_section)

    ta_section = _extract_section(body, "Textual-Analysis Flags")
    ta_empty = _is_textual_analysis_empty(ta_section)

    fls_section = _extract_section(body, "Forward-Looking Statements")

    yaml_lines = [
        f"ticker: {ticker}",
        f"brief_date: {filed}",
        f"brief_trigger: 10-K filing FY{fiscal_year}",
        "filing: 10-K",
        f"fiscal_year: \"{fiscal_year}\"",
        f"cite_key: {cite_key}",
        f"source_path: {source_path}",
        "confidence: derived",
        "thesis_state: evolving",
        "one_line_thesis: \"\"",
        ("confidence_rationale: \"machine-synthesized from 10-K filing; "
         "downstream specialist refinement expected\""),
        "key_catalysts: []",
        "key_risks: []",
        "evidence_pointers:",
        f"  - papers/{cite_key}.md",
    ]
    if claims_data:
        yaml_lines.append(f"  - claims/{cite_key}.json")
    yaml_lines.append("prediction_log_entries: []")
    yaml_lines.append(_format_yaml_segments(segments))
    if ta_empty:
        yaml_lines.append("textual_analysis: ~")
    else:
        yaml_lines.append(_format_yaml_block_scalar("textual_analysis", ta_section))
    yaml_lines.append(_format_yaml_block_scalar("forward_looking", fls_section))

    yaml_brief = "```yaml\n" + "\n".join(yaml_lines) + "\n```"

    low_paragraphs = [
        "#### Low-level block — what the inputs say",
        "",
        ("*Source: paper-reader 10-K-mode summary. Each paragraph carries an "
         "inline cite-key reference for downstream traceability.*"),
        "",
    ]
    for sec_name, item_id in LOW_LEVEL_10K_SECTIONS:
        sec_text = _extract_section(body, sec_name)
        if not sec_text:
            continue
        low_paragraphs.append(f"**{sec_name}.** {sec_text}")
        low_paragraphs.append(f"[cite_key: {cite_key}, Item {item_id}]")
        low_paragraphs.append("")
    low_block = "\n".join(low_paragraphs).rstrip()

    high_paragraphs = [
        "#### High-level block — how this updates the thesis",
        "",
        ("*Synthesized from interpretive sections of the 10-K-mode summary. "
         "Thesis-state remains `evolving` pending downstream specialist review.*"),
        "",
    ]
    for sec_name, item_id in HIGH_LEVEL_10K_SECTIONS:
        sec_text = _extract_section(body, sec_name)
        if not sec_text:
            continue
        if sec_name == "Textual-Analysis Flags" and ta_empty:
            continue
        high_paragraphs.append(f"**{sec_name}.** {sec_text}")
        if item_id == "cross-ref":
            high_paragraphs.append(f"[cite_key: {cite_key}, cross-reference]")
        else:
            high_paragraphs.append(f"[cite_key: {cite_key}, Item {item_id}]")
        high_paragraphs.append("")
    high_block = "\n".join(high_paragraphs).rstrip()

    return "\n\n".join([header, "", yaml_brief, "", low_block, "", high_block])


def _cite_key_already_present(profile_body: str, cite_key: str) -> bool:
    """Return True if a thesis block referencing this cite_key is already in the profile."""
    pattern = re.compile(rf"cite_key:\s*{re.escape(cite_key)}\b")
    return bool(pattern.search(profile_body))


# ---------------------------------------------------------------------------
# Optional side-effects: predictions / credibility seeding
# ---------------------------------------------------------------------------

def _seed_predictions(
    claims_data: dict,
    vault_path: Path,
    ticker: str,
    filed_date: str,
    cite_key: str,
) -> int:
    """Write predictions/<filed-date>-<TICKER>-<slug>.md for each projection claim."""
    pred_dir = vault_path / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for claim in claims_data.get("claims", []):
        if claim.get("type") != "projection":
            continue
        # paper-reader emits `claim_text`; hand-drafted sidecars may use `text`.
        text = claim.get("claim_text") or claim.get("text") or ""
        slug_source = vault_io.slugify(text[:60]) or f"projection-{count}"
        slug = f"{ticker.lower()}-{slug_source}"
        rel_path = f"predictions/{filed_date}-{slug}.md"
        abs_path = vault_path / rel_path
        if abs_path.exists():
            continue
        check_date = ""
        horizon = claim.get("guidance_horizon_end", "")
        if horizon:
            d = vault_io.parse_iso_date(horizon)
            if d is not None:
                check_date = (d + timedelta(days=30)).isoformat()
        fm = {
            "type": "memory",
            "title": f"Prediction: {ticker} {text[:60]}",
            "date": filed_date,
            "tags": ["prediction", ticker.lower()],
            "last_updated": filed_date,
            "status": "active",
            "category": "prediction",
            "ticker": ticker,
            "source_cite_key": cite_key,
            "check_date": check_date,
        }
        body = (
            f"## Prediction\n\n{text}\n\n"
            f"## Source\n\n- cite_key: `{cite_key}`\n"
            f"- locator: `{claim.get('source_anchor', {}).get('locator', '')}`\n"
        )
        vault_io.write_note(vault_path, rel_path, fm, body)
        print(f"PREDICTION_WRITTEN: {rel_path}")
        count += 1
    return count


def _seed_credibility(vault_path: Path, ticker: str, fiscal_year: str) -> bool:
    """Append a row to reference/credibility-log.md. Returns True if appended."""
    log_path = vault_path / "reference" / "credibility-log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    source_id = f"{ticker}_management_{fiscal_year}"
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        if source_id in existing:
            return False
    today = vault_io.today_str()
    line = f"| {today} | {source_id} | unscored | 10-K projection ingestion |\n"
    if not log_path.exists():
        header = (
            "---\n"
            "type: memory\n"
            "title: \"Credibility log\"\n"
            f"date: {today}\n"
            "tags:\n  - credibility\n"
            f"last_updated: {today}\n"
            "status: active\n"
            "category: credibility-log\n"
            "---\n\n"
            "# Credibility log\n\n"
            "Tracks per-source credibility as projection claims resolve against actuals.\n\n"
            "| date_registered | source_id | status | trigger |\n"
            "|---|---|---|---|\n"
        )
        log_path.write_text(header + line, encoding="utf-8")
    else:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    print(f"CREDIBILITY_REGISTERED: {source_id}")
    return True


# ---------------------------------------------------------------------------
# Existing helpers (unchanged)
# ---------------------------------------------------------------------------

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
    source_vault_root: Optional[Path] = None,
    seed_predictions: bool = False,
    seed_credibility: bool = False,
) -> dict:
    """
    Append a new dated thesis block to an existing ticker profile.

    Two input shapes are accepted:
      (a) hand-drafted thesis-block markdown — body contains the three-layer block.
      (b) paper-reader 10-K-mode summary — frontmatter `mode: 10k`. The block is
          synthesized from the 14-section summary and (optionally) its claims sidecar.

    Returns result dict with keys: vault_path, status.
    """
    ticker = ticker.upper()
    rel_path = f"market/tickers/{ticker}.md"
    abs_path = vault_path / rel_path

    if not abs_path.exists():
        raise FileNotFoundError(
            f"Profile not found: {abs_path}. Run --mode create first."
        )

    source_content = source_path.read_text(encoding="utf-8")
    source_fm, source_body = vault_io.parse_frontmatter(source_content)

    is_10k_input = source_fm.get("mode") == "10k"
    claims_data: Optional[dict] = None
    cite_key: str = ""
    fiscal_year: str = ""
    filed_date: str = ""

    if is_10k_input:
        _validate_10k_summary(source_fm, source_body, ticker)
        cite_key = source_fm.get("cite_key", "")
        fiscal_year = str(source_fm.get("fiscal_year", ""))
        filed_date = source_fm.get("filed", vault_io.today_str())
        claims_path = _resolve_claims_path(source_path, source_vault_root, cite_key)
        if claims_path is not None:
            claims_data = _load_claims_sidecar(claims_path)
        block_text = _synthesize_10k_thesis_block(
            source_fm, source_body, claims_data, source_path
        )
    else:
        block_text = source_body.strip()

    _validate_thesis_block(block_text)

    existing_content = abs_path.read_text(encoding="utf-8")
    existing_fm, existing_body = vault_io.parse_frontmatter(existing_content)

    # Idempotency: 10-K-mode inputs are deduped on cite_key
    if is_10k_input and cite_key and _cite_key_already_present(existing_body, cite_key):
        print(f"NOTE_EXISTS_AND_CURRENT: {rel_path}")
        return {"vault_path": rel_path, "status": "skipped"}

    thesis_header_match = re.search(
        r"^##\s+Thesis updates\s*$", existing_body, re.MULTILINE
    )
    if not thesis_header_match:
        raise ValueError(
            f"Profile missing `## Thesis updates` section: {abs_path}"
        )

    section_start = thesis_header_match.end()
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

    today = vault_io.today_str()
    existing_fm["last_updated"] = today

    vault_io.write_note(vault_path, rel_path, existing_fm, new_body)
    print(f"APPENDED: {rel_path}")

    # Optional side-effects (10-K input only; flags no-op for hand-drafted input)
    if is_10k_input and seed_predictions and claims_data:
        _seed_predictions(claims_data, vault_path, ticker, filed_date, cite_key)
    if is_10k_input and seed_credibility:
        _seed_credibility(vault_path, ticker, fiscal_year)

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
    parser.add_argument(
        "--source-vault-root",
        default=None,
        help="For --mode append-thesis with 10-K-mode input: paper-reader vault "
        "root used to locate the claims sidecar. Defaults to probing the source "
        "path's parent layout.",
    )
    parser.add_argument(
        "--seed-predictions",
        action="store_true",
        help="For 10-K-mode input: emit predictions/<date>-<slug>.md entries from "
        "projection claims in the claims sidecar.",
    )
    parser.add_argument(
        "--seed-credibility",
        action="store_true",
        help="For 10-K-mode input: register source identifier "
        "<TICKER>_management_<fiscal_year> in reference/credibility-log.md.",
    )
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    vault_path = Path(args.vault_path).expanduser()
    source_vault_root = (
        Path(args.source_vault_root).expanduser().resolve()
        if args.source_vault_root
        else None
    )

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
            result = ingest_ticker_append_thesis(
                source_path,
                args.ticker,
                vault_path,
                source_vault_root=source_vault_root,
                seed_predictions=args.seed_predictions,
                seed_credibility=args.seed_credibility,
            )
        else:
            parser.error(f"Unknown mode: {args.mode}")
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"DONE: status={result['status']}")


if __name__ == "__main__":
    main()
