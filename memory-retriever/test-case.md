# Memory-Retriever Test Case

This test case validates the shared retrieval flow for the `sample-project` project after adding the mandatory core-file baseline.

## Goal

Confirm that the current `memory-retriever` implementation:

1. provides the required instruction structure in `SKILL.md`
2. always reads the core files first in the exact order `AGENTS.md -> SOUL.md -> IDENTITY.md -> USER.md`
3. uses `memories/catalog.md` as the first shortlist source only for non-core searchable memory
4. does not read `experiences/` or archive memory
5. produces an expanded instruction with a hard priority rule, additive core baseline injections, and verbatim core-file content
6. limits omitted-candidate trace logging and follow-up duplication
7. writes a timestamped retrieval trace inside the project folder
8. adds quota guidance without turning quota state into memory cards

## Expected State

The test should pass only if all of the following are true:

1. `memory-retriever/SKILL.md` includes:
   - the hard priority rule
   - the rule that `experiences/` is never read directly
   - tiered retrieval logic
   - the mandatory core-file pre-pass
   - the exact file order `AGENTS.md -> SOUL.md -> IDENTITY.md -> USER.md`
   - the rule that core-file injections are additive baseline context and do not consume the tier budget
   - the rule that each core file is injected verbatim with `injection_mode: full_file_verbatim`
   - the two-pass catalog shortlist plus focused-read flow after the core pre-pass
   - the timestamped retrieval-round output rule
   - a hard cap on omitted-candidate logging
   - a follow-up deduplication rule against `latest-expanded-instruction.md`
   - a missing-`AGENTS.md` hard-fail rule
   - a missing-or-empty catalog fallback that returns only the core baseline and forbids full-folder scans for non-core memory
   - a categorical token guard using `token_cost_estimate`
   - a narrow exception to read `memories/provider-quotas.md`
   - quota allocation modes
   - a rule that quota guidance is not a memory card
2. `memories/catalog.md` exists and contains searchable memory entries.
3. a retrieval-round fixture exists under `memory-retriever/fixtures/sample-project/memory/retrieval-rounds/`.
4. `memory-retriever/fixtures/sample-project/memory/latest-expanded-instruction.md` exists.
5. The round file includes:
   - `instruction_path: memory-retriever/fixtures/sample-project/user-instruction.md`
   - `task_complexity: standard`
   - `core_files_read`
   - `catalog_considered`
   - selected retrieved memory
   - a `## Quota Snapshot` section
   - source paths for the four core files and the catalog-derived memory
   - the priority rule
6. The handoff file keeps this order:
   - `## Current Instruction`
   - `## Priority Rule`
   - `## Project Context`
   - `## Retrieved Memory`
   - `## Execution Note`
7. Both fixture outputs list retrieved memory in this order:
   - `Core Memory File: AGENTS.md`
   - `Core Memory File: SOUL.md`
   - `Core Memory File: IDENTITY.md`
   - `Core Memory File: USER.md`
   - `Concise Output Style`
   - `Paper-Trail-First Execution`
   - `Skill-Onboarding Pattern`
8. Both fixture outputs inject the full contents of `memories/AGENTS.md`, `memories/SOUL.md`, `memories/IDENTITY.md`, and `memories/USER.md` under those core memory file blocks.
9. Neither retrieval output includes retrieval source entries under `experiences/`, `memories/archive/`, or `memories/archive-catalog.md`.
10. The handoff file includes quota guidance for `Tavily` and `Brave` without adding `### Memory Card: Tavily` or `### Memory Card: Brave`.

## Workflow Template Handling

The test should also verify:

- `memory-retriever/SKILL.md` includes:
  - a Workflow Template Injection section with matching logic, version selection, injection format, review notification, and unrecognized workflow handling
  - updated Expanded Instruction Order including Workflow Playbook
  - updated traceability output including workflow template match
  - three injection modes: primary_playbook, maturing_guide, loose_guide
  - shared fragment resolution via `→ [shared:<fragment-id>]` notation
  - multi-round deduplication rule for workflow templates

## How To Run

Run:

```bash
python3 memory-retriever/test_memory_retriever.py
```

The script exits with status `0` on success and non-zero on failure.
