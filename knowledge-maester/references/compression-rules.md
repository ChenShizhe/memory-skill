# Compression Rules

Rules for compressing and archiving aged market notes.

## What Gets Compressed

Only **market notes** older than the configured threshold (default: 30 days based on `last_updated`):
- `market/reports/*.md`
- `market/analysis/*.md`
- `market/tickers/*.md` (only if `status: stale`)

**Never compress:**
- `literature/` notes of any type
- `reference/` notes
- `market/archive/` notes (already compressed)
- Notes with `status: active` if updated within threshold

## Compression Process

### Step 1: Identify Candidates

Query all notes in `market/reports/` and `market/analysis/` where:
- `last_updated` is older than `--days` (default 30)
- `status` is `active` or `stale`

### Step 2: Extract Durable Content

From each candidate note, extract:
- **Key findings** that remain valid beyond the news cycle
- **Confirmed predictions** from `## Predictions` sections
- **Ticker-level signals** that could inform future analysis
- **Data points** (prices, metrics) that are historically significant

Discard:
- Time-sensitive alerts or breaking-news context
- Short-term catalysts that have already played out
- Redundant background context

### Step 3: Write Compressed Summary

Create a new note in `market/archive/` with:
```
market/archive/YYYY-MM-DD-<original-slug>-archive.md
```

Frontmatter:
```yaml
type: report  # (or analysis)
title: "[Archive] <original title>"
date: <original date>
tags: <original tags + ["archived"]>
last_updated: <today>
status: archived
watchlist: <original watchlist>
archived_from: <original path>
archive_date: <today>
```

Body:
```markdown
# [Archive] <title>

*Archived from [[<original-slug>]] on YYYY-MM-DD. Original covered <time window>.*

## Durable Findings
[Extracted key findings]

## Confirmed Predictions
[Predictions that resolved]

## Historical Data Points
[Prices, metrics, events with dates]

## Links
- Original: [[<original-slug>]]
- Related: [[...]]
```

### Step 4: Move Original

1. Update original note's `status` to `archived` and `last_updated` to today.
2. Move original file to `market/archive/<original-slug>.md`.
3. Update backlinks: any notes that linked to the original must now also link to the archive copy. (Do this via a search of `[[<original-slug>]]` across vault.)

### Step 5: Update Ticker Backlinks

For each ticker in the original note's `watchlist`, update its `## Appearances` AUTO-GENERATED section to link to the archive copy instead.

## Dry Run Mode

With `--dry-run`, the script:
- Identifies all compression candidates
- Prints a summary table (note path, age, estimated durable content %)
- Does NOT modify any files

## Compression Ledger

After each run, append to `market/archive/_compression-log.md`:

```markdown
## YYYY-MM-DD Compression Run
- Compressed: N notes
- Archived to: market/archive/
- Notes list: [paths]
- Estimated durable content: N% average
```

## Hard Rules

- Literature notes are NEVER compressed
- Archive notes are NEVER compressed again
- Always create the archive copy BEFORE deleting or modifying the original
- Preserve all `<!-- human-annotated -->` content in archive copies
- Do not compress if `--dry-run` is active
