# Graph Health

Rules and checks for maintaining Citadel vault graph integrity.

## What check_graph.py Detects

### 1. Broken Wiki-Links

A `[[target]]` reference where no note file exists with a matching stem.

- Matching logic: lowercase the target, convert spaces to hyphens, check if `<target>.md` exists anywhere in the vault.
- Exempt: `[[_index]]`, `[[_dashboard]]`, `[[_catalog]]` (generated index notes).
- Severity: **WARNING** — does not fail the check, but should be resolved.

Resolution options:
- Create a stub note at the expected path.
- Remove the broken link if the entity is no longer relevant.

### 2. Orphan Notes

A note with neither incoming nor outgoing `[[wiki-links]]`.

- Exceptions: `_index.md`, `_dashboard.md`, `_catalog.md`, and any note in `templates/`.
- Severity: **WARNING**

Resolution: Add a link from or to a related note.

### 3. Missing Required Frontmatter

A note missing any field from the required frontmatter set (`type`, `title`, `date`, `tags`, `last_updated`, `status`).

- Severity: **ERROR** — causes validate_vault.py to fail.

Resolution: Add the missing fields.

### 4. Invalid Frontmatter Values

- `type` not in `{report, paper, ticker, analysis, digest, memory}`
- `status` not in `{active, archived, stale, draft}`
- `date` or `last_updated` not parseable as ISO date

Severity: **ERROR**

### 5. Stale Notes

A note where `last_updated` is older than the type's stale threshold (see vault-schema.md) and `status` is still `active`.

- Severity: **INFO** — flagged for human review only.

Resolution: Update the note with fresh information or change `status` to `stale`.

### 6. Duplicate Cite Keys

Two notes in `literature/papers/` with the same `cite_key` frontmatter value.

- Severity: **ERROR**

### 7. Paper-Bank Manifest Drift

A paper note with a `bank_path` that doesn't exist in `paper-bank/_manifest.json`, or a manifest entry with no corresponding vault note.

- Severity: **WARNING**

## check_graph.py Output Format

JSON report written to `--output` path (or printed to stdout if omitted):

```json
{
  "vault_path": "...",
  "checked_at": "YYYY-MM-DDTHH:MM:SSZ",
  "summary": {
    "total_notes": 0,
    "errors": 0,
    "warnings": 0,
    "info": 0
  },
  "issues": [
    {
      "severity": "WARNING",
      "type": "broken_link",
      "note": "market/reports/2026-03-14-energy-brief.md",
      "detail": "[[XOM]] not found in vault"
    }
  ]
}
```

Exit code:
- `0` — no errors (warnings OK)
- `1` — one or more errors found

## When to Run

- After any batch ingestion of 5+ notes
- Before deploying a compressed archive batch
- After manually editing vault notes
- As part of weekly maintenance

## Acceptable Graph Patterns

The following are intentional and should not be flagged:

- Stub notes with no outgoing links (they exist to receive backlinks)
- Template files with no frontmatter (in `templates/` directory — skip entirely)
- The `zotero/` directory (managed by Zotero MCP — do not validate its internal structure)
