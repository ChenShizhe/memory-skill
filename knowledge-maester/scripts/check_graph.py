#!/usr/bin/env python3
"""
check_graph.py — Detect graph health issues in the Citadel vault.

Checks:
  - Broken [[wiki-links]] (target note doesn't exist)
  - Orphan notes (no incoming or outgoing links)
  - Missing required frontmatter fields
  - Invalid frontmatter values
  - Stale market notes
  - Duplicate cite_keys
  - Paper-bank manifest drift

Exit codes:
  0 — no errors (warnings OK)
  1 — one or more errors found

Usage:
  python3 knowledge-maester/scripts/check_graph.py \\
    [--vault-path PATH] \\
    [--paper-bank-path PATH] \\
    [--output PATH_TO_JSON]
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vault_io

# Notes to skip during validation
SKIP_STEMS = {"_index", "_dashboard", "_catalog"}
SKIP_DIRS = {"templates", "zotero"}

# Stale thresholds (days) per type
STALE_THRESHOLDS = {
    "report": 30,
    "analysis": 60,
    "ticker": 90,
}

VALID_TYPES = vault_io.ALL_VALID_TYPES
MEMORY_VALID_TYPES = {
    "workflow",
    "decision",
    "project-pattern",
    "reference",
    "continuity",
    "user-preference",
    "hub",
    "operational",
}
VALID_STATUSES = vault_io.VALID_STATUSES
REQUIRED_FIELDS = {"type", "title", "date", "tags", "last_updated", "status"}
MEMORY_REQUIRED_FIELDS = {"type", "title", "layer", "date", "last_updated", "status"}
MEMORY_SKIP_DIRS = {".obsidian", "workflow-templates", "archive"}
MEMORY_SKIP_FILES = {"AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "catalog.md"}
MEMORY_SKIP_STEMS = {"_template", "_hub-template"}


def collect_notes(vault_path: Path, schema: str = "citadel") -> list[Path]:
    """Return all .md files to validate."""
    notes = []
    for md_file in vault_path.rglob("*.md"):
        rel_parts = md_file.relative_to(vault_path).parts

        if schema == "memory":
            if any(part in MEMORY_SKIP_DIRS for part in rel_parts[:-1]):
                continue
            if md_file.name in MEMORY_SKIP_FILES:
                continue
            if md_file.stem.startswith("_") and not md_file.stem.startswith("_hub-"):
                continue
            if md_file.stem in MEMORY_SKIP_STEMS:
                continue
        else:
            # Skip index/dashboard files
            if md_file.stem.startswith("_"):
                continue
            # Skip template directories
            if any(part in SKIP_DIRS for part in rel_parts[:-1]):
                continue

        notes.append(md_file)
    return notes


def build_link_index(notes: list[Path], vault_path: Path) -> tuple[dict, dict]:
    """
    Build:
      outgoing[rel_path] = set of referenced stems
      incoming[stem] = set of rel_paths that reference it
    """
    outgoing = {}
    incoming = {}  # stem -> set of rel_paths

    for note_path in notes:
        rel_path = str(note_path.relative_to(vault_path))
        content = note_path.read_text(encoding="utf-8", errors="replace")
        links = vault_io.extract_wiki_links(content)
        stems = set()
        for lnk in links:
            s = lnk.split("|")[0].split("#")[0].strip().lower()
            # Strip .md suffix — Obsidian treats [[note.md]] same as [[note]]
            if s.endswith(".md"):
                s = s[:-3]
            stems.add(s)
        outgoing[rel_path] = stems
        for stem in stems:
            incoming.setdefault(stem, set()).add(rel_path)

    return outgoing, incoming


def build_stem_index(notes: list[Path], vault_path: Path) -> dict[str, Path]:
    """Map lowercase stem -> path, including path-based keys for sub-notes."""
    index = {}
    for note in notes:
        index[note.stem.lower()] = note
        # Add path-based keys for sub-notes (e.g., "cite_key/intro")
        rel = note.relative_to(vault_path)
        rel_no_ext = str(rel.with_suffix("")).lower()
        index[rel_no_ext] = note
        # Obsidian also resolves short relative paths (last 2 parts)
        parts = rel.with_suffix("").parts
        if len(parts) >= 2:
            short_path = "/".join(parts[-2:]).lower()
            if short_path not in index:
                index[short_path] = note
    return index


def _is_paper_subnote(rel_path: str) -> bool:
    """Check if a note is a sub-note inside a paper directory (e.g., literature/papers/key/intro.md)."""
    parts = rel_path.split("/")
    # Pattern: literature/papers/<cite_key>/<subnote>.md — 4+ parts with papers as 2nd
    return (len(parts) >= 4
            and parts[0] == "literature"
            and parts[1] == "papers"
            and not parts[-1].startswith("_"))


def _is_paper_companion(rel_path: str) -> bool:
    """Check if a note is a companion file (e.g., cite_key-notation.md) at papers root level."""
    parts = rel_path.split("/")
    if len(parts) == 3 and parts[0] == "literature" and parts[1] == "papers":
        stem = Path(parts[2]).stem
        return "-notation" in stem or "-reading" in stem
    return False


# Reduced required fields for paper sub-notes (they use a simpler schema)
SUB_NOTE_REQUIRED_FIELDS = {"cite_key", "status"}


def check_graph(vault_path: Path, paper_bank_path: Path, schema: str = "citadel") -> dict:
    today = date.today()
    issues = []
    notes = collect_notes(vault_path, schema=schema)
    valid_types = MEMORY_VALID_TYPES if schema == "memory" else VALID_TYPES
    required_fields = MEMORY_REQUIRED_FIELDS if schema == "memory" else REQUIRED_FIELDS

    outgoing, incoming = build_link_index(notes, vault_path)
    stem_index = build_stem_index(notes, vault_path)

    seen_cite_keys = {}  # cite_key -> rel_path (primary notes only)

    for note_path in notes:
        rel_path = str(note_path.relative_to(vault_path))
        content = note_path.read_text(encoding="utf-8", errors="replace")
        fm, _ = vault_io.parse_frontmatter(content)

        is_subnote = _is_paper_subnote(rel_path)

        # --- Missing required frontmatter ---
        check_fields = SUB_NOTE_REQUIRED_FIELDS if is_subnote else required_fields
        for field in check_fields:
            if field not in fm or fm[field] == "" or fm[field] == []:
                # tags: [] is acceptable
                if field == "tags" and isinstance(fm.get("tags"), list):
                    continue
                issues.append({
                    "severity": "ERROR",
                    "type": "missing_frontmatter",
                    "note": rel_path,
                    "detail": f"Missing or empty required field: {field}",
                })

        # --- Invalid frontmatter values ---
        note_type = fm.get("type", "")
        type_check_set = vault_io.ALL_VALID_TYPES if is_subnote else valid_types
        if note_type and note_type not in type_check_set:
            issues.append({
                "severity": "ERROR",
                "type": "invalid_frontmatter",
                "note": rel_path,
                "detail": f"type={note_type!r} not in {sorted(valid_types)}",
            })

        status = fm.get("status", "")
        if status and status not in VALID_STATUSES:
            issues.append({
                "severity": "ERROR",
                "type": "invalid_frontmatter",
                "note": rel_path,
                "detail": f"status={status!r} not in {sorted(VALID_STATUSES)}",
            })

        for date_field in ("date", "last_updated"):
            val = fm.get(date_field, "")
            if val and vault_io.parse_iso_date(val) is None:
                issues.append({
                    "severity": "ERROR",
                    "type": "invalid_frontmatter",
                    "note": rel_path,
                    "detail": f"{date_field}={val!r} is not a valid ISO date",
                })

        # --- Duplicate cite_keys (skip sub-notes and companion files — they share parent's cite_key) ---
        is_companion = _is_paper_companion(rel_path)
        if schema != "memory" and not is_subnote and not is_companion:
            cite_key = fm.get("cite_key", "")
            if cite_key:
                if cite_key in seen_cite_keys:
                    issues.append({
                        "severity": "ERROR",
                        "type": "duplicate_cite_key",
                        "note": rel_path,
                        "detail": f"cite_key={cite_key!r} also used in {seen_cite_keys[cite_key]}",
                    })
                else:
                    seen_cite_keys[cite_key] = rel_path

        # --- Broken wiki-links ---
        note_outgoing = outgoing.get(rel_path, set())
        for link_stem in note_outgoing:
            if link_stem.startswith("_") and not (schema == "memory" and link_stem.startswith("_hub-")):
                continue  # skip index links
            # Skip LaTeX/math expressions accidentally parsed as wikilinks
            if re.search(r"[{}\\^]", link_stem) or link_stem.startswith("τ") or link_stem.startswith("δ"):
                continue
            if link_stem not in stem_index:
                issues.append({
                    "severity": "WARNING",
                    "type": "broken_link",
                    "note": rel_path,
                    "detail": f"[[{link_stem}]] not found in vault",
                })

        # --- Orphan notes ---
        note_stem = note_path.stem.lower()
        has_outgoing = bool(note_outgoing)
        has_incoming = bool(incoming.get(note_stem))
        # Stubs are expected to have no outgoing links — only flag if no incoming either
        is_stub = content.strip().endswith("*Stub — no content yet.*")
        if not has_outgoing and not has_incoming and not is_stub:
            issues.append({
                "severity": "WARNING",
                "type": "orphan_note",
                "note": rel_path,
                "detail": "No incoming or outgoing [[wiki-links]]",
            })

        # --- Stale market notes ---
        if note_type in STALE_THRESHOLDS and status == "active":
            last_updated_str = fm.get("last_updated", fm.get("date", ""))
            last_updated = vault_io.parse_iso_date(last_updated_str)
            if last_updated:
                age_days = (today - last_updated).days
                threshold = STALE_THRESHOLDS[note_type]
                if age_days > threshold:
                    issues.append({
                        "severity": "INFO",
                        "type": "stale_note",
                        "note": rel_path,
                        "detail": f"Not updated in {age_days} days (threshold: {threshold})",
                    })

    # --- Paper-bank manifest drift ---
    if schema != "memory" and paper_bank_path.exists():
        manifest = vault_io.read_manifest(paper_bank_path)
        manifest_keys = {e.get("cite_key") for e in manifest if e.get("cite_key")}
        vault_paper_keys = set(seen_cite_keys.keys())

        for mk in manifest_keys - vault_paper_keys:
            issues.append({
                "severity": "WARNING",
                "type": "manifest_drift",
                "note": "(manifest)",
                "detail": f"Manifest entry cite_key={mk!r} has no corresponding vault note",
            })

        for vk in vault_paper_keys - manifest_keys:
            # Only flag papers (not digests etc)
            note_rel = seen_cite_keys[vk]
            if "literature/papers/" in note_rel:
                issues.append({
                    "severity": "WARNING",
                    "type": "manifest_drift",
                    "note": note_rel,
                    "detail": f"Paper note cite_key={vk!r} not in paper-bank manifest",
                })

    # Build summary
    errors = sum(1 for i in issues if i["severity"] == "ERROR")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    info_count = sum(1 for i in issues if i["severity"] == "INFO")

    report = {
        "vault_path": str(vault_path),
        "checked_at": vault_io.today_str() + "T00:00:00Z",
        "summary": {
            "total_notes": len(notes),
            "errors": errors,
            "warnings": warnings,
            "info": info_count,
        },
        "issues": issues,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Check Citadel vault graph health")
    parser.add_argument("--vault-path", default=str(vault_io.DEFAULT_VAULT_PATH))
    parser.add_argument("--paper-bank-path", default=str(vault_io.DEFAULT_PAPER_BANK_PATH))
    parser.add_argument("--schema", choices=["citadel", "memory"], default="citadel")
    parser.add_argument("--output", help="Write JSON report to this path")
    args = parser.parse_args()

    vault_path = Path(args.vault_path).expanduser()
    paper_bank_path = Path(args.paper_bank_path).expanduser()

    if not vault_path.exists():
        print(f"ERROR: Vault not found at {vault_path}")
        sys.exit(1)

    report = check_graph(vault_path, paper_bank_path, schema=args.schema)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to {out_path}")
    else:
        print(json.dumps(report, indent=2))

    s = report["summary"]
    print(
        f"\nGraph check: {s['total_notes']} notes | "
        f"{s['errors']} errors | {s['warnings']} warnings | {s['info']} info",
        file=sys.stderr
    )

    sys.exit(1 if report["summary"]["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
