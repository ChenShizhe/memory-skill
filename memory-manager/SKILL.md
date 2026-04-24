---
name: memory-manager
description: Curate central memory from project experiences. Use when asked to ingest files from `experiences/`, maintain searchable short-term and long-term memory, manage archive memory, update the memory catalogs, and clean the active experience inbox non-destructively.
---

# Memory Manager

## Mission

Turn raw project experience files into concise, reusable central memory without losing provenance.

You are the only normal workflow skill allowed to modify searchable memory under `memories/`.
You are also the only normal workflow skill allowed to maintain the operational quota ledger in `memories/provider-quotas.md`.

## Hard Boundaries

- Read raw experience files from `experiences/`.
- Maintain searchable memory in `memories/long-term/` and `memories/short-term/`.
- Maintain archive memory in `memories/archive/`.
- Maintain:
  - `memories/catalog-index.md`
  - `memories/catalog-shards/<shard>.md`
  - `memories/archive-catalog.md`
  - `memories/manager-ledger.md`
  - `memories/provider-quotas.md`
  - `memories/proposals/`
- Clean processed experience files by moving them to `experiences/processed/`.
- Do not delete processed experience files.
- Do not update `memories/SOUL.md`, `memories/IDENTITY.md`, `memories/AGENTS.md`, or `memories/USER.md` without explicit user approval.
- Maintain workflow templates in `memories/workflow-templates/`.
- Maintain shared workflow fragments in `memories/workflow-templates/_shared/`.

## Run Reasons

Supported logical run reasons:

- `manual_ingest`
- `scheduled_ingest`
- `archive_restore`
- `rebuild_catalog`

Default to `manual_ingest` when no explicit reason is provided.

## Inputs

Use these inputs when they are provided by the caller:

- `run_reason`
- `experience_paths`
- `approval_mode`
- `restore_targets`
- `quota_update_mode`

Default behavior:

- if `experience_paths` is omitted, process all unprocessed files in active `experiences/`, while ignoring `experiences/processed/` and hidden files
- if `approval_mode` is omitted, use `propose_sensitive_changes`
- if `quota_update_mode` is omitted, use `ingest_from_experience`

## Searchable Layers

### Long-Term

Long-term memory is durable and searchable. Store:

- crucial decisions
- key execution steps
- durable corrections
- reusable workflow lessons
- recurring project patterns
- reusable domain knowledge
- workflow templates (canonical step sequences, anti-patterns, decision points for each workflow type)

### Short-Term

Short-term memory is searchable but provisional. Store:

- active continuity context
- unresolved follow-ups
- recent decisions that may still change
- ongoing project state likely to matter soon

### Archive

Archive is not searchable by `memory-retriever`. Use it for:

- expired short-term memory
- historical memory worth preserving
- material explicitly restored only by manager request

## File Contract

### Searchable catalog

Searchable long-term and short-term entries live in per-shard files under `memories/catalog-shards/<shard>.md`. Each shard has two subsections: `## Generated Entries` (auto-managed) and `## Manual Entries` (human-frozen). `memories/catalog-index.md` is the manifest; memory-retriever reads it first and opens only shortlisted shards.

Required fields per entry:

- `path`
- `layer`
- `title`
- `type`
- `topics`
- `projects`
- `summary`
- `retrieval_hints`
- `priority`
- `updated`
- `token_cost_estimate`

### Archive catalog

`memories/archive-catalog.md` contains archive entries only.

Required fields per entry:

- `path`
- `original_layer`
- `title`
- `topics`
- `projects`
- `summary`
- `archived_at`
- `restore_hints`

### Ledger

`memories/manager-ledger.md` must record one run entry per execution.

Required fields per run:

- `run_timestamp`
- `run_reason`
- `processed_experience_files`
- `classification_decisions`
- `memory_files_updated`
- `archive_files_updated`
- `catalog_updates`
- `quota_updates`
- `approval_required`
- `experience_moves`
- `workflow_template_updates`
- `workflow_type_uncertainties`

Use this exact append template:

```md
## YYYY-MM-DDTHH:MM:SS+TZ:TZ

- run_reason: manual_ingest
- processed_experience_files:
  - experiences/example-project/summary.md
- classification_decisions:
  - Long-term: ...
  - Short-term: ...
  - Ignore: ...
- memory_files_updated:
  - memories/example.md
- archive_files_updated:
  - none
- catalog_updates:
  - memories/catalog-index.md
  - memories/catalog-shards/<shard>.md
  - memories/archive-catalog.md
- quota_updates:
  - none
- approval_required:
  - none
- experience_moves:
  - experiences/example-project/summary.md -> experiences/processed/example-project/summary.md
- workflow_template_updates:
  - <path to updated or created template file, or "none">
- workflow_type_uncertainties:
  - <any guessed types that need user confirmation, or "none">
```

### Workflow Templates

`memories/workflow-templates/<workflow-type>.md` contains the canonical workflow template for one workflow type.

Required frontmatter fields:

- `workflow_type`
- `version_status` (`draft` | `beta` | `stable`)
- `version_number`
- `sessions_observed`
- `sessions_since_last_change`
- `successful_sessions`
- `failed_sessions`
- `mistake_rate_trend` (`unknown` | `declining` | `flat` | `increasing`)
- `ready_for_review` (`true` | `false`)
- `last_updated`

Required body sections:

- `## Canonical Steps` — numbered list of meaningful phases, may reference shared fragments via `→ [shared:<fragment-id>]`
- `## Anti-Patterns` — bulleted list of "don't do this" rules with source session references
- `## Decision Points` — description of where user intervention typically occurs, with observed default choices
- `## Known Variations` — named variations of the workflow that diverge from the canonical path

Use this exact template for new workflow template files:

```md
---
workflow_type: <type-name>
version_status: draft
version_number: 1
sessions_observed: 1
sessions_since_last_change: 0
successful_sessions: 0
failed_sessions: 0
mistake_rate_trend: unknown
ready_for_review: false
last_updated: YYYY-MM-DD
---

# Workflow Template: <Type Name>

## Canonical Steps

1. [step from first observed session]
2. [step from first observed session]
...

## Anti-Patterns

- [from first session's mistakes_and_corrections, if any]

## Decision Points

- [from first session's decision_points, if any]

## Known Variations

- none yet
```

### Shared Workflow Fragments

`memories/workflow-templates/_shared/<fragment-id>.md` contains a reusable step sequence referenced by multiple workflow templates.

Required frontmatter fields:

- `fragment_id`
- `used_by` (list of workflow types that reference this fragment)
- `version`
- `last_updated`

Required body sections:

- `## Steps` — numbered step list
- `## Anti-Patterns` — anti-patterns specific to this fragment

Use this exact template for new shared fragment files:

```md
---
fragment_id: <id>
used_by: [<workflow-type-1>, <workflow-type-2>]
version: 1
last_updated: YYYY-MM-DD
---

# Shared Fragment: <Name>

## Steps

1. [step]
...

## Anti-Patterns

- [if any]
```

### Quota Ledger

`memories/provider-quotas.md` is operational state, not searchable memory.

Required fields per provider:

- `scope`
- `usage_period_key`
- `used_total`
- `used_total_unit`
- `allocation_mode`
- `last_ingested_experience`
- `last_used_in_run`
- `updated_at_utc`
- `source_experiences`

Keep existing budget and rate-limit fields in place when they are already present.

## Classification Rules

Classify an extracted item as:

- `long-term` when it is durable and should shape future work
- `short-term` when it supports near-term continuity but is still provisional
- `archive` only when it already exists in searchable memory and should be retired from active retrieval
- `ignore` when it is noise, duplicate, or non-reusable

Default promotion rule:

- when in doubt, promote core experiences directly to long-term memory

Core experiences:

- crucial decisions
- key execution steps
- durable corrections
- reusable workflow lessons
- domain knowledge likely to recur

Quota lines from `## Used Quota` are operational data, not memory candidates. Never classify them as `long-term`, `short-term`, `archive`, or `ignore`.

## Deduplication Rules

### Deduplication Algorithm

Deduplication must follow a strict index-first, shard-focused path to control token use.

1. Read `memories/catalog.md` first — historically the flat catalog; now replaced by reading `memories/catalog-index.md` first to pick 1–2 candidate shards, then reading those shards.
2. Shortlist only entries whose `topics`, `projects`, `type`, or `summary` indicate a plausible overlap.
3. Open only the specific memory files referenced by those shortlisted catalog entries.
4. Compare the candidate item against those opened files.
5. If no catalog entry suggests overlap, do not scan the full `memories/` tree.

Never deduplicate by reading every searchable memory file from scratch.

Treat an item as duplicate if all are true:

- same core lesson
- same target project or same workflow area
- no meaningful new guidance
- no materially newer correction

If a new item improves an existing one, merge it and refresh metadata instead of creating a parallel entry.

## Processing Algorithm

1. Discover active experience files unless explicit `experience_paths` are provided.
2. During discovery, scan only active project folders under `experiences/`.
3. Never search inside `experiences/processed/`.
4. Ignore hidden files and hidden directories such as `.DS_Store`.
5. Skip files already recorded as processed in `memories/manager-ledger.md`.
6. Read one experience file at a time.
7. Parse the `## Used Quota` section if it exists and normalize quota records.
8. Update `memories/provider-quotas.md` from those normalized quota records before moving the experience file.
9. Extract candidate memory items from the non-quota remainder of the experience file.
10. Classify each item as `long-term`, `short-term`, `archive`, or `ignore`.
11. If the experience file contains a `## Workflow Reflection` block, extract workflow metadata.
12. Process the workflow reflection: create or update the matching workflow template per the Workflow Template Lifecycle rules. Validate the workflow type per the Workflow Type Validation rules.
13. Check for shared fragment extraction opportunities per the Shared Workflow Fragment Rules.
14. Deduplicate against searchable memory and catalogs.
15. Generate a slug via `vault_io.slugify()` and choose the layer directory (`memories/long-term/` or `memories/short-term/`).
15a. **Route to shard.** Call `route_card(frontmatter)` (see Shard Routing section) and record the shard name on the ingestion record. The card body still goes to its `long-term/<slug>.md` or `short-term/<slug>.md` path as before; the shard receives the catalog entry (the `## <slug>` block with its metadata), not the body.
15b. **Route-proposal filing.** If `route_card` returned `misc.md`, run `generate_route_candidates(frontmatter)` and call `file_route_proposal(card, candidates)` to write `memories/proposals/ROUTE-<slug>-<date>.md` per the Route Proposal Policy. Record the proposal filing in the ledger. Do not block ingestion; the card is still written to `misc.md` as described in step 15a.
16. If the destination is sensitive, prepare a proposal and do not apply the change.
17. For ADD invoke `ingest_memory.py`; for UPDATE invoke `ingest_memory.py --update`; for DELETE move the note file to `memories/archive/`.
17a. Run memory evolution: scan catalog entries for topic overlap (at least 2 shared topics), update `## Related` on up to 5 neighbor notes with reciprocal links, and do not update neighbors' `last_updated` for link-only edits.
17b. Run hub maintenance: add new notes to matching hubs, create hubs when a topic cluster reaches at least 4 notes, and run cleanup for hubs with fewer than 2 members.
18. Review searchable short-term memory for promotion or archive movement.
19. For normal runs do targeted catalog updates: append/replace the entry in the Generated subsection of the target shard file (`memories/catalog-shards/<shard>.md`) and update the matching shard block's `card_count` and `last_updated` fields in `memories/catalog-index.md` in place. For `rebuild_catalog` run reason invoke `python3 knowledge-maester/scripts/generate_memory_catalog.py --vault-path memories/`.
20. Update `memories/archive-catalog.md` when needed.
21. Move processed experience files to `experiences/processed/`.
22. After moving a processed file, remove any now-empty source directories, pruning upward until reaching `experiences/` or a non-empty directory.
23. Append the run to `memories/manager-ledger.md`.

## Memory Evolution Rules

Run memory evolution after creating a new long-term note (or updating a long-term note with materially new topics).

Algorithm:

1. Read the note's frontmatter `topics`.
2. If the note is short-term, skip evolution.
3. Scan `memories/catalog-index.md` and the relevant shards under `memories/catalog-shards/` for candidate notes with topic overlap of at least 2 shared topics.
4. Exclude hub notes (`type: hub`) from candidate targets.
5. Sort candidates by overlap count descending, then by recency (`updated`) descending.
6. Keep at most 5 candidates.
7. For each candidate:
   - add `[[<new-note-slug>]]` to its `## Related` section if missing, with a short relationship reason
   - do not change frontmatter `last_updated` on that neighbor because this is a metadata-only link edit
8. In the new note's `## Related`, add reciprocal `[[candidate-slug]]` links if missing.
9. Keep operations idempotent: never duplicate an existing wikilink.

Skip conditions:

- short-term notes never trigger evolution
- hub notes are never evolution targets

## Hub Maintenance Rules

Maintain hubs during ingestion, not by a separate scheduled tool.

Rules:

1. Add to existing hub:
   - for a new long-term note, compare its `topics` to each hub note's `topics`
   - if overlap is at least 2 topics, add the note link to that hub's `## Members` if missing
2. Create new hub:
   - after evolution, for each topic, check long-term non-hub notes in that topic cluster
   - if cluster size is at least 4 and no hub covers that topic, create `memories/long-term/_hub-<topic-slug>.md` using the hub schema and add all cluster members
   - add the hub to `memories/catalog-shards/hubs.md` (Generated subsection) and refresh `card_count` / `last_updated` for the `hubs` shard in `memories/catalog-index.md`
3. Remove undersized hubs:
   - when note archival or cleanup leaves a hub with fewer than 2 members, delete the hub file and remove its catalog entry
4. Cleanup pass on every ingest:
   - scan all `memories/long-term/_hub-*.md` files
   - for each hub with fewer than 2 members, delete the hub file and remove its catalog entry
   - strip `[[_hub-*]]` links from former member notes' `## Related` sections

## Knowledge-Maester Integration

- All long-term and short-term note writes must go through `python3 knowledge-maester/scripts/ingest_memory.py` (create and update modes).
- Graph validation for memory writes must use:

```bash
python3 knowledge-maester/scripts/check_graph.py --vault-path memories/ --schema memory
```

## Quota Update Rules

Update quota state only from `## Used Quota` lines in ingested experience logs.

Accepted quota line shapes:

- `Provider: Tavily | Scope: monthly | Used in run: 3`
- `Provider: Tavily | Scope: monthly | Used before run: 0 | Used in run: 3 | Used after run: 3`
- the same line plus `| Source: bootstrap_zero` or similar

Normalize each parsed line into:

- `provider`
- `scope`
- `used_in_run`
- optional `used_before_run`
- optional `used_after_run`
- optional `source`

Parsing rules:

- ignore surrounding whitespace
- match provider names case-insensitively
- if multiple lines for the same provider exist in one experience file, prefer the largest `used_after_run`; otherwise keep the largest `used_in_run`
- malformed quota lines are non-fatal and must be recorded under `quota_updates`

Update rules:

1. Match the provider against an existing section in `memories/provider-quotas.md`.
2. If the provider does not exist, skip it and record the skip in `quota_updates`.
3. Compute `usage_period_key` from the experience date and the provider `scope`.
4. If the stored `usage_period_key` is absent, initialize it.
5. If the stored `usage_period_key` belongs to an older period, reset `used_total` to `0` and replace the period key.
6. Prefer `used_after_run` as the cumulative snapshot when it exists.
7. If `used_after_run` is absent, treat `used_in_run` as a per-run delta and add it to the stored `used_total`.
8. When both snapshot and delta lines exist for the same provider in one experience, prefer the snapshot and do not add the delta on top.
9. Update `last_ingested_experience`, `last_used_in_run`, and `updated_at_utc`.
10. Append the experience path to `source_experiences`, dedupe identical paths, and keep only the most recent `5`.

The snapshot-first rule avoids double-counting cumulative quota snapshots when experience files are ingested out of order, while delta-only lines remain safe because each experience file is ingested once and then moved to `experiences/processed/`.

Boundary rules:

- never infer quota usage from prose outside `## Used Quota`
- never add `memories/provider-quotas.md` to `memories/catalog-index.md` or any `memories/catalog-shards/<shard>.md`
- never let malformed quota lines block normal memory ingestion
- never auto-create provider sections from arbitrary experience text

## Catalog Maintenance Rules

When updating `memories/catalog-shards/<shard>.md`, `memories/catalog-index.md`, or `memories/archive-catalog.md`:

- always use targeted append or targeted in-place updates
- append a new entry when the memory item is new (target the `## Generated Entries` subsection of the routed shard; never write to `## Manual Entries` automatically)
- update only the affected entry when metadata changes
- after every ingestion, update `memories/catalog-index.md` by recomputing the target shard's `card_count` (count `## ` slug headings across both subsections of the shard file) and `last_updated` (max `updated:` across cards in the shard); `description` and `stable_tags` are hand-edited and must never be rewritten by ingestion
- if an approved edit changes `memories/USER.md`, `memories/SOUL.md`, `memories/IDENTITY.md`, or `memories/AGENTS.md`, refresh the matching entry in `memories/catalog-shards/core-identity.md` in the same run
- never regenerate the full catalog from scratch during a normal ingest run

Rebuild the full catalog only when the run reason is `rebuild_catalog`, and do it by invoking:

```bash
python3 knowledge-maester/scripts/generate_memory_catalog.py --vault-path memories/
```

When creating or updating workflow template files:
- add or update a dedicated catalog entry in the `workflow-templates` shard (`memories/catalog-shards/workflow-templates.md`, Generated subsection) for each template
- add or update a dedicated catalog entry in the same `workflow-templates` shard for each shared fragment
- workflow template catalog entries use `type: workflow_template`
- shared fragment catalog entries use `type: workflow_fragment`

Catalog entry template for workflow templates:

```md
## workflow-template-<type-name>

- path: memories/workflow-templates/<type-name>.md
- layer: long-term
- title: Workflow Template — <Type Name>
- type: workflow_template
- topics: [workflow, <type-name>, automation-template]
- projects: [learning-by-doing]
- summary: <one-line description of this workflow type>
- retrieval_hints: Use when the current task involves <type-specific trigger>.
- priority: high
- updated: YYYY-MM-DD
- token_cost_estimate: <estimate>
```

Catalog entry template for shared fragments:

```md
## workflow-fragment-<fragment-id>

- path: memories/workflow-templates/_shared/<fragment-id>.md
- layer: long-term
- title: Workflow Fragment — <Name>
- type: workflow_fragment
- topics: [workflow, shared-fragment, <relevant-topics>]
- projects: [learning-by-doing]
- summary: <one-line description of what this fragment covers>
- retrieval_hints: Use when the current task includes <fragment-specific trigger>.
- priority: medium
- updated: YYYY-MM-DD
- token_cost_estimate: <estimate>
```

## Shard Routing

Every new or updated searchable memory card is routed to exactly one shard under `memories/catalog-shards/<shard>.md`. Routing is deterministic and follows a priority-ordered rule set. First match wins.

The routing function is `route_card(card_frontmatter) -> shard_name`, implemented in `bootstrap.py`. See that file for the canonical rule ladder.

Shards have two subsections: `## Generated Entries` (auto-managed) and `## Manual Entries` (human-frozen; never auto-rewritten). Routing targets the Generated subsection; ingestion writes go there.

When routing returns `misc.md`, the card is still written to `misc.md` immediately, and the manager files a `ROUTE-<slug>-<date>.md` proposal per the Route Proposal Policy. Ingestion does not block on the proposal; resolution happens during an interactive maintenance run (see Misc Review).

Catalog index bookkeeping (surgical, in-place update on every ingestion):

- Recompute `card_count` for the target shard by counting `## ` slug headings across both subsections of the shard file.
- Recompute `last_updated` for the target shard as the max `updated:` across cards in the shard.
- Rewrite only those two fields under the matching `### <shard-name>` block in `catalog-index.md`. `description` and `stable_tags` are never touched by ingestion.

## Git Integration Rules

If git integration has been enabled for `memories/`, perform the git step only after a successful ingest run has finished all file writes and moves.

Post-ingest git rules:

1. Check whether `memories/` is a git repo.
2. If it is not a git repo, report `git integration not enabled` and finish successfully.
3. If it is a git repo and there is no diff, do nothing.
4. If it is a git repo and there is a diff, run:

```bash
# Optional: python3 <workspace>/tools/git-integration/memories_commit.py \
#   --repo-path memories \
#   --message "memory-manager: ingest <run_reason> on YYYY-MM-DD"
```

5. Never attempt a remote push for `memories/`.
6. If the git helper fails, keep the ingested memory changes on disk, report the git failure, and do not roll back the ingest result.

This repo-commit step is local-only and is separate from the ledger append.

## Sensitive File Policy

Do not directly edit these files without approval:

- `memories/USER.md`
- `memories/SOUL.md`
- `memories/IDENTITY.md`
- `memories/AGENTS.md`

When a sensitive update is indicated:

- write the proposal to `memories/proposals/UPDATE-[FILENAME]-[DATE].md`
- include the exact intended change, the reason, and the source experience file
- record it in the ledger
- leave the file unchanged
- do not update `memories/catalog-shards/core-identity.md` yet if the run produced only a proposal
- once explicit user approval allows the core file edit to be applied, update the matching entry in `memories/catalog-shards/core-identity.md` (Generated subsection) in the same run so the searchable metadata stays aligned, and refresh `memories/catalog-index.md` for the `core-identity` shard (`card_count` / `last_updated` only)

Use this exact proposal template:

```md
# Proposed Update: USER.md

- created_at: YYYY-MM-DDTHH:MM:SS+TZ:TZ
- target_file: memories/USER.md
- source_experience: experiences/example-project/summary.md
- reason: Stable user preference detected during memory ingestion.

## Proposed Change

<write the exact proposed markdown addition or edit here>
```

## Route Proposal Policy

When ingestion routes a card to `catalog-shards/misc.md` (the fall-through case in the shard-routing ladder), the manager does not leave the routing unreviewed. Ingestion completes normally and writes the card to `misc.md`. In the same run, the manager files a routing proposal at `memories/proposals/ROUTE-<slug>-<date>.md` describing the ambiguous card and the shards the manager considered.

Use this exact template:

```md
# Proposed Route: <card-slug>

- created_at: YYYY-MM-DDTHH:MM:SS+TZ:TZ
- proposal_type: route_ambiguous_card
- card_slug: <slug>
- card_path: memories/<layer>/<slug>.md
- current_shard: catalog-shards/misc.md
- source_experience: experiences/<project>/<file>.md
- reason: Routing rules produced no match; card defaulted to misc.

## Routing signals

- type: <frontmatter type value>
- topics: <frontmatter topics list>
- projects: <frontmatter projects list>

## Candidate shards

The manager's shortlist of plausible shards with rationale per shard:

- [ ] catalog-shards/<shard-name-a>.md — <why this might fit>
- [ ] catalog-shards/<shard-name-b>.md — <why this might fit>
- [ ] propose new shard: <name> — <why a new shard might be warranted>
- [ ] confirm misc (no clear shard; card stays in misc pending periodic review)

## User decision

<!-- Check exactly one option above during an interactive memory-manager run. The manager reads this block and acts. -->
```

The candidate shards list is generated by running the routing ladder in diagnostic mode: for each shard, compute what rule(s) would fire if the card had slightly different metadata; present the 2–3 most plausible alternatives with the triggering rule's name. If no alternatives are plausible, list only `confirm misc`.

Record the proposal filing in `memories/manager-ledger.md` in the same shape as UPDATE-* proposals.

ROUTE-* proposals do not block ingestion. The card lives in misc until a maintenance run resolves the proposal. Unlike UPDATE-* proposals (which keep a sensitive target file unchanged until approval), ROUTE-* proposals record a pending re-home decision, not a pending write.

## Capacity Signals

memory-manager emits soft-threshold signals during ingestion so the catalog does not silently grow past its usable range. Signals are append-only notes to the ingestion receipt; they do not block any operation.

Thresholds:

- **Misc count ≥ 15**: at the end of ingestion, append `[SIGNAL] misc-shard at <N> cards — consider a maintenance review to re-home or archive.` to the ingestion receipt.
- **Total catalog cards ≥ 500**: append `[SIGNAL] catalog at <N> cards — consider Phase 2 (derived frontmatter query index; see memory-retriever-improvement project for design).` to the ingestion receipt.
- **Pending proposal count ≥ 10**: append `[SIGNAL] <N> proposals pending — run memory-manager in approval_mode to resolve.` to the ingestion receipt.

Thresholds are constants defined at the top of `bootstrap.py` (e.g., `MISC_SOFT_THRESHOLD = 15`, `CATALOG_PHASE2_THRESHOLD = 500`, `PROPOSAL_REVIEW_THRESHOLD = 10`), tunable without schema changes.

Signals appear only when the threshold is crossed; they are not emitted on every ingestion once surpassed. Specifically, if the previous ingestion already emitted the signal for a given threshold, and the count has not dropped below the threshold and then re-crossed, do not re-emit. Implementation hint: track "last emitted at count" in `manager-ledger.md` per-threshold and only emit when the count transits the threshold upward.

### Misc Review (maintenance mode)

When memory-manager runs with `approval_mode=propose_sensitive_changes` (or any interactive mode that processes pending proposals), after handling UPDATE-* proposals, the manager processes ROUTE-* proposals:

1. List every pending `memories/proposals/ROUTE-*.md` file, sorted by `created_at` ascending.
2. For each proposal, present the proposal body to the user and wait for the checked box.
3. Based on the user's choice:
   - `catalog-shards/<name>.md`: move the card's entry from `misc.md` to `<name>.md` (append or replace) and update the index's `card_count` and `last_updated` for both shards.
   - `propose new shard: <name>`: create `catalog-shards/<name>.md` with the standard shard header, move the card's entry there, add a new block to `catalog-index.md` with a placeholder description (`TODO: describe shard purpose`) and empty `stable_tags` for the user to fill in later, and update the "Registered projects" line if the new shard is project-scoped.
   - `confirm misc`: leave the card in misc, but mark the proposal with `resolution: confirmed_misc` and move it to `memories/proposals/resolved/`.
4. After acting on each proposal, move the proposal file to `memories/proposals/resolved/YYYY-MM/` (create subdirs as needed) and record the resolution in `manager-ledger.md`.
5. After all ROUTE-* proposals are resolved, run a direct misc-shard review: for any card still in `misc.md`, offer the same action set. This catches cards that were quarantined without a formal proposal (e.g., via manual write).

## Cleanup Policy

"Clean" means:

- remove processed files from the active inbox
- move them to `experiences/processed/<project>/`
- remove any source directories that become empty after the move
- preserve provenance
- never hard-delete in v1

## Workflow Template Lifecycle

Workflow templates progress through three statuses: `draft`, `beta`, `stable`.

### Creation

When ingesting an experience log with a `## Workflow Reflection` block and no existing template matches the `workflow_type`:

1. Create `memories/workflow-templates/<workflow-type>.md` using the template above.
2. Set `version_status: draft`.
3. Populate `## Canonical Steps` from the reflection's `steps_taken`.
4. Populate `## Anti-Patterns` from the reflection's `mistakes_and_corrections` lessons.
5. Populate `## Decision Points` from the reflection's `decision_points`.
6. Add a catalog entry for the new template.
7. Create the `memories/workflow-templates/` directory if it does not exist.

### Merging

When ingesting an experience log with a `## Workflow Reflection` block and an existing template matches the `workflow_type`:

1. Compare `steps_taken` against the template's `## Canonical Steps`.
2. Reinforce steps that match — these are confirmed patterns.
3. If new steps appear, add them to the appropriate position or to `## Known Variations`.
4. Integrate `mistakes_and_corrections` lessons into `## Anti-Patterns`, deduplicating against existing entries.
5. Update `## Decision Points` with any new observations.
6. Increment `sessions_observed`.
7. If the template body changed: reset `sessions_since_last_change` to `0`.
8. If the template body did NOT change: increment `sessions_since_last_change`.
9. Update `successful_sessions` or `failed_sessions` based on `project_outcome`.
10. Recompute `mistake_rate_trend`:
    - Compare the number of mistakes in the latest session against the average from prior sessions.
    - If trending down or zero: `declining`. If roughly the same: `flat`. If trending up: `increasing`. If insufficient data: `unknown`.
11. Update `last_updated`.
12. Update the catalog entry metadata.

### Promotion: Draft → Beta

Promote a draft to beta when:
- `sessions_observed >= 3`
- At least 2 sessions have confirmed the same core step sequence

On promotion:
- Set `version_status: beta`
- Do not change `version_number`

### Maturity Detection: Beta → Ready for Review

Flag a beta as `ready_for_review: true` when all conditions are met:
- `sessions_observed >= 5`
- `sessions_since_last_change >= 2`
- `mistake_rate_trend` is `flat` or `declining`
- `successful_sessions / sessions_observed >= 0.6`

When flagging:
- Set `ready_for_review: true`
- Add a `## Review Prompt` section at the bottom of the template file summarizing what has changed since the last stable version (or since creation if no stable version exists)

### Promotion: Beta → Stable (user-initiated)

When the user reviews and approves a beta template:
- Set `version_status: stable`
- Set `ready_for_review: false`
- Remove the `## Review Prompt` section

### Continued Learning After Stable

After a stable version is established:
- New session data accumulates into a **new beta version**: copy the stable template, set `version_status: beta`, increment `version_number`, reset maturity metrics.
- The stable version remains untouched and continues to be served by memory-retriever.
- Store the new beta alongside the stable version by using the frontmatter `version_number` to distinguish them. The file name stays the same — only one version per file. When a new beta is started, rename the stable file to `<workflow-type>-stable-v<N>.md` as a snapshot, then update the main `<workflow-type>.md` to be the new beta.
- When the new beta matures and is approved, it becomes the new stable, and the cycle repeats.

## Shared Workflow Fragment Rules

Shared fragments are reusable step sequences referenced by multiple workflow templates via `→ [shared:<fragment-id>]` notation in the `## Canonical Steps` section.

### Creation

When the manager detects that two or more workflow templates contain the same step sequence (at least 2 consecutive steps that are semantically identical):

1. Extract the common steps into a new shared fragment in `memories/workflow-templates/_shared/<fragment-id>.md`.
2. Replace the duplicated steps in each referencing template with `→ [shared:<fragment-id>]`.
3. Update the fragment's `used_by` list.
4. Add a catalog entry for the shared fragment.

Shared fragments can also be created proactively during the first template creation if the steps are clearly universal (e.g., memory retrieval at session start).

### Override Protection

When updating a shared fragment during ingestion:

1. Identify the source workflow type that triggered the update.
2. Check if the proposed change is universally beneficial (applies to all workflows that reference this fragment) or workflow-specific.
3. If **universally beneficial**: apply the change to the shared fragment. Update `version` and `last_updated`.
4. If **workflow-specific**: do NOT modify the shared fragment. Instead, add the change as a local note in the referencing workflow template's `## Known Variations` or `## Anti-Patterns` section, noting that it overrides the shared fragment for this workflow type.
5. Log the decision in the ledger entry under `classification_decisions`.

### Determining Universal vs. Specific

A change is universally beneficial if:
- It corrects an error that would affect all workflows (e.g., a step that is factually wrong)
- It adds an anti-pattern that applies regardless of workflow type
- It improves a step description for clarity without changing semantics

A change is workflow-specific if:
- It adds a step that only makes sense for one workflow type
- It modifies the order of steps in a way that only benefits one workflow type
- It adds an anti-pattern triggered by a workflow-specific mistake

## Workflow Type Validation

During ingestion, validate the `workflow_type` from the `## Workflow Reflection` block:

1. If `workflow_type_confidence` is `confirmed`: accept the type as-is.
2. If `workflow_type_confidence` is `proposed`: accept the type. If it starts with `new:`, add it to the known types list by creating a new template.
3. If `workflow_type_confidence` is `guessed`: compare the reported `steps_taken` against existing templates. If the steps closely match an existing template for a different type, record the mismatch as an uncertainty in the ledger under `classification_decisions` with a note for the user to confirm. Use the guessed type for processing but flag it.

The canonical list of known workflow types is derived from the set of files in `memories/workflow-templates/` (excluding `_shared/`).

## Memory Shape

Each memory item is its own atomic note file. Never append multiple memory items into a single note body.

File naming and location:

- slugify title with `vault_io.slugify()`
- enforce lowercase hyphen-separated slug with max length 60
- write to `memories/long-term/<slug>.md` or `memories/short-term/<slug>.md` based on classification

Use this note template for each memory file:

```yaml
---
title: "Entry Title"
type: workflow
layer: long-term
topics: [topic-1, topic-2]
projects: [project-name]
source_projects: [project-name]
status: active
date: 2026-03-15
last_updated: 2026-03-15
priority: high
token_cost_estimate: 50
retrieval_hints: "Use when ..."
---
```

```md
# Entry Title

## Summary
One short paragraph describing the core lesson.

## Guidance
- concrete actionable point one
- concrete actionable point two

## Related
- [[other-note]] - relationship reason
```

Example create invocation:

```bash
python3 knowledge-maester/scripts/ingest_memory.py \
  --source /tmp/memory-extract-entry-title.md \
  --title "Entry Title" \
  --type workflow \
  --layer long-term \
  --topics "topic-1,topic-2" \
  --projects "project-name" \
  --priority high \
  --vault-path memories/
```

## Success Conditions

A good run:

- updates the right searchable memory files
- keeps archive out of normal retrieval
- updates catalogs and ledger consistently
- does not duplicate processed experiences
- leaves a clean, inspectable paper trail
