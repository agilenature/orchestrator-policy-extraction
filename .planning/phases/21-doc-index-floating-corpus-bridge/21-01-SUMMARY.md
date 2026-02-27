---
phase: 21-doc-index-floating-corpus-bridge
plan: 01
subsystem: database
tags: [duckdb, schema, pydantic, doc-index, ccd-axis]

# Dependency graph
requires:
  - phase: 19-live-governance-bus
    provides: "bus schema chain (create_bus_schema), CheckResponse model"
  - phase: 20-causal-chain-completion
    provides: "push_links table in bus schema chain"
provides:
  - "doc_index DuckDB table for (doc_path, ccd_axis) associations"
  - "create_doc_schema() function wired into bus startup chain"
  - "CheckResponse.relevant_docs field for doc delivery wire format"
  - "DOC_INDEX_DDL constant for schema reference"
affects: [21-02, 21-03, 21-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import pattern for schema modules in create_bus_schema()"
    - "Separate DDL module per table group (doc_schema.py parallels schema.py)"

key-files:
  created:
    - src/pipeline/live/bus/doc_schema.py
    - tests/test_doc_schema.py
  modified:
    - src/pipeline/live/bus/schema.py
    - src/pipeline/live/bus/models.py

key-decisions:
  - "Lazy import in create_bus_schema() rather than top-level import -- keeps schema.py dependencies minimal"
  - "CHECK constraint on association_type with 5 values (frontmatter, regex, keyword, manual, unclassified) -- extensible via ALTER"
  - "Composite primary key (doc_path, ccd_axis) -- enables multi-axis documents, one row per axis"

patterns-established:
  - "Schema module pattern: separate DDL module per table group with create_X_schema() function"
  - "CheckResponse field extension pattern: add list field with empty default for fail-open behavior"

# Metrics
duration: 2min
completed: 2026-02-27
---

# Phase 21 Plan 01: Doc Index Schema Summary

**doc_index DuckDB table with composite PK (doc_path, ccd_axis) and CheckResponse.relevant_docs wire format field**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-27T15:19:08Z
- **Completed:** 2026-02-27T15:21:09Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created doc_index table schema with 8 columns, composite PK, CHECK constraint on association_type, and sensible defaults
- Wired doc_schema into bus startup chain via lazy import in create_bus_schema()
- Extended CheckResponse with relevant_docs field for Phase 21 doc delivery
- 8 new tests covering DDL creation, idempotency, PK enforcement, CHECK constraint, defaults, bus integration, model field, and serialization

## Task Commits

Each task was committed atomically:

1. **Task 1: Create doc_schema.py, wire into schema chain, extend CheckResponse** - `e6fa809` (feat)
2. **Task 2: Tests for doc_schema and CheckResponse extension** - `c44d7a1` (test)

## Files Created/Modified
- `src/pipeline/live/bus/doc_schema.py` - DOC_INDEX_DDL constant and create_doc_schema() function
- `src/pipeline/live/bus/schema.py` - Lazy import of create_doc_schema() at end of create_bus_schema()
- `src/pipeline/live/bus/models.py` - CheckResponse.relevant_docs field added
- `tests/test_doc_schema.py` - 8 tests covering schema and model changes

## Decisions Made
- Used lazy import pattern (import inside function body) for doc_schema in create_bus_schema() to keep schema.py top-level imports minimal and match established pattern
- Composite primary key (doc_path, ccd_axis) rather than surrogate key -- directly encodes the domain invariant that each doc-axis pair is unique
- CHECK constraint on association_type with 5 enumerated values -- provides data integrity while remaining extensible via ALTER TABLE

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- doc_index table ready for Plan 02 (frontmatter indexer)
- CheckResponse.relevant_docs ready for Plan 03/04 (session-start briefing)
- create_bus_schema() chain creates all tables idempotently on startup
- Zero regressions in existing 27 bus tests

## Self-Check: PASSED

All 4 created/modified files verified present. Both task commits (e6fa809, c44d7a1) verified in git log.

---
*Phase: 21-doc-index-floating-corpus-bridge*
*Completed: 2026-02-27*
