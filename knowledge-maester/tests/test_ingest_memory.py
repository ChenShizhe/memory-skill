"""
Unit tests for ingest_memory.py.

Run:
  python3 -m pytest knowledge-maester/tests/test_ingest_memory.py -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import vault_io
from ingest_memory import create_memory_note, update_memory_note


def _make_memory_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "memories"
    (vault / "long-term").mkdir(parents=True)
    (vault / "short-term").mkdir(parents=True)
    return vault


class TestIngestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _make_memory_vault(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_source(self, name: str, content: str) -> Path:
        source = self.tmp_path / name
        source.write_text(content, encoding="utf-8")
        return source

    def test_create_mode_with_all_flags(self):
        source = self._write_source(
            "source-create.md",
            """---
guidance:
  - legacy fallback guidance
---

# Scratch

## Summary

This is the source summary.

## Guidance

- Keep notes atomic
- Link neighbors explicitly

Text with a cross-link to [[graph-maintenance]].
""",
        )

        result = create_memory_note(
            source_path=source,
            title="Atomic Memory Ingestion",
            note_type="workflow",
            layer="long-term",
            topics=["memory-graph", "ingestion"],
            projects=["memories-obsidianization"],
            priority="high",
            vault_path=self.vault,
            related=["hub-ingestion"],
            retrieval_hints="Use when ingesting raw memory updates.",
            token_cost_estimate=42,
        )

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["vault_path"], "long-term/atomic-memory-ingestion.md")

        note_path = self.vault / result["vault_path"]
        self.assertTrue(note_path.exists())
        fm, body = vault_io.parse_frontmatter(note_path.read_text(encoding="utf-8"))

        self.assertEqual(fm["title"], "Atomic Memory Ingestion")
        self.assertEqual(fm["type"], "workflow")
        self.assertEqual(fm["layer"], "long-term")
        self.assertEqual(fm["topics"], ["memory-graph", "ingestion"])
        self.assertEqual(fm["projects"], ["memories-obsidianization"])
        self.assertEqual(fm["source_projects"], ["memories-obsidianization"])
        self.assertEqual(fm["status"], "active")
        self.assertEqual(fm["priority"], "high")
        self.assertEqual(fm["token_cost_estimate"], "42")
        self.assertEqual(fm["retrieval_hints"], "Use when ingesting raw memory updates.")
        self.assertRegex(fm["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(fm["last_updated"], r"^\d{4}-\d{2}-\d{2}$")

        self.assertIn("## Summary", body)
        self.assertIn("This is the source summary.", body)
        self.assertIn("- Keep notes atomic", body)
        self.assertIn("- Link neighbors explicitly", body)
        self.assertIn("- [[hub-ingestion]]", body)
        self.assertIn("- [[graph-maintenance]]", body)

    def test_idempotency_run_twice(self):
        source = self._write_source(
            "source-idempotent.md",
            """# Input

## Summary

No-op on second run.
""",
        )

        result1 = create_memory_note(
            source_path=source,
            title="Idempotent Ingest Test",
            note_type="workflow",
            layer="long-term",
            topics=["idempotency"],
            projects=["memories-obsidianization"],
            priority="medium",
            vault_path=self.vault,
            related=[],
            retrieval_hints="",
            token_cost_estimate=10,
        )
        content_after_first = (self.vault / "long-term" / "idempotent-ingest-test.md").read_text(
            encoding="utf-8"
        )

        result2 = create_memory_note(
            source_path=source,
            title="Idempotent Ingest Test",
            note_type="workflow",
            layer="long-term",
            topics=["idempotency"],
            projects=["memories-obsidianization"],
            priority="medium",
            vault_path=self.vault,
            related=[],
            retrieval_hints="",
            token_cost_estimate=10,
        )
        content_after_second = (self.vault / "long-term" / "idempotent-ingest-test.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(result1["status"], "created")
        self.assertEqual(result2["status"], "skipped")
        self.assertEqual(content_after_first, content_after_second)

    def test_update_mode_merges_summary_guidance_related_and_frontmatter(self):
        existing_fm = {
            "title": "Memory Merge Test",
            "type": "workflow",
            "layer": "long-term",
            "topics": ["memory"],
            "projects": ["alpha"],
            "source_projects": ["alpha"],
            "status": "active",
            "date": "2026-03-10",
            "last_updated": "2026-03-10",
            "priority": "medium",
            "token_cost_estimate": 20,
            "retrieval_hints": "old hint",
        }
        existing_body = """# Memory Merge Test

## Summary

Old summary.

## Guidance

- Keep old guidance

## Related

- [[existing-link]]
"""
        vault_io.write_note(self.vault, "long-term/memory-merge-test.md", existing_fm, existing_body)

        update_source = self._write_source(
            "source-update.md",
            """---
topics: [memory, graph]
projects: [alpha, beta]
priority: high
---

## Summary

New replacement summary.

## Guidance

- Keep old guidance
- Add fresh guidance

## Related

- [[existing-link]]
- [[new-link]]
""",
        )

        result = update_memory_note(
            note_path="long-term/memory-merge-test.md",
            source_path=update_source,
            vault_path=self.vault,
        )

        self.assertEqual(result["status"], "updated")
        fm, body = vault_io.read_note(self.vault, "long-term/memory-merge-test.md")

        self.assertEqual(fm["priority"], "high")
        self.assertEqual(fm["topics"], ["memory", "graph"])
        self.assertEqual(fm["projects"], ["alpha", "beta"])
        self.assertRegex(fm["last_updated"], r"^\d{4}-\d{2}-\d{2}$")

        self.assertIn("New replacement summary.", body)
        self.assertNotIn("Old summary.", body)
        self.assertEqual(body.count("Keep old guidance"), 1)
        self.assertIn("Add fresh guidance", body)
        self.assertIn("[[existing-link]]", body)
        self.assertIn("[[new-link]]", body)

    def test_update_mode_preserves_hub_links_without_creating_hub_stub(self):
        existing_fm = {
            "title": "Planning Pattern",
            "type": "workflow",
            "layer": "long-term",
            "topics": ["planning", "workflow-governance"],
            "projects": ["coordination"],
            "source_projects": ["coordination"],
            "status": "active",
            "date": "2026-03-10",
            "last_updated": "2026-03-10",
            "priority": "medium",
            "token_cost_estimate": 20,
            "retrieval_hints": "old hint",
        }
        existing_body = """# Planning Pattern

## Summary

Old summary.

## Guidance

- Keep old guidance

## Related

- [[_hub-coordination-patterns]]
- [[existing-link]]
"""
        vault_io.write_note(self.vault, "long-term/planning-pattern.md", existing_fm, existing_body)
        hub_fm = {
            "title": "Topic Hub: Coordination Patterns",
            "type": "hub",
            "layer": "long-term",
            "topics": ["planning", "workflow-governance"],
            "projects": [],
            "status": "active",
            "date": "2026-03-10",
            "last_updated": "2026-03-10",
            "priority": "medium",
            "token_cost_estimate": 10,
            "retrieval_hints": "Use for planning hubs.",
        }
        existing_link_fm = {
            "title": "Existing Link",
            "type": "reference",
            "layer": "long-term",
            "topics": ["planning"],
            "projects": ["coordination"],
            "source_projects": ["coordination"],
            "status": "active",
            "date": "2026-03-10",
            "last_updated": "2026-03-10",
            "priority": "low",
            "token_cost_estimate": 5,
            "retrieval_hints": "Use for existing-link test coverage.",
        }
        vault_io.write_note(
            self.vault,
            "long-term/_hub-coordination-patterns.md",
            hub_fm,
            "# Topic Hub: Coordination Patterns\n\n## Summary\nHub summary.\n",
        )
        vault_io.write_note(
            self.vault,
            "long-term/existing-link.md",
            existing_link_fm,
            "# Existing Link\n\n## Summary\nExisting note.\n",
        )

        update_source = self._write_source(
            "source-update-hub.md",
            """## Guidance

- Add fresh guidance

## Related

- [[contract-first-task-execution]]
""",
        )

        result = update_memory_note(
            note_path="long-term/planning-pattern.md",
            source_path=update_source,
            vault_path=self.vault,
        )

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["stubs_created"], ["long-term/contract-first-task-execution.md"])
        _, body = vault_io.read_note(self.vault, "long-term/planning-pattern.md")

        self.assertIn("[[_hub-coordination-patterns]]", body)
        self.assertNotIn("[[hub-coordination-patterns]]", body)
        self.assertFalse((self.vault / "long-term" / "hub-coordination-patterns.md").exists())

    def test_stub_creation_for_missing_wikilinks(self):
        source = self._write_source(
            "source-stubs.md",
            """# Source

## Summary

Testing stub creation.

Body includes [[source-neighbor]].
""",
        )

        result = create_memory_note(
            source_path=source,
            title="Stub Creation Task",
            note_type="decision",
            layer="long-term",
            topics=["stubs"],
            projects=["memories-obsidianization"],
            priority="low",
            vault_path=self.vault,
            related=["explicit-neighbor"],
            retrieval_hints="",
            token_cost_estimate=5,
        )

        self.assertEqual(result["status"], "created")
        self.assertIn("long-term/source-neighbor.md", result["stubs_created"])
        self.assertIn("long-term/explicit-neighbor.md", result["stubs_created"])

        for rel in result["stubs_created"]:
            self.assertTrue((self.vault / rel).exists())
            stub_fm, _ = vault_io.read_note(self.vault, rel)
            self.assertEqual(stub_fm["type"], "reference")


if __name__ == "__main__":
    unittest.main(verbosity=2)
