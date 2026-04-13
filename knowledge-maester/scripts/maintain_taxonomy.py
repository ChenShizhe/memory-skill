#!/usr/bin/env python3
"""
maintain_taxonomy.py — Taxonomy evolution and maintenance.

Modes:
  --report           Density stats, flags dense/sparse branches, pending terms count.
  --promote-pending  Promote approved terms from pending_terms.yaml into
                     taxonomy.yaml + synonym_map.json.
  --split BRANCH     Split a dense branch into children (non-interactive produces
                     a split_assignments.yaml for review).
  --merge SRC,SRC    Merge sparse branches into a target (--into TARGET).

Safety:
  --split and --merge require --confirm to apply changes (dry-run by default).
  A taxonomy.yaml.bak backup is created before any modification.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Resolve imports — db.py lives next to this script.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import db  # noqa: E402

# ---------------------------------------------------------------------------
# YAML loading / dumping
# ---------------------------------------------------------------------------

try:
    import yaml as _yaml

    def _load_yaml(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return _yaml.safe_load(f)

    def _dump_yaml(data: Any, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            _yaml.dump(
                data, f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

except ImportError:
    _yaml = None

    def _load_yaml(path: Path) -> Any:  # type: ignore[misc]
        raise RuntimeError(
            f"pyyaml is required to load {path}. Install with: pip install pyyaml"
        )

    def _dump_yaml(data: Any, path: Path) -> None:  # type: ignore[misc]
        raise RuntimeError("pyyaml is required. Install with: pip install pyyaml")


# ---------------------------------------------------------------------------
# Taxonomy helpers
# ---------------------------------------------------------------------------

def _load_taxonomy_nodes(taxonomy_path: Path) -> list[dict]:
    """Load taxonomy.yaml and return a list of root nodes."""
    data = _load_yaml(taxonomy_path)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return data.get("taxonomy", data.get("categories", data.get("keywords", [data])))


def _save_taxonomy(taxonomy_path: Path, nodes: list[dict]) -> None:
    """Save taxonomy nodes back to taxonomy.yaml."""
    _dump_yaml(nodes, taxonomy_path)


def _backup_taxonomy(taxonomy_path: Path) -> Path:
    """Create taxonomy.yaml.bak before modifications."""
    bak = taxonomy_path.with_suffix(".yaml.bak")
    shutil.copy2(taxonomy_path, bak)
    print(f"Backup created: {bak}")
    return bak


def _walk_nodes(nodes: list[dict], parent_path: str = "") -> list[tuple[str, str, dict]]:
    """Walk taxonomy tree, yielding (path, name, node) tuples."""
    results: list[tuple[str, str, dict]] = []
    for node in nodes:
        name = node.get("name", "")
        path = node.get("path", "")
        if not path and name:
            slug = name.lower().replace(" ", "-")
            path = f"{parent_path}/{slug}" if parent_path else slug
        results.append((path, name, node))
        for child in node.get("children", []):
            results.extend(_walk_nodes([child], path))
    return results


def _find_node_and_parent(
    nodes: list[dict],
    target_path: str,
    parent_path: str = "",
) -> Optional[tuple[dict, list[dict], str]]:
    """Find a node by path. Returns (node, parent_children_list, computed_path) or None."""
    for node in nodes:
        name = node.get("name", "")
        path = node.get("path", "")
        if not path and name:
            slug = name.lower().replace(" ", "-")
            path = f"{parent_path}/{slug}" if parent_path else slug
        if path == target_path:
            return (node, nodes, path)
        children = node.get("children", [])
        if children:
            result = _find_node_and_parent(children, target_path, path)
            if result is not None:
                return result
    return None


def _add_branch_to_taxonomy(
    nodes: list[dict],
    new_path: str,
) -> bool:
    """Add a new branch at new_path. Parent path segments must already exist.

    Returns True if the branch was added.
    """
    parts = new_path.split("/")
    if len(parts) == 1:
        # Top-level branch
        for n in nodes:
            p = n.get("path", n.get("name", "").lower().replace(" ", "-"))
            if p == new_path:
                return False  # already exists
        name = parts[0].replace("-", " ").title()
        nodes.append({"name": name, "path": new_path, "children": []})
        return True

    # Walk to the parent
    parent_path = "/".join(parts[:-1])
    result = _find_node_and_parent(nodes, parent_path)
    if result is None:
        return False  # parent doesn't exist

    parent_node, _, _ = result
    children = parent_node.setdefault("children", [])
    # Check if child already exists
    child_slug = parts[-1]
    for child in children:
        cp = child.get("path", "")
        if not cp:
            cp_name = child.get("name", "")
            cp = f"{parent_path}/{cp_name.lower().replace(' ', '-')}"
        if cp == new_path:
            return False  # already exists
    child_name = child_slug.replace("-", " ").title()
    children.append({"name": child_name, "path": new_path, "children": []})
    return True


# ---------------------------------------------------------------------------
# Synonym map helpers
# ---------------------------------------------------------------------------

def _load_synonym_map(path: Path) -> dict:
    """Load synonym_map.json, returns full data structure."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_synonym_map(data: dict, path: Path) -> None:
    """Save synonym_map.json."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _add_synonym(data: dict, alias: str, canonical: str, source: str = "promote-pending") -> bool:
    """Add an alias → canonical mapping. Returns True if new."""
    mappings = data.setdefault("mappings", {})
    if alias in mappings:
        return False
    mappings[alias] = {"canonical": canonical, "source": source}
    return True


# ===========================================================================
# Mode: --report
# ===========================================================================

def cmd_report(
    db_path: str,
    pending_path: Optional[Path],
    dense_threshold: int = 50,
    sparse_threshold: int = 2,
) -> None:
    """Print taxonomy health and density report."""
    conn = db.get_connection(db_path)

    # Total papers
    total_papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    # Total keywords
    total_keywords = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]

    # Paper counts per keyword (including subtree via materialized path)
    rows = conn.execute(
        """
        SELECT k.keyword_id, k.name, k.path,
               COUNT(DISTINCT pk.paper_id) AS paper_count
        FROM keywords k
        LEFT JOIN paper_keywords pk ON pk.keyword_id = k.keyword_id
        GROUP BY k.keyword_id
        ORDER BY k.path
        """
    ).fetchall()

    # For subtree counts: also count papers in child keywords
    keyword_subtree_counts: dict[str, int] = {}
    for row in rows:
        keyword_subtree_counts[row["path"]] = row["paper_count"]

    # Compute subtree totals: add child counts to parent
    paths_sorted = sorted(keyword_subtree_counts.keys())
    subtree_totals: dict[str, int] = {}
    for path in paths_sorted:
        total = keyword_subtree_counts[path]
        # Add papers from all child paths
        prefix = path + "/"
        for other_path, count in keyword_subtree_counts.items():
            if other_path.startswith(prefix):
                total += count
        subtree_totals[path] = total

    # Pending terms count
    pending_count = 0
    pending_entries: list[dict] = []
    if pending_path and pending_path.exists():
        pending_data = _load_yaml(pending_path)
        if isinstance(pending_data, list):
            pending_entries = pending_data
            pending_count = len(pending_entries)

    # Print report
    print("Taxonomy Health Report")
    print("\u2500" * 22)
    print(f"Total papers: {total_papers}  |  Total keywords: {total_keywords}  |  Pending terms: {pending_count}")
    print()

    # Per-branch stats
    print("Paper counts per branch:")
    for row in rows:
        direct = row["paper_count"]
        subtree = subtree_totals.get(row["path"], direct)
        suffix = f" (subtree: {subtree})" if subtree != direct else ""
        print(f"  {row['path']} \u2014 {direct} papers{suffix}")
    print()

    # Dense branches
    dense = [(p, c) for p, c in subtree_totals.items() if c > dense_threshold]
    if dense:
        print("Dense branches (consider splitting):")
        for path, count in sorted(dense, key=lambda x: -x[1]):
            print(f"  {path} \u2014 {count} papers")
    else:
        print("Dense branches (consider splitting): none")
    print()

    # Sparse branches
    sparse = [(p, c) for p, c in subtree_totals.items() if c < sparse_threshold]
    if sparse:
        print("Sparse branches (consider merging):")
        for path, count in sorted(sparse, key=lambda x: x[1]):
            print(f"  {path} \u2014 {count} papers")
    else:
        print("Sparse branches (consider merging): none")
    print()

    # Pending terms detail
    if pending_entries:
        print(f"Pending terms awaiting review: {pending_count}")
        for entry in pending_entries:
            raw = entry.get("raw_keyword", "?")
            paper = entry.get("paper", "?")
            status = entry.get("status", "pending")
            print(f'  - "{raw}" (from {paper}) [{status}]')
    else:
        print("Pending terms awaiting review: 0")

    conn.close()


# ===========================================================================
# Mode: --promote-pending
# ===========================================================================

def cmd_promote_pending(
    taxonomy_path: Path,
    synonym_map_path: Path,
    pending_path: Path,
) -> None:
    """Promote approved pending terms into taxonomy.yaml + synonym_map.json."""
    if not pending_path.exists():
        print(f"Pending terms file not found: {pending_path}")
        return

    pending_data = _load_yaml(pending_path)
    if not isinstance(pending_data, list) or not pending_data:
        print("No pending terms found.")
        return

    approved = [e for e in pending_data if e.get("status") == "approved" and e.get("suggested_canonical")]
    if not approved:
        print("No approved terms with suggested_canonical found.")
        return

    print(f"Found {len(approved)} approved term(s) to promote.")

    # Backup taxonomy before modification
    if taxonomy_path.exists():
        _backup_taxonomy(taxonomy_path)

    # Load taxonomy and synonym map
    taxonomy_nodes = _load_taxonomy_nodes(taxonomy_path) if taxonomy_path.exists() else []
    existing_paths = {path for path, _, _ in _walk_nodes(taxonomy_nodes)}

    syn_data: dict = {}
    if synonym_map_path.exists():
        syn_data = _load_synonym_map(synonym_map_path)
    if "mappings" not in syn_data:
        syn_data["mappings"] = {}

    promoted = 0
    for entry in approved:
        raw_kw = entry.get("raw_keyword", "")
        canonical = entry["suggested_canonical"]

        if canonical in existing_paths:
            # Existing taxonomy path: just add alias
            if _add_synonym(syn_data, raw_kw.lower(), canonical):
                print(f"  Added alias: \"{raw_kw}\" \u2192 {canonical}")
                promoted += 1
            else:
                print(f"  Alias already exists: \"{raw_kw}\" \u2192 {canonical}")
                promoted += 1
        else:
            # New taxonomy path: add branch + alias
            if _add_branch_to_taxonomy(taxonomy_nodes, canonical):
                print(f"  Added new branch: {canonical}")
            else:
                print(f"  Branch already exists: {canonical}")
            if _add_synonym(syn_data, raw_kw.lower(), canonical):
                print(f"  Added alias: \"{raw_kw}\" \u2192 {canonical}")
            promoted += 1

    # Save updated taxonomy and synonym map
    _save_taxonomy(taxonomy_path, taxonomy_nodes)
    print(f"Updated: {taxonomy_path}")

    _save_synonym_map(syn_data, synonym_map_path)
    print(f"Updated: {synonym_map_path}")

    # Remove promoted entries from pending
    remaining = [e for e in pending_data if e not in approved]
    _dump_yaml(remaining if remaining else [], pending_path)
    print(f"Removed {len(approved)} promoted entry/entries from {pending_path}")

    print(f"\nPromoted {promoted} term(s).")


# ===========================================================================
# Mode: --split
# ===========================================================================

def cmd_split(
    taxonomy_path: Path,
    db_path: str,
    source_branch: str,
    into_branches: list[str],
    confirm: bool = False,
) -> None:
    """Split a dense branch into children.

    Without --confirm: produces a split_assignments.yaml for review.
    With --confirm: creates the new branches and outputs the assignment file.
    """
    conn = db.get_connection(db_path)

    # Validate source branch exists
    row = conn.execute(
        "SELECT keyword_id, name, path FROM keywords WHERE path = ?",
        (source_branch,),
    ).fetchone()
    if row is None:
        print(f"ERROR: Source branch not found: {source_branch}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    source_kid = row["keyword_id"]

    # Get papers assigned to this branch
    papers = conn.execute(
        """SELECT p.paper_id, p.cite_key, p.title
           FROM papers p
           JOIN paper_keywords pk ON pk.paper_id = p.paper_id
           WHERE pk.keyword_id = ?
           ORDER BY p.cite_key""",
        (source_kid,),
    ).fetchall()

    if not papers:
        print(f"No papers found under branch: {source_branch}")
        conn.close()
        return

    print(f"Source branch: {source_branch} ({len(papers)} papers)")
    print(f"Split into: {', '.join(into_branches)}")
    print()

    # Build new child paths (relative to source branch)
    new_paths = []
    for branch_name in into_branches:
        if "/" in branch_name:
            new_paths.append(branch_name)  # absolute path given
        else:
            new_paths.append(f"{source_branch}/{branch_name}")

    # Create assignment file for review (no LLM in non-interactive mode)
    assignments = []
    for paper in papers:
        assignments.append({
            "cite_key": paper["cite_key"],
            "title": paper["title"],
            "current_branch": source_branch,
            "assigned_to": None,  # to be filled by reviewer
            "options": new_paths,
        })

    if not confirm:
        print("DRY RUN: --confirm not set. No changes applied.")
        print()
        # Write assignment file for review
        assignment_path = taxonomy_path.parent / "split_assignments.yaml"
        _dump_yaml(assignments, assignment_path)
        print(f"Assignment file written: {assignment_path}")
        print(f"Review and fill 'assigned_to' fields, then re-run with --confirm.")
        conn.close()
        return

    # With --confirm: create the new branches in taxonomy
    _backup_taxonomy(taxonomy_path)
    taxonomy_nodes = _load_taxonomy_nodes(taxonomy_path)

    for new_path in new_paths:
        if _add_branch_to_taxonomy(taxonomy_nodes, new_path):
            print(f"  Created branch: {new_path}")
        else:
            print(f"  Branch already exists: {new_path}")

    _save_taxonomy(taxonomy_path, taxonomy_nodes)
    print(f"Updated: {taxonomy_path}")

    # Write assignment file
    assignment_path = taxonomy_path.parent / "split_assignments.yaml"
    _dump_yaml(assignments, assignment_path)
    print(f"Assignment file written: {assignment_path}")
    print("Fill 'assigned_to' fields and update paper keywords manually or via normalize_keywords.py.")

    conn.close()


# ===========================================================================
# Mode: --merge
# ===========================================================================

def cmd_merge(
    taxonomy_path: Path,
    db_path: str,
    source_branches: list[str],
    target_branch: str,
    confirm: bool = False,
) -> None:
    """Merge sparse branches into a target branch.

    Without --confirm: dry-run showing what would change.
    With --confirm: reassigns papers, moves aliases, removes source branches.
    """
    conn = db.get_connection(db_path)

    # Validate target branch
    target_row = conn.execute(
        "SELECT keyword_id, name, path FROM keywords WHERE path = ?",
        (target_branch,),
    ).fetchone()
    if target_row is None:
        print(f"ERROR: Target branch not found: {target_branch}", file=sys.stderr)
        conn.close()
        sys.exit(1)
    target_kid = target_row["keyword_id"]

    # Validate and gather source branches
    source_info: list[tuple[int, str, int]] = []  # (keyword_id, path, paper_count)
    for src in source_branches:
        if src == target_branch:
            continue  # skip self
        row = conn.execute(
            "SELECT keyword_id, name, path FROM keywords WHERE path = ?",
            (src,),
        ).fetchone()
        if row is None:
            print(f"WARN: Source branch not found: {src} — skipping")
            continue
        paper_count = conn.execute(
            "SELECT COUNT(*) FROM paper_keywords WHERE keyword_id = ?",
            (row["keyword_id"],),
        ).fetchone()[0]
        source_info.append((row["keyword_id"], row["path"], paper_count))

    if not source_info:
        print("No valid source branches to merge.")
        conn.close()
        return

    total_papers_to_move = sum(c for _, _, c in source_info)
    print(f"Merge plan:")
    print(f"  Target: {target_branch}")
    for kid, path, count in source_info:
        print(f"  Source: {path} ({count} papers)")
    print(f"  Total papers to reassign: {total_papers_to_move}")
    print()

    if not confirm:
        print("DRY RUN: --confirm not set. No changes applied.")
        conn.close()
        return

    # Backup taxonomy
    _backup_taxonomy(taxonomy_path)

    # Reassign papers from source branches to target
    for src_kid, src_path, _ in source_info:
        # Get papers currently assigned to this source
        paper_rows = conn.execute(
            "SELECT paper_id, is_primary FROM paper_keywords WHERE keyword_id = ?",
            (src_kid,),
        ).fetchall()

        for pr in paper_rows:
            paper_id = pr["paper_id"]
            # Check if paper already assigned to target
            existing = conn.execute(
                "SELECT 1 FROM paper_keywords WHERE paper_id = ? AND keyword_id = ?",
                (paper_id, target_kid),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO paper_keywords (paper_id, keyword_id, is_primary) VALUES (?, ?, ?)",
                    (paper_id, target_kid, pr["is_primary"]),
                )
            # Remove old assignment
            conn.execute(
                "DELETE FROM paper_keywords WHERE paper_id = ? AND keyword_id = ?",
                (paper_id, src_kid),
            )

        # Move aliases from source to target
        conn.execute(
            "UPDATE keyword_aliases SET keyword_id = ? WHERE keyword_id = ?",
            (target_kid, src_kid),
        )

        # Remove the source keyword from DB
        conn.execute("DELETE FROM keywords WHERE keyword_id = ?", (src_kid,))
        print(f"  Merged: {src_path} \u2192 {target_branch}")

    conn.commit()
    conn.close()

    # Remove source branches from taxonomy.yaml
    taxonomy_nodes = _load_taxonomy_nodes(taxonomy_path)
    for _, src_path, _ in source_info:
        _remove_branch(taxonomy_nodes, src_path)
    _save_taxonomy(taxonomy_path, taxonomy_nodes)
    print(f"Updated: {taxonomy_path}")

    print(f"\nMerge complete. {total_papers_to_move} paper assignment(s) moved to {target_branch}.")


def _remove_branch(nodes: list[dict], target_path: str, parent_path: str = "") -> bool:
    """Remove a branch from the taxonomy tree by path. Returns True if found and removed."""
    for i, node in enumerate(nodes):
        name = node.get("name", "")
        path = node.get("path", "")
        if not path and name:
            slug = name.lower().replace(" ", "-")
            path = f"{parent_path}/{slug}" if parent_path else slug
        if path == target_path:
            nodes.pop(i)
            return True
        children = node.get("children", [])
        if children and _remove_branch(children, target_path, path):
            return True
    return False


# ===========================================================================
# CLI
# ===========================================================================

def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Taxonomy maintenance: report, promote pending terms, split, and merge branches."
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
        "--db-path",
        type=str,
        default=None,
        help="Path to SQLite database (default: <vault-path>/literature/_index.db)",
    )

    # Modes (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--report",
        action="store_true",
        default=False,
        help="Print taxonomy health and density report",
    )
    mode_group.add_argument(
        "--promote-pending",
        type=str,
        default=None,
        metavar="PENDING_FILE",
        help="Promote approved pending terms from the given file into taxonomy + synonym map",
    )
    mode_group.add_argument(
        "--split",
        type=str,
        default=None,
        metavar="BRANCH_PATH",
        help="Split a dense branch into children (requires --into)",
    )
    mode_group.add_argument(
        "--merge",
        type=str,
        default=None,
        metavar="SRC1,SRC2,...",
        help="Merge source branches into target (requires --into)",
    )

    # Shared options
    parser.add_argument(
        "--into",
        type=str,
        default=None,
        help="Target for --split (comma-separated child names) or --merge (target branch path)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Actually apply changes for --split and --merge (default: dry-run)",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_cli()
    args = parser.parse_args(argv)

    vault_path = Path(args.vault_path).expanduser().resolve()

    db_path = args.db_path or str(vault_path / "literature" / db.DEFAULT_DB_NAME)
    taxonomy_path = Path(args.taxonomy) if args.taxonomy else (vault_path / "taxonomy.yaml")
    synonym_map_path = Path(args.synonym_map) if args.synonym_map else (vault_path / "synonym_map.json")

    if args.report:
        pending_path = vault_path / "pending_terms.yaml"
        cmd_report(db_path, pending_path)

    elif args.promote_pending is not None:
        pending_path = Path(args.promote_pending).expanduser().resolve()
        cmd_promote_pending(taxonomy_path, synonym_map_path, pending_path)

    elif args.split is not None:
        if not args.into:
            parser.error("--split requires --into with comma-separated child branch names")
        into_branches = [b.strip() for b in args.into.split(",") if b.strip()]
        cmd_split(taxonomy_path, db_path, args.split, into_branches, confirm=args.confirm)

    elif args.merge is not None:
        if not args.into:
            parser.error("--merge requires --into with the target branch path")
        source_branches = [b.strip() for b in args.merge.split(",") if b.strip()]
        cmd_merge(taxonomy_path, db_path, source_branches, args.into, confirm=args.confirm)


if __name__ == "__main__":
    main()
