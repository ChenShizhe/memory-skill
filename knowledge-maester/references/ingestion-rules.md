# Ingestion Rules

Rules for converting external skill outputs into vault notes.

## Common Rules (all types)

1. **Read the source artifact first.** Never ingest without reading the full source.
2. **Apply the correct template.** See `vault-schema.md` for type-specific frontmatter.
3. **Extract entity mentions.** Scan body for ticker symbols (ALL_CAPS 1-5 chars), company names (capitalized multi-word), and country/region names. Convert to `[[wiki-links]]`.
4. **Create stubs.** For each entity mentioned that has no existing vault note, create a minimal stub note in the correct directory. Stubs have frontmatter only + a single `*Stub — no content yet.*` line.
5. **Do not duplicate.** Before creating a new note, check if a note with the same `cite_key`, `symbol`, or `slug` already exists. If so, use `polish_note.py` instead.
6. **Log stub creation.** Emit a log line for each stub note created.
7. **Set `date` to today.** Set `last_updated` to today. Do not carry dates from source frontmatter unless the type requires them (e.g. paper `year`).

## Ingestion Contract: Market-Watcher Report

**Script:** `ingest_report.py`
**Input:** Validated markdown report from `projects/<name>/market-watcher/<run-id>/final-report.md`
**Target:** `market/reports/YYYY-MM-DD-<slug>.md`

Steps:
1. Read source report. Verify it has a markdown frontmatter block with `quality_gate: pass` or absence of `quality_gate: fail`.
2. Extract from source:
   - `title` from `# Heading` or source frontmatter
   - `tags` from topic keywords
   - `watchlist` from ticker symbols found in body (ALL_CAPS 1-5 chars matching a stock symbol pattern)
   - `time_window` from report body if stated
   - `confidence` from source frontmatter or default to `medium`
   - `sources_count` from Source Index table row count
3. Write vault note using report template.
4. Populate `Key Findings` from report Executive Summary.
5. Populate `Analysis` from report Main Developments.
6. Populate `Market Dashboard` from report Market Dashboard section.
7. Populate `Risks and Counterarguments` if present in source.
8. Populate `Source Index` (carry forward from source; omit URL column if source has it).
9. Extract ticker/company/country mentions → add `[[wiki-links]]` to `## Links` section.
10. Create ticker stubs for any new symbols in watchlist (in `market/tickers/<SYMBOL>.md`).
11. Add backlink to this report in each ticker stub's `## Appearances` AUTO-GENERATED section.

## Ingestion Contract: Paper Note

**Script:** `ingest_paper.py` (default type: paper)
**Input:** Paper note markdown from paper-reader workspace + optional paper-bank entry
**Target:** `literature/papers/<cite_key>.md`

Steps:
1. Parse `cite_key` from input. Derive vault path `literature/papers/<cite_key>.md`.
2. Check if `paper-bank/<cite_key>/` exists. If so, read `paper-bank/<cite_key>/metadata.json` for authors, year, DOI.
3. Extract from source note: title, summary, key claims, methodology.
4. Write vault note using paper template.
5. Update `paper-bank/_manifest.json`: add or update entry for this cite_key with `{cite_key, title, authors, year, vault_path, bank_path, date_added}`.
6. Extract paper title mentions and related cite keys → add `[[wiki-links]]` to `## Links` section.
7. Create stubs for cited papers mentioned in source (in `literature/papers/<cited_cite_key>.md`).

## Ingestion Contract: Digest

**Script:** `ingest_paper.py --type digest`
**Input:** Digest markdown from research-synthesizer workspace
**Target:** `literature/digests/<cite_key>-digest.md`

Steps:
1. Parse `cite_key` from filename or frontmatter.
2. Write vault note using digest template.
3. Add `[[cite_key]]` link to source paper.
4. If paper note exists, add backlink in paper's `## Links` section via `polish_note.py`.

## Ingestion Contract: Field Summary

**Script:** `ingest_paper.py --type field`
**Input:** Field summary markdown from research workspace
**Target:** `literature/fields/<field-slug>.md`

Steps:
1. Derive slug from field name.
2. Write vault note as `type: memory` (closest fit; field summaries are reference material).
3. Link to all source paper notes mentioned.

## Ingestion Contract: Market-Thinker Analysis

**Script:** `ingest_analysis.py`
**Input:** Analysis markdown from market-thinker workspace
**Target:** `market/analysis/YYYY-MM-DD-<slug>.md`

Steps:
1. Extract title, confidence level, related tickers, related reports from source.
2. Write vault note using analysis template.
3. Populate `Reasoning Chain` section from source (wrap in AUTO-GENERATED markers).
4. Extract prediction statements → write to `## Predictions` section.
5. Extract evidence references → `[[wiki-links]]` to existing report notes.
6. Add backlinks in referenced report notes via `polish_note.py`.

## Ingestion Contract: Reference / Memory Note

**Script:** `ingest_reference.py`
**Input:** Source markdown + explicit metadata flags (`--title`, `--category`, optional `--tags`)
**Target:** `reference/<slug>.md`

CLI:
```bash
python3 knowledge-maester/scripts/ingest_reference.py \
  --source PATH_TO_SOURCE_MD \
  --title "Human-Readable Title" \
  --tags my-system,tool-name \
  --category tool-capability \
  [--vault-path PATH]
```

Steps:
1. Read source markdown and parse frontmatter/body.
2. Derive slug from `--title` (lowercase, hyphenated, max 60 chars).
3. Build target path `reference/<slug>.md`.
4. If target exists and `last_updated` is today or newer, exit with `NOTE_EXISTS_AND_CURRENT: <path>`.
5. Write `type: memory` frontmatter using:
   - `type`, `title`, `date`, `tags`, `last_updated`, `status`, `category`
   - `date` and `last_updated` set to today.
6. Build body sections:
   - `## Context`
   - `## Content`
   - `## Related`
   Prefer same-named sections from source; if absent, place the source body in `Content`.
7. Apply balanced entity linking:
   - Convert hyphenated names and Title-Case multi-word entities to `[[slug|Original Text]]`
   - Skip existing wiki-links, inline/fenced code spans, URLs, and known stopword phrases.
8. For each linked entity with no existing note in the vault, create a `type: memory` stub in `reference/<entity-slug>.md`.
9. Log each created stub as `STUB_CREATED: <path>`.

## Ingestion Contract: Memory Note

**Script:** `ingest_memory.py`
**Input:** Source markdown + explicit metadata flags (`--title`, `--type`, `--layer`, `--topics`, `--projects`, `--priority`)
**Target:** `<layer>/<slug>.md`

CLI:
```bash
python3 knowledge-maester/scripts/ingest_memory.py \
  --source PATH_TO_SOURCE_MD \
  --title "Title" --type TYPE --layer LAYER \
  --topics "t1,t2" --projects "p1" --priority PRIORITY \
  [--vault-path PATH] [--related "slug1,slug2"]
```

Steps (create mode):
1. Read source markdown and parse frontmatter/body.
2. Derive slug from `--title` (lowercase, hyphenated, max 60 chars).
3. Build target path `<layer>/<slug>.md`.
4. Build D1 frontmatter (title/type/layer/topics/projects/status/date/last_updated/priority/token metadata).
5. Build D1 body sections:
   - `# <title>`
   - `## Summary`
   - `## Guidance`
   - `## Related`
6. Merge explicit `--related` values with source wikilinks to populate `## Related`.
7. Write note to the memory vault.
8. Create stub notes for linked targets that do not exist yet.
9. Log each created stub as `STUB_CREATED: <path>`.

Update mode:
```bash
python3 knowledge-maester/scripts/ingest_memory.py \
  --update --note-path RELATIVE_PATH \
  --source PATH_TO_UPDATE_MD \
  [--vault-path PATH]
```

Steps (update mode):
1. Read existing note at `<vault-path>/<note-path>`.
2. Read update source markdown.
3. Merge guidance points (append new deduplicated items).
4. Merge related wikilinks (add newly discovered links only).
5. Update frontmatter (`last_updated`, and metadata merges from source where provided).
6. Write updated note and create stubs for any newly added links.

## Stub Note Format

```markdown
---
type: <type>
title: "<Name>"
date: YYYY-MM-DD
tags: []
last_updated: YYYY-MM-DD
status: active
<type-specific required fields with empty values>
---

*Stub — no content yet.*
```

## Filename Safety Rules

- Lowercase only, hyphens for spaces, no special chars
- Max 80 chars total (including `.md` extension)
- Date prefix `YYYY-MM-DD-` for time-stamped notes (report, analysis)
- Cite key as-is for paper notes (already safe)
- Ticker symbols UPPERCASE with `.md` extension

## Idempotency

All ingestion scripts are idempotent. Running the same source twice produces the same note. If the vault note already exists and is newer than the source, the script exits cleanly with a log message: `NOTE_EXISTS_AND_CURRENT: <path>`.
