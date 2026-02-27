"""DuckDB schema for the doc_index table (Phase 21).

The doc_index table stores (doc_path, ccd_axis) associations -- the mapping
from documentation files to the CCD axes they are relevant to.  Each row
represents one doc-axis pair, enabling multi-axis documents (one row per axis).

Association types capture how the link was discovered:
  frontmatter  -- extracted from the document's YAML frontmatter
  regex        -- matched by a CCD-axis regex pattern in the body
  keyword      -- matched by a keyword heuristic
  manual       -- explicitly tagged by a human
  unclassified -- source unknown or pending classification
"""

from __future__ import annotations

import duckdb

DOC_INDEX_DDL = """
CREATE TABLE IF NOT EXISTS doc_index (
    doc_path             VARCHAR NOT NULL,
    ccd_axis             VARCHAR NOT NULL,
    association_type     VARCHAR NOT NULL DEFAULT 'frontmatter'
        CHECK (association_type IN (
            'frontmatter', 'regex', 'keyword', 'manual', 'unclassified'
        )),
    extracted_confidence FLOAT NOT NULL DEFAULT 1.0,
    description_cache    VARCHAR,
    section_anchor       VARCHAR,
    content_hash         VARCHAR NOT NULL,
    indexed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (doc_path, ccd_axis)
)
"""


def create_doc_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the doc_index table idempotently."""
    conn.execute(DOC_INDEX_DDL)
