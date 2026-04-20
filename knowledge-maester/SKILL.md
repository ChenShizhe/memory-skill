---
name: knowledge-maester
description: Sole writer to the Citadel vault at ~/Documents/citadel/. Ingests content from other skills, writes/polishes vault notes, maintains graph integrity, and compresses old market notes. Use when any skill needs to persist a note to the vault, polish an existing note, check graph health, or rebuild vault indexes.
---

# Knowledge-Maester

## Mission

Serve as the **sole writer** to the Citadel vault at `~/Documents/citadel/`. No other skill writes directly to the vault. Every note created, updated, or archived passes through this skill.

Knowledge-maester:
- Converts outputs from other skills into well-formed vault notes
- Maintains graph integrity (backlinks, wiki-links, stubs)
- Compresses aged market notes into archive summaries
- Rebuilds dashboard and index notes
- Validates vault structure and frontmatter compliance

**Never fetches from the Internet.** It only processes information already retrieved by other skills.

## Vault and Paths

| Resource | Path |
|---|---|
| Vault root | `~/Documents/citadel/` |
| Market reports | `~/Documents/citadel/market/reports/` |
| Market tickers | `~/Documents/citadel/market/tickers/` |
| Market analysis | `~/Documents/citadel/market/analysis/` |
| Market archive | `~/Documents/citadel/market/archive/` |
| Literature papers | `~/Documents/citadel/literature/papers/` |
| Literature claims | `~/Documents/citadel/literature/claims/` |
| Literature digests | `~/Documents/citadel/literature/digests/` |
| Literature fields | `~/Documents/citadel/literature/fields/` |
| Literature surveys | `~/Documents/citadel/literature/surveys/` |
| Reference | `~/Documents/citadel/reference/` |
| Templates (vault) | `~/Documents/citadel/templates/` |
| Literature SQLite index | `~/Documents/citadel/literature/_index.db` |
| Literature catalog MOCs | `~/Documents/citadel/literature/_catalog/` |
| Taxonomy definition | `~/Documents/citadel/taxonomy.yaml` |
| Synonym map | `~/Documents/citadel/synonym_map.json` |
| Pending terms queue | `~/Documents/citadel/pending_terms.yaml` |
| Paper bank | `~/Documents/paper-bank/` |
| Paper bank manifest | `~/Documents/paper-bank/_manifest.json` |

## Obsidian CLI Note

The Obsidian CLI is embedded in the desktop app (1.12+) and requires Obsidian to be running with CLI enabled (Settings → General → Enable CLI). It **cannot** be used headlessly or in CI. All scripts use **direct filesystem I/O** (Python standard library) as the primary write mechanism. If Obsidian is open, scripts may optionally trigger a vault refresh via the CLI, but they never block on it.

In agent/script contexts, invoke the CLI by absolute path:

- the Obsidian CLI (see `vault_io.py` for path configuration)

Do not rely on bare `obsidian` from `PATH` in non-interactive shells, and do not use `which obsidian` as an availability check in those contexts.

`preflight_maester.py` checks and reports CLI availability without blocking on it.

## Load Order

Always load:
- [references/vault-schema.md](references/vault-schema.md)
- [references/ingestion-rules.md](references/ingestion-rules.md)

Load on demand:
- [references/graph-health.md](references/graph-health.md)
- [references/compression-rules.md](references/compression-rules.md)

## Command Map

All commands run from the repo root:

```bash
# Preflight check
python3 knowledge-maester/scripts/preflight_maester.py [--vault-path PATH]

# Ingest a market-watcher report
python3 knowledge-maester/scripts/ingest_report.py \
  --source PATH_TO_REPORT_MD \
  --project-name NAME --run-id ID \
  [--vault-path PATH]

# Ingest a paper note (from paper-reader output)
python3 knowledge-maester/scripts/ingest_paper.py \
  --cite-key CITE_KEY \
  --note PATH_TO_NOTE_MD \
  [--vault-path PATH] [--paper-bank-path PATH] \
  [--taxonomy PATH] [--synonym-map PATH] [--skip-index]

# Ingest a market-thinker analysis
python3 knowledge-maester/scripts/ingest_analysis.py \
  --source PATH_TO_ANALYSIS_MD \
  [--vault-path PATH]

# Ingest a ticker profile (create a new profile or append a thesis block)
python3 knowledge-maester/scripts/ingest_ticker.py \
  --mode create --source PATH_TO_PROFILE_MD --ticker SYMBOL \
  [--vault-path PATH] [--overwrite]

python3 knowledge-maester/scripts/ingest_ticker.py \
  --mode append-thesis --source PATH_TO_THESIS_BLOCK_MD --ticker SYMBOL \
  [--vault-path PATH]

# Ingest a reference/capability memory note
python3 knowledge-maester/scripts/ingest_reference.py \
  --source PATH_TO_SOURCE_MD \
  --title "Human-Readable Title" \
  --tags my-system,tool-name \
  --category tool-capability \
  [--vault-path PATH]

# Ingest a memory note (create mode)
python3 knowledge-maester/scripts/ingest_memory.py \
  --source PATH_TO_SOURCE_MD \
  --title "Title" --type TYPE --layer LAYER \
  --topics "t1,t2" --projects "p1" --priority PRIORITY \
  [--vault-path PATH] [--related "slug1,slug2"]

# Ingest a memory note (update mode)
python3 knowledge-maester/scripts/ingest_memory.py \
  --update --note-path RELATIVE_PATH \
  --source PATH_TO_UPDATE_MD \
  [--vault-path PATH]

# Polish an existing vault note with new information
python3 knowledge-maester/scripts/polish_note.py \
  --note-path VAULT_RELATIVE_PATH \
  --update PATH_TO_UPDATE_MD \
  [--vault-path PATH]

# Compress market notes older than N days
python3 knowledge-maester/scripts/compress_old_notes.py \
  [--days 30] [--dry-run] [--vault-path PATH]

# Check graph health (orphans, broken links, missing frontmatter)
python3 knowledge-maester/scripts/check_graph.py \
  [--vault-path PATH] [--schema citadel|memory] [--output PATH_TO_JSON]

# Rebuild _index.md and dashboard notes
python3 knowledge-maester/scripts/generate_index.py \
  [--vault-path PATH]

# Regenerate memory catalog
python3 knowledge-maester/scripts/generate_memory_catalog.py \
  [--vault-path PATH] [--output PATH]

# Full vault structural validation
python3 knowledge-maester/scripts/validate_vault.py \
  [--vault-path PATH] [--output PATH_TO_JSON]

# Build/rebuild the literature SQLite index from vault Markdown
python3 knowledge-maester/scripts/build_taxonomy_db.py \
  [--vault-path PATH] [--taxonomy PATH] [--synonym-map PATH] \
  [--db-path PATH] [--incremental] [--full-rebuild]

# Normalize paper keywords against the taxonomy (3-stage pipeline)
python3 knowledge-maester/scripts/normalize_keywords.py \
  [--vault-path PATH] [--taxonomy PATH] [--synonym-map PATH] \
  [--cite-keys "key1,key2"] [--all-unclassified] [--no-write] \
  [--pending-output PATH]

# Generate per-keyword catalog MOC pages from SQLite index
python3 knowledge-maester/scripts/generate_catalog_mocs.py \
  [--vault-path PATH] [--db-path PATH] \
  [--keyword KEYWORD_PATH | --all]

# Taxonomy maintenance: report, promote, split, merge
python3 knowledge-maester/scripts/maintain_taxonomy.py \
  [--vault-path PATH] [--taxonomy PATH] [--synonym-map PATH] \
  [--db-path PATH] \
  --report

python3 knowledge-maester/scripts/maintain_taxonomy.py \
  [--vault-path PATH] [--taxonomy PATH] [--synonym-map PATH] \
  --promote-pending pending_terms.yaml

python3 knowledge-maester/scripts/maintain_taxonomy.py \
  [--vault-path PATH] [--taxonomy PATH] [--db-path PATH] \
  --split "parent/branch" --into "child1,child2" [--confirm]

python3 knowledge-maester/scripts/maintain_taxonomy.py \
  [--vault-path PATH] [--taxonomy PATH] [--db-path PATH] \
  --merge "branch1,branch2" --into "target/branch" [--confirm]
```

## Taxonomy & Catalog Scripts

### build_taxonomy_db.py

Populates or rebuilds the SQLite literature index (`literature/_index.db`) from vault Markdown notes. Loads `taxonomy.yaml` for keyword hierarchy and `synonym_map.json` for alias resolution. Scans `literature/papers/*.md`, imports claims from `literature/claims/*.json`, builds FTS5 full-text search, and cleans orphan records.

| Flag | Default | Description |
|---|---|---|
| `--vault-path` | `~/Documents/citadel` | Vault root |
| `--taxonomy` | `<vault-path>/taxonomy.yaml` | Taxonomy definition file |
| `--synonym-map` | `<vault-path>/synonym_map.json` | Synonym/alias mapping |
| `--db-path` | `<vault-path>/literature/_index.db` | SQLite database path |
| `--incremental` | off | Skip files whose content hash matches the DB |
| `--full-rebuild` | off | Drop and recreate all tables before populating |

### normalize_keywords.py

Three-stage keyword normalization pipeline that maps raw author keywords from paper frontmatter to canonical taxonomy terms:
1. **String normalization** — lowercase, hyphen normalization, depluralization, acronym expansion
2. **Dictionary lookup** — resolve against `synonym_map.json` and `taxonomy.yaml`
3. **Pending output** — unmatched terms appended to `pending_terms.yaml` for human review (no LLM calls)

When normalization succeeds, writes `controlled_keywords` into the paper's YAML frontmatter.

| Flag | Default | Description |
|---|---|---|
| `--vault-path` | `~/Documents/citadel` | Vault root |
| `--taxonomy` | `<vault-path>/taxonomy.yaml` | Taxonomy definition file |
| `--synonym-map` | `<vault-path>/synonym_map.json` | Synonym/alias mapping |
| `--cite-keys` | (none) | Comma-separated cite keys to process |
| `--all-unclassified` | off | Process all papers with empty `controlled_keywords` |
| `--no-write` | off | Dry run — do not modify paper frontmatter |
| `--pending-output` | `<vault-path>/pending_terms.yaml` | Output path for unmatched terms |

### generate_catalog_mocs.py

Generates per-keyword Markdown catalog (MOC) pages in `literature/_catalog/` from the SQLite index. Each page includes `type: moc` frontmatter (for memory-retriever MOC detection), a paper listing table, child/parent navigation links, and statistics. Also generates `literature/_catalog/_index.md` as a taxonomy overview.

| Flag | Default | Description |
|---|---|---|
| `--vault-path` | `~/Documents/citadel` | Vault root |
| `--db-path` | `<vault-path>/literature/_index.db` | SQLite database path |
| `--keyword` | (none) | Regenerate only this keyword path |
| `--all` | off | Regenerate all keyword catalog pages |

Requires the SQLite index to exist (run `build_taxonomy_db.py` first).

### maintain_taxonomy.py

Taxonomy evolution and maintenance with four modes:

- **`--report`** — Print density stats, flag dense branches (>50 papers, consider splitting) and sparse branches (<2 papers, consider merging), and count pending terms.
- **`--promote-pending FILE`** — Promote entries with `status: approved` and `suggested_canonical` from `pending_terms.yaml` into `taxonomy.yaml` + `synonym_map.json`.
- **`--split BRANCH --into child1,child2`** — Split a dense branch into children. Without `--confirm`: outputs `split_assignments.yaml` for review. With `--confirm`: creates branches.
- **`--merge src1,src2 --into target`** — Merge sparse branches into a target. Reassigns papers, moves aliases, removes source branches. Requires `--confirm` to apply.

| Flag | Default | Description |
|---|---|---|
| `--vault-path` | `~/Documents/citadel` | Vault root |
| `--taxonomy` | `<vault-path>/taxonomy.yaml` | Taxonomy definition file |
| `--synonym-map` | `<vault-path>/synonym_map.json` | Synonym/alias mapping |
| `--db-path` | `<vault-path>/literature/_index.db` | SQLite database path |
| `--confirm` | off | Apply changes (default is dry-run for `--split` and `--merge`) |

Safety: `--split` and `--merge` require `--confirm` to apply changes. A `taxonomy.yaml.bak` backup is created before any modification.

## Memory Vault Support

Knowledge-maester's default target remains the Citadel vault at `~/Documents/citadel/`.
For memory-system operations, pass `--vault-path` to target `~/Documents/memory/` instead.

Supported memory-vault operations:
- `ingest_memory.py` — create or update D1-schema memory notes in `long-term/` or `short-term/`
- `check_graph.py --schema memory` — validate memory-vault graph health and frontmatter types
- `generate_memory_catalog.py` — regenerate the hybrid memory catalog

This memory-vault support is separate from Citadel ingestion paths such as `market/`, `literature/`, and `reference/`.

## Workflow

### Ingesting a New Note

1. Run `preflight_maester.py` — verify vault exists and templates are deployed.
2. Choose the correct ingestion script based on source type (see ingestion contracts in [references/ingestion-rules.md](references/ingestion-rules.md)).
3. The ingestion script:
   - Reads the source artifact
   - Applies the type-specific template (frontmatter + body structure)
   - Extracts entity mentions → generates `[[wiki-links]]`
   - Creates stub notes for referenced entities that don't exist yet
   - Writes the note to the correct vault subdirectory
   - Updates `_manifest.json` for paper notes
4. **Post-ingestion keyword normalization** (paper notes only, automatic when `taxonomy.yaml` exists):
   - `ingest_paper.py` runs `normalize_keywords.py` for the ingested cite key
   - Raw `keywords` from the paper frontmatter are normalized against the taxonomy
   - Resolved keywords are written as `controlled_keywords` in the paper frontmatter
   - Unmatched keywords are appended to `pending_terms.yaml` for human review
   - Unless `--skip-index` is set, an incremental `build_taxonomy_db.py` run updates the SQLite index
   - If `taxonomy.yaml` does not exist, the hook is skipped silently (backward compatible)
5. After ingestion, run `check_graph.py` to verify no broken links were introduced.

### Polishing an Existing Note

When new information arrives about an entity already in the vault:
1. Run `polish_note.py` with the existing note path and the update artifact.
2. The script merges new information (appends to relevant section, does not overwrite).
3. Updates frontmatter (`last_updated`, `sources_count`).
4. Adds new backlinks.
5. Preserves human-added annotations (content outside `<!-- AUTO-GENERATED -->` markers).

### Market Note Compression

Run periodically (e.g. weekly):
1. `compress_old_notes.py --dry-run` to preview what will be compressed.
2. `compress_old_notes.py --days 30` to execute compression on notes older than 30 days.
3. The script extracts durable lessons, writes a compressed summary in `market/archive/`, moves the original to `market/archive/`, and updates backlinks.
4. Literature notes are **never** compressed.

### Maintaining Graph Health

Run `check_graph.py` after any batch ingestion. Review `--output` JSON for:
- Orphan notes (no incoming or outgoing links)
- Broken `[[wiki-links]]` (target doesn't exist)
- Missing required frontmatter fields
- Stale market notes

Fix issues by either:
- Creating stub notes for missing targets
- Adding links from isolated notes
- Updating stale frontmatter

### Rebuilding Indexes and Dashboards

Run `generate_index.py` after significant ingestion batches. This rebuilds:
- `citadel/_index.md` — vault-wide overview
- `citadel/market/_dashboard.md` — recent reports, active watchlist, sector activity
- `citadel/literature/_catalog.md` — paper bank catalog synced with paper-bank manifest

### Rebuilding the Literature Catalog

For taxonomy-aware catalog pages, run these scripts in order after batch ingestion:

1. `normalize_keywords.py --all-unclassified` — normalize keywords for all unclassified papers
2. `build_taxonomy_db.py --incremental` — update the SQLite index with new/changed papers
3. `generate_catalog_mocs.py --all` — regenerate all per-keyword catalog MOC pages in `_catalog/`

The catalog MOCs in `literature/_catalog/` are auto-generated with `type: moc` frontmatter and are consumed by memory-retriever for exploratory queries.

## Ingestion Contracts Summary

| Source Type | Script | Input | Vault Target |
|---|---|---|---|
| Market-watcher report | `ingest_report.py` | Validated markdown from project workspace | `market/reports/` |
| Paper note | `ingest_paper.py` | Note markdown + `paper-bank/<cite_key>/` | `literature/papers/` |
| Market-thinker analysis | `ingest_analysis.py` | Analysis markdown from project workspace | `market/analysis/` |
| Ticker profile | `ingest_ticker.py` | Full profile (`--mode create`) or thesis-block fragment (`--mode append-thesis`) from a specialist's brief | `market/tickers/` |
| Synthesis digest | `ingest_paper.py --type digest` | Digest from research workspace | `literature/digests/` |
| Field summary | `ingest_paper.py --type field` | Field summary from research workspace | `literature/fields/` |
| Reference/capability note | `ingest_reference.py` | Reference markdown + explicit metadata flags | `reference/` |
| Memory note | `ingest_memory.py` | Source markdown + CLI metadata flags | `long-term/` or `short-term/` |

### Paper Ingestion Input Fields

The paper note input (from paper-reader) may include these frontmatter fields consumed by the ingestion and normalization pipeline:

| Field | Required | Description |
|---|---|---|
| `title` | yes | Paper title |
| `cite_key` | yes | Unique citation identifier |
| `authors` | yes | Author list |
| `year` | yes | Publication year |
| `keywords` | no | Raw author-provided keywords (input to normalization pipeline) |
| `author_keywords` | no | Alternate field for author keywords |
| `summary` | no | One-two sentence TL;DR (extracted by paper-reader) |
| `methods` | no | Key statistical/computational methods used |
| `controlled_keywords` | no | Canonical taxonomy paths (written by `normalize_keywords.py`, not by paper-reader) |

The `keywords`/`author_keywords` fields are consumed by `normalize_keywords.py` during the post-ingestion hook. The `summary` field is extracted from the note body Summary/Abstract sections and included in the vault note.

## Hard Rules

- Never write directly to the vault except through these scripts
- Never fetch from the Internet
- Never compress literature notes
- Never overwrite content outside `<!-- AUTO-GENERATED -->` markers in polished notes
- Never skip preflight when running ingestion in batch
- Always run `check_graph.py` after ingesting 5 or more notes
- Always record stub-note creation in the ingestion log output
