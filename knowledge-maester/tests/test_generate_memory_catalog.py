"""
Unit tests for generate_memory_catalog.py (sharded layout).

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


_SLUG_HEADING_RE = re.compile(r"^## ([^\n]+)$", re.MULTILINE)


def _collect_slugs(shards_dir: Path) -> list[str]:
    slugs = []
    for shard_file in sorted(shards_dir.glob("*.md")):
        text = shard_file.read_text(encoding="utf-8")
        for m in _SLUG_HEADING_RE.finditer(text):
            s = m.group(1).strip()
            if s in ("Generated Entries", "Manual Entries"):
                continue
            slugs.append(s)
    return slugs


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

    def _read_index(self) -> str:
        return (self.vault / "catalog-index.md").read_text(encoding="utf-8")

    def _read_shard(self, shard_filename: str) -> str:
        return (self.vault / "catalog-shards" / shard_filename).read_text(encoding="utf-8")

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
        # 4 core + alpha + beta + hub + manager-ledger
        self.assertEqual(count, 8)

        # All slugs should be present across shards.
        slugs = _collect_slugs(self.vault / "catalog-shards")
        self.assertIn("alpha-note", slugs)
        self.assertIn("beta-note", slugs)
        self.assertIn("_hub-memory", slugs)
        self.assertIn("manager-ledger", slugs)
        self.assertIn("agents-core-protocol", slugs)

        # Hub routed to hubs shard.
        self.assertIn("## _hub-memory", self._read_shard("hubs.md"))

        # Core identity entries routed to core-identity.
        core = self._read_shard("core-identity.md")
        self.assertIn("## agents-core-protocol", core)
        self.assertIn("## user-core-profile", core)

    def test_manual_entries_section_preserved_verbatim(self):
        # Seed two shards with hand-edited Manual content.
        shards = self.vault / "catalog-shards"
        shards.mkdir(parents=True)
        (shards / "misc.md").write_text(
            """# Catalog Shard — misc

(intro)

## Generated Entries

## old-generated-entry

- path: memories/long-term/old-generated-entry.md

## Manual Entries

Manual line 1.
- keep this bullet

## custom-manual-entry

- path: memories/custom.md
- note: keep spacing exactly
""",
            encoding="utf-8",
        )

        self._write_note(
            "long-term/some-note.md",
            {
                "title": "Some Note",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["unrelated"],
                "projects": [],
                "last_updated": "2026-03-16",
                "priority": "high",
            },
            """# Some Note

## Summary

Some summary.
""",
        )

        generate_catalog(self.vault)
        misc = self._read_shard("misc.md")
        self.assertIn("Manual line 1.", misc)
        self.assertIn("- keep this bullet", misc)
        self.assertIn("## custom-manual-entry", misc)
        self.assertIn("- note: keep spacing exactly", misc)
        # The old Generated entry should no longer be present (Generated is rewritten).
        self.assertNotIn("## old-generated-entry", misc)

    def test_core_identity_entries_appear_in_core_identity_shard(self):
        self._write_note(
            "long-term/zeta-note.md",
            {
                "title": "Zeta",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["zeta"],
                "projects": [],
                "last_updated": "2026-03-16",
                "priority": "high",
            },
            """# Zeta

## Summary

Zeta summary.
""",
        )

        generate_catalog(self.vault)
        core = self._read_shard("core-identity.md")
        # All four core identity slugs present in this shard.
        for slug in (
            "## agents-core-protocol",
            "## soul-core-principles",
            "## identity-core-boundaries",
            "## user-core-profile",
        ):
            self.assertIn(slug, core)
        # Zeta goes to misc (no project, no matching topic).
        misc = self._read_shard("misc.md")
        self.assertIn("## zeta-note", misc)

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
        slugs = _collect_slugs(self.vault / "catalog-shards")
        self.assertIn("real-note", slugs)
        self.assertNotIn("_template", slugs)
        self.assertNotIn("_hub-template", slugs)

    def test_routing_determinism_for_paper_reading_topics(self):
        self._write_note(
            "long-term/deterministic-paper-note.md",
            {
                "title": "Paper Pipeline Note",
                "type": "workflow",
                "layer": "long-term",
                "topics": ["paper-reading", "paper-discovery"],
                "projects": [],
                "last_updated": "2026-04-23",
                "priority": "high",
            },
            """# Paper Pipeline Note

## Summary

Paper summary.
""",
        )
        generate_catalog(self.vault)
        paper_shard = self._read_shard("paper-reading.md")
        self.assertIn("## deterministic-paper-note", paper_shard)

    def test_dedup_manual_wins_on_regeneration(self):
        # Seed a shard whose Manual already has a slug; generator writes an
        # entry with the same slug to Generated. We verify both coexist in the
        # shard (per D1, dedup happened during the migration; at regeneration
        # time we keep Manual verbatim and rewrite Generated). This exercises
        # the preservation contract, not the migration-time dedup.
        shards = self.vault / "catalog-shards"
        shards.mkdir(parents=True)
        (shards / "core-identity.md").write_text(
            """# Catalog Shard — core-identity

(intro)

## Generated Entries

## Manual Entries

## agents-core-protocol

- path: memories/AGENTS.md
- note: Manual wins
""",
            encoding="utf-8",
        )
        generate_catalog(self.vault)
        core = self._read_shard("core-identity.md")
        # Manual entry preserved verbatim.
        self.assertIn("- note: Manual wins", core)
        # Generated copy also present (the generator always writes core entries).
        # The slug appears twice (once in Generated, once in Manual) in this file.
        matches = re.findall(r"^## agents-core-protocol\s*$", core, re.MULTILINE)
        self.assertEqual(len(matches), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
