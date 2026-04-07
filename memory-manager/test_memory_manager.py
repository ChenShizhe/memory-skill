#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
        "catalog_md": ROOT / "memories/catalog.md",
        "archive_catalog_md": ROOT / "memories/archive-catalog.md",
        "ledger_md": ROOT / "memories/manager-ledger.md",
        "quota_md": ROOT / "memories/provider-quotas.md",
        "workflows_md": ROOT / "memories/example-workflows.md",
        "patterns_md": ROOT / "memories/example-patterns.md",
    }
    missing = [name for name, path in workspace_files.items() if not path.exists()]
    if missing:
        print(f"SKIP: workspace files not found (integration test requires configured workspace): {', '.join(missing)}")
        catalog_md = None
        archive_catalog_md = None
        ledger_md = None
        quota_md = None
        workflows_md = None
        patterns_md = None
    else:
        catalog_md = read_text(workspace_files["catalog_md"])
        archive_catalog_md = read_text(workspace_files["archive_catalog_md"])
        ledger_md = read_text(workspace_files["ledger_md"])
        quota_md = read_text(workspace_files["quota_md"])
        workflows_md = read_text(workspace_files["workflows_md"])
        patterns_md = read_text(workspace_files["patterns_md"])

    assert_contains(skill_md, "## Deduplication Rules", "deduplication section")
    assert_contains(skill_md, "### Deduplication Algorithm", "catalog-first algorithm section")
    assert_contains(skill_md, "Read `memories/catalog.md` first.", "catalog-first rule")
    assert_contains(skill_md, "Use this exact append template:", "ledger template instruction")
    assert_contains(skill_md, "memories/proposals/UPDATE-[FILENAME]-[DATE].md", "proposal file policy")
    assert_contains(skill_md, "## Catalog Maintenance Rules", "catalog maintenance section")
    assert_contains(skill_md, "never regenerate the full catalog from scratch during a normal ingest run", "append-only catalog rule")
    assert_contains(skill_md, "refresh the matching `memories/catalog.md` entry in the same run", "core file catalog refresh rule")
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
    assert_contains(skill_md, "do not update `memories/catalog.md` yet if the run produced only a proposal", "proposal-only catalog hold rule")

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

    if catalog_md is not None:
        for needle in (
            "memories/AGENTS.md",
            "memories/SOUL.md",
            "memories/IDENTITY.md",
            "memories/USER.md",
        ):
            assert_contains(catalog_md, needle, "searchable catalog entry")

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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"memory-manager test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
