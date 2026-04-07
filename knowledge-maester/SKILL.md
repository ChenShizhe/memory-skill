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
  [--vault-path PATH] [--paper-bank-path PATH]

# Ingest a market-thinker analysis
python3 knowledge-maester/scripts/ingest_analysis.py \
  --source PATH_TO_ANALYSIS_MD \
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
```

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
4. After ingestion, run `check_graph.py` to verify no broken links were introduced.

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

## Ingestion Contracts Summary

| Source Type | Script | Input | Vault Target |
|---|---|---|---|
| Market-watcher report | `ingest_report.py` | Validated markdown from project workspace | `market/reports/` |
| Paper note | `ingest_paper.py` | Note markdown + `paper-bank/<cite_key>/` | `literature/papers/` |
| Market-thinker analysis | `ingest_analysis.py` | Analysis markdown from project workspace | `market/analysis/` |
| Synthesis digest | `ingest_paper.py --type digest` | Digest from research workspace | `literature/digests/` |
| Field summary | `ingest_paper.py --type field` | Field summary from research workspace | `literature/fields/` |
| Reference/capability note | `ingest_reference.py` | Reference markdown + explicit metadata flags | `reference/` |
| Memory note | `ingest_memory.py` | Source markdown + CLI metadata flags | `long-term/` or `short-term/` |

## Hard Rules

- Never write directly to the vault except through these scripts
- Never fetch from the Internet
- Never compress literature notes
- Never overwrite content outside `<!-- AUTO-GENERATED -->` markers in polished notes
- Never skip preflight when running ingestion in batch
- Always run `check_graph.py` after ingesting 5 or more notes
- Always record stub-note creation in the ingestion log output
