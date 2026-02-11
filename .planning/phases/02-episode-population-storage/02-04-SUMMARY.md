---
phase: 02-episode-population-storage
plan: 04
subsystem: pipeline
tags: [duckdb, merge-upsert, episode-storage, pipeline-integration, reaction-labeling, validation]

# Dependency graph
requires:
  - phase: 02-episode-population-storage (plans 01-03)
    provides: Episode model, schema, validator, populator, reaction labeler
  - phase: 01-event-stream-foundation
    provides: PipelineRunner, event writer, segmenter, tagger, CLI
provides:
  - write_episodes() with DuckDB MERGE for idempotent episode upserts
  - read_episodes_by_session() for querying episodes
  - Full pipeline: segment -> populate -> label -> validate -> write episodes
  - CLI episode stats and reaction label distribution output
affects: [03-constraint-extraction, 04-preference-learning, 05-analytical-queries]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MERGE INTO with staging table for STRUCT column construction"
    - "struct_pack() in SQL for DuckDB STRUCT column insertion"
    - "Tag lookup dict for reaction labeling from stored events"

key-files:
  created:
    - tests/test_episode_storage.py
  modified:
    - src/pipeline/storage/writer.py
    - src/pipeline/runner.py
    - src/pipeline/cli/extract.py
    - tests/test_runner.py

key-decisions:
  - "Staging table + MERGE for episodes (struct_pack in INSERT SELECT avoids STRUCT binding issues)"
  - "_find_next_human_message builds tag list from tag_by_event_id for ReactionLabeler compatibility"
  - "Episode validation gates storage: invalid episodes logged but never written to episodes table"

patterns-established:
  - "MERGE upsert via staging table: flat staging -> struct_pack() -> MERGE INTO target"
  - "Phase 2 stages run after Phase 1 write (events/segments must be in DB before episode population)"

# Metrics
duration: 7min
completed: 2026-02-11
---

# Phase 2 Plan 4: Episode Storage + Integration Summary

**DuckDB MERGE upsert for episodes with full pipeline integration: populate, label reactions, validate, and write via staging table struct_pack pattern**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-11T20:32:10Z
- **Completed:** 2026-02-11T20:39:39Z
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- write_episodes() uses DuckDB MERGE for idempotent episode upserts (no duplicates on re-run)
- PipelineRunner orchestrates all Phase 2 stages: populate -> label -> validate -> write episodes
- CLI reports episode counts (populated/valid/invalid) and reaction label distribution
- 16 new tests: 12 storage tests + 4 integration tests (198 total, up from 182)

## Task Commits

Each task was committed atomically:

1. **Task 1: Episode writer with MERGE upsert + storage tests** - `1feac78` (feat)
2. **Task 2: PipelineRunner integration + CLI update + end-to-end tests** - `c55ae7a` (feat)

## Files Created/Modified
- `src/pipeline/storage/writer.py` - Added write_episodes() with MERGE, read_episodes_by_session(), staging table pattern with struct_pack()
- `src/pipeline/runner.py` - Extended PipelineRunner with Steps 9-11 (populate, validate, write episodes), _find_next_human_message helper
- `src/pipeline/cli/extract.py` - Episode stats and reaction label distribution in session/batch summaries
- `tests/test_episode_storage.py` - 12 tests: MERGE upsert, STRUCT dot notation, JSON queries, no duplicates, read_episodes_by_session
- `tests/test_runner.py` - 4 new tests: full pipeline with episodes, idempotent rerun, validation rejects, reaction labeling

## Decisions Made
- Used staging table + struct_pack() in SQL for STRUCT column insertion (avoids DuckDB parameter binding issues with nested STRUCT types)
- _find_next_human_message constructs a dict with 'tags' list from tag_by_event_id mapping for ReactionLabeler compatibility (labeler expects tags as list, not single primary_tag)
- Episode validation runs as separate Step 10 after population (Step 9) -- invalid episodes are logged but never written to the episodes table

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 is complete: all 4 plans executed, 198 tests passing
- Full pipeline: JSONL -> events -> segments -> episodes in DuckDB with hybrid schema
- Ready for Phase 3 (Constraint Extraction) or Phase 4 (Preference Learning)
- The episodes table with flat + STRUCT + JSON columns supports analytical queries needed by downstream phases

---
*Phase: 02-episode-population-storage*
*Completed: 2026-02-11*
