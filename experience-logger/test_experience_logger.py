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
    skill_md = read_text(ROOT / "experience-logger/SKILL.md")

    assert_contains(skill_md, "Only put machine-parseable provider quota lines", "machine-parseable quota rule")
    assert_contains(skill_md, "Used in run: <integer>", "delta quota template")
    assert_contains(skill_md, "Prefer delta-style quota logging with `Used in run`.", "delta quota preference")
    assert_contains(skill_md, "Used before run: <integer> | Used in run: <integer> | Used after run: <integer>", "snapshot quota template")
    assert_contains(skill_md, "write `- none` in `## Used Quota`", "non-ledgered quota fallback")
    assert_contains(skill_md, "Keep provider names stable and simple", "provider-name stability rule")

    # Workflow reflection assertions
    assert_contains(skill_md, "## Workflow Reflection Rules", "workflow reflection rules section")
    assert_contains(skill_md, "workflow_type:", "workflow type field in template")
    assert_contains(skill_md, "workflow_type_confidence: confirmed | proposed | guessed", "workflow type confidence field")
    assert_contains(skill_md, "project_outcome: success | failure | partial | ongoing", "project outcome field")
    assert_contains(skill_md, "outcome_reasons:", "outcome reasons field")
    assert_contains(skill_md, "mistakes_and_corrections:", "mistakes and corrections field")
    assert_contains(skill_md, "root_cause:", "root cause field in mistakes template")
    assert_contains(skill_md, "suggested_template_update:", "suggested template update field")
    assert_contains(skill_md, "meaningful phase", "step granularity guidance")

    print("experience-logger test passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"experience-logger test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
