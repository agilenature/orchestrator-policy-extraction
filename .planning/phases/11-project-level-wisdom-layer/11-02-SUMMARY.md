---
phase: 11-project-level-wisdom-layer
plan: 02
subsystem: rag
tags: [wisdom, bm25, fts, rrf, duckdb, retriever, enrichment]

# Dependency graph
requires:
  - phase: 11-project-level-wisdom-layer plan 01
    provides: WisdomEntity, WisdomRef, EnrichedRecommendation models, WisdomStore
  - phase: 05-training-infrastructure plan 02
    provides: HybridRetriever, Recommender, RRF pattern
provides:
  - WisdomRetriever with hybrid BM25 + dead end detection
  - Recommender wisdom enrichment (optional EnrichedRecommendation)
  - 15 new tests for retriever and integration
affects: [11-project-level-wisdom-layer, pipeline-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [FTS on project_wisdom table, RRF fusion for wisdom search, dead end threshold filtering, optional enrichment layer]

key-files:
  created:
    - src/pipeline/wisdom/retriever.py
    - tests/test_wisdom_retriever.py
  modified:
    - src/pipeline/rag/recommender.py
    - src/pipeline/wisdom/__init__.py

key-decisions:
  - "WisdomRetriever accesses store._conn for raw SQL (same-package access pattern)"
  - "Vector search returns empty when no embeddings present (BM25-only fallback)"
  - "Dead end detection uses abs(bm25_score) >= 0.6 threshold (DuckDB FTS returns negative scores)"
  - "Scope overlap boosts relevance by 1.5x for matching paths"
  - "Lazy import of EnrichedRecommendation in recommender._maybe_enrich() to avoid circular imports"
  - "FTS index auto-built on first retrieve() if not explicitly rebuilt"

patterns-established:
  - "Optional enrichment: accept optional collaborator in __init__, conditionally wrap output"
  - "FTS index on project_wisdom: PRAGMA create_fts_index with overwrite=1"

# Metrics
duration: 9min
completed: 2026-02-20
---

# Phase 11 Plan 02: WisdomRetriever + Recommender Integration Summary

**WisdomRetriever with BM25 search via DuckDB FTS, dead end detection, and Recommender enrichment returning EnrichedRecommendation**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-20T14:53:20Z
- **Completed:** 2026-02-20T15:02:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- WisdomRetriever with hybrid BM25 search using DuckDB FTS on title + description
- Dead end detection with BM25 threshold filtering (abs score >= 0.6)
- Recommender accepts optional wisdom_retriever, returns EnrichedRecommendation when set
- 687 tests passing (672 baseline + 15 new), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create WisdomRetriever** - `4245d01` (feat)
2. **Task 2: Integrate WisdomRetriever into Recommender** - `ecef59c` (feat)
3. **Task 3: Write tests** - `ea78b5b` (test)

## Files Created/Modified
- `src/pipeline/wisdom/retriever.py` - WisdomRetriever class with BM25 search, RRF fusion, dead end detection, scope filtering
- `src/pipeline/rag/recommender.py` - Added optional wisdom_retriever param, _maybe_enrich() method
- `src/pipeline/wisdom/__init__.py` - Added WisdomRetriever to exports
- `tests/test_wisdom_retriever.py` - 15 tests covering retrieval, dead ends, scope, integration

## Decisions Made
- WisdomRetriever accesses store._conn for raw SQL queries (acceptable since both are in the same wisdom package)
- Vector search returns empty list when no embeddings present, falling back to BM25-only results
- Dead end detection uses abs(bm25_score) >= 0.6 threshold because DuckDB FTS match_bm25 returns negative scores (more negative = stronger match)
- Scope overlap boosts relevance score by 1.5x multiplicative factor for path-matching entities
- EnrichedRecommendation imported lazily inside _maybe_enrich() to avoid circular import between rag/ and wisdom/ packages
- FTS index auto-built on first retrieve() call if not explicitly rebuilt (lazy initialization)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- WisdomRetriever and Recommender enrichment ready for pipeline integration
- 687 tests passing, zero regressions
- Ready for Plan 11-03 (Wisdom Extraction CLI) or Plan 11-04 (Pipeline Integration)

## Self-Check: PASSED

All files verified present, all commit hashes found in git log.

---
*Phase: 11-project-level-wisdom-layer*
*Completed: 2026-02-20*
