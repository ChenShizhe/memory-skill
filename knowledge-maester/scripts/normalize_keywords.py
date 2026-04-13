#!/usr/bin/env python3
"""
normalize_keywords.py — 3-stage keyword normalization pipeline.

Maps raw keywords from paper frontmatter to canonical taxonomy terms:
  Stage 1: String normalization (lowercase, hyphens, plurals, whitespace)
  Stage 2: Dictionary lookup against synonym_map.json
  Stage 3: Output unmatched terms to pending_terms.yaml (no LLM calls)

Can update paper frontmatter with controlled_keywords when normalization succeeds.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Resolve imports — db.py and vault_io.py live next to this script.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import vault_io  # noqa: E402
except ImportError:
    vault_io = None

# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

try:
    import yaml as _yaml

    def _load_yaml(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return _yaml.safe_load(f)

    def _dump_yaml(data: Any, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            _yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

except ImportError:
    _yaml = None

    def _load_yaml(path: Path) -> Any:
        raise RuntimeError(
            f"pyyaml is required to load {path}. Install with: pip install pyyaml"
        )

    def _dump_yaml(data: Any, path: Path) -> None:
        raise RuntimeError("pyyaml is required. Install with: pip install pyyaml")


# ---------------------------------------------------------------------------
# Frontmatter parsing — prefer vault_io, fallback to minimal parser
# ---------------------------------------------------------------------------

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if vault_io is not None:
        return vault_io.parse_frontmatter(content)
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
    """Minimal YAML key-value parser (no nesting, supports inline/block lists)."""
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        if line.startswith("  - ") or line.startswith("- "):
            i += 1
            continue
        colon_pos = line.find(":")
        if colon_pos == -1:
            i += 1
            continue
        key = line[:colon_pos].strip()
        value_str = line[colon_pos + 1:].strip()
        if value_str == "" or value_str == "[]":
            items = []
            j = i + 1
            while j < len(lines) and (
                lines[j].startswith("  - ") or lines[j].startswith("- ")
            ):
                item = lines[j].strip().lstrip("- ").strip()
                items.append(item)
                j += 1
            if items:
                result[key] = items
                i = j
                continue
            result[key] = [] if value_str == "[]" else ""
        else:
            if value_str.startswith("[") and value_str.endswith("]"):
                inner = value_str[1:-1]
                items = [
                    x.strip().strip('"').strip("'")
                    for x in inner.split(",")
                    if x.strip()
                ]
                result[key] = items
            else:
                v = value_str.strip('"').strip("'")
                result[key] = v
        i += 1
    return result


def _render_frontmatter(fm: dict) -> str:
    """Render a frontmatter dict back to YAML block string (without --- delimiters)."""
    if vault_io is not None:
        return vault_io.render_frontmatter(fm)
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
            s = str(value)
            if ":" in s or '"' in s or s.startswith("{"):
                s = f'"{s}"'
            lines.append(f"{key}: {s}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Known acronym expansions (small built-in table)
# ---------------------------------------------------------------------------

KNOWN_ACRONYMS: dict[str, str] = {
    "mle": "maximum likelihood estimation",
    "em": "expectation maximization",
    "mcmc": "markov chain monte carlo",
    "ode": "ordinary differential equation",
    "sde": "stochastic differential equation",
    "pde": "partial differential equation",
    "cnn": "convolutional neural network",
    "rnn": "recurrent neural network",
    "lstm": "long short-term memory",
    "gnn": "graph neural network",
    "vae": "variational autoencoder",
    "gan": "generative adversarial network",
    "nlp": "natural language processing",
    "rl": "reinforcement learning",
    "sgd": "stochastic gradient descent",
    "gmm": "gaussian mixture model",
    "hmm": "hidden markov model",
    "kde": "kernel density estimation",
    "garch": "generalized autoregressive conditional heteroskedasticity",
    "arma": "autoregressive moving average",
    "arima": "autoregressive integrated moving average",
}


# ---------------------------------------------------------------------------
# Stage 1: String normalization
# ---------------------------------------------------------------------------

# Common English plural suffixes to collapse (applied in order, first match wins)
_PLURAL_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ies$"), "y"),       # "strategies" → "strategy"
    (re.compile(r"sses$"), "ss"),     # "processes" → "process"
    (re.compile(r"ices$"), "ix"),     # "matrices" → "matrix"
    (re.compile(r"ves$"), "f"),       # "halves" → "half"
    # Generic: only strip trailing "s" after a consonant (not vowel+s like "hawkes")
    # and only for words of 5+ chars to avoid mangling short words
    (re.compile(r"([bcdfghjklmnpqrtvwxyz])s$"), r"\1"),
]

# Some words where naive depluralization would fail — keep as-is or map explicitly
_PLURAL_EXCEPTIONS: dict[str, str] = {
    "processes": "process",
    "analyses": "analysis",
    "matrices": "matrix",
    "indices": "index",
    "vertices": "vertex",
    "hypotheses": "hypothesis",
    "theses": "thesis",
    "bases": "basis",
    "crises": "crisis",
    "series": "series",
    "species": "species",
    "news": "news",
    "statistics": "statistics",
    "mathematics": "mathematics",
    "physics": "physics",
    "dynamics": "dynamics",
    "economics": "economics",
    "genetics": "genetics",
    "robotics": "robotics",
    "logistics": "logistics",
    "stochastics": "stochastics",
    "informatics": "informatics",
    "bayesian": "bayesian",
    "gaussian": "gaussian",
    "bias": "bias",
    "atlas": "atlas",
    "bus": "bus",
    "corpus": "corpus",
    "focus": "focus",
    "status": "status",
    "census": "census",
    "consensus": "consensus",
}


def _depluralize(word: str) -> str:
    """Best-effort singular form of a single word."""
    if word in _PLURAL_EXCEPTIONS:
        return _PLURAL_EXCEPTIONS[word]
    if len(word) <= 3:
        return word
    for pattern, replacement in _PLURAL_RULES:
        new = pattern.sub(replacement, word)
        if new != word:
            return new
    return word


def normalize_string(raw: str) -> str:
    """Stage 1: deterministic string normalization.

    - Lowercase
    - Strip leading/trailing whitespace
    - Normalize hyphens: treat spaces between words as hyphens when the
      hyphenated form is the conventional compound (e.g., self exciting → self-exciting)
    - Collapse plurals (per-word)
    - Expand known acronyms
    """
    text = raw.strip().lower()

    # Normalize unicode hyphens / dashes to ASCII hyphen
    text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", text)

    # Collapse multiple whitespace / tabs
    text = re.sub(r"\s+", " ", text)

    # Expand known acronyms (full-match only)
    if text in KNOWN_ACRONYMS:
        text = KNOWN_ACRONYMS[text]

    # Normalize hyphen vs space: if the term already contains a hyphen,
    # keep hyphens; also recognise "self exciting" → "self-exciting" patterns.
    # Strategy: for two-word phrases where hyphenated form is common,
    # join with hyphen.  We also normalise "self exciting" → "self-exciting".
    _HYPHEN_PREFIXES = {
        "self", "non", "semi", "multi", "cross", "pre", "post", "co", "re",
        "over", "under", "inter", "intra", "anti", "sub", "super", "meta",
        "quasi", "pseudo", "well", "high", "low", "long", "short",
    }
    parts = text.split(" ")
    if len(parts) == 2 and parts[0] in _HYPHEN_PREFIXES:
        text = f"{parts[0]}-{parts[1]}"

    # Also normalise existing "self exciting" with hyphen if space-separated
    # (general: replace space with hyphen when adjacent to existing hyphen pattern)
    # Already handled above.

    # Depluralize each word (split on hyphens and spaces)
    tokens = re.split(r"([\s-])", text)
    depluralized = []
    for token in tokens:
        if re.match(r"[\s-]", token):
            depluralized.append(token)
        else:
            depluralized.append(_depluralize(token))
    text = "".join(depluralized)

    return text.strip()


# ---------------------------------------------------------------------------
# Stage 2: Dictionary lookup (synonym_map.json)
# ---------------------------------------------------------------------------

def load_synonym_map(path: Path) -> dict[str, str]:
    """Load synonym_map.json and return a dict mapping normalized alias → canonical path.

    Keys are run through normalize_string() so lookups match after Stage 1.

    Supports two formats:
      v1: { "mappings": { "<alias>": { "canonical": "<path>", ... } } }
      flat: { "<alias>": "<path>" }
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    mappings = data.get("mappings", data) if isinstance(data, dict) else {}
    result: dict[str, str] = {}

    for alias, value in mappings.items():
        if isinstance(value, dict):
            canonical = value.get("canonical", "")
        else:
            canonical = str(value)
        if canonical:
            # Store both the raw lowercased key and the fully-normalized key
            # so lookups work from either direction
            raw_key = alias.strip().lower()
            norm_key = normalize_string(alias)
            result[raw_key] = canonical
            if norm_key != raw_key:
                result[norm_key] = canonical

    return result


def load_taxonomy_terms(path: Path) -> set[str]:
    """Load taxonomy.yaml and collect all canonical term paths and names (lowercased)."""
    data = _load_yaml(path)
    if data is None:
        return set()
    terms: set[str] = set()

    def _walk(node: Any, parent_path: str = "") -> None:
        if isinstance(node, dict):
            name = node.get("name", "")
            path = node.get("path", "")
            if not path and name:
                slug = name.lower().replace(" ", "-")
                path = f"{parent_path}/{slug}" if parent_path else slug
            if path:
                terms.add(path.lower())
            if name:
                terms.add(name.lower())
            for child in node.get("children", []):
                _walk(child, path)
        elif isinstance(node, list):
            for item in node:
                _walk(item, parent_path)

    nodes = data if isinstance(data, list) else data.get("categories", data.get("keywords", [data]))
    if isinstance(nodes, dict):
        nodes = [nodes]
    for node in nodes:
        _walk(node)

    return terms


def resolve_keyword(
    normalized: str,
    synonym_map: dict[str, str],
    taxonomy_terms: set[str],
) -> Optional[str]:
    """Stage 2: look up a normalized keyword in the synonym map and taxonomy.

    Returns the canonical taxonomy path if resolved, else None.
    """
    # Direct synonym match
    if normalized in synonym_map:
        return synonym_map[normalized]

    # Direct taxonomy match (by name or path)
    if normalized in taxonomy_terms:
        return normalized

    return None


# ---------------------------------------------------------------------------
# Stage 3: Pending terms output (NO LLM calls)
# ---------------------------------------------------------------------------

def build_pending_entry(
    raw_keyword: str,
    cite_key: str,
    source: str = "from author keywords",
) -> dict[str, Any]:
    """Build a pending_terms.yaml entry for an unmatched keyword."""
    return {
        "raw_keyword": raw_keyword,
        "paper": cite_key,
        "context": source,
        "suggested_canonical": None,
        "status": "pending",
    }


def write_pending_terms(entries: list[dict[str, Any]], output_path: Path) -> None:
    """Append new pending entries to pending_terms.yaml (merge, no duplicates)."""
    existing: list[dict[str, Any]] = []
    if output_path.exists():
        existing = _load_yaml(output_path) or []
        if not isinstance(existing, list):
            existing = []

    # Dedup by (raw_keyword, paper)
    seen = {(e["raw_keyword"], e["paper"]) for e in existing}
    for entry in entries:
        key = (entry["raw_keyword"], entry["paper"])
        if key not in seen:
            existing.append(entry)
            seen.add(key)

    _dump_yaml(existing, output_path)


# ---------------------------------------------------------------------------
# Frontmatter update
# ---------------------------------------------------------------------------

def _update_frontmatter_keywords(
    md_path: Path,
    controlled_keywords: list[str],
) -> bool:
    """Write controlled_keywords into the YAML frontmatter of a Markdown file.

    Returns True if the file was modified.
    """
    content = md_path.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(content)

    old = fm.get("controlled_keywords", [])
    if isinstance(old, str):
        old = [k.strip() for k in old.split(",") if k.strip()]
    if sorted(old) == sorted(controlled_keywords):
        return False  # no change needed

    fm["controlled_keywords"] = controlled_keywords
    fm_block = _render_frontmatter(fm)
    new_content = f"---\n{fm_block}\n---\n\n{body.lstrip()}"
    md_path.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Paper discovery
# ---------------------------------------------------------------------------

def _find_paper_files(
    vault_path: Path,
    cite_keys: Optional[list[str]] = None,
    all_unclassified: bool = False,
) -> list[Path]:
    """Find paper Markdown files to process."""
    papers_dir = vault_path / "literature" / "papers"
    if not papers_dir.exists():
        print(f"  WARN: papers directory not found: {papers_dir}", file=sys.stderr)
        return []

    md_files = sorted(papers_dir.glob("*.md"))

    if cite_keys is not None:
        key_set = set(cite_keys)
        selected = []
        for f in md_files:
            content = f.read_text(encoding="utf-8")
            fm, _ = _parse_frontmatter(content)
            ck = fm.get("cite_key", f.stem)
            if ck in key_set:
                selected.append(f)
        return selected

    if all_unclassified:
        selected = []
        for f in md_files:
            content = f.read_text(encoding="utf-8")
            fm, _ = _parse_frontmatter(content)
            controlled = fm.get("controlled_keywords", [])
            if not controlled or controlled == "[]":
                selected.append(f)
        return selected

    return md_files


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    vault_path: Path,
    taxonomy_path: Path,
    synonym_map_path: Path,
    cite_keys: Optional[list[str]] = None,
    all_unclassified: bool = False,
    write_frontmatter: bool = True,
    pending_output: Optional[Path] = None,
) -> dict[str, Any]:
    """Run the 3-stage keyword normalization pipeline.

    Returns a summary dict with counts and details.
    """
    # Load resources
    synonym_map: dict[str, str] = {}
    if synonym_map_path.exists():
        synonym_map = load_synonym_map(synonym_map_path)

    taxonomy_terms: set[str] = set()
    if taxonomy_path.exists():
        taxonomy_terms = load_taxonomy_terms(taxonomy_path)

    # Find papers
    paper_files = _find_paper_files(vault_path, cite_keys, all_unclassified)

    total_raw = 0
    total_resolved = 0
    total_unmatched = 0
    papers_updated = 0
    all_pending: list[dict[str, Any]] = []

    for md_path in paper_files:
        content = md_path.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(content)
        cite_key = fm.get("cite_key", md_path.stem)

        # Gather raw keywords from frontmatter
        raw_keywords = fm.get("keywords", [])
        if isinstance(raw_keywords, str):
            raw_keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

        if not raw_keywords:
            continue

        resolved_for_paper: list[str] = []
        unmatched_for_paper: list[str] = []

        for raw_kw in raw_keywords:
            total_raw += 1

            # Stage 1: string normalization
            normalized = normalize_string(raw_kw)

            # Stage 2: dictionary lookup
            canonical = resolve_keyword(normalized, synonym_map, taxonomy_terms)

            if canonical is not None:
                resolved_for_paper.append(canonical)
                total_resolved += 1
            else:
                unmatched_for_paper.append(raw_kw)
                total_unmatched += 1
                all_pending.append(build_pending_entry(raw_kw, cite_key))

        # Write controlled_keywords to frontmatter if any were resolved
        if resolved_for_paper and write_frontmatter:
            # Deduplicate while preserving order
            seen: set[str] = set()
            deduped: list[str] = []
            for kw in resolved_for_paper:
                if kw not in seen:
                    deduped.append(kw)
                    seen.add(kw)
            if _update_frontmatter_keywords(md_path, deduped):
                papers_updated += 1

    # Stage 3: write pending terms
    if pending_output is None:
        pending_output = vault_path / "pending_terms.yaml"
    if all_pending:
        write_pending_terms(all_pending, pending_output)

    return {
        "papers_processed": len(paper_files),
        "total_raw_keywords": total_raw,
        "total_resolved": total_resolved,
        "total_unmatched": total_unmatched,
        "papers_updated": papers_updated,
        "pending_terms_file": str(pending_output) if all_pending else None,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="3-stage keyword normalization pipeline. "
        "Maps raw keywords to canonical taxonomy terms, "
        "outputs unmatched terms to pending_terms.yaml."
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=str(Path.home() / "Documents" / "citadel"),
        help="Path to the Obsidian vault root (default: ~/Documents/citadel)",
    )
    parser.add_argument(
        "--taxonomy",
        type=str,
        default=None,
        help="Path to taxonomy.yaml (default: <vault-path>/taxonomy.yaml)",
    )
    parser.add_argument(
        "--synonym-map",
        type=str,
        default=None,
        help="Path to synonym_map.json (default: <vault-path>/synonym_map.json)",
    )
    parser.add_argument(
        "--cite-keys",
        type=str,
        default=None,
        help='Comma-separated cite keys to process (e.g., "smith2024methods,jones2023analysis")',
    )
    parser.add_argument(
        "--all-unclassified",
        action="store_true",
        default=False,
        help="Process all papers with empty or missing controlled_keywords",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        default=False,
        help="Do not write controlled_keywords to paper frontmatter (dry run)",
    )
    parser.add_argument(
        "--pending-output",
        type=str,
        default=None,
        help="Path for pending_terms.yaml output (default: <vault-path>/pending_terms.yaml)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_cli()
    args = parser.parse_args(argv)

    vault_path = Path(args.vault_path).expanduser().resolve()
    if not vault_path.exists():
        print(f"ERROR: vault path does not exist: {vault_path}", file=sys.stderr)
        sys.exit(1)

    taxonomy_path = Path(args.taxonomy) if args.taxonomy else (vault_path / "taxonomy.yaml")
    synonym_map_path = Path(args.synonym_map) if args.synonym_map else (vault_path / "synonym_map.json")

    cite_keys = None
    if args.cite_keys:
        cite_keys = [k.strip() for k in args.cite_keys.split(",") if k.strip()]

    pending_output = Path(args.pending_output) if args.pending_output else None

    print(f"Vault:       {vault_path}")
    print(f"Taxonomy:    {taxonomy_path} {'(exists)' if taxonomy_path.exists() else '(not found)'}")
    print(f"Synonym map: {synonym_map_path} {'(exists)' if synonym_map_path.exists() else '(not found)'}")
    if cite_keys:
        print(f"Cite keys:   {', '.join(cite_keys)}")
    elif args.all_unclassified:
        print("Mode:        all unclassified papers")
    else:
        print("Mode:        all papers")
    print()

    result = run_pipeline(
        vault_path=vault_path,
        taxonomy_path=taxonomy_path,
        synonym_map_path=synonym_map_path,
        cite_keys=cite_keys,
        all_unclassified=args.all_unclassified,
        write_frontmatter=not args.no_write,
        pending_output=pending_output,
    )

    print("=== Results ===")
    print(f"  Papers processed:     {result['papers_processed']}")
    print(f"  Raw keywords seen:    {result['total_raw_keywords']}")
    print(f"  Resolved (canonical): {result['total_resolved']}")
    print(f"  Unmatched (pending):  {result['total_unmatched']}")
    print(f"  Papers updated:       {result['papers_updated']}")
    if result["pending_terms_file"]:
        print(f"  Pending terms file:   {result['pending_terms_file']}")
    print("\nDone.")


if __name__ == "__main__":
    main()
