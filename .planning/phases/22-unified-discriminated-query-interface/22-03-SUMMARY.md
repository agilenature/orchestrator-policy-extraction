---
phase: 22-unified-discriminated-query-interface
plan: 03
subsystem: query
tags: [duckdb, attach, cross-project, bm25, session-filtering, cli]

requires:
  - phase: 22-unified-discriminated-query-interface
    provides: "Plan 01: query_sessions (BM25/ILIKE), query_code (rg/grep); Plan 02: unified query CLI with --source dispatch, --project stub, db_path in projects.json"
provides:
  - "Cross-project doc queries via DuckDB ATTACH READ_ONLY"
  - "Cross-project session filtering via session_ids from sessions_location"
  - "_resolve_project() for project registry lookup"
  - "_get_project_session_ids() for session ID extraction from JSONL dirs"
  - "_query_docs_cross_project() with ATTACH lifecycle management"
  - "32 integration tests covering all 6 phase success criteria"
affects: [phase-23, live-session-governance, intelligence-profile]

tech-stack:
  added: []
  patterns:
    - "DuckDB ATTACH READ_ONLY for cross-DB queries with fully-qualified table names"
    - "Session ID extraction from JSONL filename stems for project-scoped filtering"
    - "Fail-open pattern for cross-project queries (return [] on any error)"

key-files:
  created:
    - "tests/test_cross_project_query.py"
  modified:
    - "src/pipeline/cli/query.py"
    - "src/pipeline/session_query.py"

key-decisions:
  - "Direct axis matching only for cross-project doc queries (no axis_edges expansion) -- remote DBs may lack axis_edges table"
  - "Code search blocked for remote projects (local-only per research Pitfall 8)"
  - "Session filtering via JOIN with episodes table when session_ids provided"
  - "Fully-qualified remote.doc_index names to avoid USE/DETACH ordering issues"

patterns-established:
  - "ATTACH pattern: connect :memory:, ATTACH remote READ_ONLY, use fully-qualified names, DETACH, close"
  - "Session ID extraction: glob *.jsonl in sessions_location, extract stems"

duration: 7min
completed: 2026-02-27
---

# Phase 22 Plan 03: Cross-Project Query Summary

**Cross-project --project flag wired to DuckDB ATTACH for remote doc_index queries and session_id filtering for episode search, with 32 integration tests covering all 6 phase success criteria**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-27T17:13:57Z
- **Completed:** 2026-02-27T17:20:26Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Cross-project doc queries via DuckDB ATTACH READ_ONLY with graceful cleanup
- Session filtering by project's session_ids (from sessions_location JSONL filenames)
- Graceful error messages for null db_path, unknown projects, remote code search
- 32 integration tests verifying all 6 phase success criteria plus edge cases
- Full backward compatibility: 2021 tests passing, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Cross-project doc query via ATTACH and session filtering** - `64d2390` (feat)
2. **Task 2: Integration tests covering all 6 success criteria** - `12ad850` (test)

## Files Created/Modified
- `src/pipeline/cli/query.py` - Cross-project --project flag with ATTACH for docs, session filtering, code blocking
- `src/pipeline/session_query.py` - Extended query_sessions() with optional session_ids filter parameter
- `tests/test_cross_project_query.py` - 32 integration tests covering SC-1 through SC-6 plus edge cases

## Decisions Made
- Direct axis matching only for cross-project queries (skip axis_edges expansion since remote may lack that table)
- Use fully-qualified `remote.doc_index` table names to avoid USE/DETACH ordering complexity
- Code search blocked for remote projects with informative message (per research Pitfall 8)
- BM25 session filtering uses subquery on episodes table; ILIKE filtering uses JOIN

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed backward compatibility with existing test assertion**
- **Found during:** Task 1
- **Issue:** Changed "unknown project" message broke existing test asserting "not found" substring
- **Fix:** Updated message to "Project {id!r} not found in registry" to maintain backward compatibility
- **Files modified:** src/pipeline/cli/query.py
- **Verification:** All 36 existing tests pass
- **Committed in:** 64d2390 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Trivial message wording fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 22 is now complete: all 3 plans executed, all 6 success criteria verified
- Unified query interface ready for integration with live session governance
- Cross-project query infrastructure available for future intelligence profile features

---
*Phase: 22-unified-discriminated-query-interface*
*Completed: 2026-02-27*
