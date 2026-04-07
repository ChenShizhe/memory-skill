#!/usr/bin/env python3
"""
preflight_maester.py — Verify vault exists, templates are deployed, and
report Obsidian CLI availability.

Exit codes:
  0 — all critical checks pass (CLI may or may not be available)
  1 — critical failure (vault missing or templates undeployed)

Usage:
  python3 knowledge-maester/scripts/preflight_maester.py [--vault-path PATH]
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Import vault_io from the same scripts directory
sys.path.insert(0, str(Path(__file__).parent))
import vault_io

EXPECTED_DIRS = [
    "market/reports",
    "market/tickers",
    "market/analysis",
    "market/archive",
    "literature/papers",
    "literature/claims",
    "literature/digests",
    "literature/fields",
    "literature/surveys",
    "reference",
    "templates",
    "zotero",
]

EXPECTED_TEMPLATES = [
    "templates/report.md",
    "templates/paper.md",
    "templates/ticker.md",
    "templates/analysis.md",
    "templates/digest.md",
    "templates/memory.md",
]

EXPECTED_PAPER_BANK_FILES = ["_manifest.json"]


def check_obsidian_cli() -> tuple[bool, str]:
    """Return (available, message)."""
    cli_path = vault_io.OBSIDIAN_CLI_PATH
    if not cli_path.exists():
        return False, (
            f"Obsidian CLI binary not found at {cli_path}. "
            "Install/update the desktop app (v1.12+) and keep filesystem I/O as the primary path."
        )

    try:
        result = subprocess.run(
            [str(cli_path), "--version"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, f"Obsidian CLI available: {version}"
        return False, (
            "Obsidian CLI returned non-zero exit. Ensure Obsidian is open and "
            "CLI is enabled (Settings → General → Enable CLI)."
        )
    except FileNotFoundError:
        return False, (
            f"Obsidian CLI binary missing at runtime: {cli_path}. "
            "Scripts will use direct filesystem I/O instead."
        )
    except subprocess.TimeoutExpired:
        return False, (
            "Obsidian CLI check timed out. Ensure Obsidian is open and responsive; "
            "scripts will continue with direct filesystem I/O."
        )


def run_preflight(vault_path: Path, paper_bank_path: Path) -> int:
    errors = []
    warnings = []
    info = []

    # 1. Vault root
    if not vault_path.exists():
        errors.append(f"CRITICAL: Vault not found at {vault_path}")
        print("\n".join(errors))
        return 1
    info.append(f"OK: Vault found at {vault_path}")

    # 2. Required subdirectories
    for rel_dir in EXPECTED_DIRS:
        abs_dir = vault_path / rel_dir
        if not abs_dir.exists():
            warnings.append(f"MISSING DIR: {rel_dir} (will be created on first use)")
        else:
            info.append(f"OK: {rel_dir}/")

    # 3. Templates
    missing_templates = []
    for rel_tmpl in EXPECTED_TEMPLATES:
        if not (vault_path / rel_tmpl).exists():
            missing_templates.append(rel_tmpl)
        else:
            info.append(f"OK: {rel_tmpl}")
    if missing_templates:
        errors.append(f"MISSING TEMPLATES: {', '.join(missing_templates)}")

    # 4. Paper bank
    if not paper_bank_path.exists():
        warnings.append(f"WARNING: Paper bank not found at {paper_bank_path}")
    else:
        info.append(f"OK: Paper bank at {paper_bank_path}")
        for f in EXPECTED_PAPER_BANK_FILES:
            if not (paper_bank_path / f).exists():
                warnings.append(f"WARNING: {f} missing from paper bank")

    # 5. Obsidian CLI (non-blocking)
    cli_ok, cli_msg = check_obsidian_cli()
    if cli_ok:
        info.append(f"OK: {cli_msg}")
    else:
        warnings.append(f"INFO: {cli_msg}")

    # Print results
    print("=== Knowledge-Maester Preflight ===")
    for msg in info:
        print(f"  {msg}")
    for msg in warnings:
        print(f"  {msg}")
    for msg in errors:
        print(f"  {msg}")

    if errors:
        print(f"\nPREFLIGHT FAILED: {len(errors)} critical issue(s)")
        return 1

    print(f"\nPREFLIGHT PASSED ({len(warnings)} warning(s))")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Preflight check for knowledge-maester")
    parser.add_argument(
        "--vault-path",
        default=str(vault_io.DEFAULT_VAULT_PATH),
        help="Path to Citadel vault"
    )
    parser.add_argument(
        "--paper-bank-path",
        default=str(vault_io.DEFAULT_PAPER_BANK_PATH),
        help="Path to paper bank"
    )
    args = parser.parse_args()

    vault_path = Path(args.vault_path).expanduser()
    paper_bank_path = Path(args.paper_bank_path).expanduser()
    sys.exit(run_preflight(vault_path, paper_bank_path))


if __name__ == "__main__":
    main()
