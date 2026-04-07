#!/usr/bin/env python3
"""
ingest_paper.py — Entry-point shim for the knowledge-maester skill root.

The canonical implementation lives at scripts/ingest_paper.py.
This shim allows invocation from the skill root directory and re-exports
all public symbols, including the schema v2 frontmatter emitter which
writes schema_version, validation_status, extraction_confidence, source_type,
source_path, source_parse_status, bibliography_status, and auto_block_hash.

Schema v2 required frontmatter fields (emitted by ingest_paper in scripts/):
  schema_version: "2"
  extraction_confidence: 0.9
  validation_status: "pending"
  source_type: <from source_format or pipeline args>
  source_path: <from pipeline args>
  source_parse_status: "complete"
  bibliography_status: "pending"
  auto_block_hash: ""
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from ingest_paper import (  # noqa: F401, E402
    ingest_paper,
    ingest_note_type,
    ingest_digest,
    ingest_field,
    main,
    TYPE_TO_DIRECTORY,
    NON_PAPER_IDENTITY_FIELDS,
)

if __name__ == "__main__":
    main()
