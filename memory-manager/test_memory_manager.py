#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "memory-manager"))
from bootstrap import (  # noqa: E402
    route_card,
    route_card_with_index,
    normalize_tags,
    SYNONYMS,
    write_entry_to_shard,
    update_index_for_shard,
    SHARD_HEADER_TEMPLATE,
    file_route_proposal,
    generate_route_candidates,
    check_and_emit_capacity_signals,
    process_route_proposals,
    MISC_SOFT_THRESHOLD,
    CATALOG_PHASE2_THRESHOLD,
    PROPOSAL_REVIEW_THRESHOLD,
)
sys.path.insert(0, str(ROOT / "memory-manager" / "test_fixtures"))
from route_card_old import route_card_old  # noqa: E402


def read_text(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"Missing {label}: {needle}")


def main() -> int:
    skill_md = read_text(ROOT / "memory-manager/SKILL.md")

    # Integration tests: these require a configured workspace with live memory files.
    # Skip gracefully if the workspace is not set up.
    workspace_files = {
        "catalog_index_md": ROOT / "memories/catalog-index.md",
        "archive_catalog_md": ROOT / "memories/archive-catalog.md",
        "ledger_md": ROOT / "memories/manager-ledger.md",
        "quota_md": ROOT / "memories/provider-quotas.md",
        "workflows_md": ROOT / "memories/example-workflows.md",
        "patterns_md": ROOT / "memories/example-patterns.md",
    }
    catalog_shards_dir = ROOT / "memories/catalog-shards"
    missing = [name for name, path in workspace_files.items() if not path.exists()]
    if missing:
        print(f"SKIP: workspace files not found (integration test requires configured workspace): {', '.join(missing)}")
        catalog_index_md = None
        shard_bundle = None
        archive_catalog_md = None
        ledger_md = None
        quota_md = None
        workflows_md = None
        patterns_md = None
    else:
        catalog_index_md = read_text(workspace_files["catalog_index_md"])
        shard_bundle = ""
        if catalog_shards_dir.exists():
            for shard_file in sorted(catalog_shards_dir.glob("*.md")):
                shard_bundle += "\n" + read_text(shard_file)
        archive_catalog_md = read_text(workspace_files["archive_catalog_md"])
        ledger_md = read_text(workspace_files["ledger_md"])
        quota_md = read_text(workspace_files["quota_md"])
        workflows_md = read_text(workspace_files["workflows_md"])
        patterns_md = read_text(workspace_files["patterns_md"])

    assert_contains(skill_md, "## Deduplication Rules", "deduplication section")
    assert_contains(skill_md, "### Deduplication Algorithm", "index-first algorithm section")
    assert_contains(
        skill_md,
        "Read `memories/catalog.md` first — historically the flat catalog; now replaced by reading `memories/catalog-index.md` first to pick 1–2 candidate shards",
        "index-first shortlist rule",
    )
    assert_contains(skill_md, "## Shard Routing", "shard routing section")
    assert_contains(skill_md, "route_card(card_frontmatter) -> shard_name", "route_card signature")
    assert_contains(skill_md, "Use this exact append template:", "ledger template instruction")
    assert_contains(skill_md, "memories/proposals/UPDATE-[FILENAME]-[DATE].md", "proposal file policy")
    assert_contains(skill_md, "## Catalog Maintenance Rules", "catalog maintenance section")
    assert_contains(skill_md, "never regenerate the full catalog from scratch during a normal ingest run", "append-only catalog rule")
    assert_contains(
        skill_md,
        "refresh the matching entry in `memories/catalog-shards/core-identity.md`",
        "core-identity shard refresh rule",
    )
    assert_contains(skill_md, "Never search inside `experiences/processed/`.", "processed-folder ignore rule")
    assert_contains(skill_md, "remove any now-empty source directories", "empty-folder cleanup rule")
    assert_contains(skill_md, "memories/provider-quotas.md", "quota ledger ownership")
    assert_contains(skill_md, "`quota_update_mode`", "quota input")
    assert_contains(skill_md, "Update quota state only from `## Used Quota` lines", "quota ingestion rule")
    assert_contains(skill_md, "`Provider: Tavily | Scope: monthly | Used in run: 3`", "delta quota line shape")
    assert_contains(skill_md, "treat `used_in_run` as a per-run delta", "delta quota update rule")
    assert_contains(skill_md, "prefer the snapshot and do not add the delta on top", "snapshot precedence rule")
    assert_contains(skill_md, "- `quota_updates`", "ledger quota field")
    assert_contains(skill_md, "## Git Integration Rules", "git integration section")
    assert_contains(skill_md, "tools/git-integration/memories_commit.py", "git helper command")
    assert_contains(skill_md, "report `git integration not enabled` and finish successfully", "non-git fallback")
    assert_contains(skill_md, "Never attempt a remote push for `memories/`.", "local-only memories rule")
    assert_contains(skill_md, "do not update `memories/catalog-shards/core-identity.md` yet if the run produced only a proposal", "proposal-only catalog hold rule")

    # Workflow template assertions
    assert_contains(skill_md, "## Workflow Template Lifecycle", "workflow template lifecycle section")
    assert_contains(skill_md, "## Shared Workflow Fragment Rules", "shared fragment rules section")
    assert_contains(skill_md, "## Workflow Type Validation", "workflow type validation section")
    assert_contains(skill_md, "memories/workflow-templates/", "workflow templates directory reference")
    assert_contains(skill_md, "memories/workflow-templates/_shared/", "shared fragments directory reference")
    assert_contains(skill_md, "version_status: draft", "draft status in template")
    assert_contains(skill_md, "version_status: beta", "beta status reference")
    assert_contains(skill_md, "version_status: stable", "stable status reference")
    assert_contains(skill_md, "ready_for_review:", "ready for review field")
    assert_contains(skill_md, "sessions_observed", "sessions observed metric")
    assert_contains(skill_md, "mistake_rate_trend", "mistake rate trend metric")
    assert_contains(skill_md, "successful_sessions / sessions_observed >= 0.6", "success rate threshold")
    assert_contains(skill_md, "workflow_template_updates:", "ledger workflow template field")
    assert_contains(skill_md, "workflow_type_uncertainties:", "ledger workflow type uncertainty field")
    assert_contains(skill_md, "type: workflow_template", "catalog type for templates")
    assert_contains(skill_md, "type: workflow_fragment", "catalog type for fragments")
    assert_contains(skill_md, "Override Protection", "override protection heading")
    assert_contains(skill_md, "→ [shared:", "shared fragment reference notation")

    # Route Proposal Policy and Capacity Signals (brief m1-02).
    assert_contains(skill_md, "## Route Proposal Policy", "route proposal policy section")
    assert_contains(skill_md, "memories/proposals/ROUTE-<slug>-<date>.md", "route proposal file path")
    assert_contains(skill_md, "proposal_type: route_ambiguous_card", "route proposal type field")
    assert_contains(skill_md, "## Candidate shards", "route proposal candidate shards section")
    assert_contains(skill_md, "confirm misc (no clear shard", "route proposal confirm misc option")
    assert_contains(skill_md, "## Capacity Signals", "capacity signals section")
    assert_contains(skill_md, "[SIGNAL] misc-shard at", "misc signal format")
    assert_contains(skill_md, "[SIGNAL] catalog at", "catalog signal format")
    assert_contains(skill_md, "[SIGNAL]", "proposal signal marker")
    assert_contains(skill_md, "proposals pending — run memory-manager", "proposal signal format")
    assert_contains(skill_md, "MISC_SOFT_THRESHOLD", "misc threshold constant reference")
    assert_contains(skill_md, "CATALOG_PHASE2_THRESHOLD", "catalog threshold constant reference")
    assert_contains(skill_md, "PROPOSAL_REVIEW_THRESHOLD", "proposal threshold constant reference")
    assert_contains(skill_md, "### Misc Review (maintenance mode)", "misc review subsection")
    assert_contains(skill_md, "15b. **Route-proposal filing.**", "ingestion pipeline step 15b")

    if catalog_index_md is not None:
        assert_contains(catalog_index_md, "### core-identity", "index core-identity block")
        assert_contains(catalog_index_md, "- stable_tags:", "stable_tags field")
    if shard_bundle:
        for needle in (
            "memories/AGENTS.md",
            "memories/SOUL.md",
            "memories/IDENTITY.md",
            "memories/USER.md",
        ):
            assert_contains(shard_bundle, needle, "core-identity shard entry path")

    if archive_catalog_md is not None:
        assert_contains(archive_catalog_md, "# Archive Memory Catalog", "archive catalog header")

    if ledger_md is not None:
        assert_contains(ledger_md, "experiences/example-project/summary.md", "ledger processed file")
        assert_contains(
            ledger_md,
            "experiences/example-project/summary.md -> experiences/processed/example-project/summary.md",
            "ledger move record",
        )
        assert_contains(ledger_md, "- quota_updates:", "ledger quota updates field")

    if quota_md is not None:
        for needle in (
            "## Tavily",
            "- usage_period_key: 2026-03",
            "- used_total_unit: requests",
            "- allocation_mode: reserved_cap",
            "- allocation_cap: 200",
            "- last_ingested_experience: none",
            "## Brave",
            "- allocation_unit: requests",
            "## NewsAPI",
            "- allocation_mode: budget_total",
        ):
            assert_contains(quota_md, needle, "quota ledger field")

    if workflows_md is not None:
        for needle in (
            "Paper-Trail-First Execution",
            "Skills-As-Portable-Instructions",
        ):
            assert_contains(workflows_md, needle, "workflow entry")

    if patterns_md is not None:
        for needle in (
            "Core Workspace Layout",
            "Credentials-And-Boundaries",
            "Skill-Onboarding Pattern",
        ):
            assert_contains(patterns_md, needle, "project pattern entry")

    # Integration tests: workspace experience path checks (require configured workspace)
    active_experience = ROOT / "experiences/example-project/summary.md"
    active_experience_dir = ROOT / "experiences/example-project"
    processed_experience = ROOT / "experiences/processed/example-project/summary.md"

    if processed_experience.parent.exists():
        if active_experience.exists():
            raise AssertionError(f"Active inbox should be cleaned, but file still exists: {active_experience}")
        if active_experience_dir.exists():
            raise AssertionError(f"Empty source directory should be removed, but still exists: {active_experience_dir}")
        if not processed_experience.exists():
            raise AssertionError(f"Processed experience is missing: {processed_experience}")

    print("memory-manager test passed")
    return 0


# ---------------------------------------------------------------------------
# route_card unit tests and shard-write integration tests
# ---------------------------------------------------------------------------

class TestRouteCard(unittest.TestCase):
    def test_core_identity_path(self) -> None:
        self.assertEqual(route_card({"path": "memories/AGENTS.md"}), "core-identity.md")
        self.assertEqual(route_card({"path": "memories/USER.md"}), "core-identity.md")

    def test_workflow_template_type(self) -> None:
        self.assertEqual(
            route_card({"type": "workflow_template", "path": "memories/workflow-templates/foo.md"}),
            "workflow-templates.md",
        )

    def test_role_profile_type(self) -> None:
        self.assertEqual(route_card({"type": "role_profile"}), "roles.md")

    def test_hub_type(self) -> None:
        self.assertEqual(
            route_card({"type": "hub", "path": "memories/long-term/_hub-memory.md"}),
            "hubs.md",
        )

    def test_single_graduated_project(self) -> None:
        self.assertEqual(
            route_card({"projects": ["research-meeting"]}),
            "project-research-meeting.md",
        )

    def test_single_non_graduated_project(self) -> None:
        self.assertEqual(
            route_card({"projects": ["lsm4brain"]}),
            "project-continuity.md",
        )

    def test_paper_reader_slug_prefix(self) -> None:
        self.assertEqual(
            route_card({"slug": "paper-reader-pipeline-tips", "projects": []}),
            "paper-reading.md",
        )

    def test_paper_reading_topic(self) -> None:
        self.assertEqual(
            route_card({"topics": ["paper-reader", "paper-discovery"], "projects": []}),
            "paper-reading.md",
        )

    def test_memory_prefix(self) -> None:
        self.assertEqual(
            route_card({"slug": "memory-ingestion-flow", "projects": []}),
            "memory-system.md",
        )

    def test_memory_topic(self) -> None:
        self.assertEqual(
            route_card({"topics": ["retrieval"], "projects": []}),
            "memory-system.md",
        )

    def test_market_slug(self) -> None:
        self.assertEqual(
            route_card({"slug": "market-watcher-quota", "projects": []}),
            "market-ops.md",
        )

    def test_tooling_git_topic(self) -> None:
        self.assertEqual(
            route_card({"topics": ["git"], "projects": []}),
            "tooling-ops.md",
        )

    def test_session_handoff_topic(self) -> None:
        self.assertEqual(
            route_card({"topics": ["session-handoff"], "projects": []}),
            "session-ops.md",
        )

    def test_skill_slug_prefix(self) -> None:
        self.assertEqual(
            route_card({"slug": "skill-onboarding-pattern", "projects": []}),
            "skill-ops.md",
        )

    def test_agent_ops_topic(self) -> None:
        self.assertEqual(
            route_card({"topics": ["agent-ops", "safety"], "projects": []}),
            "agent-ops.md",
        )

    def test_writing_style_topic(self) -> None:
        self.assertEqual(
            route_card({"topics": ["writing", "review"], "projects": []}),
            "writing-style.md",
        )

    def test_falls_through_to_misc(self) -> None:
        self.assertEqual(
            route_card({"topics": ["unfamiliar-topic"], "projects": []}),
            "misc.md",
        )


# ---------------------------------------------------------------------------
# Labeled corpus + per-rule + precedence + coverage tests (2026-05-01).
#
# Each fixture asserts BOTH the destination shard AND the firing rule index
# (via route_card_with_index). Rule-index assertion catches ordering bugs
# ("rule X moved up, broke rule Y") that pure shard-equality tests miss.
# Pattern: DroolsAssert / DMN Unique hit-policy.
# ---------------------------------------------------------------------------


class TestRoutingCorpus(unittest.TestCase):
    """One fixture per rule + variants. Asserts (shard, rule_index)."""

    CORPUS: list[tuple[str, dict, str, int]] = [
        # === Block 1: identity / type / project ===
        ("core-identity AGENTS.md", {"path": "memories/AGENTS.md"}, "core-identity.md", 1),
        ("core-identity USER.md", {"path": "memories/USER.md"}, "core-identity.md", 1),
        ("workflow_template", {"type": "workflow_template"}, "workflow-templates.md", 2),
        ("role_profile", {"type": "role_profile"}, "roles.md", 3),
        ("hub", {"type": "hub"}, "hubs.md", 4),
        ("graduated project (research-meeting)", {"projects": ["research-meeting"]}, "project-research-meeting.md", 5),
        ("graduated project (coordination)", {"projects": ["coordination"]}, "project-coordination.md", 5),
        ("non-graduated sole project", {"projects": ["lsm4brain"]}, "project-continuity.md", 6),

        # === Block 2: topical — paper-reading (rule 7) ===
        ("paper-reader- slug", {"slug": "paper-reader-foo", "projects": []}, "paper-reading.md", 7),
        ("paper-discovery- slug", {"slug": "paper-discovery-foo", "projects": []}, "paper-reading.md", 7),
        ("paper-review- slug", {"slug": "paper-review-foo", "projects": []}, "paper-reading.md", 7),
        ("paper-reading topic", {"topics": ["paper-reading"], "projects": []}, "paper-reading.md", 7),
        ("paper-reader topic", {"topics": ["paper-reader"], "projects": []}, "paper-reading.md", 7),
        ("reading-strategy (NEW)", {"topics": ["reading-strategy"], "projects": []}, "paper-reading.md", 7),
        ("industry-reports (NEW)", {"topics": ["industry-reports"], "projects": []}, "paper-reading.md", 7),
        # `stopping-rule` was considered for paper-reading but dropped: too
        # generic (matches autonomous-iteration / decision-making cards too).
        # The motivating card `marginal-return-stopping-rule-for-industry-
        # report-reading` still routes via `reading-strategy` / `industry-
        # reports` so coverage is preserved.

        # === Block 2: topical — memory-system (rule 8) ===
        ("memory- slug prefix", {"slug": "memory-foo", "projects": []}, "memory-system.md", 8),
        ("catalog- slug prefix", {"slug": "catalog-foo", "projects": []}, "memory-system.md", 8),
        ("manager-ledger path (NEW)", {"path": "memories/manager-ledger.md", "projects": []}, "memory-system.md", 8),
        ("memory-manager project prefix (NEW)", {"projects": ["memory-manager-v1", "foo"]}, "memory-system.md", 8),
        ("memory-ingestion topic", {"topics": ["memory-ingestion"], "projects": []}, "memory-system.md", 8),
        ("retrieval topic", {"topics": ["retrieval"], "projects": []}, "memory-system.md", 8),
        ("memory-manager topic (NEW)", {"topics": ["memory-manager"], "projects": []}, "memory-system.md", 8),
        ("operations topic (NEW)", {"topics": ["operations"], "projects": []}, "memory-system.md", 8),
        ("ingestion-ledger topic (NEW)", {"topics": ["ingestion-ledger"], "projects": []}, "memory-system.md", 8),

        # === Block 2: topical — market-ops (rule 9) ===
        ("market- slug prefix", {"slug": "market-foo", "projects": []}, "market-ops.md", 9),
        ("portfolio- slug prefix", {"slug": "portfolio-foo", "projects": []}, "market-ops.md", 9),
        ("US-Iran project prefix (NEW)", {"projects": ["US-Iran-tracker", "foo"]}, "market-ops.md", 9),
        ("us-iran lowercase project prefix (NEW)", {"projects": ["us-iran-bridge", "foo"]}, "market-ops.md", 9),
        ("market-watcher topic", {"topics": ["market-watcher"], "projects": []}, "market-ops.md", 9),
        ("provider-orchestration (NEW)", {"topics": ["provider-orchestration"], "projects": []}, "market-ops.md", 9),
        ("report-validation (NEW)", {"topics": ["report-validation"], "projects": []}, "market-ops.md", 9),
        ("evidence-synthesis (NEW)", {"topics": ["evidence-synthesis"], "projects": []}, "market-ops.md", 9),
        ("geopolitics (NEW)", {"topics": ["geopolitics"], "projects": []}, "market-ops.md", 9),
        ("market-risk (NEW)", {"topics": ["market-risk"], "projects": []}, "market-ops.md", 9),
        ("us-iran topic (NEW)", {"topics": ["us-iran"], "projects": []}, "market-ops.md", 9),

        # === Block 2: topical — tooling-ops (rule 10) ===
        ("git topic", {"topics": ["git"], "projects": []}, "tooling-ops.md", 10),
        ("credential-broker topic", {"topics": ["credential-broker"], "projects": []}, "tooling-ops.md", 10),
        ("obsidian (NEW)", {"topics": ["obsidian"], "projects": []}, "tooling-ops.md", 10),
        ("knowledge-graph (NEW)", {"topics": ["knowledge-graph"], "projects": []}, "tooling-ops.md", 10),
        ("vault-operations (NEW)", {"topics": ["vault-operations"], "projects": []}, "tooling-ops.md", 10),
        ("model-routing (NEW)", {"topics": ["model-routing"], "projects": []}, "tooling-ops.md", 10),
        ("provider-selection (NEW)", {"topics": ["provider-selection"], "projects": []}, "tooling-ops.md", 10),
        ("capability-map (NEW)", {"topics": ["capability-map"], "projects": []}, "tooling-ops.md", 10),
        ("pandoc (NEW)", {"topics": ["pandoc"], "projects": []}, "tooling-ops.md", 10),
        ("latex (NEW)", {"topics": ["latex"], "projects": []}, "tooling-ops.md", 10),
        ("mathjax (NEW)", {"topics": ["mathjax"], "projects": []}, "tooling-ops.md", 10),
        ("deliverable-tooling (NEW)", {"topics": ["deliverable-tooling"], "projects": []}, "tooling-ops.md", 10),
        ("reproducibility (NEW)", {"topics": ["reproducibility"], "projects": []}, "tooling-ops.md", 10),

        # === Block 2: topical — writing-style (rule 11, precedes session-ops) ===
        ("writing topic", {"topics": ["writing"], "projects": []}, "writing-style.md", 11),
        ("manuscript topic", {"topics": ["manuscript"], "projects": []}, "writing-style.md", 11),
        ("review topic", {"topics": ["review"], "projects": []}, "writing-style.md", 11),
        ("academic-writing topic", {"topics": ["academic-writing"], "projects": []}, "writing-style.md", 11),
        ("documentation-design (NEW)", {"topics": ["documentation-design"], "projects": []}, "writing-style.md", 11),
        ("deliverable-design (NEW)", {"topics": ["deliverable-design"], "projects": []}, "writing-style.md", 11),
        ("user-facing (NEW)", {"topics": ["user-facing"], "projects": []}, "writing-style.md", 11),
        ("citations (NEW)", {"topics": ["citations"], "projects": []}, "writing-style.md", 11),
        ("bibtex (NEW)", {"topics": ["bibtex"], "projects": []}, "writing-style.md", 11),
        ("reference-management (NEW)", {"topics": ["reference-management"], "projects": []}, "writing-style.md", 11),

        # SYNONYMS (canonicalized via normalize_tags before rules execute)
        ("manuscript-review SYNONYM->manuscript", {"topics": ["manuscript-review"], "projects": []}, "writing-style.md", 11),
        ("review-style SYNONYM->review", {"topics": ["review-style"], "projects": []}, "writing-style.md", 11),
        ("review-writing SYNONYM->review", {"topics": ["review-writing"], "projects": []}, "writing-style.md", 11),
        ("writing-voice SYNONYM->writing", {"topics": ["writing-voice"], "projects": []}, "writing-style.md", 11),
        ("academic-review SYNONYM->review", {"topics": ["academic-review"], "projects": []}, "writing-style.md", 11),
        # paper-review synonym → review (writing-style). The misc-drain cards
        # tagged paper-review are about review-comment style, not paper-reading
        # workflow, so the canonical is `review` not `paper-reading`.
        ("paper-review SYNONYM->review", {"topics": ["paper-review"], "projects": []}, "writing-style.md", 11),

        # === Block 2: topical — session-ops (rule 12) ===
        ("research-meeting- slug", {"slug": "research-meeting-foo", "projects": []}, "session-ops.md", 12),
        ("session- slug", {"slug": "session-foo", "projects": []}, "session-ops.md", 12),
        ("research-meeting topic", {"topics": ["research-meeting"], "projects": []}, "session-ops.md", 12),
        ("session-handoff topic", {"topics": ["session-handoff"], "projects": []}, "session-ops.md", 12),
        ("decision-making (NEW)", {"topics": ["decision-making"], "projects": []}, "session-ops.md", 12),
        ("rule-enforcement (NEW)", {"topics": ["rule-enforcement"], "projects": []}, "session-ops.md", 12),
        ("evaluation (NEW)", {"topics": ["evaluation"], "projects": []}, "session-ops.md", 12),
        ("documentation-pattern (NEW)", {"topics": ["documentation-pattern"], "projects": []}, "session-ops.md", 12),
        ("subagent-delegation (NEW)", {"topics": ["subagent-delegation"], "projects": []}, "session-ops.md", 12),
        ("verification (NEW)", {"topics": ["verification"], "projects": []}, "session-ops.md", 12),
        ("research-process (NEW)", {"topics": ["research-process"], "projects": []}, "session-ops.md", 12),
        ("planning (NEW)", {"topics": ["planning"], "projects": []}, "session-ops.md", 12),
        ("workflow-governance (NEW)", {"topics": ["workflow-governance"], "projects": []}, "session-ops.md", 12),
        ("project-kickoff (NEW)", {"topics": ["project-kickoff"], "projects": []}, "session-ops.md", 12),
        ("personal-productivity (NEW)", {"topics": ["personal-productivity"], "projects": []}, "session-ops.md", 12),

        # === Block 2: topical — skill-ops (rule 13) ===
        ("ralph- slug", {"slug": "ralph-foo", "projects": []}, "skill-ops.md", 13),
        ("skill- slug", {"slug": "skill-foo", "projects": []}, "skill-ops.md", 13),
        ("skill-design topic", {"topics": ["skill-design"], "projects": []}, "skill-ops.md", 13),
        ("strangler-fig topic", {"topics": ["strangler-fig"], "projects": []}, "skill-ops.md", 13),
        ("agent-architecture (NEW)", {"topics": ["agent-architecture"], "projects": []}, "skill-ops.md", 13),
        ("modularity (NEW)", {"topics": ["modularity"], "projects": []}, "skill-ops.md", 13),
        ("resilience (NEW)", {"topics": ["resilience"], "projects": []}, "skill-ops.md", 13),

        # === Block 2: topical — agent-ops (rule 14) ===
        ("agent-ops topic", {"topics": ["agent-ops"], "projects": []}, "agent-ops.md", 14),
        ("safety topic", {"topics": ["safety"], "projects": []}, "agent-ops.md", 14),
        ("preflight topic", {"topics": ["preflight"], "projects": []}, "agent-ops.md", 14),
        ("paper-trail topic", {"topics": ["paper-trail"], "projects": []}, "agent-ops.md", 14),

        # === Block 3: fallback (rule 15) ===
        ("falls through to misc", {"topics": ["unfamiliar-topic"], "projects": []}, "misc.md", 15),
    ]

    def test_corpus(self) -> None:
        for label, frontmatter, expected_shard, expected_rule in self.CORPUS:
            with self.subTest(label=label):
                shard, rule = route_card_with_index(frontmatter)
                self.assertEqual(shard, expected_shard, f"{label}: shard mismatch")
                self.assertEqual(rule, expected_rule, f"{label}: rule index mismatch")

    def test_precedence_writing_beats_session(self) -> None:
        """Card with both documentation-pattern (session-ops) and
        documentation-design (writing-style) routes to writing-style.
        Writing-style precedes session-ops in the ladder by design.
        """
        shard, rule = route_card_with_index({
            "topics": ["documentation-pattern", "documentation-design"],
            "projects": [],
        })
        self.assertEqual(shard, "writing-style.md")
        self.assertEqual(rule, 11)

    def test_coverage_every_rule_fires(self) -> None:
        """Every rule index 1-15 fires at least once across the corpus."""
        fired = set()
        for _label, frontmatter, _shard, _rule in self.CORPUS:
            _shard, rule = route_card_with_index(frontmatter)
            fired.add(rule)
        expected = set(range(1, 16))
        missing = expected - fired
        self.assertFalse(missing, f"Rule indices never fire across corpus: {sorted(missing)}")


class TestSynonyms(unittest.TestCase):
    """SYNONYMS dict + normalize_tags helper."""

    def test_synonyms_dict_has_six_initial_entries(self) -> None:
        self.assertEqual(len(SYNONYMS), 6)
        self.assertIn("manuscript-review", SYNONYMS)
        self.assertEqual(SYNONYMS["manuscript-review"], "manuscript")

    def test_normalize_tags_extends_with_canonical(self) -> None:
        result = normalize_tags(["manuscript-review", "foo"])
        self.assertIn("manuscript-review", result)  # original preserved
        self.assertIn("manuscript", result)  # canonical added
        self.assertIn("foo", result)  # non-synonym preserved

    def test_normalize_tags_handles_empty(self) -> None:
        self.assertEqual(normalize_tags([]), set())
        self.assertEqual(normalize_tags(None), set())
        self.assertEqual(normalize_tags(""), set())

    def test_normalize_tags_lowercases(self) -> None:
        result = normalize_tags(["Foo", "BAR"])
        self.assertEqual(result, {"foo", "bar"})

    def test_synonym_routes_through_canonical(self) -> None:
        """A card tagged with a synonym should route as if it carried the
        canonical tag."""
        shard, _ = route_card_with_index({"topics": ["manuscript-review"], "projects": []})
        self.assertEqual(shard, "writing-style.md")


# ---------------------------------------------------------------------------
# Golden-file snapshot + differential test against route_card_old (2026-05-01).
#
# Pattern: differential testing (McKeeman 1998 / Evans & Savoia) at
# file-system scale. The 246 existing cards under ~/Documents/memory/ are
# the historical corpus; this test routes them through the snapshotted
# pre-2026-05-01 ladder AND the current ladder, and asserts that any diff
# is in the explicit whitelist of intended migrations.
#
# Skips gracefully if ~/Documents/memory/ is not present (CI / fresh clones).
# ---------------------------------------------------------------------------


import os
import yaml


def _live_memory_root() -> Path | None:
    """Locate the live memory root or return None if unavailable."""
    candidates = [
        Path.home() / "Documents" / "memory",
        Path(os.environ.get("MEMORY_ROOT", "/nonexistent")),
    ]
    for c in candidates:
        if c.is_dir() and (c / "long-term").is_dir():
            return c
    return None


_FRONTMATTER_RE = __import__("re").compile(r"^---\n(.*?)\n---", __import__("re").DOTALL)


def _read_frontmatter(card_path: Path) -> dict | None:
    try:
        text = card_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    if "slug" not in fm:
        fm["slug"] = card_path.stem
    if "path" not in fm:
        rel = "memories/" + str(card_path.relative_to(card_path.parents[1]))
        fm["path"] = rel
    return fm


class TestGoldenSnapshot(unittest.TestCase):
    """Golden-file regression: re-route the live 246-card corpus and assert
    the result matches a committed snapshot. Diffs in routing_snapshot.txt
    become the review artifact for any future routing-rule PR.
    """

    SNAPSHOT_PATH = Path(__file__).parent / "test_fixtures" / "routing_snapshot.txt"

    @staticmethod
    def _produce_snapshot(memory_root: Path) -> str:
        rows = []
        for sub in ("long-term", "short-term"):
            d = memory_root / sub
            if not d.is_dir():
                continue
            for card_path in sorted(d.glob("*.md")):
                fm = _read_frontmatter(card_path)
                if fm is None:
                    continue
                shard, rule = route_card_with_index(fm)
                rows.append(f"{fm['slug']} -> {shard}, rule_{rule}")
        rows.sort()
        return "\n".join(rows) + "\n"

    def test_snapshot_matches_or_emit(self) -> None:
        memory_root = _live_memory_root()
        if memory_root is None:
            self.skipTest("Live memory root not present; skipping golden snapshot.")
        produced = self._produce_snapshot(memory_root)
        if not self.SNAPSHOT_PATH.exists() or os.environ.get("UPDATE_GOLDEN") == "1":
            self.SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.SNAPSHOT_PATH.write_text(produced, encoding="utf-8")
            print(f"WROTE golden snapshot: {self.SNAPSHOT_PATH}")
            return
        committed = self.SNAPSHOT_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            produced,
            committed,
            "Routing snapshot diff. Re-run with UPDATE_GOLDEN=1 if intentional, "
            "and commit the diff in the same PR.",
        )


class TestDifferentialRouteCard(unittest.TestCase):
    """Differential test: route_card_old vs current route_card on the live
    corpus. Asserts every (slug, old_shard, new_shard) diff is in the
    INTENDED_MIGRATIONS whitelist. Catches accidental routing changes that
    the labeled corpus might not cover.
    """

    # 2026-05-01 ladder widening — slugs that intentionally migrate.
    # Each entry: (slug, expected_old_shard, expected_new_shard).
    # Empty list means "no diffs allowed."
    INTENDED_MIGRATIONS: list[tuple[str, str, str]] = [
        # === Misc drains (cards that previously fell through to misc) ===
        ("anchor-string-verification-for-review-comments", "misc.md", "writing-style.md"),
        ("bibtex-per-field-verification-from-canonical-source", "misc.md", "writing-style.md"),
        ("confidence-rating-with-path-to-higher", "misc.md", "session-ops.md"),
        ("core-vs-adapter-architecture", "misc.md", "skill-ops.md"),
        ("cross-check-primary-sources-on-surprise-conclusions", "misc.md", "session-ops.md"),
        ("diagnose-vs-pick-decision-shapes", "misc.md", "session-ops.md"),
        ("dont-propose-bypasses-for-load-bearing-rules", "misc.md", "session-ops.md"),
        ("escalate-after-sandbox-dns-failure", "misc.md", "market-ops.md"),
        ("excalidraw-file-first-agent-workflow", "misc.md", "tooling-ops.md"),
        ("give-user-facing-guidance-in-final-actionable-form", "misc.md", "writing-style.md"),
        ("hierarchical-summarization-before-drafting", "misc.md", "market-ops.md"),
        ("inline-review-planning-pattern", "misc.md", "session-ops.md"),
        ("iterative-milestones-for-personal-projects", "misc.md", "session-ops.md"),
        ("marginal-return-stopping-rule-for-industry-report-reading", "misc.md", "paper-reading.md"),
        ("non-lead-author-manuscript-comment-style", "misc.md", "writing-style.md"),
        ("openclaw-routing-and-memorysearch-pinning", "misc.md", "tooling-ops.md"),
        ("pandoc-math-deliverable-setup-pattern", "misc.md", "tooling-ops.md"),
        ("python-extraction-for-large-provider-jsons", "misc.md", "market-ops.md"),
        ("review-voice-constructive-by-default", "misc.md", "writing-style.md"),
        ("review-writing-workflow-patterns", "misc.md", "writing-style.md"),
        ("sensitive-proposal-staging", "misc.md", "memory-system.md"),
        ("stringent-production-profile-expectations", "misc.md", "market-ops.md"),
        ("subagent-summaries-are-partial", "misc.md", "session-ops.md"),
        ("summary-block-at-top-of-deliverable", "misc.md", "writing-style.md"),
        ("us-iran-follow-up", "misc.md", "market-ops.md"),

        # === Cross-shard refinements (writing-style now wins for deliverable
        #     and manuscript-discipline cards previously routed to session-ops
        #     via "session-" slug-substring or research-meeting topic) ===
        ("anchor-collaborator-deliverables-on-existing-objects", "session-ops.md", "writing-style.md"),
        ("hawkes-session-9-continuity", "session-ops.md", "writing-style.md"),
        ("hawkes-session-10-continuity", "session-ops.md", "writing-style.md"),
        ("hawkes-session-11-continuity", "session-ops.md", "writing-style.md"),
        ("hawkes-session-15-continuity", "session-ops.md", "writing-style.md"),
        ("lemma-side-by-side-means-display-equations", "session-ops.md", "writing-style.md"),
        ("non-lead-author-findings-tracker-format", "session-ops.md", "writing-style.md"),
        ("two-deliverables-when-consumption-modes-differ", "session-ops.md", "writing-style.md"),

        # === skill-ops -> writing-style for documentation-design cards ===
        ("user-facing-agent-facing-doc-separation", "skill-ops.md", "writing-style.md"),

        # === skill-ops -> session-ops for subagent-delegation cards
        #     (silent context consumption is fundamentally a subagent-behavior
        #     pattern even though it touches skill-design) ===
        ("silent-context-consumption-is-the-default", "skill-ops.md", "session-ops.md"),
    ]

    def test_no_unexpected_diffs(self) -> None:
        memory_root = _live_memory_root()
        if memory_root is None:
            self.skipTest("Live memory root not present; skipping differential test.")
        diffs: list[tuple[str, str, str]] = []
        for sub in ("long-term", "short-term"):
            d = memory_root / sub
            if not d.is_dir():
                continue
            for card_path in sorted(d.glob("*.md")):
                fm = _read_frontmatter(card_path)
                if fm is None:
                    continue
                old_shard = route_card_old(fm)
                new_shard = route_card(fm)
                if old_shard != new_shard:
                    diffs.append((fm["slug"], old_shard, new_shard))

        whitelist = set(self.INTENDED_MIGRATIONS)
        unexpected = [d for d in diffs if d not in whitelist]
        if unexpected:
            sample = "\n  ".join(f"{s}: {o} -> {n}" for s, o, n in unexpected[:20])
            self.fail(
                f"{len(unexpected)} unexpected routing diffs (showing up to 20):\n  {sample}\n"
                f"If these are intended, add them to INTENDED_MIGRATIONS."
            )
        # Optional warning: whitelist entries that didn't actually migrate
        # (e.g., card was deleted or re-tagged) are not failures.


class TestShardWriteAndIndexUpdate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.shards = self.root / "catalog-shards"
        self.shards.mkdir()
        # Minimal index with a paper-reading block.
        (self.root / "catalog-index.md").write_text(
            """# Memory Catalog Index

## Registered projects

<!-- registry -->

## Shards

### paper-reading
- path: catalog-shards/paper-reading.md
- description: paper-reader pipeline and vault integration.
- stable_tags: [paper-reader, paper-discovery]
- card_count: 0
- last_updated:

### misc
- path: catalog-shards/misc.md
- description: Quarantine.
- stable_tags: [misc]
- card_count: 0
- last_updated:
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ingest_paper_card_routes_to_paper_reading(self) -> None:
        frontmatter = {
            "slug": "paper-reader-foo",
            "topics": ["paper-reader", "paper-discovery"],
            "projects": [],
        }
        shard = route_card(frontmatter)
        self.assertEqual(shard, "paper-reading.md")

        entry = (
            "## paper-reader-foo\n\n"
            "- path: memories/long-term/paper-reader-foo.md\n"
            "- topics: [paper-reader, paper-discovery]\n"
            "- updated: 2026-04-23\n"
        )
        write_entry_to_shard(self.shards, shard, "paper-reader-foo", entry)

        shard_text = (self.shards / shard).read_text()
        self.assertIn("## paper-reader-foo", shard_text)
        # Entry is in Generated subsection. Use real line-starting heading
        # positions (the header blurb mentions `## Generated Entries` inline).
        import re as _re
        def _line_pos(pattern: str) -> int:
            m = _re.search(pattern, shard_text, _re.MULTILINE)
            return m.start() if m else -1
        gen_idx = _line_pos(r"^## Generated Entries\s*$")
        man_idx = _line_pos(r"^## Manual Entries\s*$")
        slug_idx = _line_pos(r"^## paper-reader-foo\s*$")
        self.assertTrue(gen_idx < slug_idx < man_idx)

        update_index_for_shard(self.root, shard)
        index_text = (self.root / "catalog-index.md").read_text()
        self.assertIn("- card_count: 1", index_text)
        self.assertIn("- last_updated: 2026-04-23", index_text)
        # stable_tags and description untouched.
        self.assertIn("- stable_tags: [paper-reader, paper-discovery]", index_text)
        self.assertIn("paper-reader pipeline and vault integration", index_text)

    def test_hawkes_single_project_routes_to_project_continuity(self) -> None:
        # Hawkes is not graduated, so a sole-project Hawkes card goes to
        # project-continuity (per the routing ladder rule 6).
        frontmatter = {"slug": "hawkes-continuity", "projects": ["hawkes"]}
        self.assertEqual(route_card(frontmatter), "project-continuity.md")

    def test_research_meeting_single_project_routes_to_project_shard(self) -> None:
        frontmatter = {
            "slug": "research-meeting-notes",
            "projects": ["research-meeting"],
        }
        self.assertEqual(route_card(frontmatter), "project-research-meeting.md")


# ---------------------------------------------------------------------------
# Route-proposal and capacity-signal unit tests
# ---------------------------------------------------------------------------


class TestFileRouteProposal(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proposals = self.root / "proposals"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_creates_proposal_file_with_expected_template(self) -> None:
        card = {
            "slug": "ambiguous-card",
            "card_path": "memories/long-term/ambiguous-card.md",
            "type": "project-pattern",
            "topics": ["unusual-topic", "other"],
            "projects": [],
            "source_experience": "experiences/demo/summary.md",
        }
        candidates = [("paper-reading.md", "partial topic overlap")]
        target = file_route_proposal(card, candidates, proposals_dir=self.proposals)
        self.assertTrue(target.exists())
        self.assertTrue(target.name.startswith("ROUTE-ambiguous-card-"))
        self.assertTrue(target.name.endswith(".md"))
        text = target.read_text(encoding="utf-8")
        self.assertIn("# Proposed Route: ambiguous-card", text)
        self.assertIn("proposal_type: route_ambiguous_card", text)
        self.assertIn("card_slug: ambiguous-card", text)
        self.assertIn("card_path: memories/long-term/ambiguous-card.md", text)
        self.assertIn("current_shard: catalog-shards/misc.md", text)
        self.assertIn("experiences/demo/summary.md", text)
        self.assertIn("## Routing signals", text)
        self.assertIn("type: project-pattern", text)
        self.assertIn("unusual-topic", text)
        self.assertIn("## Candidate shards", text)
        self.assertIn("- [ ] catalog-shards/paper-reading.md — partial topic overlap", text)
        self.assertIn("- [ ] confirm misc", text)
        self.assertIn("## User decision", text)


class TestGenerateRouteCandidates(unittest.TestCase):
    def test_partial_topic_overlap_returns_shards(self) -> None:
        fm = {"topics": ["paper-reading", "memory-ingestion"]}
        result = generate_route_candidates(fm)
        shards = [s for s, _ in result]
        self.assertIn("paper-reading.md", shards)
        self.assertIn("memory-system.md", shards)

    def test_no_overlap_returns_empty(self) -> None:
        fm = {"topics": ["completely-unknown-topic"]}
        self.assertEqual(generate_route_candidates(fm), [])

    def test_caps_at_three(self) -> None:
        # Topics overlapping four shards.
        fm = {"topics": ["paper-reading", "memory-ingestion", "market", "git"]}
        result = generate_route_candidates(fm)
        self.assertLessEqual(len(result), 3)


class TestCapacitySignals(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "catalog-shards").mkdir()
        (self.root / "proposals").mkdir()
        (self.root / "manager-ledger.md").write_text(
            "# Memory Manager Ledger\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_misc_signal_emits_at_threshold_and_not_re_emits(self) -> None:
        signals = check_and_emit_capacity_signals(
            self.root,
            misc_card_count=MISC_SOFT_THRESHOLD,
            total_card_count=0,
            pending_proposal_count=0,
        )
        self.assertEqual(len(signals), 1)
        self.assertIn("misc-shard at 15", signals[0])

        # Second call with the count still above threshold: no re-emit.
        signals2 = check_and_emit_capacity_signals(
            self.root,
            misc_card_count=MISC_SOFT_THRESHOLD + 1,
            total_card_count=0,
            pending_proposal_count=0,
        )
        self.assertEqual(signals2, [])

    def test_catalog_phase2_signal(self) -> None:
        signals = check_and_emit_capacity_signals(
            self.root,
            misc_card_count=0,
            total_card_count=CATALOG_PHASE2_THRESHOLD,
            pending_proposal_count=0,
        )
        self.assertEqual(len(signals), 1)
        self.assertIn("catalog at 500", signals[0])

    def test_proposal_review_signal(self) -> None:
        signals = check_and_emit_capacity_signals(
            self.root,
            misc_card_count=0,
            total_card_count=0,
            pending_proposal_count=PROPOSAL_REVIEW_THRESHOLD,
        )
        self.assertEqual(len(signals), 1)
        self.assertIn("10 proposals pending", signals[0])

    def test_below_threshold_emits_nothing(self) -> None:
        signals = check_and_emit_capacity_signals(
            self.root,
            misc_card_count=MISC_SOFT_THRESHOLD - 1,
            total_card_count=CATALOG_PHASE2_THRESHOLD - 1,
            pending_proposal_count=PROPOSAL_REVIEW_THRESHOLD - 1,
        )
        self.assertEqual(signals, [])


class TestProcessRouteProposals(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.shards = self.root / "catalog-shards"
        self.shards.mkdir()
        self.proposals = self.root / "proposals"
        self.proposals.mkdir()

        # Minimal index with misc and paper-reading blocks.
        (self.root / "catalog-index.md").write_text(
            """# Memory Catalog Index

## Registered projects

## Shards

### paper-reading
- path: catalog-shards/paper-reading.md
- description: paper-reader pipeline.
- stable_tags: [paper-reader]
- card_count: 0
- last_updated:

### misc
- path: catalog-shards/misc.md
- description: Quarantine.
- stable_tags: [misc]
- card_count: 2
- last_updated:
""",
            encoding="utf-8",
        )

        # Seed misc with two cards.
        misc_text = (
            "# Catalog Shard — misc\n\n"
            "Searchable memory cards routed to misc.\n\n"
            "## Generated Entries\n\n"
            "## card-one\n\n"
            "- path: memories/long-term/card-one.md\n"
            "- topics: [paper-reading]\n"
            "- updated: 2026-04-22\n\n"
            "## card-two\n\n"
            "- path: memories/long-term/card-two.md\n"
            "- topics: [paper-reading]\n"
            "- updated: 2026-04-22\n\n"
            "## Manual Entries\n"
        )
        (self.shards / "misc.md").write_text(misc_text, encoding="utf-8")

        # Empty paper-reading shard.
        (self.shards / "paper-reading.md").write_text(
            SHARD_HEADER_TEMPLATE.format(name="paper-reading"),
            encoding="utf-8",
        )

        # Two ROUTE-* proposals with the paper-reading option pre-checked.
        def _proposal(slug: str) -> str:
            return (
                f"# Proposed Route: {slug}\n\n"
                f"- created_at: 2026-04-23T10:00:00-07:00\n"
                f"- proposal_type: route_ambiguous_card\n"
                f"- card_slug: {slug}\n"
                f"- card_path: memories/long-term/{slug}.md\n"
                f"- current_shard: catalog-shards/misc.md\n"
                f"- source_experience: experiences/demo.md\n"
                f"- reason: test fixture\n\n"
                f"## Routing signals\n\n"
                f"- type: project-pattern\n"
                f"- topics: paper-reading\n"
                f"- projects: (none)\n\n"
                f"## Candidate shards\n\n"
                f"- [x] catalog-shards/paper-reading.md — partial overlap\n"
                f"- [ ] confirm misc\n\n"
                f"## User decision\n"
            )

        (self.proposals / "ROUTE-card-one-2026-04-23.md").write_text(
            _proposal("card-one"), encoding="utf-8"
        )
        (self.proposals / "ROUTE-card-two-2026-04-23.md").write_text(
            _proposal("card-two"), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_maintenance_moves_cards_and_archives_proposals(self) -> None:
        results = process_route_proposals(self.root, interactive=False)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["action"], "moved_to:paper-reading.md")

        # misc shard emptied.
        misc_text = (self.shards / "misc.md").read_text()
        self.assertNotIn("## card-one", misc_text)
        self.assertNotIn("## card-two", misc_text)

        # paper-reading gained them.
        paper_text = (self.shards / "paper-reading.md").read_text()
        self.assertIn("## card-one", paper_text)
        self.assertIn("## card-two", paper_text)

        # index updated.
        index_text = (self.root / "catalog-index.md").read_text()
        # misc card_count should now be 0; paper-reading should be 2.
        misc_block = index_text.split("### misc", 1)[1]
        self.assertIn("- card_count: 0", misc_block)
        paper_block = index_text.split("### paper-reading", 1)[1].split("###", 1)[0]
        self.assertIn("- card_count: 2", paper_block)

        # proposal files moved to resolved/YYYY-MM/.
        self.assertFalse(list(self.proposals.glob("ROUTE-*.md")))
        resolved_files = list((self.proposals / "resolved").rglob("ROUTE-*.md"))
        self.assertEqual(len(resolved_files), 2)
        for p in resolved_files:
            self.assertIn("resolution: moved_to:paper-reading.md", p.read_text())


if __name__ == "__main__":
    # Run both the SKILL.md script test and the unittest suites.
    try:
        main_result = main()
    except AssertionError as exc:
        print(f"memory-manager test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if main_result != 0:
        raise SystemExit(main_result)
    # Run the unittest suites.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestRouteCard))
    suite.addTests(loader.loadTestsFromTestCase(TestRoutingCorpus))
    suite.addTests(loader.loadTestsFromTestCase(TestSynonyms))
    suite.addTests(loader.loadTestsFromTestCase(TestGoldenSnapshot))
    suite.addTests(loader.loadTestsFromTestCase(TestDifferentialRouteCard))
    suite.addTests(loader.loadTestsFromTestCase(TestShardWriteAndIndexUpdate))
    suite.addTests(loader.loadTestsFromTestCase(TestFileRouteProposal))
    suite.addTests(loader.loadTestsFromTestCase(TestGenerateRouteCandidates))
    suite.addTests(loader.loadTestsFromTestCase(TestCapacitySignals))
    suite.addTests(loader.loadTestsFromTestCase(TestProcessRouteProposals))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
