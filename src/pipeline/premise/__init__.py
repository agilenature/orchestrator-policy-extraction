"""Premise Registry module for Phase 14.1 Premise-Assertion Gate.

Provides the data layer for tracking AI premise declarations: DuckDB schema,
Pydantic models, PREMISE block parser, and registry CRUD operations.

The Premise Registry stores every PREMISE declaration seen across sessions,
with validation state, foil outcomes, staining records, and derivation chain
metadata. The PREMISE block parser extracts structured premises from AI text
output using regex-based parsing.

Exports:
    PremiseRecord: Pydantic model for premise registry rows (20 columns)
    ParsedPremise: Pydantic model for parsed PREMISE block fields
    PremiseRegistry: DuckDB CRUD for premise_registry table
    parse_premise_blocks: Extract PREMISE blocks from AI text
    parse_foil_verified_blocks: Extract FOIL_VERIFIED blocks from AI text
    create_premise_schema: Create premise_registry table + indexes in DuckDB
"""

from src.pipeline.premise.models import ParsedPremise, PremiseRecord
from src.pipeline.premise.parser import parse_foil_verified_blocks, parse_premise_blocks
from src.pipeline.premise.registry import PremiseRegistry
from src.pipeline.premise.schema import create_premise_schema

__all__ = [
    "PremiseRecord",
    "ParsedPremise",
    "PremiseRegistry",
    "parse_premise_blocks",
    "parse_foil_verified_blocks",
    "create_premise_schema",
]
