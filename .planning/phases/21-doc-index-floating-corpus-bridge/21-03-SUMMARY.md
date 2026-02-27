---
phase: 21-doc-index-floating-corpus-bridge
plan: 03
subsystem: governance-bus
tags: [duckdb, governor-daemon, session-start, doc-delivery, briefing]

requires:
  - phase: 21-01
    provides: "doc_index DuckDB schema, CheckResponse.relevant_docs field"
provides:
  - "GovernorDaemon._query_relevant_docs() -- DuckDB doc_index query with dedup, ordering, max-3"
  - "ConstraintBriefing.relevant_docs field on frozen Pydantic model"
  - "/api/check response includes relevant_docs alongside constraints"
  - "session_start.py prints relevant docs with [OPE] prefix"
  - "15 tests covering daemon, briefing model, server endpoint, session output"
affects: [21-04, session-start-hook, governor-daemon]

tech-stack:
  added: []
  patterns: ["DuckDB regular connection for daemon reads (not read_only=True due to concurrent write conn)", "model_copy(update=) for frozen Pydantic model field injection", "doc_path dedup in Python after SQL ORDER BY"]

key-files:
  created:
    - tests/test_doc_briefing.py
  modified:
    - src/pipeline/live/governor/briefing.py
    - src/pipeline/live/governor/daemon.py
    - src/pipeline/live/bus/server.py
    - src/pipeline/live/hooks/session_start.py

key-decisions:
  - "Use regular DuckDB connection (not read_only=True) because DuckDB rejects read_only connections when a read-write connection is already open to the same file"
  - "Dedup by doc_path in Python (first occurrence wins due to ORDER BY) rather than SQL DISTINCT ON (not supported in DuckDB)"
  - "Max 3 docs returned after dedup, always-show docs prioritized, confidence DESC for remaining"

patterns-established:
  - "GovernorDaemon now reads from both constraints.json AND DuckDB doc_index"
  - "Frozen ConstraintBriefing extended via model_copy(update=) pattern"
  - "Doc delivery is confidence-ranked across all classified docs (no per-session axis filtering)"

duration: 9min
completed: 2026-02-27
---

# Phase 21 Plan 03: Doc Briefing Delivery Pipeline Summary

**GovernorDaemon queries doc_index via DuckDB, delivers top-3 confidence-ranked docs through /api/check to session_start.py with [OPE] prefix output**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-27T15:26:28Z
- **Completed:** 2026-02-27T15:35:14Z
- **Tasks:** 2
- **Files modified:** 5 (4 source + 1 test)

## Accomplishments
- GovernorDaemon._query_relevant_docs() reads doc_index via DuckDB, returns top 3 non-unclassified docs deduplicated by doc_path, with always-show docs first then by confidence DESC
- /api/check response now includes relevant_docs alongside constraints and interventions
- session_start.py prints relevant docs with [OPE] prefix, path, axis, and description (truncated to 80 chars)
- Graceful fallback: missing doc_index table or empty table returns [], never crashes
- 15 comprehensive tests covering daemon, briefing model, server endpoint, and session output

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend GovernorDaemon with doc_index query + wire through /api/check** - `c8536bb` (feat)
2. **Task 2: Extend session_start.py printing + tests** - `4988c87` (feat)

## Files Created/Modified
- `src/pipeline/live/governor/briefing.py` - Added relevant_docs field to frozen ConstraintBriefing model
- `src/pipeline/live/governor/daemon.py` - Added _query_relevant_docs() method with DuckDB doc_index query; updated get_briefing() to include docs via model_copy
- `src/pipeline/live/bus/server.py` - Updated /api/check handler to return relevant_docs in response JSON + error fallback
- `src/pipeline/live/hooks/session_start.py` - Added relevant_docs printing block after constraints output
- `tests/test_doc_briefing.py` - 15 tests: 8 daemon, 2 briefing model, 2 server, 3 session_start

## Decisions Made
- **DuckDB connection mode:** Used regular connection (not read_only=True) because DuckDB rejects read_only connections when a read-write connection (the bus server's write connection for bus_sessions) is already open to the same file. Only SELECT queries are issued, so MVCC keeps reads safe.
- **Dedup strategy:** Python-side dedup by doc_path after SQL ORDER BY, since DuckDB does not support DISTINCT ON.
- **No per-session axis filtering:** constraints.json has no ccd_axis field, so doc delivery is confidence-ranked across all classified docs (axis is used for indexing, not delivery filtering).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DuckDB read_only=True incompatible with concurrent write connection**
- **Found during:** Task 1 (GovernorDaemon doc_index query)
- **Issue:** Plan specified `duckdb.connect(self._db_path, read_only=True)` but DuckDB raises ConnectionException ("Can't open a connection to same database file with a different configuration than existing connections") when a read-write connection is already open -- which always happens because the bus server opens a write connection for bus_sessions.
- **Fix:** Changed to `duckdb.connect(self._db_path)` (regular connection). Only SELECT queries are issued, so MVCC guarantees safe reads. Updated docstrings to document the pattern.
- **Files modified:** src/pipeline/live/governor/daemon.py
- **Verification:** Verified with test script that both connections can coexist and doc_index rows are returned correctly.
- **Committed in:** c8536bb (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix -- without it, doc delivery would silently return empty on every request when the bus server is running. No scope creep.

## Issues Encountered
- Pre-existing test failure in tests/test_segmenter.py::TestBasicSegmentation::test_multiple_sequential_episodes (unrelated to Phase 21 changes, confirmed by running test before changes)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Doc briefing delivery pipeline complete: daemon queries, server delivers, session_start prints
- Plan 04 (doc_indexer CLI) can proceed -- it populates the doc_index table that this pipeline reads
- Plan 02 (doc_indexer.py implementation) executing in parallel -- no dependency conflict

---
*Phase: 21-doc-index-floating-corpus-bridge*
*Completed: 2026-02-27*
