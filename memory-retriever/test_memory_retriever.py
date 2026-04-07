#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "memory-retriever" / "fixtures" / "sample-project"
CORE_FILES = ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md")


def read_text(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def assert_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"Missing {label}: {needle}")


def assert_not_contains(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"Unexpected {label}: {needle}")


def assert_in_order(text: str, needles: tuple[str, ...], label: str) -> None:
    last_index = -1
    for needle in needles:
        index = text.find(needle)
        if index == -1:
            raise AssertionError(f"Missing {label}: {needle}")
        if index <= last_index:
            raise AssertionError(f"Out-of-order {label}: {needle}")
        last_index = index


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def assert_full_core_injection(document: str, core_file: str, label: str) -> None:
    header = f"### Core Memory File: {core_file}"
    source = f"- source: memories/{core_file}"
    pattern = (
        rf"{re.escape(header)}\n\n"
        rf"{re.escape(source)}\n"
        r"- injection_mode: full_file_verbatim\n\n"
        r"```md\n"
        r"(.*?)\n?"
        r"```"
    )
    match = re.search(pattern, document, flags=re.DOTALL)
    if not match:
        raise AssertionError(f"Missing {label} core injection block for {core_file}")

    # Integration test: compare against live workspace core files if available
    core_path = ROOT / "memories" / core_file
    if not core_path.exists():
        return  # Skip content comparison when workspace core files are not configured
    expected = normalize_newlines(read_text(core_path))
    actual = normalize_newlines(match.group(1))
    if actual != expected:
        raise AssertionError(f"{label} core injection content mismatch for {core_file}")


def main() -> int:
    skill_md = read_text(ROOT / "memory-retriever/SKILL.md")

    # Integration tests: these require a configured workspace with live memory files.
    catalog_path = ROOT / "memories/catalog.md"
    if not catalog_path.exists():
        print("SKIP: memories/catalog.md not found (integration test requires configured workspace)")
        catalog_md = None
    else:
        catalog_md = read_text(catalog_path)
    round_files = sorted((FIXTURE_ROOT / "memory/retrieval-rounds").glob("*.md"))
    if not round_files:
        raise AssertionError("Missing retrieval round fixture")
    round_md = read_text(round_files[-1])
    latest_md = read_text(FIXTURE_ROOT / "memory/latest-expanded-instruction.md")

    assert_contains(skill_md, "current instruction outranks all retrieved memory", "priority rule")
    assert_contains(skill_md, "Never read raw files from `experiences/`.", "experience exclusion rule")
    assert_contains(skill_md, "Current instruction outranks all quota guidance as well.", "quota priority rule")
    assert_contains(skill_md, "## Retrieval Tiers", "retrieval tiers section")
    assert_contains(skill_md, "### Core File Pre-Pass", "core pre-pass section")
    assert_contains(skill_md, "### Pass 1: Cheap Shortlist", "pass 1 section")
    assert_contains(skill_md, "### Pass 2: Focused Read", "pass 2 section")
    assert_contains(skill_md, "The retriever may also read `memories/provider-quotas.md` as a special operational source", "quota read exception")
    assert_contains(skill_md, "Quota guidance is an operational add-on to the handoff, not part of retrieved memory.", "quota guidance section")
    assert_contains(skill_md, "- `quota_allocation_mode`", "quota input")
    assert_contains(skill_md, "if the current instruction invokes `market-watcher`, auto-request `Tavily` and `Brave`", "auto quota rule")
    assert_contains(skill_md, "emit quota state as `### Memory Card: ...`", "quota memory-card ban")
    assert_contains(skill_md, "YYYY-MM-DDTHH-MM-round-001.md", "timestamped round output rule")
    assert_contains(skill_md, "list at most `5` omitted candidates", "omitted candidate cap")
    assert_contains(skill_md, "...and X others", "omitted candidate overflow rule")
    assert_contains(skill_md, "both its `source` path and its card title do not already appear in `latest-expanded-instruction.md`", "follow-up dedupe rule")
    assert_contains(skill_md, "Core-file injections are additive baseline context and do not count against Tier 1 or Tier 2 catalog-card budgets.", "additive baseline rule")
    assert_contains(skill_md, "Every retrieval run must inject the entirety of each core file in this exact order:", "core full injection rule")
    assert_contains(skill_md, "- injection_mode: full_file_verbatim", "core injection mode")
    assert_contains(skill_md, "Do not summarize or paraphrase the mandatory core files.", "no core compression rule")
    assert_contains(skill_md, "Use `memories/catalog.md` as the first shortlist source for non-core searchable memory.", "catalog-after-core rule")
    assert_contains(skill_md, "Missing or unreadable `memories/AGENTS.md`:", "agents hard fail rule")
    assert_contains(skill_md, "Empty `memories/catalog.md`:", "empty catalog fallback")
    assert_contains(skill_md, "continue with core baseline only", "core-only fallback")
    assert_contains(skill_md, "do not scan the `memories/` folder directly for non-core memory", "no full-folder fallback")
    assert_contains(skill_md, "if you are already extracting `2+` catalog-derived memory cards, drop any candidate whose `token_cost_estimate` is over `500`", "categorical token guard")
    assert_in_order(
        skill_md,
        (
            "memories/AGENTS.md",
            "memories/SOUL.md",
            "memories/IDENTITY.md",
            "memories/USER.md",
        ),
        "core file order",
    )

    # Workflow template injection assertions
    assert_contains(skill_md, "## Workflow Template Injection", "workflow template injection section")
    assert_contains(skill_md, "### Version Selection", "version selection subsection")
    assert_contains(skill_md, "### Review Notification", "review notification subsection")
    assert_contains(skill_md, "### Unrecognized Workflow", "unrecognized workflow subsection")
    assert_contains(skill_md, "primary_playbook", "stable injection mode")
    assert_contains(skill_md, "maturing_guide", "beta injection mode")
    assert_contains(skill_md, "loose_guide", "draft injection mode")
    assert_contains(skill_md, "### Workflow Playbook", "workflow playbook section in expanded instruction")
    assert_contains(skill_md, "## Workflow Template Match", "workflow template match in round file")
    assert_contains(skill_md, "ready_for_review: true", "review flag check")
    assert_contains(skill_md, "type: workflow_template", "catalog type matching")
    assert_contains(skill_md, "→ [shared:", "shared fragment resolution reference")

    if catalog_md is not None:
        assert_contains(catalog_md, "## example-memory-note", "catalog entry")
        assert_contains(catalog_md, "## example-follow-up", "short-term catalog entry")

    assert_contains(
        round_md,
        "instruction_path: memory-retriever/fixtures/sample-project/user-instruction.md",
        "instruction path",
    )
    assert_contains(round_md, "task_complexity: standard", "task complexity")
    assert_contains(round_md, "- core_files_read:", "core files read section")
    assert_contains(round_md, "- catalog_considered:", "catalog considered section")
    assert_contains(round_md, "## Selected Retrieved Memory", "selected retrieved memory section")
    assert_contains(round_md, "## Quota Snapshot", "quota snapshot section")
    assert_contains(round_md, "### Memory Card: Concise Output Style", "user preference memory card")
    assert_contains(round_md, "### Memory Card: Paper-Trail-First Execution", "workflow memory card")
    assert_contains(round_md, "### Memory Card: Skill-Onboarding Pattern", "project pattern memory card")
    assert_contains(round_md, "memories/legacy-memories.md", "legacy source path")
    assert_contains(round_md, "memories/research-workflows.md", "workflow source path")
    assert_contains(round_md, "memories/project-patterns.md", "project pattern source path")
    assert_contains(round_md, "- provider: Tavily", "tavily quota record")
    assert_contains(round_md, "- provider: Brave", "brave quota record")
    assert_contains(round_md, "- allocation_status: allocated", "allocated quota status")
    assert_contains(round_md, "Current instruction outranks all retrieved memory.", "round priority rule")
    assert_in_order(
        round_md,
        (
            "### Core Memory File: AGENTS.md",
            "### Core Memory File: SOUL.md",
            "### Core Memory File: IDENTITY.md",
            "### Core Memory File: USER.md",
            "### Memory Card: Concise Output Style",
            "### Memory Card: Paper-Trail-First Execution",
            "### Memory Card: Skill-Onboarding Pattern",
        ),
        "round retrieved memory order",
    )

    assert_in_order(
        latest_md,
        (
            "## Current Instruction",
            "## Priority Rule",
            "## Project Context",
            "## Retrieved Memory",
            "## Execution Note",
        ),
        "handoff sections",
    )
    assert_contains(latest_md, "Analyze code quality metrics", "current instruction content")
    assert_contains(latest_md, "Current instruction outranks all retrieved memory.", "handoff priority rule")
    assert_contains(latest_md, "full core session files from AGENTS, SOUL, IDENTITY, and USER", "core baseline note")
    assert_contains(latest_md, "- Quota guidance:", "quota guidance heading")
    assert_contains(latest_md, "Tavily: used 0 requests in 2026-03; task allowance 200 requests.", "tavily execution note")
    assert_contains(latest_md, "Brave: used 0 requests in 2026-03; task allowance 200 requests.", "brave execution note")
    assert_not_contains(latest_md, "### Memory Card: Tavily", "quota memory card")
    assert_in_order(
        latest_md,
        (
            "### Core Memory File: AGENTS.md",
            "### Core Memory File: SOUL.md",
            "### Core Memory File: IDENTITY.md",
            "### Core Memory File: USER.md",
            "### Memory Card: Concise Output Style",
            "### Memory Card: Paper-Trail-First Execution",
            "### Memory Card: Skill-Onboarding Pattern",
        ),
        "latest retrieved memory order",
    )

    for text in (round_md, latest_md):
        assert_not_contains(text, "- source: experiences/", "retrieval source")
        assert_not_contains(text, "- source: memories/archive/", "archive source")
        assert_not_contains(text, "- source: memories/archive-catalog.md", "archive catalog source")

    for core_file in CORE_FILES:
        assert_full_core_injection(round_md, core_file, "round output")
        assert_full_core_injection(latest_md, core_file, "latest output")

    print("memory-retriever test passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"memory-retriever test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
