"""
Unit tests for generate_memory_catalog.py.

Run:
  python3 -m pytest knowledge-maester/tests/test_generate_memory_catalog.py -v
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import vault_io
from generate_memory_catalog import generate_catalog


class TestGenerateMemoryCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = self.tmp_path / "memories"
        (self.vault / "long-term").mkdir(parents=True)
        (self.vault / "short-term").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_note(self, rel_path: str, fm: dict, body: str) -> None:
        vault_io.write_note(self.vault, rel_path, fm, body)

    def _read_catalog(self) -> str:
        return (self.vault / "catalog.md").read_text(encoding="utf-8")

    @staticmethod
    def _generated_slugs(catalog: str) -> list[str]:
        marker = "## Generated Entries"
        if marker not in catalog:
            return []
        generated_text = catalog.split(marker, 1)[1]
        generated_text = generated_text.split("## Manual Entries", 1)[0]
        return re.findall(r"^##\s+([^\n]+)$", generated_text, flags=re.MULTILINE)

    def test_generate_catalog_with_temp_vault_notes(self):
        self._write_note(
            "long-term/alpha-note.md",
            {
                "title": "Alpha Note",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["alpha", "memory"],
                "projects": ["proj-a"],
                "last_updated": "2026-03-16",
                "priority": "high",
                "retrieval_hints": "Use for alpha",
                "token_cost_estimate": 21,
            },
            """# Alpha Note

## Summary

First line of summary.

Second paragraph should not be used.

## Guidance

- Keep this stable
""",
        )

        self._write_note(
            "short-term/beta-note.md",
            {
                "title": "Beta Note",
                "type": "continuity",
                "layer": "short-term",
                "topics": ["beta"],
                "projects": ["proj-b"],
                "last_updated": "2026-03-15",
                "priority": "medium",
                "retrieval_hints": "Use for beta",
                "token_cost_estimate": 9,
            },
            """# Beta Note

## Summary

Beta summary paragraph.
""",
        )

        self._write_note(
            "long-term/_hub-memory.md",
            {
                "title": "Topic Hub: Memory",
                "type": "hub",
                "layer": "long-term",
                "topics": ["memory"],
                "projects": [],
                "last_updated": "2026-03-16",
                "priority": "medium",
            },
            """# Topic Hub: Memory

## Summary

Hub summary.
""",
        )

        self._write_note(
            "manager-ledger.md",
            {
                "title": "Manager Ledger",
                "type": "operational",
                "layer": "long-term",
                "topics": ["ops"],
                "projects": ["memories-obsidianization"],
                "last_updated": "2026-03-16",
                "priority": "low",
            },
            """# Manager Ledger

## Summary

Operational summary.
""",
        )

        count = generate_catalog(self.vault)
        self.assertEqual(count, 8)  # 4 core + alpha + beta + hub + manager-ledger

        catalog = self._read_catalog()
        self.assertIn("## alpha-note", catalog)
        self.assertIn("- path: memories/long-term/alpha-note.md", catalog)
        self.assertIn("- summary: First line of summary.", catalog)
        self.assertIn("- topics: [alpha, memory]", catalog)
        self.assertIn("## _hub-memory", catalog)
        self.assertIn("## manager-ledger", catalog)

    def test_manual_entries_section_preserved_verbatim(self):
        initial_catalog = """# Searchable Memory Catalog

This catalog tracks all searchable central memory that `memory-retriever` may use.

## Generated Entries

## alpha-old

- path: memories/long-term/alpha-old.md

## Manual Entries

Manual line 1.
- keep this bullet

## custom-manual-entry

- path: memories/custom.md
- note: keep spacing exactly
"""
        (self.vault / "catalog.md").write_text(initial_catalog, encoding="utf-8")

        self._write_note(
            "long-term/alpha-note.md",
            {
                "title": "Alpha Note",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["alpha"],
                "projects": ["proj-a"],
                "last_updated": "2026-03-16",
                "priority": "high",
            },
            """# Alpha

## Summary

Alpha summary.
""",
        )

        generate_catalog(self.vault)
        catalog = self._read_catalog()
        self.assertIn("\n\nManual line 1.\n- keep this bullet\n\n## custom-manual-entry\n", catalog)
        self.assertIn("- note: keep spacing exactly", catalog)

    def test_core_identity_entries_appear_first(self):
        self._write_note(
            "long-term/zeta-note.md",
            {
                "title": "Zeta",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["zeta"],
                "projects": ["proj-z"],
                "last_updated": "2026-03-16",
                "priority": "high",
            },
            """# Zeta

## Summary

Zeta summary.
""",
        )

        generate_catalog(self.vault)
        catalog = self._read_catalog()
        slugs = self._generated_slugs(catalog)
        self.assertGreaterEqual(len(slugs), 4)
        self.assertEqual(
            slugs[:4],
            [
                "agents-core-protocol",
                "soul-core-principles",
                "identity-core-boundaries",
                "user-core-profile",
            ],
        )

    def test_template_files_are_skipped(self):
        self._write_note(
            "long-term/_template.md",
            {
                "title": "Template",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["template"],
                "projects": [],
                "last_updated": "2026-03-16",
                "priority": "low",
            },
            """# Template

## Summary

Should be skipped.
""",
        )

        self._write_note(
            "long-term/_hub-template.md",
            {
                "title": "Hub Template",
                "type": "hub",
                "layer": "long-term",
                "topics": ["template"],
                "projects": [],
                "last_updated": "2026-03-16",
                "priority": "low",
            },
            """# Hub Template

## Summary

Should be skipped.
""",
        )

        self._write_note(
            "long-term/real-note.md",
            {
                "title": "Real Note",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["real"],
                "projects": ["proj"],
                "last_updated": "2026-03-16",
                "priority": "medium",
            },
            """# Real

## Summary

Real summary.
""",
        )

        generate_catalog(self.vault)
        catalog = self._read_catalog()
        self.assertIn("## real-note", catalog)
        self.assertNotIn("## _template", catalog)
        self.assertNotIn("## _hub-template", catalog)


if __name__ == "__main__":
    unittest.main(verbosity=2)
