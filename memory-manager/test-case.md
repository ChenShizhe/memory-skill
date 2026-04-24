# Memory-Manager Test Case

This test case validates the first implemented ingestion flow for the `example-project` experience.

## Goal

Confirm that the current `memory-manager` implementation:

1. provides the required instruction structure in `SKILL.md`
2. created the required catalog-index, shard directory, and ledger files
3. extracted long-term memory from the `example-project` experience
4. moved the processed experience out of the active inbox
5. removed the now-empty source folder from the active inbox
6. preserved a non-destructive paper trail
7. owns and documents quota-ledger maintenance

## Expected State

The test should pass only if all of the following are true:

1. `memory-manager/SKILL.md` includes:
   - an index-first shortlist then shard focused-read deduplication algorithm
   - an exact ledger template
   - a sensitive proposal file policy
   - catalog maintenance rules that avoid full rewrites
   - a rule that approved edits to `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, or `USER.md` also refresh the matching entry in `memories/catalog-shards/core-identity.md`
   - a rule that proposal-only runs do not update `memories/catalog-shards/core-identity.md` for those sensitive files
   - an explicit rule to ignore `experiences/processed/` during discovery
   - an explicit rule to remove empty source folders after moving processed files
   - `memories/provider-quotas.md` as a maintained file
   - quota parsing from `## Used Quota`
   - `quota_updates` in the ledger schema
2. `memories/catalog-index.md` exists and lists shard blocks with `description` and `stable_tags`; `memories/catalog-shards/core-identity.md` contains entries for `memories/AGENTS.md`, `memories/SOUL.md`, `memories/IDENTITY.md`, and `memories/USER.md`; the shard file `memories/catalog-shards/workflow-templates.md` is the canonical home for `workflow_template` and `workflow_fragment` entries; other fixture entries land in their routed shards.
3. `memories/archive-catalog.md` exists
4. `memories/manager-ledger.md` exists and records:
   - `experiences/example-project/summary.md`
   - the move into `experiences/processed/example-project/summary.md`
   - a `quota_updates` field
5. `memories/provider-quotas.md` exists and contains:
   - `usage_period_key`
   - `used_total_unit`
   - `allocation_mode`
   - `last_ingested_experience`
   - `last_used_in_run`
6. `memories/example-workflows.md` contains:
   - `Paper-Trail-First Execution`
   - `Skills-As-Portable-Instructions`
7. `memories/example-patterns.md` contains:
   - `Core Workspace Layout`
   - `Credentials-And-Boundaries`
   - `Skill-Onboarding Pattern`
8. `experiences/example-project/summary.md` no longer exists
9. `experiences/processed/example-project/summary.md` exists
10. `experiences/example-project/` no longer exists

## Workflow Template Handling

The test should also verify:

11. `memory-manager/SKILL.md` includes:
    - a Workflow Template Lifecycle section with draft/beta/stable progression
    - a Shared Workflow Fragment Rules section with override protection
    - a Workflow Type Validation section
    - workflow template and shared fragment file contracts with exact templates
    - maturity detection heuristic with success rate threshold
    - updated processing algorithm with workflow reflection extraction
    - updated ledger schema with workflow_template_updates and workflow_type_uncertainties fields
    - catalog entry templates for workflow_template and workflow_fragment types (both land in the `workflow-templates` shard)
    - shared fragment reference notation `→ [shared:<fragment-id>]`

## How To Run

Run:

```bash
python3 memory-manager/test_memory_manager.py
```

The script exits with status `0` on success and non-zero on failure.
