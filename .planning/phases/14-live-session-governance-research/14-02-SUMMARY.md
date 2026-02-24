---
phase: 14-live-session-governance-research
plan: 02
subsystem: governance
tags: [bus, ipc, unix-socket, starlette, uvicorn, governor, ddf, copilot, memory-candidates, policy-automatization]

# Dependency graph
requires:
  - phase: 14-live-session-governance-research (plan 01)
    provides: GovernanceSignal model, HookInput, GovernanceDecision, hook contracts (LIVE-01/LIVE-02/LIVE-03)
provides:
  - Inter-session coordination bus API specification (LIVE-04): 10 routes with full request/response schemas
  - Governing session pattern (LIVE-05): daemon architecture, decision matrix, Policy Automatization Detector
  - DDF co-pilot architecture (LIVE-06): three intervention types with write-on-detect memory_candidates deposit
  - memory_candidates schema extensions (session_id, subject, origin, confidence, perception_pointer)
  - ai_flame_events table schema for AI-side DDF detection
  - copilot_interventions table schema for Fringe Drift tracking
  - governance_signals, governance_decisions, constraint_usage_stats DuckDB table schemas
affects: [phase-15-live-governance-implementation, phase-16-sacred-fire-intelligence, phase-17-candidate-assessment, phase-18-bridge-warden]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bus as governance hub: single Python process co-locates HTTP server, governor, and co-pilot"
    - "Pull-based broadcast delivery: interventions piggybacked on PreToolUse /api/check responses"
    - "Write-on-detect: co-pilot deposits to memory_candidates immediately on concept capture"
    - "Policy Automatization Detector: epistemological_origin-differentiated graduation thresholds"

key-files:
  created:
    - .planning/phases/14-live-session-governance-research/14-02-DESIGN.md
  modified: []

key-decisions:
  - "Governor is Python daemon co-located with bus (not a Claude Code session): zero LLM token cost for routine monitoring"
  - "Bus uses Unix domain socket at /tmp/ope-governance-bus.sock: no port conflicts, sub-ms latency, local-only security"
  - "Broadcast delivery is pull-based (piggybacked on /api/check): no push infrastructure needed, interventions delivered at natural tool-call cadence"
  - "Policy Automatization Detector differentiates by epistemological_origin: principled constraints graduate at 10 sessions (lower threshold), reactive at 20 sessions"
  - "Three DDF co-pilot intervention types: O_AXS (post-naming, confidence 0.8), Fringe (pre-naming negative, confidence 0.6), Affect Spike (pre-naming positive, confidence 0.75)"
  - "AI-side DDF deposits have lower confidence (0.7) than human-side (0.8) per raven-cost-function-absent CCD axis"
  - "memory_candidates schema extended with session_id, subject, origin, confidence, perception_pointer for co-pilot deposits"

patterns-established:
  - "Bus-first with standalone fallback: hooks call bus when available, fall back to direct file loading"
  - "Intervention rate limiting: max 1 intervention per 10 prompts per session, 5-minute cooldown"
  - "Capture window pattern: monitor next 2 user prompts after intervention for concept extraction"

# Metrics
duration: 8min
completed: 2026-02-24
---

# Phase 14 Plan 02: Multi-Session Coordination Layer Design Summary

**Complete design specification for inter-session governance bus (10 API routes), governing session daemon with Policy Automatization Detector, and DDF co-pilot with three intervention types depositing to memory_candidates via write-on-detect**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-24T01:15:04Z
- **Completed:** 2026-02-24T01:23:32Z
- **Tasks:** 3
- **Files created:** 1

## Accomplishments

- Fully specified inter-session coordination bus (LIVE-04) with 10 API routes, shared state model, session discovery protocol, and lifecycle management
- Designed governing session pattern (LIVE-05) as a Python daemon co-located with the bus, including decision matrix for 10 signal types, Policy Automatization Detector with epistemological_origin-differentiated graduation thresholds, multi-project support, and 5 failure recovery strategies
- Designed DDF co-pilot architecture (LIVE-06) with all three intervention types (O_AXS, Fringe, Affect Spike), write-on-detect memory_candidates deposit mechanism, AI-side DDF detection, bus integration, and Fringe Drift rate metric

## Task Commits

Each task was committed atomically:

1. **Task 1: Design inter-session coordination bus (LIVE-04)** - `fde988e` (docs)
2. **Task 2: Design governing session pattern (LIVE-05)** - included in `fde988e` (all content written atomically)
3. **Task 3: Design DDF co-pilot architecture (LIVE-06)** - included in `fde988e` (all content written atomically)

_Note: All three sections were created in a single document write (design document). Content for all tasks is present and verified._

## Files Created/Modified

- `.planning/phases/14-live-session-governance-research/14-02-DESIGN.md` - Complete design specification covering LIVE-04 (bus), LIVE-05 (governor), LIVE-06 (DDF co-pilot) with 1424 lines of specification

## Decisions Made

1. **Governor as Python daemon, not Claude Code session** - Zero LLM token cost for routine monitoring (constraint checking, signal aggregation, staleness detection are purely algorithmic). Claude Code can be spawned on-demand for decisions requiring LLM reasoning (Phase 15 Wave 4+).

2. **Governor co-located with bus process** - Direct in-memory access to shared state eliminates IPC overhead. Single `govern bus start` command starts both bus and governor. The bus becomes the governance hub.

3. **Pull-based broadcast delivery** - Intervention prompts and block messages are queued per-session and delivered on the next `/api/check` call. This avoids push infrastructure and delivers at the natural tool-call cadence (Claude Code sessions call tools frequently).

4. **Epistemological_origin-differentiated graduation** - Principled constraints (valued, affect-integrated per MAS) graduate after 10 sessions at <1% violation rate. Reactive constraints (single correction, narrow scope) require 20 sessions at <2%. This implements the Desktop-to-Library transition from 14-CONTEXT.md.

5. **Three co-pilot intervention types with distinct confidence levels** - O_AXS (post-naming, 0.8), Fringe (pre-naming negative, 0.6), Affect Spike (pre-naming positive, 0.75). Confidence reflects epistemological quality: post-naming is highest because the human has already articulated the concept.

6. **memory_candidates schema extension** - Five new columns (session_id, subject, origin, confidence, perception_pointer) added via ALTER TABLE in Phase 15. Backward-compatible with existing Phase 13.3 entries.

## Deviations from Plan

None -- plan executed exactly as written. All three tasks produced the specified content within the design document.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

- **14-02-DESIGN.md** provides complete implementation specifications for Phase 15 Waves 3-6:
  - Wave 3: Bus server + API routes (10 fully specified routes)
  - Wave 4: Governor + Policy Automatization Detector
  - Wave 4: DDF co-pilot Type 1 (O_AXS)
  - Wave 5: DDF co-pilot Types 2+3 (Fringe + Affect Spike)
  - Wave 5: AI-side DDF detection
  - Wave 6: Fringe Drift metrics + dashboard
- **DuckDB schemas** specified for 6 new/extended tables (governance_signals, governance_decisions, constraint_usage_stats, ai_flame_events, copilot_interventions, memory_candidates extensions)
- **No blockers** -- all architectural decisions are made; implementers can build from this spec without clarifying questions
- **Depends on:** 14-01-PLAN.md being executed first (provides GovernanceSignal model, hook contracts, stream processor design that the bus and co-pilot integrate with)

## Self-Check: PASSED

- FOUND: `.planning/phases/14-live-session-governance-research/14-02-DESIGN.md`
- FOUND: `.planning/phases/14-live-session-governance-research/14-02-SUMMARY.md`
- FOUND: commit `fde988e` (Task 1/2/3 design document)

---
*Phase: 14-live-session-governance-research*
*Completed: 2026-02-24*
