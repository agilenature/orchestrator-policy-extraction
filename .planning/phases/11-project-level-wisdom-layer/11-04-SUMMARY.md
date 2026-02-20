---
phase: 11-project-level-wisdom-layer
plan: 04
subsystem: cli
tags: [click, cli, wisdom, fts, scope-decision]

# Dependency graph
requires:
  - phase: 11-project-level-wisdom-layer
    provides: WisdomStore, WisdomIngestor, WisdomRetriever
provides:
  - wisdom CLI subcommands (ingest, check-scope, reindex, list)
  - CLI registration in __main__.py entrypoint
affects: [governance, cli-documentation]

# Tech tracking
tech-stack:
  added: []
  patterns: [click group subcommands for wisdom management]

key-files:
  created:
    - src/pipeline/cli/wisdom.py
    - tests/test_cli_wisdom.py
  modified:
    - src/pipeline/cli/__main__.py

key-decisions:
  - "wisdom_group registered alongside existing extract/validate/train/audit groups"
  - "check-scope filters search_by_scope results to scope_decision entities only"
  - "list shows first 80 chars of description with ellipsis truncation"
  - "8 tests instead of planned 5 for better coverage (list-after-ingest, filter-by-type, check-scope-with-match)"

patterns-established:
  - "Wisdom CLI follows same click group pattern as audit/train groups"

# Metrics
duration: 4min
completed: 2026-02-20
---

# Phase 11 Plan 04: CLI Wisdom Subcommands + check-scope Summary

**Click CLI group with ingest/check-scope/reindex/list subcommands integrating wisdom layer into pipeline CLI**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-20T15:13:02Z
- **Completed:** 2026-02-20T15:17:24Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Four wisdom CLI subcommands: ingest (bulk JSON loader), check-scope (scope decision lookup), reindex (FTS rebuild), list (entity browser with type filter)
- Wisdom group registered in __main__.py alongside extract, validate, train, audit
- 8 CLI tests covering all subcommands including edge cases (empty DB, missing files, scope matching)
- 700 tests passing (692 baseline + 8 new), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create wisdom CLI subcommands** - `d9a9a34` (feat)
2. **Task 2: Register wisdom group in __main__.py** - `a56c098` (feat)
3. **Task 3: Write CLI tests** - `3861b3f` (test)

## Files Created/Modified
- `src/pipeline/cli/wisdom.py` - Four subcommands: ingest, check-scope, reindex, list with shared logging setup
- `src/pipeline/cli/__main__.py` - Added wisdom_group import and registration
- `tests/test_cli_wisdom.py` - 8 CLI tests using CliRunner with tmp_path isolation

## Decisions Made
- Wrote 8 tests instead of planned 5 to cover list-after-ingest, type filtering, and scope matching with populated data
- check-scope only shows scope_decision entities (filters out breakthroughs, dead_ends, method_decisions from search_by_scope results)
- Description preview in list truncates at 80 chars with "..." suffix

## Deviations from Plan

None - plan executed exactly as written. Three additional tests were added beyond the 5 specified to improve coverage.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 11 complete: all 4 plans delivered (models+store, retriever+recommender, ingestor+seed, CLI)
- Full wisdom pipeline operational: `python -m src.pipeline.cli wisdom ingest|check-scope|reindex|list`
- 700 tests passing across all subsystems
- Ready for Phase 12 (Governance) when scheduled

---
*Phase: 11-project-level-wisdom-layer*
*Completed: 2026-02-20*
