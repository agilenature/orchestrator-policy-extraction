---
phase: 14-live-session-governance-research
plan: 03
subsystem: live-governance-design
tags: [blueprint, phase-15, waves, api-contracts, test-strategy, hooks, stream-processor, bus, governor]

# Dependency graph
requires:
  - phase: 14-live-session-governance-research (plan 01)
    provides: "14-01-DESIGN.md: LIVE-01, LIVE-02, LIVE-03 design specifications"
  - phase: 14-live-session-governance-research (plan 02)
    provides: "14-02-DESIGN.md: LIVE-04, LIVE-05, LIVE-06 design specifications"
provides:
  - "14-03-BLUEPRINT.md: Complete Phase 15 implementation blueprint with 5 waves, 9 plans, 33 files, ~125 tests"
  - "Phase 15 wave structure: hooks -> stream -> bus -> governor -> integration"
  - "API contracts for all major classes/functions with Python type hints"
  - "Test strategy with ~125 test scenarios across unit, integration, and protocol categories"
  - "Plan-level mapping for /gsd:plan-phase Phase 15 input"
affects: [phase-15-live-governance-implementation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Blueprint-as-plan-input: design research synthesized into executable wave structure"
    - "Wave dependency ordering: hooks first (standalone), then stream, bus, governor, integration"
    - "API contract specification with Python type hints in blueprint format"

key-files:
  created:
    - .planning/phases/14-live-session-governance-research/14-03-BLUEPRINT.md

key-decisions:
  - "Phase 15 scope: LIVE-01 through LIVE-05 only; LIVE-06 (DDF co-pilot) deferred to Phase 15 Wave 6+ or Phase 16"
  - "9 plans across 5 waves with explicit sequencing constraints"
  - "Models in hooks/models.py not a separate shared module: keeps hook scripts self-contained for standalone mode"
  - "SSE (/api/events/stream) may start as polling, upgrade to SSE in Wave 5 if needed"

patterns-established:
  - "Design-to-blueprint synthesis: research phase produces DESIGN.md, blueprint phase produces BLUEPRINT.md as plan-phase input"

# Metrics
duration: 6min
completed: 2026-02-24
---

# Phase 14 Plan 03: Phase 15 Implementation Blueprint Summary

**Complete Phase 15 implementation blueprint with 5 waves, 9 plans, 33 file targets, 86 API contract signatures, ~125 test scenarios, and plan-level mapping for /gsd:plan-phase input**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-24T01:28:11Z
- **Completed:** 2026-02-24T01:34:55Z
- **Tasks:** 2 (merged into single document write)
- **Files created:** 1

## Accomplishments

1. **Phase 15 wave structure defined:** 5 waves (hooks, stream, bus, governor, integration) with explicit dependency ordering and file targets for all 18 source files and 15 test files.

2. **API contracts specified:** 86 function/class signatures with Python type hints extracted from 14-01-DESIGN.md and 14-02-DESIGN.md, grouped by wave. Covers all Pydantic models, hook entry points, adapter interfaces, bus route handlers, governor daemon, decision matrix, and broadcast protocol.

3. **Test strategy documented:** ~125 test scenarios across 5 waves with specific test categories (unit, integration, protocol), test infrastructure requirements (io.StringIO for hooks, tempfile for JSONL, httpx.AsyncClient for bus routes), and per-wave count estimates.

4. **Requirements mapped:** All 5 LIVE requirements (LIVE-01 through LIVE-05) restated with implementation-level acceptance criteria including latency targets (PreToolUse <200ms, bus /api/check <5ms, stream processor <200ms).

5. **Plan mapping created:** 9 GSD plans with task counts, duration estimates (~5.5 hours total), and sequencing constraints ready for Phase 15 `/gsd:plan-phase`.

## Task Commits

1. **Task 1+2: Complete blueprint document** - `ec00cc7` (docs)
   - Tasks merged: both wave structure (sections 0-2) and technical specs (sections 3-4) written as a single coherent document because API contracts reference wave file targets and test strategy references API contracts.

## Files Created/Modified

- `.planning/phases/14-live-session-governance-research/14-03-BLUEPRINT.md` - Complete Phase 15 implementation blueprint (1166 lines)

## Decisions Made

1. **Phase 15 scope boundary:** LIVE-01 through LIVE-05 in scope. LIVE-06 (DDF co-pilot), Policy Automatization Detector, ai_flame_events, memory_candidates schema extensions, and governor dashboard deferred to Phase 15 Wave 6+ or Phase 16. Rationale: core governance infrastructure must be operational before the DDF/assessment layers build on it.

2. **Models in hooks/models.py:** All Pydantic models (HookInput, GovernanceDecision, GovernanceSignal, LiveEvent, etc.) placed in `hooks/models.py` rather than a separate shared models module. Rationale: hook scripts must be standalone executables (called by Claude Code); keeping models in the hooks subpackage ensures minimal import chains for standalone mode.

3. **SSE endpoint risk mitigation:** `/api/events/stream` (SSE) identified as medium risk. Mitigation: start with polling-based event consumption; upgrade to true SSE in Wave 5 only if needed. Core bus functionality does not depend on SSE.

4. **DuckDB single-writer pattern:** Bus process owns all DuckDB writes (governance_signals, governance_decisions). Stream processor writes via bus API (`POST /api/events`), not directly. Rationale: avoids concurrent write conflicts.

## Deviations from Plan

### Task Merge

**Tasks 1 and 2 were written as a single document** rather than two separate commits. The plan specified Task 1 (wave structure) and Task 2 (API contracts, tests, requirements) as separate operations. In practice, the API contracts in section 3.1 reference file targets from section 1 (waves), and the test strategy in section 3.2 references API contracts from 3.1. Writing the full document as one coherent unit ensures cross-reference consistency. This is the same merge pattern as 14-01 and 14-02.

**Total deviations:** 1 (task merge, structural only -- all content present)
**Impact on plan:** None. Both tasks' verify criteria are satisfied. The blueprint is complete.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

Phase 14 is now complete (all 4 plans: research, design-01, design-02, blueprint).

**Phase 15 can begin immediately.** The blueprint provides:
- 9 executable GSD plans with task descriptions and file targets
- All API contracts with Python type hints
- Test strategy with ~125 specific test scenarios
- Sequencing constraints between plans
- Risk mitigations for known technical uncertainties

**Prerequisites for Phase 15:**
- `pip install watchdog>=6.0.0` (needed for Wave 2)
- Existing dependencies (starlette, uvicorn, httpx) already in the project environment

**Phase 14 deliverables:**
- `14-RESEARCH.md` -- Hook protocol analysis, Claude Code integration research
- `14-01-DESIGN.md` -- LIVE-01, LIVE-02, LIVE-03 design specifications
- `14-02-DESIGN.md` -- LIVE-04, LIVE-05, LIVE-06 design specifications
- `14-03-BLUEPRINT.md` -- Phase 15 implementation blueprint

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `.planning/phases/14-live-session-governance-research/14-03-BLUEPRINT.md` | FOUND (1166 lines) |
| Commit ec00cc7 | FOUND |
| Section 0 (Phase 15 overview) | PRESENT |
| Section 1 (Wave definitions, 5 waves) | PRESENT |
| Section 2 (Wave dependency graph) | PRESENT |
| Section 3.1 (API contracts, 86 signatures) | PRESENT |
| Section 3.2 (Test strategy, ~125 tests) | PRESENT |
| Section 3.3 (LIVE-01 through LIVE-05 requirements) | PRESENT |
| Section 3.4 (Success criteria, 9 items) | PRESENT |
| Section 3.5 (Risks and mitigations, 7 items) | PRESENT |
| Section 3.6 (Plan mapping, 9 plans) | PRESENT |
| Section 4 (Cross-references) | PRESENT |

---
*Phase: 14-live-session-governance-research*
*Completed: 2026-02-24*
