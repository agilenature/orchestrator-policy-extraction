---
phase: 23-autonomous-loop-mode-switch-detection
plan: 01
subsystem: detection
tags: [pydantic, yaml-frontmatter, drift-detection, ebc, pipeline]

# Dependency graph
requires:
  - phase: 09-obstacle-escalation-detection
    provides: "EscalationDetector pattern for write-class tool identification"
  - phase: 01-event-stream-foundation
    provides: "PipelineConfig, config.yaml, runner.py Step pattern"
provides:
  - ExternalBehavioralContract Pydantic model with expected_write_paths
  - parse_ebc_from_plan YAML frontmatter parser
  - EBCDriftDetector comparing EBC against session write operations
  - write_alert JSON artifact writer to data/alerts/
  - EBCDriftConfig integrated into PipelineConfig
  - Runner Step 23 with ImportError-safe wiring
affects: [23-02, 23-03, autonomous-loop-mode-switch]

# Tech tracking
tech-stack:
  added: []
  patterns: [ebc-contract-model, frontmatter-parsing, file-set-drift-detection]

key-files:
  created:
    - src/pipeline/ebc/__init__.py
    - src/pipeline/ebc/models.py
    - src/pipeline/ebc/parser.py
    - src/pipeline/ebc/detector.py
    - src/pipeline/ebc/writer.py
    - tests/test_ebc_models.py
    - tests/test_ebc_parser.py
    - tests/test_ebc_detector.py
    - tests/test_ebc_writer.py
    - data/alerts/.gitkeep
  modified:
    - src/pipeline/models/config.py
    - src/pipeline/runner.py
    - data/config.yaml

key-decisions:
  - "EBC detector operates on raw event dicts from read_events(), not TaggedEvent objects -- matches the data available at Step 23 in the pipeline"
  - "write_alert accepts optional alerts_dir parameter for test isolation rather than monkeypatching module-level ALERTS_DIR"
  - "Tolerance patterns use fnmatch on both full path and filename component for reliable __init__.py filtering"
  - "Drift score = weighted_sum / max(expected_count, 1), capped at 1.0 -- normalized against contract size"

patterns-established:
  - "EBC contract model: frozen Pydantic models with expected_write_paths property combining files_modified and artifact paths"
  - "Frontmatter parser: split on --- maxsplit=2, yaml.safe_load, must_haves extraction, type->plan_type rename"
  - "File-set drift detection: actual vs expected comparison with tolerance filtering and weighted scoring"

# Metrics
duration: 7min
completed: 2026-02-28
---

# Phase 23 Plan 01: EBC Drift Detection Core Pipeline Summary

**Pydantic EBC models, PLAN.md frontmatter parser, file-set drift detector with configurable threshold, JSON alert writer, and Runner Step 23 integration**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-27T23:57:10Z
- **Completed:** 2026-02-28T00:04:22Z
- **Tasks:** 2
- **Files created:** 10
- **Files modified:** 3

## Accomplishments

- ExternalBehavioralContract parses any valid PLAN.md frontmatter into a machine-readable contract with expected_write_paths
- EBCDriftDetector distinguishes Edit/Write (write-class) from Read/Glob/Grep (read-class) tool operations
- Alert artifacts are valid JSON with drift_score, signals, phase, plan persisted to data/alerts/
- Runner Step 23 wired with ImportError-safe pattern, fires when self._ebc is set and enabled
- 49 new tests (28 model/parser + 21 detector/writer), zero regressions in existing 2070-test suite

## Task Commits

Each task was committed atomically:

1. **Task 1: Create EBC Pydantic models, PLAN.md parser, and model tests** - `1c0e1e8` (feat)
2. **Task 2: Create EBCDriftDetector, alert writer, config, runner integration, and tests** - `1c0ebb8` (feat)

## Files Created/Modified

- `src/pipeline/ebc/__init__.py` - Package exports for all EBC components
- `src/pipeline/ebc/models.py` - ExternalBehavioralContract, EBCArtifact, EBCKeyLink, DriftSignal, EBCDriftAlert
- `src/pipeline/ebc/parser.py` - parse_ebc_from_plan() YAML frontmatter parser
- `src/pipeline/ebc/detector.py` - EBCDriftDetector with _extract_write_paths and tolerance filtering
- `src/pipeline/ebc/writer.py` - write_alert() JSON artifact writer
- `src/pipeline/models/config.py` - EBCDriftConfig with threshold validators
- `src/pipeline/runner.py` - Step 23 EBC drift detection + self._ebc attribute
- `data/config.yaml` - ebc_drift section with defaults
- `data/alerts/.gitkeep` - Alert output directory
- `tests/test_ebc_models.py` - 16 model construction/serialization/frozen tests
- `tests/test_ebc_parser.py` - 12 parser tests including real PLAN.md integration
- `tests/test_ebc_detector.py` - 16 drift detection, tolerance, extraction tests
- `tests/test_ebc_writer.py` - 5 file writing and JSON validity tests

## Decisions Made

- EBC detector operates on raw event dicts (from `read_events()`), not TaggedEvent objects, matching data available at Step 23
- `write_alert` accepts optional `alerts_dir` parameter for test isolation rather than monkeypatching
- Tolerance patterns check both full path and filename component via fnmatch for reliable __init__.py filtering
- Drift score normalized against contract size: `weighted_sum / max(expected_count, 1)`, capped at 1.0

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 02 (Runner integration with set_ebc + PLAN.md auto-discovery) has all prerequisites: models, parser, detector, writer, config, and runner attribute are in place
- Plan 03 (Recovery commands and state injection) has write_alert and inject_state config ready
- self._ebc is initialized to None; Plan 02 will add set_ebc() method and auto-discovery

---
*Phase: 23-autonomous-loop-mode-switch-detection*
*Completed: 2026-02-28*
