---
phase: 01-event-stream-foundation
plan: 01
subsystem: pipeline
tags: [pydantic, duckdb, yaml, config, data-models, schema]

# Dependency graph
requires:
  - phase: none
    provides: "First plan in project - no dependencies"
provides:
  - "PipelineConfig Pydantic model + load_config() for YAML-based configuration"
  - "CanonicalEvent, TaggedEvent, Classification frozen Pydantic models"
  - "EpisodeSegment mutable Pydantic model with add_event()/close()"
  - "DuckDB schema (events + episode_segments tables) with create_schema()"
  - "Deterministic event ID generation via make_event_id()"
affects: [01-02, 01-03, 01-04, 01-05, 02-event-classification, 03-episode-segmentation]

# Tech tracking
tech-stack:
  added: [loguru]
  patterns: [pydantic-v2-frozen-models, yaml-config-validation, duckdb-schema-creation, deterministic-event-ids]

key-files:
  created:
    - src/pipeline/__init__.py
    - src/pipeline/models/__init__.py
    - src/pipeline/models/config.py
    - src/pipeline/models/events.py
    - src/pipeline/models/segments.py
    - src/pipeline/storage/__init__.py
    - src/pipeline/storage/schema.py
  modified:
    - data/config.yaml
    - requirements.txt

key-decisions:
  - "Merged existing config patterns (tags, mode_inference, gates) into new locked-decision config structure"
  - "Used CombinationModeConfig sub-model for risk_model.combination_mode instead of bare dict"
  - "LabelDefinition sub-model for classification labels enables future schema evolution"
  - "episode_segments has 16 columns (plan said 15, but research SQL spec actually defines 16)"

patterns-established:
  - "Pydantic v2 frozen models for immutable pipeline data (CanonicalEvent, Classification, TaggedEvent)"
  - "Pydantic v2 mutable models for builder pattern (EpisodeSegment with add_event/close)"
  - "load_config() pattern: YAML -> Pydantic validation with clear error messages"
  - "DuckDB :memory: for testing, file path for production"
  - "Deterministic event IDs: SHA-256(source:session:turn:ts:actor:type)[:16]"

# Metrics
duration: 5min
completed: 2026-02-11
---

# Phase 1 Plan 01: Foundation Layer Summary

**YAML config with 21 locked decisions, frozen Pydantic v2 models for events/classifications, mutable EpisodeSegment, and DuckDB schema with events + episode_segments tables**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-11T18:34:17Z
- **Completed:** 2026-02-11T18:38:51Z
- **Tasks:** 4
- **Files modified:** 9

## Accomplishments
- Complete config.yaml rewrite encoding all 21 locked decisions from CLARIFICATIONS-ANSWERED.md with preserved existing patterns (tags, mode inference, gates)
- Pydantic v2 config model hierarchy (PipelineConfig + 9 sub-models) with field validators for ranges and enum values
- Frozen event models (CanonicalEvent, Classification, TaggedEvent) with deterministic make_event_id() producing 16-char hex hashes
- DuckDB schema with events (17 columns) and episode_segments (16 columns) tables, 4 indexes, idempotent creation

## Task Commits

Each task was committed atomically:

1. **Task 1a: Rewrite config.yaml + create init files** - `dec30d6` (feat)
2. **Task 1b: Pydantic config models + load_config()** - `b5082f4` (feat)
3. **Task 2: Event and segment Pydantic models** - `c83899d` (feat)
4. **Task 3: DuckDB schema + requirements.txt** - `0ec2d0b` (feat)

## Files Created/Modified
- `data/config.yaml` - Complete pipeline config with all 21 locked decisions
- `src/pipeline/__init__.py` - Pipeline package init
- `src/pipeline/models/__init__.py` - Models package init
- `src/pipeline/models/config.py` - PipelineConfig + 9 sub-models + load_config()
- `src/pipeline/models/events.py` - CanonicalEvent, Classification, TaggedEvent (frozen)
- `src/pipeline/models/segments.py` - EpisodeSegment (mutable with add_event/close)
- `src/pipeline/storage/__init__.py` - Storage package init
- `src/pipeline/storage/schema.py` - get_connection(), create_schema(), drop_schema()
- `requirements.txt` - Updated deps: added loguru, removed jsonlines, uncommented pytest

## Decisions Made
- Merged existing config patterns (tags, mode_inference, gate_patterns, constraint_patterns) into the new locked-decision config structure rather than discarding them, since downstream components will use them
- Created LabelDefinition as a proper Pydantic sub-model instead of using a bare dict for classification.labels, enabling future schema validation of label definitions
- Added CombinationModeConfig sub-model for risk_model.combination_mode to provide typed access
- Episode_segments table has 16 columns (the plan description said 15 but the research SQL spec actually defines 16 including created_at)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing loguru dependency**
- **Found during:** Task 1a (pre-work)
- **Issue:** loguru not installed, needed for requirements.txt and downstream pipeline logging
- **Fix:** `pip3 install loguru>=0.7`
- **Files modified:** None (pip install only)
- **Verification:** `pip3 show loguru` confirms 0.7.3 installed

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal -- loguru was already specified in the plan as needed. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Config, models, and schema are ready for all downstream plans
- Plan 01-02 (JSONL adapter) can import CanonicalEvent and use make_event_id()
- Plan 01-03 (tagger) can import TaggedEvent, Classification, and load_config()
- Plan 01-04 (segmenter) can import EpisodeSegment and use config.episode_timeout_seconds
- Plan 01-05 (storage writer) can use get_connection() and create_schema()
- No blockers identified

## Self-Check: PASSED

All 10 files verified present. All 4 task commit hashes verified in git log.

---
*Phase: 01-event-stream-foundation*
*Completed: 2026-02-11*
