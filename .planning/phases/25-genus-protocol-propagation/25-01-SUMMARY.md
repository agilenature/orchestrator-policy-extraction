---
phase: 25-genus-protocol-propagation
plan: 01
subsystem: governance
tags: [genus, premise-declaration, session-start, governor-daemon, axis-edges]

requires:
  - phase: 24-genus-check-gate
    provides: axis_edges table with genus_of edges and genus_staging ingestion
provides:
  - genus_count field in CheckResponse and ConstraintBriefing models
  - _query_genus_count method in GovernorDaemon querying axis_edges
  - genus hint output in session_start.py when genus_count > 0
  - GENUS field format in CLAUDE.md Premise Declaration Protocol
  - 6 Phase 25 requirements in REQUIREMENTS.md
affects: [25-genus-protocol-propagation, genus-first-skill, reframe-skill]

tech-stack:
  added: []
  patterns:
    - "genus_count fail-open query pattern: check table existence via information_schema before querying"
    - "silent-when-zero hint pattern: session_start outputs [OPE] prefix only when count > 0"

key-files:
  created: []
  modified:
    - "~/.claude/CLAUDE.md"
    - "src/pipeline/live/bus/models.py"
    - "src/pipeline/live/governor/daemon.py"
    - "src/pipeline/live/bus/server.py"
    - "src/pipeline/live/hooks/session_start.py"
    - "src/pipeline/live/governor/briefing.py"
    - ".planning/REQUIREMENTS.md"

key-decisions:
  - "GENUS field is optional in premise declarations (additive only, no changes to existing fields)"
  - "genus_count uses fail-open pattern returning 0 on any error"
  - "Repo-scoped genus count requires both axis_edges and bus_sessions tables"

patterns-established:
  - "GENUS line format: GENUS: [mechanism name] | INSTANCES: [instance A, instance B]"
  - "Fundamentality criterion: >=2 citable instances + causal explanation (mechanism not symptom)"

duration: 3min
completed: 2026-02-28
---

# Phase 25 Plan 01: Genus Protocol Propagation Wave 1 Summary

**GENUS field added to CLAUDE.md Premise Declaration Protocol, genus_count propagated through GovernorDaemon/CheckResponse/server/session_start, and 6 Phase 25 requirements defined in REQUIREMENTS.md**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T13:41:30Z
- **Completed:** 2026-02-28T13:44:39Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Extended global CLAUDE.md with optional GENUS field in declaration format and Genus Declaration subsection with fundamentality criterion and mechanism-vs-symptom distinction table
- Added genus_count field to CheckResponse and ConstraintBriefing models with default 0
- Implemented _query_genus_count in GovernorDaemon: queries axis_edges for genus_of edges with repo scoping via bus_sessions JOIN, fail-open returns 0
- Added genus_count to /api/check response JSON in both success and fail-open paths
- Added genus hint to session_start.py: emits `[OPE] GENUS: N prior genera available` when count > 0, silent when 0
- Defined 6 Phase 25 requirements (GENEXT-01, GENEXT-02, GENORACLE-01-03, REFRAME-01) with traceability

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend CLAUDE.md with GENUS field format** - not version-controlled (global config at ~/.claude/CLAUDE.md outside project repo)
2. **Task 2: Extend CheckResponse + GovernorDaemon + server + session_start** - `f08dbaa` (feat)
3. **Task 3: Add Phase 25 requirements to REQUIREMENTS.md** - `4d848f1` (docs)

## Files Created/Modified
- `~/.claude/CLAUDE.md` - Added GENUS line to declaration format, added Genus Declaration subsection
- `src/pipeline/live/bus/models.py` - Added genus_count: int = 0 to CheckResponse
- `src/pipeline/live/governor/briefing.py` - Added genus_count: int = 0 to ConstraintBriefing
- `src/pipeline/live/governor/daemon.py` - Added _query_genus_count method, updated get_briefing
- `src/pipeline/live/bus/server.py` - Added genus_count to check() response in success and fail-open paths
- `src/pipeline/live/hooks/session_start.py` - Added genus hint output section
- `.planning/REQUIREMENTS.md` - Added 6 Phase 25 requirements + traceability rows + coverage update

## Decisions Made
- GENUS field is optional in premise declarations -- additive only, existing protocol untouched
- genus_count fail-open query: checks axis_edges table existence via information_schema, returns 0 on any error
- Repo-scoped genus count: requires both axis_edges and bus_sessions tables; falls back to global count when bus_sessions missing

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 1 complete: CLAUDE.md documentation contract and passive advisory channel operational
- Ready for 25-02 (genus oracle handler) -- axis_edges query pattern established in _query_genus_count

## Self-Check: PASSED

All 8 files verified present. Both commit hashes (f08dbaa, 4d848f1) confirmed in git log.

---
*Phase: 25-genus-protocol-propagation*
*Completed: 2026-02-28*
