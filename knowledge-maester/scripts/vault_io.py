"""
vault_io.py — Shared utilities for Citadel vault read/write operations.

All vault operations use direct filesystem I/O. Obsidian CLI is optional
(requires desktop app running with CLI enabled).
"""
import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional

DEFAULT_VAULT_PATH = Path.home() / "Documents" / "citadel"
DEFAULT_PAPER_BANK_PATH = Path.home() / "Documents" / "paper-bank"
OBSIDIAN_CLI_PATH = Path(os.environ.get("OBSIDIAN_CLI_PATH", "/Applications/Obsidian.app/Contents/MacOS/obsidian"))

VALID_TYPES = {
    "report", "paper", "ticker", "analysis", "digest", "memory",
    "moc", "reading-note", "stub", "survey", "concept",
    "notation-summary", "literature-note", "conference",
}
# Types used by paper sub-notes (method.md, intro.md, etc. inside paper dirs)
SUB_NOTE_TYPES = {
    "method", "theory", "model", "gaps", "empirical", "notation",
    "proofs", "intro", "method-note", "theory-note", "model-note",
    "intro-note", "proofs-note", "gaps-note", "empirical-note",
    "notation-note",
}
ALL_VALID_TYPES = VALID_TYPES | SUB_NOTE_TYPES
VALID_STATUSES = {"active", "archived", "stale", "draft", "reviewed", "stub", "dummy", "not-applicable"}

REQUIRED_FRONTMATTER_FIELDS = {"type", "title", "date", "tags", "last_updated", "status"}

# Ticker pattern: 1-5 uppercase letters (optionally with =F or -F suffix for futures)
TICKER_PATTERN = re.compile(r'\b([A-Z]{1,5}(?:[=\-][A-Z]{1,2})?)\b')

# Wiki-link pattern
WIKI_LINK_PATTERN = re.compile(r'\[\[([^\[\]]+)\]\]')

# Known common English words to exclude from ticker detection
_TICKER_EXCLUSIONS = {
    "A", "I", "THE", "AND", "OR", "FOR", "IN", "ON", "AT", "TO", "OF", "IS",
    "IT", "AS", "BY", "UP", "AN", "BE", "DO", "GO", "IF", "MY", "NO", "SO",
    "US", "UK", "EU", "UN", "GDP", "CPI", "YOY", "QOQ", "YTD", "IPO",
    "CEO", "CFO", "COO", "CTO", "AI", "ML", "IT", "FY", "Q1", "Q2", "Q3", "Q4",
    "ID", "NA", "OK", "TBD", "TBC", "WIP", "PR", "MR", "DR",
    "PDF", "API", "URL", "CLI", "ETF", "USD", "CNY", "EUR", "JPY", "GBP",
    "BTC", "ETH", "NFT", "ESG", "R&D",
}


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def today_str() -> str:
    return date.today().isoformat()


def parse_iso_date(s: str) -> Optional[date]:
    """Return date or None if unparseable."""
    try:
        return date.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 60) -> str:
    """Lowercase, hyphen-separated slug from text."""
    text = text.lower()
    text = re.sub(r"[''\"()]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].rstrip("-")


# ---------------------------------------------------------------------------
# Frontmatter parsing (minimal YAML subset — colon-separated key-value lines)
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Split content into (frontmatter_dict, body_text).
    Returns ({}, content) if no frontmatter block found.
    """
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")
    fm = _parse_yaml_subset(fm_text)
    return fm, body


def _parse_yaml_subset(text: str) -> dict:
    """Parse a minimal YAML block (no nesting, supports lists)."""
    result = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        # list item continuation
        if line.startswith("  - ") or line.startswith("- "):
            i += 1
            continue
        colon_pos = line.find(":")
        if colon_pos == -1:
            i += 1
            continue
        key = line[:colon_pos].strip()
        value_str = line[colon_pos + 1:].strip()
        # check if next lines are list items
        if value_str == "" or value_str == "[]":
            items = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith("  - ") or lines[j].startswith("- ")):
                item = lines[j].strip().lstrip("- ").strip()
                items.append(item)
                j += 1
            if items:
                result[key] = items
                i = j
                continue
            result[key] = [] if value_str == "[]" else ""
        else:
            # strip inline list
            if value_str.startswith("[") and value_str.endswith("]"):
                inner = value_str[1:-1]
                items = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
                result[key] = items
            else:
                # strip quotes
                v = value_str.strip('"').strip("'")
                result[key] = v
        i += 1
    return result


def render_frontmatter(fm: dict) -> str:
    """Render a frontmatter dict back to YAML block string (without --- delimiters)."""
    lines = []
    for key, value in fm.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        elif value is None or value == "":
            lines.append(f'{key}: ""')
        else:
            # Quote strings containing colons or special chars
            s = str(value)
            if ":" in s or '"' in s or s.startswith("{"):
                s = f'"{s}"'
            lines.append(f"{key}: {s}")
    return "\n".join(lines)


def write_note(vault_path: Path, rel_path: str, fm: dict, body: str) -> Path:
    """
    Write a vault note at vault_path/rel_path.
    Creates parent directories as needed.
    Returns the absolute path.
    """
    abs_path = vault_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    fm_block = render_frontmatter(fm)
    content = f"---\n{fm_block}\n---\n\n{body.lstrip()}"
    abs_path.write_text(content, encoding="utf-8")
    return abs_path


def read_note(vault_path: Path, rel_path: str) -> tuple[dict, str]:
    """Read a vault note. Returns (frontmatter, body)."""
    abs_path = vault_path / rel_path
    if not abs_path.exists():
        raise FileNotFoundError(f"Note not found: {abs_path}")
    content = abs_path.read_text(encoding="utf-8")
    return parse_frontmatter(content)


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

def extract_tickers(text: str) -> list[str]:
    """Extract likely ticker symbols from text (uppercase 1-5 char words)."""
    matches = TICKER_PATTERN.findall(text)
    tickers = []
    seen = set()
    for m in matches:
        if m not in _TICKER_EXCLUSIONS and m not in seen:
            tickers.append(m)
            seen.add(m)
    return tickers


def extract_wiki_links(text: str) -> list[str]:
    """Extract all [[target]] references from text."""
    return WIKI_LINK_PATTERN.findall(text)


# ---------------------------------------------------------------------------
# Note existence helpers
# ---------------------------------------------------------------------------

def note_exists(vault_path: Path, rel_path: str) -> bool:
    return (vault_path / rel_path).exists()


def find_note_by_stem(vault_path: Path, stem: str) -> Optional[Path]:
    """Search vault for a .md file whose stem matches (case-insensitive)."""
    stem_lower = stem.lower().replace(" ", "-")
    for md_file in vault_path.rglob("*.md"):
        if md_file.stem.lower() == stem_lower:
            return md_file
    return None


# ---------------------------------------------------------------------------
# Stub note creation
# ---------------------------------------------------------------------------

def create_stub(vault_path: Path, rel_path: str, note_type: str, title: str) -> Path:
    """Create a minimal stub note if it doesn't already exist."""
    abs_path = vault_path / rel_path
    if abs_path.exists():
        return abs_path
    today = today_str()
    fm = {
        "type": note_type,
        "title": title,
        "date": today,
        "tags": [],
        "last_updated": today,
        "status": "active",
    }
    if note_type == "ticker":
        fm["symbol"] = title
        fm["name"] = ""
        fm["sector"] = ""
        fm["watchlist"] = []
    elif note_type == "paper":
        fm["cite_key"] = Path(rel_path).stem
        fm["canonical_id"] = ""
        fm["authors"] = []
        fm["year"] = ""
        fm["content_status"] = ""
        fm["review_status"] = "draft"
        fm["bank_path"] = ""
    elif note_type == "memory":
        fm["category"] = "tool-capability"
    body = "*Stub — no content yet.*\n"
    return write_note(vault_path, rel_path, fm, body)


# ---------------------------------------------------------------------------
# Ticker stub + backlink helpers
# ---------------------------------------------------------------------------

def ensure_ticker_stub(vault_path: Path, symbol: str) -> tuple[Path, bool]:
    """
    Ensure a ticker note exists for symbol. Returns (path, created).
    """
    rel_path = f"market/tickers/{symbol}.md"
    abs_path = vault_path / rel_path
    if abs_path.exists():
        return abs_path, False
    path = create_stub(vault_path, rel_path, "ticker", symbol)
    return path, True


def add_ticker_appearance(vault_path: Path, symbol: str, report_slug: str) -> None:
    """Add [[report_slug]] to ticker note's AUTO-GENERATED Appearances section."""
    rel_path = f"market/tickers/{symbol}.md"
    abs_path = vault_path / rel_path
    if not abs_path.exists():
        return
    content = abs_path.read_text(encoding="utf-8")
    link = f"- [[{report_slug}]]"
    if link in content:
        return  # already present
    # Insert before /AUTO-GENERATED
    if "<!-- /AUTO-GENERATED -->" in content:
        content = content.replace(
            "<!-- /AUTO-GENERATED -->",
            f"{link}\n<!-- /AUTO-GENERATED -->"
        )
    else:
        content += f"\n<!-- AUTO-GENERATED -->\n## Appearances\n{link}\n<!-- /AUTO-GENERATED -->\n"
    abs_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Paper-bank manifest
# ---------------------------------------------------------------------------

def read_manifest(paper_bank_path: Path) -> list[dict]:
    manifest_path = paper_bank_path / "_manifest.json"
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Handle dict format: {"papers": {"key": {...}, ...}} or {"key": {...}, ...}
            papers = data.get("papers", data)
            if isinstance(papers, dict):
                return list(papers.values())
            return []
        return []
    except (json.JSONDecodeError, OSError):
        return []


def write_manifest(paper_bank_path: Path, entries: list[dict]) -> None:
    manifest_path = paper_bank_path / "_manifest.json"
    manifest_path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def upsert_manifest_entry(paper_bank_path: Path, entry: dict) -> None:
    """Add or update manifest entry by cite_key."""
    manifest_path = paper_bank_path / "_manifest.json"
    cite_key = entry.get("cite_key", "")

    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
    else:
        manifest = {}

    if not isinstance(manifest, dict):
        manifest = {}

    papers = manifest.get("papers", {})
    if not isinstance(papers, dict):
        papers = {}
    papers[cite_key] = entry
    manifest["papers"] = papers

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# AUTO-GENERATED section helpers
# ---------------------------------------------------------------------------

def update_autogenerated_section(content: str, new_section_content: str) -> str:
    """Replace content between AUTO-GENERATED markers."""
    pattern = re.compile(
        r"<!-- AUTO-GENERATED -->.*?<!-- /AUTO-GENERATED -->",
        re.DOTALL
    )
    replacement = f"<!-- AUTO-GENERATED -->\n{new_section_content}\n<!-- /AUTO-GENERATED -->"
    if pattern.search(content):
        return pattern.sub(replacement, content)
    # Append if markers not present
    return content + f"\n\n<!-- AUTO-GENERATED -->\n{new_section_content}\n<!-- /AUTO-GENERATED -->\n"


# ---------------------------------------------------------------------------
# Obsidian CLI (optional)
# ---------------------------------------------------------------------------

def try_obsidian_refresh(vault_path: Path) -> bool:
    """
    Attempt an Obsidian CLI vault refresh. Returns True if successful.
    This is optional — failure does not block vault operations.
    """
    if not OBSIDIAN_CLI_PATH.exists():
        return False

    try:
        result = subprocess.run(
            [str(OBSIDIAN_CLI_PATH), "--vault", str(vault_path), "--refresh"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
