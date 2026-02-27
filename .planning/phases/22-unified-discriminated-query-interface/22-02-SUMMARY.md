---
phase: 22-unified-discriminated-query-interface
plan: 02
subsystem: cli, query
tags: [click, cli, duckdb, ripgrep, bm25, unified-query]

# Dependency graph
requires:
  - phase: 22-01
    provides: "query_sessions() and query_code() backends"
  - phase: 21-03
    provides: "query_docs() axis retrieval and doc_index table"
provides:
  - "Unified query CLI command with --source dispatch to docs/sessions/code"
  - "Project registry db_path field for cross-project query resolution"
  - "17 CLI integration tests for the query command"
affects: ["22-03 cross-project ATTACH queries"]

# Tech tracking
tech-stack:
  added: []
  patterns: ["--source flag dispatch to multiple backends", "project registry db_path resolution"]

key-files:
  created:
    - src/pipeline/cli/query.py
    - tests/test_cli_query.py
  modified:
    - src/pipeline/cli/__main__.py
    - data/projects.json

key-decisions:
  - "query is a Click command (not group) -- single entry point with --source flag"
  - "query_docs results get source='docs' added inline (other backends already include source)"
  - "--project resolves db_path from projects.json; full ATTACH logic deferred to Plan 03"
  - "db_path is null for non-OPE projects (no separate DuckDB yet)"

patterns-established:
  - "Unified query dispatch: single command with --source Choice dispatching to typed backends"
  - "Project registry resolution: --project flag reads db_path from data/projects.json"

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 22 Plan 02: Unified Query CLI Summary

**Single `query` command dispatching to docs (axis), sessions (BM25), and code (rg) backends via --source flag, with project registry db_path for cross-project queries**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T17:05:10Z
- **Completed:** 2026-02-27T17:10:29Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Unified query CLI command with `--source docs|sessions|code|all` dispatching to three backends
- Project registry updated with `db_path` field on all 4 projects for cross-project resolution
- 17 integration tests covering all source modes, output format, --top, --project, backward compatibility
- Backward compatibility preserved: existing `docs query` subcommand still works unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: Create unified query CLI command + register in __main__.py** - `c0f715b` (feat)
2. **Task 2: Add db_path to projects.json entries** - `57ba1a3` (feat)

## Files Created/Modified
- `src/pipeline/cli/query.py` - Unified query command with --source dispatch, --project resolution, output formatting
- `src/pipeline/cli/__main__.py` - Register query_cmd, update docstring with new usage line
- `data/projects.json` - Add db_path field to all 4 project entries, update timestamp
- `tests/test_cli_query.py` - 17 tests: source modes, output format, --top, --project, backward compat

## Decisions Made
- query is a Click command (not a group) -- provides a single entry point with --source flag rather than nested subcommands
- doc_query results get `source: "docs"` key injected at dispatch time (session_query and code_query already include their own source keys)
- `--project` resolves db_path from projects.json for Plan 02; full cross-project ATTACH logic is Plan 03
- Non-OPE projects get `db_path: null` since they have no separate DuckDB (sessions all live in data/ope.db)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Unified query command fully operational for local queries
- Project registry has db_path field ready for Plan 03's cross-project ATTACH queries
- Plan 03 can implement DuckDB ATTACH for cross-project database access using the db_path entries

---
*Phase: 22-unified-discriminated-query-interface*
*Completed: 2026-02-27*
