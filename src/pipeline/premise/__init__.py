"""Premise Registry module for Phase 14.1 Premise-Assertion Gate.

Provides the data layer for tracking AI premise declarations: DuckDB schema,
Pydantic models, PREMISE block parser, registry CRUD operations, foil
instantiation, staining pipeline, and staging ingestion.

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
    FoilInstantiator: Three-tier foil matching + divergence detection
    FoilMatch: A matched historical premise with match metadata
    DivergenceNode: First point of tool call divergence
    StainingPipeline: Staining from amnesia + derivation propagation
    ingest_staging: JSONL staging to DuckDB ingestion
    run_staining: Execute staining pipeline from amnesia events
"""

from src.pipeline.premise.foil import DivergenceNode, FoilInstantiator, FoilMatch
from src.pipeline.premise.ingestion import ingest_staging, run_staining
from src.pipeline.premise.models import ParsedPremise, PremiseRecord
from src.pipeline.premise.parser import parse_foil_verified_blocks, parse_premise_blocks
from src.pipeline.premise.registry import PremiseRegistry
from src.pipeline.premise.schema import create_premise_schema
from src.pipeline.premise.staining import StainingPipeline

__all__ = [
    "PremiseRecord",
    "ParsedPremise",
    "PremiseRegistry",
    "parse_premise_blocks",
    "parse_foil_verified_blocks",
    "create_premise_schema",
    "FoilInstantiator",
    "FoilMatch",
    "DivergenceNode",
    "StainingPipeline",
    "ingest_staging",
    "run_staining",
]
