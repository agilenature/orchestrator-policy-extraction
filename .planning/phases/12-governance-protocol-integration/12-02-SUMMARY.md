---
phase: 12-governance-protocol-integration
plan: 02
subsystem: governance
tags: [markdown-parser, regex, constraint-store, wisdom-store, duckdb, pydantic]

requires:
  - phase: 12-01
    provides: "GovernanceConfig, StabilityCheckDef, WisdomEntity.metadata, stability_outcomes table"
provides:
  - "GovDocParser: Markdown parser extracting typed entities from H2/H3 sections"
  - "GovDocIngestor: Dual-store writer (constraints to JSON, wisdom to DuckDB)"
  - "GovIngestResult: Pydantic model for ingestion outcome tracking"
  - "data/objectivism_premortem.md: Canonical fixture with 11 stories + 15 assumptions"
affects: [12-03-governance-pipeline-integration, 12-04-governance-stability-checks]

tech-stack:
  added: []
  patterns:
    - "Header-hierarchy keyword classification for Markdown parsing"
    - "Sequential dual-store write pattern: constraints first, wisdom second"
    - "Co-occurrence heuristic linking all constraints to all wisdom from same document"
    - "Forbidden-language regex for severity upgrade"

key-files:
  created:
    - src/pipeline/governance/__init__.py
    - src/pipeline/governance/parser.py
    - src/pipeline/governance/ingestor.py
    - data/objectivism_premortem.md
    - tests/test_governance_parser.py
    - tests/test_governance_ingestor.py
  modified: []

key-decisions:
  - "SECTION_KEYWORDS uses substring matching -- bare 'Decisions' does NOT match, only 'Scope Decisions' or 'Method Decisions'"
  - "List item extraction uses line-by-line state machine for multi-line continuation support"
  - "Co-occurrence linkage: ALL constraint IDs from same document linked to ALL wisdom entities (full cross-product)"
  - "DECISIONS.md sections (scope_decision, method_decision) produce only wisdom, never constraints"
  - "Severity heuristic: word-boundary regex for prohibition language (must not, never, forbidden, do not, shall not)"

patterns-established:
  - "GovDocParser.parse_document() as the canonical entry point for governance Markdown extraction"
  - "GovDocIngestor.ingest_file() with dry_run and source_id parameters for controlled ingestion"
  - "ParsedEntity dataclass as the interchange format between parser and ingestor"

duration: 7min
completed: 2026-02-20
---

# Phase 12 Plan 02: Governance Parser/Ingestor Summary

**Header-hierarchy Markdown parser with dual-store ingestor writing assumptions as constraints and failure stories as wisdom, plus 26-entity pre-mortem fixture**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-20T16:54:26Z
- **Completed:** 2026-02-20T17:01:04Z
- **Tasks:** 2
- **Files created:** 6

## Accomplishments

- GovDocParser extracts entities from H2/H3 Markdown sections via keyword classification (failure_story, assumption, scope_decision, method_decision)
- GovDocIngestor writes constraints to ConstraintStore (JSON) then wisdom to WisdomStore (DuckDB) with sequential persistence
- Forbidden severity heuristic upgrades constraints matching prohibition language ("must not", "never", etc.)
- Co-occurrence linkage populates related_constraint_ids in wisdom metadata for document-level cross-referencing
- data/objectivism_premortem.md fixture with 11 failure stories and 15 assumptions synthesized from project analysis documents
- 45 new tests (27 parser + 18 ingestor), 778 total passing, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Markdown parser + governance ingestor** - `ff7f811` (feat)
2. **Task 2: Objectivism pre-mortem fixture** - `9e57ff2` (feat)

## Files Created/Modified

- `src/pipeline/governance/__init__.py` - Package init exporting GovDocParser and GovDocIngestor
- `src/pipeline/governance/parser.py` - Header-hierarchy Markdown parser with keyword classification
- `src/pipeline/governance/ingestor.py` - Dual-store ingestor with severity heuristic and co-occurrence linkage
- `data/objectivism_premortem.md` - Canonical pre-mortem fixture (11 failure stories, 15 assumptions)
- `tests/test_governance_parser.py` - 27 tests for parser classification, extraction, and edge cases
- `tests/test_governance_ingestor.py` - 18 tests for ingestion, severity, linkage, idempotency, and error handling

## Decisions Made

- SECTION_KEYWORDS uses case-insensitive substring matching: bare "Decisions" does NOT match to avoid ambiguity
- List item extraction handles multi-line continuation via line-by-line state machine
- Co-occurrence heuristic links ALL constraint IDs from a document to ALL wisdom entities from the same document
- DECISIONS.md sections (scope_decision, method_decision) produce only wisdom entities, never constraints
- Severity heuristic uses word-boundary regex for prohibition language detection
- Pre-mortem fixture synthesized from three source analysis documents (REUSABLE_KNOWLEDGE_GUIDE, DECISION_AMNESIA_REPORT, VALIDATION_GATE_AUDIT)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Parser and ingestor ready for pipeline integration (Plan 12-03)
- Pre-mortem fixture ready for integration testing
- GovDocIngestor.ingest_file() provides the dry_run parameter for safe testing in pipeline context

## Self-Check: PASSED

- All 6 created files verified present on disk
- Commit ff7f811 (Task 1) verified in git log
- Commit 9e57ff2 (Task 2) verified in git log
- Parser extracts 11 dead_end + 15 assumption entities from fixture
- 45 governance tests pass, 778+ total tests pass with zero regressions

---
*Phase: 12-governance-protocol-integration*
*Completed: 2026-02-20*
