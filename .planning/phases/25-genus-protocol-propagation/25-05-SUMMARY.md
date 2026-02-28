---
phase: 25-genus-protocol-propagation
plan: 05
subsystem: skills
tags: [reframe, reasoning-protocols, crow-injection, genus-oracle, process-level]

requires:
  - phase: 25-02
    provides: /api/genus-consult endpoint for Tier 2 genus oracle queries
  - phase: 25-03
    provides: Genus protocol propagation design patterns
provides:
  - Global /reframe skill with three reasoning protocols and three-tier capability detection
  - Process-level companion to /elevate (object-level)
  - Verbatim protocol directive emission for immediate session use
affects: [elevate-skill, genus-protocol-propagation, premise-registry]

tech-stack:
  added: []
  patterns: [three-tier-capability-detection, protocol-selection-by-failure-signature, crow-injection-pair]

key-files:
  created:
    - ~/.claude/skills/reframe/SKILL.md
    - ~/.claude/skills/reframe/reframe-framework.md
  modified: []

key-decisions:
  - "Files created outside OPE repo in ~/.claude/skills/reframe/ (global skill directory) -- cannot be committed to OPE git"
  - "Protocol escalation is monotonic: Pattern-Not-Symptom (3) > Axis-Before-Fix (2) > Premise-Declare-First (1)"
  - "Default protocol is Premise-Declare-First when no clear signals detected (safest fallback)"

patterns-established:
  - "Skill pair pattern: /elevate (object-level WHAT) + /reframe (process-level HOW) as complementary Crow injections"
  - "Three-tier capability detection: OPE-local > OPE-via-bus > Lightweight, with fail-open fallback"

duration: 2min
completed: 2026-02-28
---

# Phase 25 Plan 05: /reframe Skill Summary

**Global /reframe skill with three reasoning protocols (Premise-Declare-First, Axis-Before-Fix, Pattern-Not-Symptom), three-tier capability detection, and genus oracle integration as process-level companion to /elevate**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T13:51:47Z
- **Completed:** 2026-02-28T13:54:29Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- Created reframe-framework.md reference document with three reasoning protocols, protocol selection logic, capability tiers, and /elevate integration guidance
- Created /reframe SKILL.md with full 7-step execution flow: load framework, parse problem, detect capabilities, gather evidence, select protocol, emit directive, present output
- Three-tier capability detection: Tier 1 (OPE-local with DuckDB queries), Tier 2 (OPE-via-bus with genus-consult API), Tier 3 (Lightweight with MEMORY.md + git log)
- Genus oracle integration in Tier 1 and Tier 2 grounds protocol selection with confidence scores

## Task Commits

Both files created outside OPE repository (in `~/.claude/skills/reframe/`), so no per-task git commits possible. Files verified in place.

1. **Task 1: Create reframe-framework.md** - No commit (file outside repo). Verified: 145 lines, 9 Protocol references, 9 protocol name references.
2. **Task 2: Create SKILL.md** - No commit (file outside repo). Verified: 163 lines, correct frontmatter, 12 protocol name references, genus-consult integration.

## Files Created/Modified
- `~/.claude/skills/reframe/reframe-framework.md` - Reference document: three protocols, selection logic, capability tiers, /elevate integration
- `~/.claude/skills/reframe/SKILL.md` - Invocable skill: 7-step execution (parse, detect tier, gather evidence, select protocol, emit directive)

## Decisions Made
- Files live in `~/.claude/skills/reframe/` (global, outside OPE repo) -- this is by design for cross-project invocability
- Protocol escalation is monotonic (3 > 2 > 1) to prevent under-response to recurring failures
- Default to Premise-Declare-First when no signals detected (surfaces hidden assumptions as safest fallback)
- Fail-open on bus connectivity: Tier 2 silently falls back to Tier 3 if OPE_BUS_SOCKET unreachable

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Files outside OPE git repository**
- **Found during:** Task 1 (commit attempt)
- **Issue:** Plan specifies per-task commits but `~/.claude/skills/reframe/` is outside the OPE git repository at `/Users/david/projects/orchestrator-policy-extraction`
- **Fix:** Created files at correct global path, verified in place, documented as non-committable. No code change needed -- this is the intended location for global skills.
- **Files affected:** ~/.claude/skills/reframe/reframe-framework.md, ~/.claude/skills/reframe/SKILL.md
- **Verification:** `ls` confirms both files exist, `wc -l` confirms line counts meet minimums
- **Committed in:** N/A (files outside git repo)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Expected behavior -- global skills are designed to live outside any project repo. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- /reframe skill is invocable from any Claude Code session via `/reframe`
- Plans 03 and 04 of Phase 25 are still pending -- this plan (05) was executed independently as it only depends on 25-02 and 25-03 design patterns
- Phase 25 completion requires plans 03, 04 to also be completed

## Self-Check: PASSED

- FOUND: ~/.claude/skills/reframe/SKILL.md (163 lines)
- FOUND: ~/.claude/skills/reframe/reframe-framework.md (145 lines)
- FOUND: 25-05-SUMMARY.md
- No per-task commits expected (files outside git repo)

---
*Phase: 25-genus-protocol-propagation*
*Completed: 2026-02-28*
