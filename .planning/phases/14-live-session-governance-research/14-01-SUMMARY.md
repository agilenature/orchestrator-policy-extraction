---
phase: 14-live-session-governance-research
plan: 01
subsystem: live-governance-design
tags: [hooks, stream-processor, governance, design, pydantic, episode-boundary]
dependency_graph:
  requires: []
  provides:
    - "14-01-DESIGN.md: Complete specification for LIVE-01, LIVE-02, LIVE-03"
    - "PreToolUse hook contract with JSON schemas and decision logic"
    - "SessionStart hook contract with CCD-axis-grouped briefing format"
    - "JSONL stream processor architecture with watchdog, adapters, and boundary state machine"
    - "GovernanceSignal model with boundary_dependency dispatch routing"
  affects:
    - "14-02-DESIGN.md: bus /api/check endpoint consumes same GovernanceDecision model"
    - "14-02-DESIGN.md: bus /api/events endpoint receives GovernanceSignal emissions"
    - "Phase 15 implementation: builds from this spec without architectural decisions"
    - "data/schemas/constraint.schema.json: needs ccd_axis and epistemological_origin fields"
tech_stack:
  added: []
  patterns:
    - "Fail-open hook design (exit 0 on all errors)"
    - "CCD-axis grouping for algebraic Desktop compression"
    - "TENTATIVE_END / CONFIRMED_END episode boundary state machine"
    - "boundary_dependency field for event_level vs episode_level signal dispatch"
key_files:
  created:
    - ".planning/phases/14-live-session-governance-research/14-01-DESIGN.md"
  modified: []
decisions:
  - id: "14-01-D1"
    title: "CCD Constraint Architecture: algebraic, not arithmetic"
    decision: "All constraints carry ccd_axis and epistemological_origin; briefings group by axis, not flat concretes"
    rationale: "12-15 principle axes cover 80%+ of 332 active constraints; Crow cost 12, not 332"
  - id: "14-01-D2"
    title: "Fail-open hook design"
    decision: "Every failure mode in PreToolUse and SessionStart hooks results in 'allow'"
    rationale: "Governance is advisory infrastructure, not a security boundary; blocking work due to governance bugs is worse than missing a violation"
  - id: "14-01-D3"
    title: "boundary_dependency dispatch routing"
    decision: "GovernanceSignal carries boundary_dependency (event_level|episode_level); event_level fires immediately, episode_level buffers until CONFIRMED_END"
    rationale: "Amnesia detection requires episode context; emitting at event time produces false positives"
  - id: "14-01-D4"
    title: "TTL episodes excluded from constraint training"
    decision: "Episodes confirmed via 30-min timeout inactivity are NOT used for constraint extraction training"
    rationale: "Inferred outcome corrupts reaction labels; completeness_score=4/5 with property 4 missing"
  - id: "14-01-D5"
    title: "X_ASK excluded from end triggers in stream processor"
    decision: "X_ASK is structurally mid-episode; never appears as end trigger or in confidence scoring"
    rationale: "Consistent with post-hoc segmenter locked decision; prevents false-positive episode splits"
metrics:
  duration: "8 min"
  completed: "2026-02-24"
---

# Phase 14 Plan 01: Single-Session Governance Layer Design Summary

**One-liner:** Complete design specification for PreToolUse constraint enforcement (LIVE-01), SessionStart CCD-axis-grouped briefing (LIVE-02), and real-time JSONL stream processor with TENTATIVE_END/CONFIRMED_END episode boundary state machine (LIVE-03).

## Performance Metrics

| Metric | Value |
|--------|-------|
| Duration | 8 min |
| Tasks completed | 2/2 |
| Design sections | 3 major (Hook Contracts, Stream Processor, Cross-Cutting) + 2 appendices |
| JSON schemas defined | 5 (PreToolUse input, deny output, warn output, SessionStart input, SessionStart output) |
| Pydantic models defined | 6 (HookInput, GovernanceDecision, AxisGroup, ConstraintBriefing, GovernanceSignal, LiveEvent) |
| Incremental adapters designed | 3 (EscalationAdapter, AmnesiaAdapter, PolicyCheckAdapter) |
| Architectural decisions made | 5 (CCD architecture, fail-open, boundary_dependency, TTL exclusion, X_ASK exclusion) |

## Accomplishments

1. **LIVE-01 PreToolUse Hook Contract**: Complete specification with JSON schemas for all 3 output variants (deny, warn, silent allow), decision logic table, text extraction strategy per tool type (Bash, Write, Edit, Read, Glob, Grep), fallback behavior for 6 failure modes, and latency budget (70-115ms direct, 55-90ms via bus).

2. **LIVE-02 SessionStart Hook Contract**: Complete specification with CCD-axis-grouped briefing format, scope filtering via `scopes_overlap()`, durability score integration for CRITICAL classification, truncation strategy for 2000-char limit, and constraint compression ratio design goal (12-15 axes covering 80%+ of 332 active constraints).

3. **LIVE-03 JSONL Stream Processor Architecture**: Full design including watchdog FSEvents integration with position tracking and partial line handling, LiveEventAdapter with 8 pre-compiled tag inference rules, 3 incremental detector adapters, governance signal emission to 3 targets (stdout, DuckDB, bus), latency analysis (<10ms per event, ~20ms end-to-end), and the TENTATIVE_END/CONFIRMED_END episode boundary state machine.

4. **CCD Architecture Decision**: Binding decision that all constraints carry `ccd_axis` and `epistemological_origin` fields, briefings group by axis rather than listing flat concretes, and the compression ratio target is 12-15 principles covering 80%+ of scope. This is the Phase 3 to Phase 4 inflection point described in 14-CONTEXT.md.

5. **Episode Boundary State Machine**: Complete state machine specification with 5 states (INITIAL, OPEN, TENTATIVE_END, CONFIRMED_END, REOPENED), confidence scoring at TENTATIVE_END, signal dispatch routing by boundary_dependency, false positive handling on REOPENED, and TTL episode completeness flagging (4/5 properties).

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Hook contracts and data models (LIVE-01 + LIVE-02) | 2ad030e | 14-01-DESIGN.md (sections 1-3 + appendices) |
| 2 | JSONL stream processor architecture (LIVE-03) | (included in 2ad030e) | 14-01-DESIGN.md sections 2.1-2.7 |

Note: Both tasks were completed in a single write of the design document. The document was written as a complete unit rather than two separate appends because the data models in section 1.3 (GovernanceSignal, LiveEvent) are shared between hook contracts and stream processor.

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `.planning/phases/14-live-session-governance-research/14-01-DESIGN.md` | Created | Complete design specification (~1626 lines) |

## Decisions Made

| ID | Decision | Rationale | Impact |
|----|----------|-----------|--------|
| 14-01-D1 | CCD-axis grouping for constraint briefings | 12-15 axes cover 80%+ of 332 constraints; Crow cost: 12 Desktop slots, not 332 | Phase 15 must classify existing constraints by axis; briefing format is algebraic |
| 14-01-D2 | Fail-open hook design | Governance bugs must not block work | All error paths exit 0; PreToolUse never crashes tool execution |
| 14-01-D3 | boundary_dependency dispatch routing | Amnesia requires episode context; event-level signals are independent | IncrementalAmnesiaAdapter buffers until CONFIRMED_END; EscalationAdapter emits immediately |
| 14-01-D4 | TTL episodes excluded from training | Inferred outcome corrupts reaction labels | completeness_score=4/5; pattern detection still allowed |
| 14-01-D5 | X_ASK excluded from end triggers | Consistent with post-hoc segmenter | Prevents false-positive episode splits in stream processor |

## Deviations from Plan

### Task Merge

**Tasks 1 and 2 were written as a single document** rather than two separate commits. The plan specified Task 1 (hook contracts) and Task 2 (stream processor) as separate append operations. In practice, section 1.3 (Shared Data Models) defines GovernanceSignal and LiveEvent which are consumed by section 2 (stream processor). Writing both together ensures consistency between the data models and their consumers. This is a structural decision, not a content deviation.

### Constraint Count Update

**Plan stated 208 constraints; actual count is 419 (332 active).** The design document uses the current verified count rather than the plan's older figure. The compression ratio target (12-15 axes covering 80%+) was adjusted to reference 332 active constraints rather than 208.

### scopes_overlap() Location Correction

**Plan referenced `src/pipeline/durability/utils.py`; actual location is `src/pipeline/utils.py`.** The design document uses the correct path. This was validated via Grep before writing.

## Issues Encountered

None. The research document (14-RESEARCH.md) and existing codebase provided sufficient context for all design decisions.

## Next Phase Readiness

The design document is complete and sufficient for Phase 15 implementation:
- **LIVE-01 (PreToolUse hook):** Implementable from section 1.1 without clarifying questions
- **LIVE-02 (SessionStart hook):** Implementable from section 1.2 without clarifying questions
- **LIVE-03 (Stream processor):** Implementable from section 2 without clarifying questions
- **Shared models:** Defined in section 1.3 with full field types and descriptions
- **File structure:** Specified in section 3.3

**Prerequisite for Phase 15:** The constraint JSON schema must be extended with `ccd_axis` and `epistemological_origin` fields (section 1.4). This can be done as the first task of Phase 15 implementation.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `.planning/phases/14-live-session-governance-research/14-01-DESIGN.md` | FOUND (1626 lines) |
| `.planning/phases/14-live-session-governance-research/14-01-SUMMARY.md` | FOUND |
| Commit 2ad030e | FOUND |
