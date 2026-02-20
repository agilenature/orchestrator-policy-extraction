---
phase: 11-project-level-wisdom-layer
plan: 01
subsystem: database, wisdom
tags: [duckdb, pydantic, sha256, crud, array-search]

requires:
  - phase: 10-cross-session-decision-durability
    provides: DuckDB schema pattern, frozen Pydantic v2 model pattern, storage/schema.py

provides:
  - WisdomEntity model with 4 entity types and factory method
  - WisdomRef lightweight reference with relevance scoring
  - EnrichedRecommendation wrapping Recommendation with wisdom context
  - WisdomStore with full CRUD, tag search, scope search, upsert
  - project_wisdom DuckDB table with CHECK constraints and indexes

affects: [11-02, 11-03, 11-04, wisdom-enrichment, recommendation-pipeline]

tech-stack:
  added: []
  patterns: [wisdom-id-generation, scope-search-with-repo-wide-fallback, list_has_any-tag-search]

key-files:
  created:
    - src/pipeline/wisdom/__init__.py
    - src/pipeline/wisdom/models.py
    - src/pipeline/wisdom/store.py
    - tests/test_wisdom_store.py
  modified:
    - src/pipeline/storage/schema.py

key-decisions:
  - "WisdomEntity uses Any type for EnrichedRecommendation.recommendation to avoid circular import with rag/recommender.py"
  - "Wisdom ID: w- prefix + 16 hex chars from SHA-256(entity_type + title) -- deterministic and collision-resistant"
  - "search_by_scope returns entities with empty scope_paths as repo-wide matches alongside exact path matches"
  - "search_by_tags uses DuckDB list_has_any() for OR-semantics: any tag match is sufficient"
  - "WisdomStore._ensure_schema() creates table inline for standalone usage independent of schema.py"
  - "delete() is idempotent (no error on nonexistent), update() raises ValueError on nonexistent"

patterns-established:
  - "Wisdom ID generation: SHA-256 of concatenated key fields, truncated to 16 hex, w- prefixed"
  - "Scope search with repo-wide fallback: empty scope_paths list treated as applicable everywhere"

duration: 7min
completed: 2026-02-20
---

# Phase 11 Plan 01: Wisdom Models + WisdomStore + Schema DDL Summary

**Frozen Pydantic v2 models for 4 wisdom entity types with DuckDB-backed CRUD/search store and project_wisdom table DDL**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-20T14:42:45Z
- **Completed:** 2026-02-20T14:50:06Z
- **Tasks:** 4
- **Files modified:** 5

## Accomplishments
- WisdomEntity, WisdomRef, EnrichedRecommendation frozen Pydantic v2 models with factory method and deterministic ID generation
- WisdomStore with 8 methods: add, get, update, delete, list, search_by_tags, search_by_scope, upsert
- project_wisdom DuckDB table with CHECK constraint, VARCHAR[] arrays, DOUBLE[] embedding column, and 2 indexes
- 29 tests covering models, CRUD, search, and edge cases (672 total, zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wisdom models** - `36625f5` (feat)
2. **Task 2: Schema DDL** - `6db9277` (feat)
3. **Task 3: WisdomStore** - `6fe421c` (feat)
4. **Task 4: Tests** - `bfde192` (test)

## Files Created/Modified
- `src/pipeline/wisdom/__init__.py` - Package exports for WisdomEntity, WisdomRef, EnrichedRecommendation, WisdomStore
- `src/pipeline/wisdom/models.py` - Frozen Pydantic v2 models and _make_wisdom_id helper
- `src/pipeline/wisdom/store.py` - DuckDB-backed WisdomStore with CRUD, tag search, scope search, upsert
- `src/pipeline/storage/schema.py` - Added project_wisdom CREATE TABLE with CHECK constraint and indexes
- `tests/test_wisdom_store.py` - 29 tests covering models and all store operations

## Decisions Made
- Used `Any` type for `EnrichedRecommendation.recommendation` to avoid circular import with `rag/recommender.py`
- Wisdom ID format: `w-` prefix + 16 hex chars from SHA-256(entity_type + title)
- `search_by_scope()` includes entities with empty `scope_paths` as repo-wide matches
- `search_by_tags()` uses DuckDB `list_has_any()` for OR-semantics matching
- `delete()` is idempotent; `update()` raises ValueError on nonexistent (asymmetric by design)
- WisdomStore creates table inline via `_ensure_schema()` for standalone usage

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wisdom models and store ready for Plan 11-02 (Wisdom Enricher)
- EnrichedRecommendation ready to wrap existing Recommendation from RAG pipeline
- WisdomStore API ready for extraction pipeline integration in Plan 11-03
- project_wisdom table ready in DuckDB schema for all subsequent plans

## Self-Check: PASSED

All 5 created/modified files verified present. All 4 task commits verified in git log. 29 tests collected and passing.

---
*Phase: 11-project-level-wisdom-layer*
*Completed: 2026-02-20*
