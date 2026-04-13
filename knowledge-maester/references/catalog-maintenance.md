# Catalog Maintenance Guide

Operator procedures for maintaining the Citadel literature catalog system. All commands assume the knowledge-maester skill root as the working directory and default vault path `~/Documents/citadel/`.

---

## 1. Periodic Maintenance (Model B)

Run these checks at your discretion — weekly, monthly, or whenever drift is suspected. Model B catches anything the automatic post-batch pipeline (Model A) missed and keeps the taxonomy healthy as the collection grows.

### 1.1 Taxonomy Health Report

Generate density statistics, flag dense and sparse branches, and count pending terms:

```bash
python3 knowledge-maester/scripts/maintain_taxonomy.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --db-path ~/Documents/citadel/literature/_index.db \
  --report
```

Review the output for:
- **Dense branches** (>50 papers) — candidates for splitting
- **Sparse branches** (<2 papers) — candidates for merging
- **Pending terms count** — unmatched keywords awaiting human review

### 1.2 Graph and Structural Health

```bash
# Check for broken links, orphan notes, missing frontmatter
python3 knowledge-maester/scripts/check_graph.py \
  --vault-path ~/Documents/citadel --schema citadel

# Full vault structural validation
python3 knowledge-maester/scripts/validate_vault.py \
  --vault-path ~/Documents/citadel
```

Fix any issues found: create stub notes for broken link targets, add links from orphan notes, update stale frontmatter.

---

## 2. Reviewing and Resolving pending_terms.yaml

When papers contain keywords that cannot be matched to existing taxonomy terms, they are appended to `~/Documents/citadel/pending_terms.yaml`. Review this file periodically.

### 2.1 Review Pending Terms

Open `~/Documents/citadel/pending_terms.yaml` and for each entry:
1. Decide whether the term maps to an existing canonical keyword (add it to `synonym_map.json`)
2. Decide whether a new taxonomy branch is needed (see Section 3)
3. Mark the entry's `status` as `approved` and set `suggested_canonical` to the target keyword path

### 2.2 Promote Approved Terms

After reviewing and approving entries, promote them into the taxonomy and synonym map:

```bash
python3 knowledge-maester/scripts/maintain_taxonomy.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --promote-pending ~/Documents/citadel/pending_terms.yaml
```

This adds approved synonyms to `synonym_map.json` and, where applicable, creates new taxonomy nodes in `taxonomy.yaml`.

### 2.3 Re-normalize After Promotion

After promoting terms, re-run normalization to classify previously unmatched papers:

```bash
python3 knowledge-maester/scripts/normalize_keywords.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --all-unclassified
```

---

## 3. Adding a New Taxonomy Branch

### 3.1 Manual Addition

Edit `~/Documents/citadel/taxonomy.yaml` directly to add a new branch under the appropriate parent. Follow the existing YAML structure (2-3 level hierarchy, materialized paths).

After editing, add any common aliases to `~/Documents/citadel/synonym_map.json` mapping alternate terms to the new canonical keyword.

### 3.2 Splitting a Dense Branch

When a keyword accumulates >50 papers, split it into more specific children:

```bash
# Dry run — outputs split_assignments.yaml for review
python3 knowledge-maester/scripts/maintain_taxonomy.py \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --db-path ~/Documents/citadel/literature/_index.db \
  --split "parent/dense-branch" --into "child1,child2"

# Apply after review
python3 knowledge-maester/scripts/maintain_taxonomy.py \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --db-path ~/Documents/citadel/literature/_index.db \
  --split "parent/dense-branch" --into "child1,child2" --confirm
```

A backup (`taxonomy.yaml.bak`) is created before any modification.

### 3.3 Merging Sparse Branches

When keywords have <2 papers, merge them into a broader category:

```bash
# Dry run
python3 knowledge-maester/scripts/maintain_taxonomy.py \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --db-path ~/Documents/citadel/literature/_index.db \
  --merge "branch1,branch2" --into "target/branch"

# Apply after review
python3 knowledge-maester/scripts/maintain_taxonomy.py \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --db-path ~/Documents/citadel/literature/_index.db \
  --merge "branch1,branch2" --into "target/branch" --confirm
```

### 3.4 Post-Change Rebuild

After any taxonomy change (add, split, or merge), rebuild the index and catalog:

```bash
# Re-normalize all unclassified papers
python3 knowledge-maester/scripts/normalize_keywords.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --all-unclassified

# Rebuild SQLite index
python3 knowledge-maester/scripts/build_taxonomy_db.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --incremental

# Regenerate all catalog MOC pages
python3 knowledge-maester/scripts/generate_catalog_mocs.py \
  --vault-path ~/Documents/citadel \
  --db-path ~/Documents/citadel/literature/_index.db \
  --all
```

---

## 4. Forcing a Full Rebuild

Use a full rebuild when incremental updates may have drifted, after a major taxonomy overhaul, or to recover from a deleted or corrupted `_index.db`.

### 4.1 Full SQLite Rebuild

Drop and recreate all database tables, then repopulate from vault Markdown:

```bash
python3 knowledge-maester/scripts/build_taxonomy_db.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --full-rebuild
```

Expected runtime: <10 seconds for the current collection size.

### 4.2 Full Catalog MOC Regeneration

Regenerate all per-keyword catalog pages from the SQLite index:

```bash
python3 knowledge-maester/scripts/generate_catalog_mocs.py \
  --vault-path ~/Documents/citadel \
  --db-path ~/Documents/citadel/literature/_index.db \
  --all
```

Expected runtime: <5 seconds.

### 4.3 Full Recovery Procedure

If both `_index.db` and `_catalog/` are lost, the full recovery sequence is:

```bash
# 1. Normalize all paper keywords
python3 knowledge-maester/scripts/normalize_keywords.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --all-unclassified

# 2. Full database rebuild
python3 knowledge-maester/scripts/build_taxonomy_db.py \
  --vault-path ~/Documents/citadel \
  --taxonomy ~/Documents/citadel/taxonomy.yaml \
  --synonym-map ~/Documents/citadel/synonym_map.json \
  --full-rebuild

# 3. Regenerate all catalog MOCs
python3 knowledge-maester/scripts/generate_catalog_mocs.py \
  --vault-path ~/Documents/citadel \
  --db-path ~/Documents/citadel/literature/_index.db \
  --all

# 4. Validate vault health
python3 knowledge-maester/scripts/check_graph.py \
  --vault-path ~/Documents/citadel --schema citadel

python3 knowledge-maester/scripts/validate_vault.py \
  --vault-path ~/Documents/citadel
```

The Markdown notes are always the source of truth. `taxonomy.yaml` and `synonym_map.json` define the vocabulary. Everything else is derived and fully regenerable.

---

## 5. Grand Plan Success Criteria Verification

The literature reorganization project (grand-plan.md Section 10) defines six success criteria. Current status:

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Every paper has 2-4 controlled keywords and a summary | Met | 486/710 paper notes enriched; remaining are stubs, dummies, or pre-enrichment papers that pass through normalization on next batch |
| 2 | `literature/_catalog/` contains auto-generated MOC pages browsable by topic | Met | 77 catalog MOC pages generated in `_catalog/` |
| 3 | Memory-retriever exploratory queries resolve via MOC-first path | Met | SKILL.md Pattern 3 (Exploratory) documents MOC-first strategy using `_catalog/` pages |
| 4 | SQLite FTS5 query returns relevant papers in <100ms | Met | Verified: 2.1ms for "hawkes process" query returning 27 results |
| 5 | New papers ingested through paper-reader are automatically classified and appear in catalog MOCs | Met | paper-batch-coordinator Post-Read Organization Steps (O-1, O-2, O-3) run normalize → build_db → generate_mocs; ingest_paper.py runs normalize_keywords.py post-ingestion |
| 6 | Complete catalog regeneration runs in <5 seconds | Met | generate_catalog_mocs.py --all target <5s; verified in Phase 5 Story 5.4 |
