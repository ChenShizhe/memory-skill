# Vault Schema

## Note Types

The vault uses six note types. Each has type-specific frontmatter and a shared body structure.

### Required Frontmatter Fields (all types)

| Field | Type | Description |
|---|---|---|
| `type` | string | Note type identifier (see below) |
| `title` | string | Human-readable note title |
| `date` | ISO date | Date note was first created |
| `tags` | list | Semantic tags for search/grouping |
| `last_updated` | ISO date | Date note was last modified |
| `status` | string | `active` \| `archived` \| `stale` \| `draft` |

### Type: `report`

Target directory: `market/reports/`
Filename convention: `YYYY-MM-DD-<slug>.md`

Additional frontmatter:
```yaml
type: report
watchlist: []          # list of ticker symbols mentioned
time_window: ""        # e.g. "2026-03-07 to 2026-03-14"
confidence: ""         # low | medium | high
sources_count: 0
project_name: ""       # source project
run_id: ""             # source run
```

Body sections (in order):
```markdown
## Key Findings
## Analysis
## Market Dashboard
## Risks and Counterarguments
## Source Index
| ID | Source | Date | Type |
|---|---|---|---|
## Links
- Related: [[note-1]], [[note-2]]
```

### Type: `paper`

Target directory: `literature/papers/`
Filename convention: `<cite_key>.md`

Additional frontmatter:
```yaml
type: paper
cite_key: ""           # e.g. author2024topic
canonical_id: ""       # DOI or arXiv ID
authors: []
year:
content_status: ""     # full-text | abstract-only | unavailable
review_status: draft   # draft | reviewed | archived
bank_path: ""          # path under paper-bank/ (e.g. author2024topic/)
```

Body sections:
```markdown
## Summary
## Key Claims
## Methodology
## Links
- Related: [[note-1]]
- Cites: [[cite_key]]
```

### Type: `ticker`

Target directory: `market/tickers/`
Filename convention: `<SYMBOL>.md` (uppercase)

Ticker notes come in two shapes — **stub** and **profile** — that share the `type: ticker` identifier and the same filename convention.

#### Ticker stub

Stubs are auto-created by `ingest_report.py` and `ingest_analysis.py` whenever a ticker symbol is mentioned in an ingested report or analysis. A stub is a minimal shell that other notes can back-link into via the AUTO-GENERATED Appearances section.

Frontmatter:
```yaml
type: ticker
symbol: ""             # e.g. NVDA
name: ""               # company name
sector: ""
watchlist: []          # report notes that include this ticker
```

Body sections:
```markdown
## Thesis
## Key Metrics
## Catalysts
## Risks
## Notes
<!-- AUTO-GENERATED: backlinks updated by knowledge-maester -->
## Appearances
- [[report-note-1]]
<!-- /AUTO-GENERATED -->
```

#### Ticker profile

Profiles are richer specialist-produced documents, ingested via `ingest_ticker.py`. A profile uses a two-layer structure: static `## Fundamentals` + append-only `## Thesis updates` with dated blocks. Each dated block carries a three-layer structure (YAML brief + low-level evidence block + high-level thesis-update block).

Additional profile frontmatter (extends the stub frontmatter):
```yaml
type: ticker
symbol: ""
name: ""
sector: ""
exchange: ""               # e.g. NYSE, NASDAQ, SHSE
watchlist: []
profile_layers:            # enumerates the layers present in the body
  - fundamentals
  - thesis_updates
owner_specialist: ""       # e.g. power-grid-specialist
source_caveats: ""         # single-line note on source completeness
```

Body sections:
```markdown
## Fundamentals
*Last reviewed: YYYY-MM-DD — <owner_specialist>.*

### Business description
### Segments and revenue breakdown
### Key customers and suppliers
### Geographic footprint
### Management
### Main competitors

## Thesis updates

### YYYY-MM-DD — <brief-trigger> (<owner_specialist>)

```yaml
<structured brief per role-file Output schema>
```

#### Low-level block — what the inputs say
<source-by-source evidence log; no interpretation>

#### High-level block — how this updates the thesis
<thesis-state reasoning; what would move the thesis>

<!-- AUTO-GENERATED -->
## Appearances
<!-- /AUTO-GENERATED -->
```

The AUTO-GENERATED Appearances section is preserved when `ingest_ticker.py --mode create --overwrite` re-creates an existing profile.

Template: `templates/ticker-profile-template.md` (for profiles) and `templates/ticker-template.md` (for stubs).

#### Profile — 10-K-mode summary input

`ingest_ticker.py --mode append-thesis` accepts paper-reader 10-K-mode summary output as an alternative to a hand-drafted thesis-block fragment. Detection is via source frontmatter `mode: 10k`. The script synthesizes a three-layer thesis block from the 14-section summary plus its (optional) claims sidecar and appends it to `## Thesis updates`.

Synthesized YAML brief schema:
```yaml
ticker: <SYMBOL>
brief_date: <filing-date>
brief_trigger: 10-K filing FY<YYYY>
filing: 10-K
fiscal_year: <YYYY>
cite_key: <TICKER>_10k_FY<YYYY>
source_path: <paper-reader-vault-root>/papers/<cite_key>.md
confidence: derived
thesis_state: evolving
one_line_thesis: ""
confidence_rationale: "machine-synthesized from 10-K filing; downstream specialist refinement expected"
key_catalysts: []
key_risks: []
evidence_pointers:
  - papers/<cite_key>.md
  - claims/<cite_key>.json   # only if sidecar resolved
prediction_log_entries: []
segments:                     # parsed from `## Segment Performance` table; `~` if parse fails
  - name: "<segment-name>"
    revenue: "<value>"
    margin: "<value>"
    yoy_change: "<value>"
textual_analysis: ~           # `~` while paper-reader textual-analysis screening (T-009) is unshipped
forward_looking: |
  <verbatim Forward-Looking Statements section>
```

Idempotency for 10-K-mode input is by `cite_key` rather than by date — re-running with the same paper-reader summary returns `NOTE_EXISTS_AND_CURRENT`.

### Type: `analysis`

Target directory: `market/analysis/`
Filename convention: `YYYY-MM-DD-<slug>.md`

Additional frontmatter:
```yaml
type: analysis
related_tickers: []
related_reports: []
confidence: ""
```

Body sections:
```markdown
## Context
## Analysis
## Reasoning Chain
<!-- AUTO-GENERATED -->
- Step 1: ...
<!-- /AUTO-GENERATED -->
## Predictions
## Conclusion
## Sources
## Links
```

### Type: `digest`

Target directory: `literature/digests/`
Filename convention: `<cite_key>-digest.md`

Additional frontmatter:
```yaml
type: digest
source_paper: ""       # note title of the paper
cite_key: ""
field: ""              # e.g. "reinforcement learning"
```

Body sections:
```markdown
## One-Paragraph Summary
## Key Contributions
## Claims Worth Tracking
## Open Questions
## Links
- Paper: [[cite_key]]
```

### Type: `memory`

Target directory: `reference/`
Filename convention: `<slug>.md`

Additional frontmatter:
```yaml
type: memory
category: ""           # e.g. "tool-capability", "workflow", "decision"
```

Body sections:
```markdown
## Context
## Content
## Related
```

## Auto-Generated Sections

Any content between `<!-- AUTO-GENERATED -->` and `<!-- /AUTO-GENERATED -->` may be overwritten by knowledge-maester scripts. Content outside those markers is treated as human-authored and is never modified by polish operations.

## Stale Thresholds

| Note type | Becomes stale after |
|---|---|
| report | 30 days |
| analysis | 60 days |
| ticker | 90 days (if no new reports reference it) |
| paper/digest/field | Never stale |
| memory | Never stale |

## Slug Generation

Slugs are lowercase, hyphen-separated. Special characters removed. Max 60 characters.

Example: `"Energy Market Brief — March 2026"` → `energy-market-brief-march-2026`
