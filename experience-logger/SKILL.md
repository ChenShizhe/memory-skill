---
name: experience-logger
description: Write standardized project experience logs into `experiences/` so `memory-manager` can ingest them consistently.
---

# Experience Logger

## Mission

Write a concise, factual experience record at the end of a task or project round so later ingestion by `memory-manager` is cheap and reliable.

## Scope

This skill records experience. It does not curate long-term memory, deduplicate central memory, or decide archival policy.

## Output Path Rules

Use one of these output paths:

- One-shot summary:
  - `experiences/<project>/YYYY-MM-DD-summary.md`
- Multi-round summary:
  - `experiences/<project>/YYYY-MM-DDTHH-MM-round-001.md`

Prefer the one-shot summary when there is only one clear logging event.

## Hard Rules

- Keep the log factual and concise.
- Prefer concrete file paths over vague references.
- Record what was actually done, not what was merely considered.
- If quota-limited tools or APIs were used, record the quota usage explicitly.
- Only put machine-parseable provider quota lines in `## Used Quota`.
- Use plain integer counts in quota fields with no prose suffixes such as `queries`, `requests`, or parenthetical notes.
- If tests or validation were run, record the exact command and result.
- If no tests were run, state that explicitly.
- Do not mix durable memory curation into the experience log. Leave that to `memory-manager`.

## Required Sections

Use this exact section order:

```md
# Experience Log: <Project Title>

**Date:** YYYY-MM-DD
**Project:** <project-name>

## Task Objective

<what this round was supposed to achieve>

## Actions Taken

1. ...
2. ...

## Outputs Produced

- <file or artifact>

## Used Quota

- Provider: <name> | Scope: <monthly|daily|per-run|hourly|per-second> | Used in run: <integer>

## User Corrections Or Preferences Observed

- ...

## Mistakes Or Failed Paths

- ...

## Reusable Lessons

- ...

## Follow-Up Context For Future Rounds

- ...

## Workflow Reflection

- workflow_type: [known type or "new: <proposed-name>"]
- workflow_type_confidence: confirmed | proposed | guessed
- project_outcome: success | failure | partial | ongoing
- outcome_reasons: [user-provided reasons, or "not provided"]
- steps_taken:
  1. [meaningful phase description]
  ...
- decision_points:
  - [where the user intervened and what they chose]
- mistakes_and_corrections:
  - mistake: [what went wrong]
    root_cause: [why]
    correction: [what fix was applied]
    lesson: [what to do differently next time]
- deviations_from_expected:
  - [anything non-standard about this session's workflow]
- suggested_template_update:
  - [proposed change to the workflow template, or "none"]

## Validation

- Command run: `<command>` or `none`
- Result: `pass`, `fail`, or `not run`
```

## Empty-Section Policy

If a section has nothing meaningful to report:

- write `- none` for bullet sections
- write `None.` for prose sections

Do not remove required sections.

## Quota Logging Rules

- Prefer delta-style quota logging with `Used in run`.
- Use `Used before run` and `Used after run` only when you have a true provider-wide cumulative snapshot for the same quota period.
- If you include a snapshot line, use this exact shape:
  - `Provider: <name> | Scope: <monthly|daily|per-run|hourly|per-second> | Used before run: <integer> | Used in run: <integer> | Used after run: <integer>`
- If usage is qualitative, approximate, or not intended for `memories/provider-quotas.md`, write `- none` in `## Used Quota` and mention the usage elsewhere in the log.
- Keep provider names stable and simple so `memory-manager` can match them against `memories/provider-quotas.md`.

## Workflow Reflection Rules

The `## Workflow Reflection` section captures structured workflow metadata for cross-session learning. Memory-manager uses this section to build and update workflow templates.

### Workflow Type Tagging

- Use one of the known types: `brainstorming`, `skill-creation`, `skill-testing`, `skill-application`, `skill-modification`, `system-modification`.
- If the session does not fit any known type, use `new: <proposed-name>` and set `workflow_type_confidence` to `proposed`.
- For human-in-the-loop sessions: the agent should have proposed the type during the session and the user should have confirmed it. Set confidence to `confirmed` or `proposed`.
- For automated sessions: if the type was specified in the instruction, set confidence to `confirmed`. If the agent inferred it, set confidence to `guessed`.

### Step Granularity

Record steps at the "meaningful phase" level — not per-tool-call, not per-milestone. Examples of good phase descriptions:
- "Read user-instruction.md and identified task scope"
- "Retrieved memories via memory-retriever (Tier 2)"
- "Drafted implementation plan and iterated with user (2 review rounds)"
- "Implemented changes to SKILL.md"
- "Ran validation tests — all passed"

### Mistakes and Corrections

Each entry in `mistakes_and_corrections` must include all four fields: `mistake`, `root_cause`, `correction`, `lesson`. If no mistakes occurred, write `- none`.

The `lesson` field is the most important — it should describe what the workflow should do differently in future sessions to avoid the same mistake.

### Project Outcome

The user declares the project outcome at session end. If the user does not explicitly declare an outcome:
- Use `ongoing` if the project will continue in future sessions
- Use `partial` if the session achieved some goals but not all
- Ask the user before declaring `success` or `failure`

Record the user's stated reasons in `outcome_reasons`. If no reasons were provided, write `not provided`.

### Suggested Template Updates

If the session revealed a workflow pattern that should be added to or modify the existing workflow template, describe it here. This helps memory-manager decide what to merge into the template.

If nothing notable, write `- none`.

## Quality Bar

A good experience log:

- is easy for a human to scan
- is specific enough for `memory-manager` to extract durable lessons
- separates facts, mistakes, and follow-up work clearly
- captures machine-parseable run usage when the task consumed shared or limited external providers
- captures structured workflow metadata that memory-manager can use to build or update workflow templates
