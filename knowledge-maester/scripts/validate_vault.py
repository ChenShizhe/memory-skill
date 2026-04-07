#!/usr/bin/env python3
"""
validate_vault.py — Full vault structural validation.

Checks all notes for frontmatter compliance and structure.
More comprehensive than check_graph.py — use this for a full audit.

Exit codes:
  0 — all notes pass (or warnings only)
  1 — one or more errors

Usage:
  python3 knowledge-maester/scripts/validate_vault.py \\
    [--vault-path PATH] \\
    [--output PATH_TO_JSON]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io
import check_graph as cg  # reuse collection + checks

# Type-specific required fields (beyond the shared required set)
TYPE_REQUIRED_FIELDS = {
    "report": {"watchlist", "confidence", "sources_count", "status"},
    "paper": {"cite_key", "review_status", "bank_path"},
    "ticker": {"symbol"},
    "analysis": {"confidence"},
    "digest": {"cite_key", "field"},
    "memory": {"category"},
}

# Body section requirements per type
TYPE_REQUIRED_SECTIONS = {
    "report": ["Key Findings"],
    "paper": ["Summary"],
    "ticker": ["Thesis"],
    "analysis": ["Analysis"],
    "digest": ["One-Paragraph Summary"],
    "memory": ["Content"],
}


def validate_vault(vault_path: Path, paper_bank_path: Path) -> dict:
    notes = cg.collect_notes(vault_path)
    issues = []

    for note_path in notes:
        rel_path = str(note_path.relative_to(vault_path))
        content = note_path.read_text(encoding="utf-8", errors="replace")
        fm, body = vault_io.parse_frontmatter(content)

        note_type = fm.get("type", "")

        # --- Shared required fields (already in check_graph, repeat here for standalone use) ---
        for field in vault_io.REQUIRED_FRONTMATTER_FIELDS:
            if field not in fm:
                issues.append({
                    "severity": "ERROR",
                    "type": "missing_required_field",
                    "note": rel_path,
                    "detail": f"Missing required field: {field}",
                })

        # --- Invalid type value ---
        if note_type and note_type not in vault_io.VALID_TYPES:
            issues.append({
                "severity": "ERROR",
                "type": "invalid_type",
                "note": rel_path,
                "detail": f"type={note_type!r} not in {sorted(vault_io.VALID_TYPES)}",
            })

        # --- Type-specific required fields ---
        if note_type in TYPE_REQUIRED_FIELDS:
            for field in TYPE_REQUIRED_FIELDS[note_type]:
                if field not in fm or fm[field] == "" or fm[field] == []:
                    issues.append({
                        "severity": "WARNING",
                        "type": "missing_type_field",
                        "note": rel_path,
                        "detail": f"type={note_type!r} missing field: {field}",
                    })

        # --- Required body sections (skip stubs) ---
        is_stub = body.strip().startswith("*Stub — no content yet.*") or body.strip() == ""
        if note_type in TYPE_REQUIRED_SECTIONS and not is_stub:
            for section in TYPE_REQUIRED_SECTIONS[note_type]:
                import re
                pattern = re.compile(
                    r"^#{1,3}\s+" + re.escape(section) + r"\s*$",
                    re.MULTILINE | re.IGNORECASE
                )
                if not pattern.search(body):
                    issues.append({
                        "severity": "WARNING",
                        "type": "missing_section",
                        "note": rel_path,
                        "detail": f"Expected section '## {section}' not found",
                    })

        # --- Type-specific value validation ---
        if note_type == "paper":
            cite_key = fm.get("cite_key", "")
            if cite_key and not _is_valid_cite_key(cite_key):
                issues.append({
                    "severity": "WARNING",
                    "type": "invalid_cite_key",
                    "note": rel_path,
                    "detail": f"cite_key={cite_key!r} doesn't match expected pattern (e.g. author2024example)",
                })

        if note_type == "ticker":
            symbol = fm.get("symbol", "")
            if symbol and not symbol.isupper():
                issues.append({
                    "severity": "WARNING",
                    "type": "invalid_symbol",
                    "note": rel_path,
                    "detail": f"symbol={symbol!r} should be uppercase",
                })

        if note_type in ("report", "analysis"):
            confidence = fm.get("confidence", "")
            if confidence and confidence not in ("low", "medium", "high", ""):
                issues.append({
                    "severity": "WARNING",
                    "type": "invalid_confidence",
                    "note": rel_path,
                    "detail": f"confidence={confidence!r} should be low|medium|high",
                })

        # --- Frontmatter-only notes (stubs) ---
        body_stripped = body.strip()
        is_stub = body_stripped == "*Stub — no content yet.*" or body_stripped == ""
        if not is_stub and note_type in ("report", "paper", "analysis") and len(body_stripped) < 50:
            issues.append({
                "severity": "INFO",
                "type": "thin_content",
                "note": rel_path,
                "detail": f"Note body is very short ({len(body_stripped)} chars) — may need content",
            })

    errors = sum(1 for i in issues if i["severity"] == "ERROR")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    info_count = sum(1 for i in issues if i["severity"] == "INFO")

    return {
        "vault_path": str(vault_path),
        "validated_at": vault_io.today_str(),
        "summary": {
            "total_notes": len(notes),
            "errors": errors,
            "warnings": warnings,
            "info": info_count,
            "passed": errors == 0,
        },
        "issues": issues,
    }


def _is_valid_cite_key(key: str) -> bool:
    """Rough check: author name + year pattern."""
    import re
    return bool(re.match(r"^[a-zA-Z]+\d{4}[a-zA-Z]*$", key))


def main():
    parser = argparse.ArgumentParser(description="Full vault structural validation")
    parser.add_argument("--vault-path", default=str(vault_io.DEFAULT_VAULT_PATH))
    parser.add_argument("--paper-bank-path", default=str(vault_io.DEFAULT_PAPER_BANK_PATH))
    parser.add_argument("--output", help="Write JSON report to this path")
    args = parser.parse_args()

    vault_path = Path(args.vault_path).expanduser()
    paper_bank_path = Path(args.paper_bank_path).expanduser()

    if not vault_path.exists():
        print(f"ERROR: Vault not found at {vault_path}")
        sys.exit(1)

    report = validate_vault(vault_path, paper_bank_path)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Validation report written to {out_path}")
    else:
        print(json.dumps(report, indent=2))

    s = report["summary"]
    status = "PASS" if s["passed"] else "FAIL"
    print(
        f"\nValidation {status}: {s['total_notes']} notes | "
        f"{s['errors']} errors | {s['warnings']} warnings | {s['info']} info",
        file=sys.stderr
    )

    sys.exit(0 if s["passed"] else 1)


if __name__ == "__main__":
    main()
