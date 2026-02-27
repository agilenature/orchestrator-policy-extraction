---
phase: 22-unified-discriminated-query-interface
plan: 01
subsystem: query
tags: [duckdb, bm25, fts, ripgrep, subprocess, session-search, code-search]

# Dependency graph
requires:
  - phase: 05-training-infrastructure
    provides: "episode_search_text table with FTS index for BM25 search"
  - phase: 21-doc-index-floating-corpus-bridge
    provides: "query_docs() pattern (fail-open, dict shape with source key)"
provides:
  - "query_sessions(): BM25/ILIKE episode search with metadata enrichment"
  - "query_code(): subprocess rg/grep code search with fallback"
affects: [22-02-PLAN, 22-03-PLAN, unified-cli-dispatcher]

# Tech tracking
tech-stack:
  added: []
  patterns: [try-bm25-catch-fallback-ilike, subprocess-rg-grep-fallback, fail-open-return-empty-list]

key-files:
  created:
    - src/pipeline/session_query.py
    - src/pipeline/code_query.py
    - tests/test_session_query.py
    - tests/test_code_query.py
  modified: []

key-decisions:
  - "FTS index detection via try/catch on BM25 query rather than catalog lookup (duckdb_tables() does not expose FTS internal tables)"
  - "Consistent dict shape with 'source' key across all query backends for unified CLI dispatch"

patterns-established:
  - "try-bm25-catch-fallback: Attempt BM25 query, catch CatalogException, fall back to ILIKE -- reliable FTS detection pattern for DuckDB"
  - "subprocess-search-fallback: Check shutil.which('rg'), fall back to grep -- portable code search"
  - "query-backend-contract: All query_*() functions return list[dict] with 'source' key and fail-open to []"

# Metrics
duration: 4min
completed: 2026-02-27
---

# Phase 22 Plan 01: Query Backends Summary

**BM25 session search and subprocess code search backends with fail-open pattern and consistent dict shape for unified CLI dispatch**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-27T16:57:48Z
- **Completed:** 2026-02-27T17:02:19Z
- **Tasks:** 2
- **Files created:** 4

## Accomplishments
- `query_sessions()` with BM25 fulltext search over episode_search_text, automatic ILIKE fallback when FTS index absent, metadata enrichment from episodes table
- `query_code()` with ripgrep subprocess search, grep fallback when rg unavailable, line-number parsing with truncated content previews
- 34 tests total (19 session query + 15 code query) covering BM25, ILIKE, real filesystem, grep fallback, edge cases, fail-open behavior

## Task Commits

Each task was committed atomically:

1. **Task 1: Create query_sessions() BM25 search with ILIKE fallback** - `76bacec` (feat)
2. **Task 2: Create query_code() subprocess search with rg/grep fallback** - `5668b94` (feat)

## Files Created/Modified
- `src/pipeline/session_query.py` - BM25/ILIKE episode search with metadata enrichment from episodes table
- `src/pipeline/code_query.py` - Subprocess rg/grep code search with line-number parsing
- `tests/test_session_query.py` - 19 tests: BM25 path, ILIKE fallback, edge cases, fail-open
- `tests/test_code_query.py` - 15 tests: real filesystem search, dict shape, grep fallback, edge cases

## Decisions Made
- **FTS detection via try/catch:** DuckDB's FTS internal tables are not visible via `duckdb_tables()` or `information_schema`. The reliable pattern is to attempt the BM25 query and catch `CatalogException` to fall back to ILIKE.
- **Consistent source key:** Both backends return dicts with a `source` field ("sessions" or "code") matching the `query_docs()` pattern, enabling Wave 2 unified dispatch.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FTS index detection method does not work with DuckDB FTS**
- **Found during:** Task 1 (query_sessions BM25 search)
- **Issue:** Plan specified detecting FTS index via `SELECT table_name FROM duckdb_tables() WHERE table_name LIKE 'fts_main_episode_search_text%'`, but DuckDB FTS internal tables are not exposed through this catalog view
- **Fix:** Changed to try/catch pattern -- attempt BM25 query, catch `duckdb.CatalogException`, fall back to ILIKE
- **Files modified:** src/pipeline/session_query.py
- **Verification:** Tests pass for both BM25 path (with FTS index) and ILIKE fallback (without)
- **Committed in:** 76bacec (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential correctness fix. The try/catch approach is more robust than catalog lookup.

## Issues Encountered
None beyond the FTS detection deviation documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both query backends ready for Wave 2 CLI integration (22-02-PLAN)
- `query_sessions()` and `query_code()` export the same fail-open contract as `query_docs()`
- All three backends return consistent dict shape with `source` key for unified dispatch

---
*Phase: 22-unified-discriminated-query-interface*
*Completed: 2026-02-27*
