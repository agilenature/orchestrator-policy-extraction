"""Governance protocol integration (Phase 12).

Parses governance Markdown documents (pre-mortem, DECISIONS.md) and
ingests extracted entities into ConstraintStore and WisdomStore.

Exports:
    GovDocParser: Markdown document parser
    GovDocIngestor: Dual-store ingestor
"""
from src.pipeline.governance.parser import GovDocParser
from src.pipeline.governance.ingestor import GovDocIngestor
