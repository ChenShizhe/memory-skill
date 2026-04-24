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
    write_entry_to_shard,
    update_index_for_shard,
    SHARD_HEADER_TEMPLATE,
)


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
    suite.addTests(loader.loadTestsFromTestCase(TestShardWriteAndIndexUpdate))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
