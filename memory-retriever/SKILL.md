---
name: memory-retriever
description: Build a traceable expanded instruction from the current task plus central memory, with mandatory full-file core memory injection and selective searchable memory cards.
---

# Memory Retriever

## Mission

Turn the current project instruction into a traceable execution handoff by injecting the full contents of the mandatory core files plus only the searchable memory that materially improves the work.

The current instruction always outranks retrieved memory.
Quota guidance is operational context, not retrieved memory.

## Hard Boundaries

- Start every retrieval run with a core-file pre-pass in this exact order:
  - `memories/AGENTS.md`
  - `memories/SOUL.md`
  - `memories/IDENTITY.md`
  - `memories/USER.md`
- Core-file injection into the expanded instruction is conditional on the auto-detection matrix (see Auto-Detection Logic). The pre-pass always reads the files for internal reasoning; injection is skipped when a handoff is present.
- Use `memories/catalog-index.md` as the first shortlist source, then open only the shortlisted shards under `memories/catalog-shards/` for non-core searchable memory.
- Do not let the core-file pre-pass turn into general scanning of `memories/`.
- Read `projects/<active-project>/domain-prior.md` only when it exists.
- Read prior retrieval rounds only from the same project.
- Write only inside `<resolved_project_root>/memory/` (see Path Resolution for how the project root is resolved).
- Mid-session recall (`query` mode) does not write to disk. Results are returned inline only.
- Never read raw files from `experiences/`.
- Never read `memories/archive-catalog.md` or files under `memories/archive/` (including `memories/archive/catalog-flat-*.md`).
- Never convert quota state into memory cards.
- Never modify files under `memories/`.

## Inputs

Logical input fields:

- `instruction_path`
- `active_project`
- `retrieval_round_mode`
- `follow_up_objective`
- `trace_required`
- `force_tier`
- `quota_request`
- `quota_allocation_mode`
- `project_root`
- `query`
- `session_phase`
- `caller_type`
- `fresh_session`
- `vault_path`

Defaults:

- `retrieval_round_mode`: `initial`
- `trace_required`: `true` for project tasks
- `quota_allocation_mode`: `auto_if_relevant`
- `project_root`: not set (uses default path resolution)
- `query`: not set (full retrieval mode; when set, switches to mid-session recall)
- `session_phase`: not set (inferred from other inputs; see Session Phase)
- `caller_type`: `agent`
- `fresh_session`: `false`
- `vault_path`: `~/Documents/citadel/`

## Path Resolution

All relative paths in this skill (e.g., `memories/`, `projects/<active-project>/`) are resolved against a **resolved project root**.

### Resolution Logic

1. If `project_root` is provided and non-empty, use it as the resolved project root.
2. Otherwise, fall back to the default: `$WORKSPACE_ROOT/projects/<active_project>/`.

When `project_root` is provided, all reads and writes use that path instead of the default workspace-based resolution. The `active_project` field is still required for naming retrieval round files and other project-scoped references, but it does not influence the filesystem root.

### Validation

Before any reads or writes, the retriever must verify that the resolved project root directory exists on the filesystem.

- If `project_root` is provided and the path does not exist: **fail immediately** with the message:
  `project_root path does not exist: <resolved_path>`
- If `project_root` is not provided and the default path does not exist: **fail immediately** with the message:
  `Default project path does not exist: $WORKSPACE_ROOT/projects/<active_project>/`

Do not create the directory automatically. Do not fall back silently to a different path.

### Backward Compatibility

Existing invocations that do not supply `project_root` are unaffected. They continue to resolve paths against the default `$WORKSPACE_ROOT/projects/<active_project>/` exactly as before.

## Session Phase

The `session_phase` parameter controls what the retriever writes to disk and whether core files are injected. Valid values: `start`, `mid`, `close`.

### Inference Logic

If `session_phase` is not provided, it is inferred:

1. If `retrieval_round_mode` is `initial` → infer `start`.
2. If `query` is present → infer `mid`.
3. If `retrieval_round_mode` is `follow_up` → infer `mid`.
4. Otherwise → infer `start`.

An explicitly provided `session_phase` always overrides inference.

### Phase Behavior

**`start`**

- Run the full mandatory core-file pre-pass (inject all four core files).
- Write the retrieval round file and `latest-expanded-instruction.md`.
- Apply the full retrieval algorithm (tier classification, catalog shortlist, focused read, graph expansion, workflow template injection).

**`mid`**

- Do not inject the mandatory core files (they were already injected at session start).
- Do not write `latest-expanded-instruction.md` or retrieval round files when in mid-session recall (`query` mode).
- For `follow_up` retrieval rounds during `mid`, retrieval round files and `latest-expanded-instruction.md` are still written as specified in the Multi-Round Retrieval section.

**`close`**

- Do not inject the mandatory core files.
- Do not write retrieval round files or `latest-expanded-instruction.md`.
- The retriever returns only a lightweight acknowledgement; no new memory is retrieved.
- Close phase is intended for session teardown signals. No retrieval work is performed.

## Caller Type

The `caller_type` parameter indicates who is invoking the retriever. Default: `agent`.

### Values

- `agent` (default): Standard retrieval behavior. All current retrieval rules apply unchanged. The retriever searches central memory only (`memories/` and project-scoped sources).
- `specialist`: Enables vault-level search across the citadel structure. When `caller_type` is `specialist` and a `query` is provided, the retriever runs the four-stage progressive funnel against the citadel vault in addition to (or instead of) central memory, depending on the query pattern.

### Activation Rules

Specialist mode activates only when **both** conditions are met:

1. `caller_type` is `specialist`.
2. `query` is provided (non-empty).

If `caller_type` is `specialist` but `query` is absent, the retriever falls back to standard `agent` behavior for the current invocation and logs a warning in the Execution Note:

```md
- [WARNING] caller_type=specialist without query — falling back to agent behavior.
```

### Vault Path

The `vault_path` parameter specifies the root directory of the citadel vault to search.

- Default: `~/Documents/citadel/`
- The path must point to an existing directory. If the directory does not exist, the retriever emits a warning and skips vault search:

```md
- [WARNING] vault_path does not exist: <resolved_path> — vault search skipped.
```

- `vault_path` is only used when specialist mode is active. It is ignored for `caller_type: agent`.

### Specialist Retrieval Scope

When specialist mode is active, the retriever searches:

- All Markdown files under `vault_path` (the citadel vault).
- Frontmatter metadata (tags, aliases, dates, custom properties).
- Wikilinks (`[[...]]`) and heading structure within vault notes.
- Maps of Content (MOC files) — notes whose primary purpose is linking to and organizing other notes.

The retriever does **not**:

- Modify any vault files.
- Read non-Markdown files (images, PDFs, etc.) from the vault.
- Build or maintain a persistent index. Each query performs a fresh traversal.

## Vault Query Patterns

When specialist mode is active, the retriever classifies the `query` into one of three patterns. The pattern determines which stages of the four-stage progressive funnel are executed and in what order.

### Pattern 1: Known-Item

**When to use:** The query targets a specific, identifiable note — a named paper, a particular concept, a specific ticker report, or any item the caller can name or narrowly describe.

**Signals:**

- Query contains a specific title, cite key placeholder, filename, or unique identifier.
- Query asks for "the note about X" or "the paper on Y" where X/Y is specific.

**Funnel behavior:** Stage 1 (metadata filter) only. Return the matching note's frontmatter and a content summary. If Stage 1 yields no match, report "no match found" rather than broadening to later stages.

**Example queries:**

- "Find the note on variational autoencoders in the literature folder."
- "Retrieve the market report for AAPL from Q1 2026."

### Pattern 2: Topic Search

**When to use:** The query asks about a topic, theme, or research area without targeting a single known note. The caller wants a curated set of relevant notes.

**Signals:**

- Query describes a subject area, research question, or thematic interest.
- Query uses words like "what do we know about," "notes related to," "everything on."

**Funnel behavior:** Full four-stage funnel. Stage 1 filters candidates by metadata relevance, Stage 2 scans structure to rank them, Stage 3 reads targeted content from top candidates, and Stage 4 expands via graph connections if the initial result set is thin.

**Example queries:**

- "What notes do we have on point-process models?"
- "Find all literature related to Bayesian experimental design."

### Pattern 3: Exploratory

**When to use:** The query is open-ended — the caller wants to understand what the vault contains about a broad area, or wants to discover unexpected connections.

**Signals:**

- Query is broad or abstract ("what's in the vault about markets," "show me the landscape of our literature notes").
- Query explicitly asks for an overview, map, or inventory.

**Funnel behavior:** MOC-first. The retriever starts by identifying and reading Maps of Content relevant to the query topic, including catalog MOCs in `literature/_catalog/` (see MOC detection heuristic under Segment-Read Strategy). Catalog MOCs provide a taxonomy-organized structural overview and link to individual paper notes, enabling the funnel to drill down when deeper detail is needed. If MOCs exist and cover the topic, return the MOC-derived map without descending into individual notes. If no relevant MOCs exist, fall back to the full four-stage funnel (Pattern 2 behavior).

**Example queries:**

- "What areas of literature do we have notes on?"
- "Give me an overview of the market analysis vault."
- "What keyword categories exist in the literature catalog?"

### Pattern Classification

The retriever classifies the query pattern before executing the funnel. Classification is based on the signal heuristics above. When ambiguous:

- If the query names a specific item → Known-Item.
- If the query describes a topic without naming a specific item → Topic Search.
- If the query asks for breadth, overview, or discovery → Exploratory.

The selected pattern is reported in the inline recall output (see Mid-Session Recall) and in the trace file for full retrieval runs.

## Progressive Funnel Stages

The four-stage progressive funnel is the retrieval strategy used when specialist mode is active. Each stage reads progressively deeper into vault notes, and later stages run only when earlier stages indicate the information is worth the additional token cost. The funnel is designed so that most queries resolve cheaply; expensive deep reads happen only for high-value candidates.

### Optional Pre-Stage: SQLite Acceleration

When `vault_path/literature/_index.db` exists, the retriever may use it as a fast pre-filter before entering the four-stage funnel. This is an optional acceleration layer — the funnel operates correctly without it.

**Activation conditions — all must be true:**

1. The file `vault_path/literature/_index.db` exists and is a readable SQLite database with an FTS5 virtual table (`papers_fts`).
2. The query pattern is Known-Item (Pattern 1) or Topic Search (Pattern 2).
3. `caller_type` is `specialist`.

**Behavior:**

1. Open `_index.db` and run an FTS5 query: `SELECT cite_key, title, snippet(...) FROM papers_fts WHERE papers_fts MATCH ?`
2. Use the result set to pre-filter Stage 1 candidates — only files matching returned `cite_key` values enter the metadata filter, replacing the file-enumeration step for literature queries.
3. Non-literature vault files (outside `literature/`) are still discovered via normal file enumeration in Stage 1.
4. If the FTS5 query returns zero results, proceed to the normal Stage 1 file enumeration (the pre-stage yields no narrowing, not a "no match found" verdict).

**When `_index.db` is missing or unreadable:**

The pre-stage is skipped entirely. The retriever falls back to normal file-based Stage 1 enumeration. This is graceful degradation, not an error — no warning is emitted because the database is an optional accelerator, not required infrastructure.

**Cost:** ~50–200 tokens (SQL result parsing only; no vault file reads).

### Stage 1: Metadata Filter

**Purpose:** Narrow the vault to a candidate set using only frontmatter and file-level metadata — no note body is read.

**What is read:**

- YAML frontmatter (tags, aliases, dates, custom properties).
- Filename and folder path.
- File size (to estimate read cost).

**Token cost:** ~100–500 tokens.

**Behavior:**

1. Enumerate Markdown files under `vault_path`.
2. Parse frontmatter from each file.
3. Score candidates by metadata relevance to the query (tag overlap, alias match, date range, folder context).
4. Discard files with no metadata signal. Retain the top candidates (up to 20) for Stage 2.
5. If no candidates survive, report "no match found" and stop.

For Known-Item queries, the funnel stops here. Return the matching note's frontmatter and a content summary extracted from Stage 2 only if needed for disambiguation.

### Stage 2: Structural Scan

**Purpose:** Read the heading structure and wikilinks of each candidate — enough to rank relevance without reading full prose.

**What is read:**

- All headings (e.g., `# Title`, `## Section`) to build an outline.
- Wikilinks (`[[...]]`) to identify connections.
- Frontmatter that was already parsed in Stage 1 (no re-read).

**Token cost:** ~500–1,500 tokens (across all candidates from Stage 1).

**Behavior:**

1. For each Stage 1 candidate, extract the heading tree and wikilink list.
2. Score candidates by structural relevance: heading keywords matching the query, density of outgoing links to other relevant notes, presence of section headings that suggest topical depth.
3. Rank candidates. Retain the top results (up to 10) for Stage 3.
4. If the structural scan reveals that a candidate is clearly off-topic (e.g., headings are unrelated despite tag overlap), drop it.

### Stage 3: Targeted Content Read

**Purpose:** Read the actual prose of the highest-ranked candidates — but only the sections identified as relevant by Stage 2, not the full file.

**What is read:**

- Specific sections (heading-to-next-heading spans) identified as relevant during Stage 2.
- Frontmatter (already available from Stage 1).
- If a note is under 500 tokens total, read the full file instead of extracting sections.

**Token cost:** ~1,000–3,000 tokens (across all candidates from Stage 2).

**Behavior:**

1. For each Stage 2 candidate, read the sections whose headings scored highest for query relevance.
2. Extract guidance, findings, or content that directly addresses the query.
3. Score extracted content by quality: specificity, recency, actionability.
4. Assemble the result set from the best extractions.
5. If the result set is sufficient (covers the query topic with adequate depth), stop. Otherwise, proceed to Stage 4.

### Stage 4: Graph Expansion

**Purpose:** Follow wikilinks and MOC references from the Stage 3 result set to discover related notes that were not in the original candidate set.

**Condition:** Stage 4 runs only when the Stage 3 result set is thin (fewer than 3 substantive results for a Topic Search query) or when the query pattern is Exploratory and MOC traversal is needed.

**What is read:**

- Wikilink targets from Stage 3 result notes that were not already in the candidate set.
- MOC files referenced by or referencing Stage 3 result notes.
- Frontmatter and targeted sections of newly discovered notes (applying Stage 1–3 logic to each).

**Token cost:** ~1,000–2,000 tokens (conditional).

**Behavior:**

1. Collect outgoing wikilinks and MOC references from Stage 3 result notes.
2. Deduplicate against notes already seen in Stages 1–3.
3. Apply Stage 1 metadata filter to expansion candidates.
4. Apply Stage 2 structural scan to surviving expansion candidates.
5. Read targeted content (Stage 3) from the top expansion candidates (up to 3 notes).
6. Merge expansion results into the final result set.

### Total Cost

Typical total cost per query: **~2,000–5,000 tokens**. Known-Item queries that resolve at Stage 1 cost ~100–500 tokens. Topic Search queries that require the full funnel cost ~2,500–5,000 tokens. Exploratory queries with graph expansion cost ~3,000–7,000 tokens in the worst case.

The token costs above cover content read from vault files. They do not include the retriever's internal reasoning overhead or the output tokens used to format the result.

## Token Budget Enforcement

Every retrieval invocation operates within a token budget that caps the content returned to the caller. The budget covers vault content and memory cards delivered in the result — it does not include the retriever's internal reasoning overhead, file enumeration, or output formatting tokens.

### Budget Defaults

| Invocation Context | Default Budget | Rationale |
|---|---|---|
| Subagent access (`caller_type: specialist`) | **5,000 tokens** | Subagents receive a full context allocation for vault queries. Sufficient for a complete four-stage funnel pass. |
| Main-agent mid-session recall (`query` mode) | **1,000 tokens** | Mid-session recall is lightweight. The main agent's context window must be protected for the ongoing discussion. |

A caller may override the default by providing an explicit `token_budget` parameter. The override must be a positive integer. If not provided, the default for the invocation context applies.

### What Counts Against the Budget

- Vault note content returned in the result (frontmatter + body text).
- Memory card content (catalog-derived cards included in the output).
- MOC content when read in full.

### What Does Not Count

- The retriever's internal reasoning and scoring work.
- File enumeration and metadata parsing during Stage 1.
- Heading and wikilink extraction during Stage 2 (structural scan is internal).
- Output formatting tokens (Markdown delimiters, section headers, HTML comment wrappers).

### Insertion Strategy: Greedy Ranked Insertion

Content is assembled into the result using greedy ranked insertion:

1. Score all candidate content segments by relevance to the query (using the funnel stage scores).
2. Sort candidates in descending relevance order.
3. Insert candidates one at a time, highest relevance first.
4. Before inserting each candidate, check whether it fits within the remaining budget.
5. If a candidate fits entirely, insert it and subtract its token cost from the remaining budget.
6. If a candidate does not fit entirely, apply natural-boundary truncation (see below) and insert the truncated version.
7. Stop when the budget is exhausted or all candidates have been processed.

### Natural-Boundary Truncation

When a content segment exceeds the remaining budget, do not cut mid-sentence or mid-paragraph. Instead, truncate at the nearest natural boundary:

1. **Heading boundary** (preferred): Truncate at the last complete heading-level section that fits.
2. **Paragraph boundary**: If no heading boundary is available, truncate at the last complete paragraph that fits.
3. **Sentence boundary** (last resort): If no paragraph boundary is available, truncate at the last complete sentence that fits.

After truncation, append a truncation notice:

```md
- [TRUNCATED] Content truncated at <boundary-type> boundary. <N> tokens of <total> returned.
```

### Budget Reporting

Every retrieval result must include a budget report in the output. For full retrieval runs, append to the `### Execution Note` section. For mid-session recall, append after the guidance block inside the `<!-- memory-recall -->` delimiters.

Format:

```md
- **Token budget:** <used>/<budget> tokens consumed (<remaining> remaining).
```

When the budget is fully exhausted:

```md
- **Token budget:** <budget>/<budget> tokens consumed (0 remaining). Some content was truncated or omitted.
```

## Segment-Read Strategy

When reading vault notes during Stage 3 (Targeted Content Read) or any other content extraction step, the retriever uses heading-based segment extraction rather than reading full files. This minimizes token cost while preserving the coherence of extracted content.

### Heading-Based Extraction

To read a specific section from a vault note:

1. Identify the target heading (the heading whose content is relevant to the query, as determined by Stage 2 scoring).
2. Read from the target heading to the next heading of **equal or higher level** (i.e., same or fewer `#` characters).
3. Include all content between these two boundaries: prose, lists, code blocks, embedded links.

**Example:** To extract the `## Methods` section from a note:

- Start at the `## Methods` heading.
- Read all content until the next `##` or `#` heading (or end of file if no such heading follows).
- Subsections within `## Methods` (e.g., `### Data Collection`, `### Analysis`) are included because they are lower-level headings.

### Frontmatter Inclusion

Always include the note's YAML frontmatter in the extracted segment, regardless of which heading is targeted. Frontmatter provides essential metadata (tags, aliases, dates) that contextualizes the extracted content. Frontmatter token cost counts against the budget.

### MOC Full-File Reads

Maps of Content (MOC files) are always read in full, never segment-extracted. MOCs are structural documents whose value lies in their complete link inventory. Partial MOC reads would defeat the purpose of using MOCs for navigation and overview.

MOC detection heuristic: A note is treated as a MOC if any of the following are true:

- Its filename starts with `_MOC-` or `MOC-`.
- Its frontmatter contains `type: moc` or `type: map-of-content`.
- Its title heading contains "Map of Content" or "MOC".
- It resides under `literature/_catalog/` (catalog MOC files generated by the knowledge-maester taxonomy pipeline).

### Small-File Full Reads

When a vault note's total token cost is estimated at **under 500 tokens**, read the full file instead of extracting individual sections. The overhead of segment extraction is not justified for small notes, and full-file reads ensure no context is lost.

This rule applies at Stage 3 and during graph expansion (Stage 4). The 500-token threshold is estimated from file size before reading the full content.

### Extraction Order

When multiple segments are extracted from the same note:

1. Frontmatter (always first).
2. Extracted segments in document order (the order they appear in the source file).

When segments are extracted from different notes, the ordering follows the greedy ranked insertion strategy defined in Token Budget Enforcement.

## Graceful Degradation

The progressive funnel assumes vault notes follow common Obsidian conventions. When a convention is absent, the retriever degrades gracefully rather than failing. The table below documents the adjusted behavior for each missing convention.

| Missing Convention | Affected Stages | Degraded Behavior |
|---|---|---|
| **No frontmatter** | Stage 1 (Metadata Filter) | Skip tag, alias, and date scoring. Fall back to filename and folder path as the sole metadata signals. Candidates advance to Stage 2 on folder/filename relevance alone. |
| **No tags** | Stage 1 (Metadata Filter) | Tag-overlap scoring produces zero signal. Rely on aliases, dates, custom properties, filename, and folder path for candidate scoring. If frontmatter exists but contains no `tags` field, treat the same as no tags. |
| **No MOCs** | Stage 4 (Graph Expansion), Pattern 3 (Exploratory) | MOC-first strategy for Exploratory queries is unavailable. Fall back immediately to the full four-stage funnel (Pattern 2 behavior). Stage 4 graph expansion uses wikilinks only; MOC traversal is skipped. |
| **No wikilinks** | Stage 2 (Structural Scan), Stage 4 (Graph Expansion) | Link-density scoring in Stage 2 produces zero signal; rank candidates by heading relevance only. Stage 4 has no outgoing links to follow; graph expansion is effectively disabled unless MOCs provide links. |
| **No heading structure** | Stage 2 (Structural Scan), Stage 3 (Targeted Content Read), Segment-Read Strategy | Stage 2 heading-keyword scoring produces zero signal; rank candidates by metadata and link signals only. Stage 3 cannot perform heading-based segment extraction; read the full file instead (subject to the 500-token small-file rule — files over 500 tokens are read in full but capped by the token budget via natural-boundary truncation at paragraph or sentence level). |
| **No `_index.db`** | Pre-Stage (SQLite Acceleration) | SQLite pre-stage is skipped entirely. The retriever falls back to normal file-based Stage 1 enumeration with no performance penalty beyond the loss of the FTS5 shortcut. No warning is emitted — the database is an optional accelerator, not required infrastructure. |

When multiple conventions are absent simultaneously, the degradations compose. A vault with no frontmatter, no tags, and no heading structure reduces Stage 1 to filename/folder matching, Stage 2 to link-only scoring, and Stage 3 to full-file reads. The funnel still operates but with lower precision and potentially higher token cost per query.

The retriever does not emit warnings for missing conventions. Convention absence is a normal vault state, not an error. The fail-loud policy applies to missing infrastructure (core files, catalog, project root), not to vault content quality.

## Subagent Integration

When a main agent delegates vault-related work to a subagent, the subagent needs access to citadel content. Two mechanisms are available. The main agent chooses the mechanism based on delegation context; both may be used across different delegations within the same session.

### Mechanism A: Pre-Retrieved Context

The main agent retrieves vault content before delegation and includes it in the subagent's delegation brief.

**When to use:**

- The main agent already knows which vault content is relevant.
- The subagent's task is narrowly scoped and the needed context can be pre-identified.
- The main agent wants to control exactly what vault content the subagent sees.

**How it works:**

1. The main agent invokes the retriever with `caller_type: specialist` and a `query` targeting the content the subagent will need.
2. The retriever returns vault content within the applicable token budget.
3. The main agent includes the retrieved content in the subagent's delegation brief as a `### Vault Context` section.
4. The subagent uses the provided context without making its own vault queries.

**Delegation brief format:**

```md
### Vault Context

- retrieved_by: main agent (pre-delegation)
- query: <the query used to retrieve this content>
- token_cost: <tokens consumed>

<retrieved vault content>
```

**Constraints:**

- The main agent's token budget applies to the retrieval (5,000 tokens for specialist access).
- The subagent must not re-query the vault when pre-retrieved context is provided. If the provided context is insufficient, the subagent reports the gap in its output rather than searching independently.

### Mechanism B: Subagent Self-Search

The subagent searches the citadel vault directly using file tools, guided by funnel instructions included in its delegation brief.

**When to use:**

- The main agent cannot predict which vault content is relevant before delegation.
- The subagent's task requires exploratory or broad vault access.
- The task benefits from the subagent's ability to iteratively refine its vault search based on intermediate findings.

**How it works:**

1. The main agent includes funnel instructions in the subagent's delegation brief: the vault path, the four-stage progressive funnel specification, and the segment-read strategy.
2. The subagent uses its own file-reading tools to traverse the vault, following the funnel stages.
3. The subagent applies the token budget and segment-read rules as specified in the funnel instructions.

**Delegation brief format:**

```md
### Vault Access

- mechanism: self-search
- vault_path: <vault_path value>
- token_budget: 5000
- funnel_reference: memory-retriever SKILL.md § Progressive Funnel Stages
- segment_read_reference: memory-retriever SKILL.md § Segment-Read Strategy

Instructions: Search the vault at the path above using the four-stage progressive funnel.
Stage 1: Metadata filter. Stage 2: Structural scan. Stage 3: Targeted content read.
Stage 4: Graph expansion (conditional). Apply heading-based segment extraction.
Stay within the token budget for all vault content read.
```

**Constraints:**

- The subagent must follow the same funnel stages, segment-read strategy, and token budget rules defined in this skill file.
- The subagent must not modify any vault files.
- The subagent reports its vault search trace (stages executed, candidates considered, content extracted, tokens consumed) in its structured output file.

### Mechanism Selection Guidance

| Signal | Recommended Mechanism |
|---|---|
| Main agent knows the specific notes or topic needed | A (pre-retrieved) |
| Task requires broad or exploratory vault access | B (self-search) |
| Subagent task is a literature review or survey | B (self-search) |
| Subagent needs a single known document | A (pre-retrieved) |
| Main agent wants to minimize subagent complexity | A (pre-retrieved) |
| Main agent cannot predict relevant content | B (self-search) |

## Auto-Detection Logic

At session start (`session_phase=start`), the retriever checks the resolved project root for two files to determine session state:

1. `<project_root>/handoff.md` — presence indicates prior session context is available.
2. `<project_root>/user-instruction.md` — presence indicates a new session with explicit instructions.

These files are checked for existence only. Their content is not injected as memory cards.

### Detection Matrix

| `handoff.md` exists | `user-instruction.md` exists | Behavior |
|:-:|:-:|---|
| yes | (either) | **Incremental retrieval.** Prior session context is live. Skip core file injection (pre-flight already loaded them). Retrieve only incremental catalog-derived memory. Report handoff date (staleness check). |
| no | yes | **Full bootstrap.** New project session or first run. Inject core files. Retrieve full catalog-derived memory. |
| no | no | **Core-identity-only bootstrap.** Quick ad-hoc session. Inject core files. Minimal or no catalog-derived memory (likely Tier 0). |

Auto-detection runs only when `session_phase=start`. During `mid` or `close` phases, the detection matrix is not evaluated.

### Override: `fresh_session`

An optional boolean parameter `fresh_session` (default: `false`) forces full bootstrap even when a handoff exists.

Use case: the user knows the handoff is outdated and wants a clean start.

When `fresh_session=true`:

- Treat as if no handoff exists (apply the full bootstrap or core-identity-only row based on `user-instruction.md` presence).
- Still read the handoff for reference if available, but do not use it as a basis for incremental retrieval.
- Force `retrieval_round_mode=initial` regardless of what was passed. `fresh_session` and `follow_up` are contradictory; `fresh_session` wins.

When `fresh_session=false` (default): normal auto-detection applies.

### What "Skip Core File Injection" Means

When the detection matrix says "skip core file injection," the retriever:

- Still reads the core files internally (for its own reasoning about retrieval relevance).
- Does NOT inject them into the expanded instruction output (because the startup protocol's pre-flight already loaded them into the agent's context).
- Notes in the trace file: `core_injection: skipped (handoff present, pre-flight assumed)`.

Fallback: if core file injection is skipped and the retriever detects that pre-flight may not have run (e.g., no evidence of core files in conversation context), it falls back to injecting core files and logs a warning.

## Handoff Staleness Reporting

At session start, when a handoff is detected via the auto-detection matrix, the retriever includes the handoff's `last_updated` date in the expanded instruction output.

### Format

Append the following line to the `### Execution Note` section of the expanded instruction:

```md
- Handoff detected: last updated YYYY-MM-DD (<N days ago>).
```

Replace `YYYY-MM-DD` with the `last_updated` date from the handoff file's frontmatter, and `<N days ago>` with the number of days between that date and the current date.

### No Automated Threshold

The retriever does not define a staleness threshold. It reports the date; the human decides whether the handoff is current enough. A 2-week-old handoff might be perfectly valid if no work happened in between. A 1-day-old handoff might be outdated if the user made significant changes offline.

If the user determines the handoff is stale, they can either:

- Ask the agent to proceed as if no handoff exists (equivalent to `fresh_session=true`).
- Continue with the handoff as-is, noting which parts are outdated.

## Retrieval Sources

Mandatory core session files:

- `memories/AGENTS.md`
- `memories/SOUL.md`
- `memories/IDENTITY.md`
- `memories/USER.md`

Catalog-backed searchable memory:

- `memories/catalog-index.md` (shard manifest; always read first in Pass 1a)
- `memories/catalog-shards/<shard>.md` (opened only for shortlisted shards in Pass 1b)
- searchable long-term notes under `memories/long-term/` (atomic Obsidian notes)
- searchable short-term notes under `memories/short-term/`
- hub notes under `memories/long-term/_hub-*.md` (topic cluster indexes)
- `projects/<active-project>/domain-prior.md`
- prior retrieval round files for the same project
- `memories/workflow-templates/<workflow-type>.md`
- `memories/workflow-templates/_shared/<fragment-id>.md`

The retriever may also read `memories/provider-quotas.md` as a special operational source when quota allocation is relevant. It is not part of the searchable-memory shortlist.

## Priority Rule

The expanded instruction must always state explicitly:

- current instruction outranks all retrieved memory

And the expanded instruction must always place the current instruction first.

Current instruction outranks all quota guidance as well.

## Retrieval Tiers

### Tier 0: Simple

Use for:

- quick factual tasks
- one-shot utility tasks
- tasks with no visible continuity need
- tasks where user-specific style memory is unnecessary

Behavior:

- default to no additional catalog-derived memory
- return no retrieval file unless traceability is explicitly required
- target added catalog context: `0-150` tokens

### Tier 1: Standard

Use for:

- ordinary project tasks
- tasks where user preferences change presentation or execution
- tasks with modest continuity needs

Behavior:

- retrieve `1-3` catalog-derived memory cards
- target added catalog context: `150-350` tokens

### Tier 2: Complex

Use for:

- multi-stage projects
- tasks with strong continuity requirements
- tasks where several prior lessons likely affect quality

Behavior:

- retrieve `4-8` catalog-derived memory cards
- target added catalog context: `350-900` tokens
- allow later follow-up retrieval rounds

Core-file injections are additive baseline context and do not count against Tier 1 or Tier 2 catalog-card budgets.

## Tier Classification Algorithm

Determine the tier before opening catalog-shortlisted memory files.

- Tier 0 if:
  - no active project continuity
  - no user-preference dependence beyond the core baseline
  - no multi-stage structure
- Tier 1 if:
  - ordinary project work
  - modest continuity
  - likely benefit from a small number of catalog-derived memory cards
- Tier 2 if:
  - explicit multi-stage or continuity-heavy work
  - strong dependence on prior context
  - likely need for several catalog-derived memory cards

If uncertain between Tier 0 and Tier 1, use Tier 1 only when catalog memory would clearly improve execution.

## Core Baseline Rule

Every retrieval run must inject the entirety of each core file in this exact order:

1. `### Core Memory File: AGENTS.md`
2. `### Core Memory File: SOUL.md`
3. `### Core Memory File: IDENTITY.md`
4. `### Core Memory File: USER.md`

Use this exact injection shape for each core file:

````md
### Core Memory File: AGENTS.md

- source: memories/AGENTS.md
- injection_mode: full_file_verbatim

```md
<entire file contents from first line to last line>
```
````

Core-file injection rules:

- Copy core file contents verbatim, including frontmatter and headings.
- Do not summarize or paraphrase the mandatory core files.
- Preserve line order within each injected core file block.
- Emit core-file injections first inside `Retrieved Memory`, before any catalog-derived memory cards.

## Retrieval Algorithm

### Core File Pre-Pass

Read first, in this exact order:

1. `memories/AGENTS.md`
2. `memories/SOUL.md`
3. `memories/IDENTITY.md`
4. `memories/USER.md`

Then:

1. inject the four full core-file blocks
2. keep them as additive baseline context
3. preserve the same title-plus-source pair for follow-up deduplication and replacement

### Pass 1: Cheap Shortlist

Pass 1 runs in two substeps.

**Pass 1a — Shard selection.** Read only `memories/catalog-index.md` (never a shard file in this substep). For each shard listed:

1. Compute the number of `stable_tags` that overlap with the current task's topic set (topics extracted from the instruction text, the project's `domain-prior.md` topics, and any explicit topic cues in the user message).
2. Award a keyword-match score from the shard `description` text against the instruction — case-insensitive whole-word matches on nouns; at most 1 point per overlap; cap at 3.
3. Combined shard score = 2 × (stable_tag overlap) + (description keyword points).
4. Shortlist the top 2–4 shards. Always include `core-identity` as a baseline shard unless a handoff is present and incremental retrieval is in effect (in which case core-identity can be skipped along with core-file injection).
5. If no shard scores above zero on tag overlap (none have even one tag match), fall back to `{core-identity, misc}` and emit: `[WARNING] no shard matched task topics — falling back to core-identity + misc.`

**Pass 1b — Focused read.** Open only the shortlisted shards. Score each card inside the opened shards using the existing per-card rules:

- exact project match
- topic overlap
- workflow overlap
- deliverable overlap
- user preference relevance beyond the core baseline
- whether prior retrieval already covered the same point
- workflow template match (entries of `type: workflow_template` whose `workflow_type` topic matches the inferred task type)

Read cards from both `## Generated Entries` and `## Manual Entries` subsections of each opened shard; both are valid retrieval sources.

Hub shortcut rules (scoped to opened shards):

- use the hub shortcut when the task's topics match a hub's topics with overlap `>= 2`; otherwise use the standard shard scan
- when a hub entry (`type: hub`) is shortlisted, read its `## Members` section
- add all member note slugs to the candidate shortlist
- a hub's `## Members` section is followed only if the hub entry appeared in an opened shard
- do not load the hub itself as a memory card; it is an index

### Pass 2: Focused Read

Open only shortlisted searchable memory files and score them by:

1. direct relevance to the current task
2. project continuity
3. likely impact on output quality
4. recency or stability depending on memory type

Penalize:

- generic memory that does not change action
- guidance already present in the instruction or core baseline
- long low-yield files
- memory already used in the latest retrieval round
- memory conflicting with the current instruction

Apply this categorical token guard:

- if you are already extracting `2+` catalog-derived memory cards, drop any candidate whose `token_cost_estimate` is over `500`
- use this guard instead of trying to do fine-grained token arithmetic

### Pass 2.5: Graph Expansion

Trigger:

- run only for Tier 2 complexity
- run only when there is remaining card budget (`< 8` cards selected after Pass 2)

Algorithm:

1. For each selected memory card, read its `## Related` section and collect `[[wikilink]]` targets.
2. Deduplicate expansion targets against:
   - already-selected notes
   - already-considered-and-rejected Pass 2 candidates
3. Score each expansion candidate using:
   - relevance to the current task (same scoring criteria as Pass 2)
   - relationship annotation quality (links with clear annotations score higher)
4. Select up to `2` expansion candidates total across the run.
5. Load selected expansion candidates as normal memory cards.

Guard rails:

- max `2` expansion notes per retrieval run
- Tier 0 and Tier 1 skip this pass entirely
- rejected Pass 2 candidates are not reconsidered
- expansion candidates are scored; linked notes are not auto-included

## Workflow Template Injection

When a project task's instruction suggests a recognizable workflow type, the retriever attempts to inject the matching workflow template as a session playbook.

### Matching Logic

1. Read the current instruction and infer the likely workflow type based on task description, keywords, and project context.
2. Check the `workflow-templates` shard at `memories/catalog-shards/workflow-templates.md` (routed via `catalog-index.md`) for entries of `type: workflow_template`.
3. If a matching template exists, read the template file.
4. If no template matches, note this in the expanded instruction (see Unrecognized Workflow below).

### Version Selection

When a matching template is found:

- If `version_status` is `stable`: inject as a **primary playbook**. The agent should follow these steps unless the instruction explicitly overrides them.
- If `version_status` is `beta`: inject as a **maturing guide**. The agent should use it as a reference but expect deviations.
- If `version_status` is `draft`: inject as a **loose guide**. The agent should be aware of it but not treat it as authoritative.

### Injection Format

Inject the workflow template as a dedicated section in the expanded instruction, after `### Retrieved Memory` and before `### Execution Note`:

```md
### Workflow Playbook

- workflow_type: <type>
- version_status: <draft|beta|stable>
- version_number: <N>
- sessions_observed: <N>
- injection_mode: <primary_playbook|maturing_guide|loose_guide>

#### Canonical Steps

[copied from template]

#### Anti-Patterns

[copied from template]

#### Decision Points

[copied from template]
```

If the template references shared fragments via `→ [shared:<fragment-id>]`, resolve the reference by reading the shared fragment file and inlining its steps under the reference marker.

### Review Notification

If the matched template has `ready_for_review: true` in its frontmatter:

Append a review notification to the `### Execution Note` section:

```md
- **Workflow review available:** The *<workflow-type>* workflow template (beta v<N>) has matured and is ready for your review. To inspect and promote it, ask the memory-manager to review the template.
```

### Unrecognized Workflow

If the task appears to be a project task but no workflow template matches the inferred type:

Append to the `### Execution Note` section:

```md
- **No workflow template matched.** This task does not match any known workflow type. During this session, please confirm the workflow type so a new template can be started in the next memory-manager ingestion.
```

### No Workflow Applicable

If the task is clearly not a project workflow (e.g., a one-shot question, a trivial utility task), do not attempt workflow template injection. This aligns with the existing Tier 0 behavior.

## Quota Guidance

Quota guidance is an operational add-on to the handoff, not part of retrieved memory.

### Allocation Modes

- `none`
  - skip quota processing entirely
- `auto_if_relevant`
  - if the current instruction invokes `market-watcher`, auto-request `Tavily` and `Brave`
  - otherwise do not auto-request any providers
- `explicit_only`
  - allocate only for providers listed in `quota_request`

### Quota Read Rules

You may read:

- `memories/provider-quotas.md`

You must not:

- read raw `experiences/` to estimate quota
- add quota state to `memories/catalog-index.md` or any `memories/catalog-shards/<shard>.md`
- emit quota state as `### Memory Card: ...`
- let missing quota data block normal retrieval

### Allowance Algorithm

For each requested provider:

1. Read the provider entry from `memories/provider-quotas.md`.
2. If the provider entry is missing, emit `allocation_status: unavailable`.
3. If `allocation_mode=reserved_cap`, require matching `allocation_unit` and `used_total_unit`, then compute `task_allowance = max(0, allocation_cap - used_total)`.
4. If `allocation_mode=budget_total`, require matching `budget_unit` and `used_total_unit`, then compute `task_allowance = max(0, budget_total - used_total)`.
5. If `allocation_mode=rate_limit_only`, emit `allocation_status: rate_limit_only` and no numeric allowance.
6. For allocatable providers in v1, set `remaining_after_allowance = 0` because the allowance is the full currently available advisory budget.

If units do not match, emit `allocation_status: mixed_units` and do not invent a numeric allowance.

This is advisory only. No quota is reserved or written back during retrieval.

## Catalog Memory Card Schema

This schema applies only to catalog-derived memory cards. It does not apply to the mandatory full-file core injections.

Each selected memory card must contain:

- `type`
- `source`
- `why_it_matters`
- `guidance`

Use this exact structure:

```md
### Memory Card: <title>

- type: user_preference
- source: memories/long-term/legacy-interaction-rules.md
- why_it_matters: <one sentence>
- guidance:
  - <point 1>
  - <point 2>
```

## Expanded Instruction Order

The handoff file must always use this order:

1. Current Instruction
2. Priority Rule
3. Project Context
4. Retrieved Memory
5. Workflow Playbook (if a matching workflow template exists)
6. Execution Note

Inside `Retrieved Memory`, emit the mandatory core-file injections first in this order:

1. `### Core Memory File: AGENTS.md`
2. `### Core Memory File: SOUL.md`
3. `### Core Memory File: IDENTITY.md`
4. `### Core Memory File: USER.md`

Then append any catalog-derived cards.

Quota guidance belongs under `Project Context` or `Execution Note`, never under `Retrieved Memory`.

## Traceability Output

For project tasks, write:

- `projects/<active-project>/memory/retrieval-rounds/YYYY-MM-DDTHH-MM-round-001.md`
- `projects/<active-project>/memory/latest-expanded-instruction.md`

The round file must contain:

- retrieval timestamp
- retrieval trigger
- instruction path
- task complexity tier
- core files read
- candidate shortlist summary
- selected retrieved memory (core-file injections plus catalog-derived cards)
- graph expansion trace (`trigger`, `source_notes_expanded`, `expansion_candidates_considered`, `expansion_notes_added`)
- workflow template matched (path and version status, or "none")
- review notification emitted (true/false)
- quota snapshot when quota allocation is relevant
- omitted candidates when useful
- final expanded instruction

Trace logging cap:

- list at most `5` omitted candidates
- if more omitted candidates exist, append `...and X others`
- do not let omitted-candidate logging dominate the trace file

Use this exact round-file shape:

````md
# Memory Retrieval Round

- retrieved_at: YYYY-MM-DDTHH:MM:SS+TZ:TZ
- retrieval_round_mode: initial
- instruction_path: projects/example/user-instruction.md
- task_complexity: standard

## Shortlist Summary

- core_files_read:
  - memories/AGENTS.md
  - memories/SOUL.md
  - memories/IDENTITY.md
  - memories/USER.md
- catalog_considered:
  - memories/catalog-index.md shard: <shard-name>
  - memories/catalog-shards/<shard>.md entry: <slug>
- omitted:
  - ...

## Selected Retrieved Memory

### Core Memory File: AGENTS.md

- source: memories/AGENTS.md
- injection_mode: full_file_verbatim

```md
...
```

### Memory Card: ...

## Graph Expansion

- trigger: tier_2_with_remaining_budget
- source_notes_expanded:
  - memories/long-term/paper-trail-first-execution.md → 2 candidates found
- expansion_candidates_considered:
  - memories/long-term/skills-as-portable-instructions.md (score: 0.8, selected)
  - memories/long-term/catalog-first-deduplication.md (score: 0.3, skipped)
- expansion_notes_added: 1

## Workflow Template Match

- matched_template: memories/workflow-templates/skill-creation.md
- version_status: beta
- version_number: 1
- injection_mode: maturing_guide
- review_notification: false

## Quota Snapshot

- provider: Tavily
- scope: monthly
- usage_period_key: 2026-03
- used_total: 17
- used_total_unit: requests
- allocation_status: allocated
- task_allowance: 183
- allowance_unit: requests
- remaining_after_allowance: 0
- source: central_memory

## Expanded Instruction

### Current Instruction
...

### Priority Rule
Current instruction outranks all retrieved memory.

### Project Context
...

### Retrieved Memory
...

### Execution Note
...
````

The expanded instruction should use compact quota guidance such as:

```md
### Execution Note

- Current instruction outranks all retrieved memory.
- Quota guidance:
  - Tavily: used 17 requests in 2026-03; task allowance 183 requests.
  - Brave: used 0 requests in 2026-03; task allowance 200 requests.
```

If quota state is unavailable, say so plainly and continue normal retrieval.

If no workflow template matched, use this shape instead for the `## Workflow Template Match` block:

```md
## Workflow Template Match

- matched_template: none
- unrecognized_workflow_note: true
```

## Multi-Round Retrieval

For `follow_up` mode:

1. read the current instruction
2. read `latest-expanded-instruction.md`
3. read the latest retrieval round file
4. reread the four mandatory core files in the same order
5. identify the narrow missing context gap
6. add only incremental memory cards
7. write a new timestamped round file
8. refresh `latest-expanded-instruction.md`

Do not restate the full prior retrieval set unless needed.

Follow-up deduplication rule:

- before adding an incremental memory card, verify that both its `source` path and its card title do not already appear in `latest-expanded-instruction.md`
- if either already exists, skip that card entirely
- apply the same title-plus-source dedupe rule to core-file injections
- if a core file changes, replace the existing injected block under the same `### Core Memory File: ...` heading instead of creating a second copy
- for follow-up rounds, do not re-inject the workflow template if it was already injected in the initial round; the template injection in `latest-expanded-instruction.md` persists across rounds

## Mid-Session Recall (`query` parameter)

When the `query` parameter is provided, the retriever switches to mid-session recall mode: a lightweight, read-only lookup narrowly focused on a single topic.

### When to Use

Mid-session recall is for topic-specific memory lookups during an active session — for example, recalling a specific user preference, a prior decision, or a known constraint without running a full retrieval cycle.

### Behavior

1. Read `memories/catalog-index.md` to shortlist 1–2 shards, then read those shards and score entries by relevance to the `query` string.
2. Open at most `3` shortlisted searchable memory files.
3. Extract only the guidance that directly addresses the query topic.
4. Do not read or inject the mandatory core files (`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`).
5. Do not run graph expansion, workflow template injection, or quota allocation.
6. Do not apply the tier classification algorithm; mid-session recall is tier-independent.
7. If central memory (steps 1–3) yields insufficient guidance for the query, fall back to a citadel vault search as described in the Citadel Fallback section below.

### Token Budget

Total output must not exceed **1,000 tokens**. The budget is shared across central memory and citadel fallback — tokens consumed by central memory results reduce the budget available for the citadel search. If extracted guidance exceeds this budget, trim the lowest-relevance entries until the output fits.

### Citadel Fallback

When central memory produces no relevant guidance or the results are clearly insufficient for the query topic, the retriever extends the search to the citadel vault.

**Activation conditions** — the fallback triggers when any of the following are true:

- Central memory search returned zero guidance points.
- All returned guidance points scored below the relevance threshold (i.e., none directly addresses the query).
- The query explicitly references vault content, literature, or market notes.

**Fallback behavior:**

1. Calculate the remaining token budget: `remaining = 1,000 - tokens_consumed_by_central_memory`.
2. If `remaining < 100`, skip the vault search — insufficient budget for a meaningful result.
3. Search the citadel vault at `vault_path` using the progressive funnel, constrained to the remaining budget.
4. Apply the same segment-read strategy and natural-boundary truncation rules as specialist mode.
5. Merge vault results after central memory results in the output, clearly attributed.

**Output format extension:**

When citadel fallback is used, the inline recall block includes vault sources:

```md
<!-- memory-recall: query -->

- **topic**: <query text>
- **sources**: <central memory paths>, <vault note paths>
- **central_memory_tokens**: <tokens used by central memory results>
- **vault_tokens**: <tokens used by vault results>
- **guidance**:
  - <central memory point 1>
  - <central memory point 2>
  - [vault] <vault-derived point 1>
  - [vault] <vault-derived point 2>

<!-- /memory-recall -->
```

**Constraints:**

- Central memory is always searched first. The citadel is a fallback, not a parallel source.
- The shared 1,000-token budget is firm. Vault results must fit within whatever budget remains after central memory.
- Vault fallback follows the same no-disk-writes rule as standard mid-session recall.
- The `[vault]` prefix on guidance points lets the caller distinguish the source tier.

### No Disk Writes

Mid-session recall must not write any files. No retrieval round files, no expanded instruction files, no trace files. The result is returned inline only.

### Output Format

Return a compact inline block using this exact shape:

```md
<!-- memory-recall: query -->

- **topic**: <query text>
- **sources**: <comma-separated source paths>
- **guidance**:
  - <point 1>
  - <point 2>
  - ...

<!-- /memory-recall -->
```

Rules for the inline block:

- Use the HTML comment delimiters exactly as shown so the caller can locate the block programmatically.
- List only sources that contributed guidance; omit sources that were read but yielded nothing relevant.
- Each guidance point must be a single concise sentence or phrase.
- If no relevant memory is found, return:

```md
<!-- memory-recall: query -->

- **topic**: <query text>
- **sources**: none
- **guidance**:
  - No relevant memory found for this query.

<!-- /memory-recall -->
```

### Interaction with Other Modes

- `query` is mutually exclusive with `retrieval_round_mode: follow_up`. If both are provided, `query` takes precedence and `follow_up_objective` is ignored.
- `query` may be used with or without `active_project`. When `active_project` is set, `domain-prior.md` is included in the candidate sources for relevance scoring.
- All other parameters (`force_tier`, `trace_required`, `quota_request`, `quota_allocation_mode`) are ignored during mid-session recall.

## Failure Handling

- Resolved project root does not exist:
  - fail immediately before any retrieval
  - emit the validation message from the Path Resolution section
  - do not attempt partial retrieval or silent fallback
- Missing or unreadable `memories/AGENTS.md`:
  - fail with a clear note that the mandatory core session dispatcher is unavailable
- Missing or unreadable `memories/SOUL.md`, `memories/IDENTITY.md`, or `memories/USER.md`:
  - continue best-effort with the remaining core files
  - record the missing file in `## Shortlist Summary`
  - note in `Execution Note` that the core baseline was partial
- Missing or unreadable `memories/catalog-index.md`:
  - continue with core baseline only
  - record that catalog-backed retrieval was unavailable
  - skip non-core retrieval entirely (same behavior as missing flat catalog today)
- Empty `memories/catalog-index.md`:
  - continue with core baseline only
  - do not scan the `memories/` folder directly for non-core memory
- Missing `memories/catalog-shards/` directory, or a shard file referenced by the index missing:
  - emit a warning and note which shard was unreadable
  - skip that shard and continue Pass 1b with the remaining shortlisted shards
- Missing `domain-prior.md`:
  - continue without project-local context
- No relevant searchable memory found:
  - return the core baseline plus current instruction only
  - do not scan the `memories/` folder directly for non-core memory
- Shortlist too large:
  - drop the lowest-value candidates until within token budget
- Follow-up retrieval duplicates prior round:
  - emit a no-op incremental result and record that prior coverage is sufficient
- Only archive memory appears relevant:
  - do not read archive automatically; require explicit manager restoration first

## Fail-Loud Policy

The retriever must never silently degrade. Every missing or unreadable resource must produce an explicit, categorized report. Silent fallbacks are forbidden.

### Failure Categories

| Condition | Severity | Behavior |
|---|---|---|
| `memories/AGENTS.md` missing or unreadable | **Fatal** | Halt retrieval immediately. Do not produce an expanded instruction. |
| `memories/SOUL.md` missing or unreadable | **Warning** | Continue with remaining core files. Collect warning in Execution Note. |
| `memories/IDENTITY.md` missing or unreadable | **Warning** | Continue with remaining core files. Collect warning in Execution Note. |
| `memories/USER.md` missing or unreadable | **Warning** | Continue with remaining core files. Collect warning in Execution Note. |
| `memories/catalog-index.md` missing or unreadable | **Warning** | Continue with core baseline only. Skip catalog-backed retrieval. Collect warning in Execution Note. |
| `memories/catalog-shards/<shard>.md` missing or unreadable for a shortlisted shard | **Warning** | Skip the missing shard. Continue Pass 1b with remaining shortlisted shards. Collect warning in Execution Note. |
| Resolved project root does not exist | **Warning** | Collect warning in Execution Note. |

### Fatal vs. Warning Distinction

- **Fatal**: The retriever cannot produce a meaningful expanded instruction. Retrieval halts with an error message. No output files are written.
- **Warning**: The retriever can still produce a useful expanded instruction, but with reduced context. The warning is recorded so downstream agents are aware of the gap.

### Warning Collection

All warnings must be collected and reported in the `### Execution Note` section of the expanded instruction. Use this format:

```md
### Execution Note

- **Retrieval warnings:**
  - [WARNING] memories/SOUL.md missing or unreadable — core baseline is partial.
  - [WARNING] memories/catalog-index.md missing — catalog-backed retrieval skipped.
```

Each warning entry must state the missing resource and the degraded behavior applied. Warnings do not block the retrieval run; they ensure downstream agents can assess the completeness of the expanded instruction.

## Success Conditions

A good retrieval run:

- never reads `experiences/`
- starts with the mandatory core-file pre-pass
- uses `memories/catalog-index.md` as the first shortlist source, then opens only the shortlisted shards under `memories/catalog-shards/`
- keeps the current instruction first
- injects full core memory files first, then compact, justified catalog-derived memory cards
- writes timestamped project-local trace files
- remains cheap enough for normal session startup
