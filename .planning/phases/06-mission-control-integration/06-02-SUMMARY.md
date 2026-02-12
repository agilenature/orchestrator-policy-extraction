---
phase: 06-mission-control-integration
plan: 02
subsystem: api
tags: [typescript, next.js, api-routes, episode-builder, mapper, lifecycle, sqlite]

# Dependency graph
requires:
  - phase: 06-mission-control-integration
    plan: 01
    provides: "SQLite episode schema (5 tables) and TypeScript CRUD functions"
  - phase: 02-episode-population-storage
    provides: "Pydantic Episode model field names and structure"
provides:
  - "EpisodeBuilder class tracking 6 task lifecycle transitions"
  - "Mapper functions converting MC task data to episode schema fields"
  - "Next.js 15 API routes for episode CRUD and event streaming"
  - "Database connection singleton (getDb)"
affects: [06-03-PLAN, 06-04-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hybrid JSON parse + prose heuristic for planning output extraction"
    - "Status progression guards for idempotent lifecycle methods"
    - "Next.js 15 async params pattern for route handlers"
    - "Lazy database singleton via getDb() for API routes"

key-files:
  created:
    - "mission-control/src/lib/episodes/mapper.ts"
    - "mission-control/src/lib/episodes/builder.ts"
    - "mission-control/src/lib/db/index.ts"
    - "mission-control/src/app/api/episodes/route.ts"
    - "mission-control/src/app/api/episodes/[id]/route.ts"
    - "mission-control/src/app/api/episodes/[id]/events/route.ts"
  modified: []

key-decisions:
  - "Hybrid planningOutputToAction: JSON.parse first, prose keyword extraction fallback"
  - "Status progression guards: idempotent lifecycle methods skip if episode already past expected state"
  - "Word-boundary regex for mode keyword detection in prose (prevents partial matches)"
  - "Next.js 15 async params: { params: Promise<{ id: string }> } pattern for route handlers"
  - "Database connection singleton via getDb() with MC_DB_PATH env var override"
  - "Input validation via allowlists (not zod) matching schema CHECK constraints"

patterns-established:
  - "mission-control/src/lib/episodes/ for episode business logic"
  - "mission-control/src/app/api/episodes/ for episode HTTP API"
  - "getDb() singleton for database access in API routes"

# Metrics
duration: 4min
completed: 2026-02-12
---

# Phase 6 Plan 02: Episode Capture from Task Lifecycle Summary

**EpisodeBuilder with 6 lifecycle methods + mapper functions (hybrid JSON/prose parsing) + Next.js 15 API routes for episode CRUD and event streaming**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-12T01:47:11Z
- **Completed:** 2026-02-12T01:51:23Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- EpisodeBuilder class with 6 idempotent lifecycle methods covering full task state machine (created -> planning -> execution -> testing -> review -> completed)
- Mapper functions with hybrid parsing: JSON.parse for structured output, prose heuristic extraction with word-boundary mode keyword matching and file path detection
- 6 API route handlers across 3 files (GET/POST collection, GET/PATCH individual, GET/POST events) with input validation and proper HTTP status codes
- Database connection singleton with lazy initialization and env var override

## Task Commits

Each task was committed atomically:

1. **Task 1: Episode mapper + builder from task lifecycle** - `1cb32a9` (feat)
2. **Task 2: Episode API routes (CRUD + events)** - `75b291d` (feat)

## Files Created/Modified
- `mission-control/src/lib/episodes/mapper.ts` - 18 interfaces (snake_case) + taskToObservation, planningOutputToAction, executionToOutcome
- `mission-control/src/lib/episodes/builder.ts` - EpisodeBuilder class with onTaskCreated, onPlanningComplete, onExecutionStarted, onTestingComplete, onReviewReady, onReviewComplete
- `mission-control/src/lib/db/index.ts` - getDb() database connection singleton
- `mission-control/src/app/api/episodes/route.ts` - GET (list with filters) and POST (create) handlers
- `mission-control/src/app/api/episodes/[id]/route.ts` - GET (single) and PATCH (reaction + field update) handlers
- `mission-control/src/app/api/episodes/[id]/events/route.ts` - GET (list events) and POST (append event) handlers

## Decisions Made
- Hybrid planningOutputToAction: tries JSON.parse first for structured MC output, falls back to prose heuristic (mode keywords, file path extraction, default medium risk)
- Status progression guards: each lifecycle method checks current episode status and skips with warning if already past expected state (idempotent)
- Word-boundary regex matching for mode keywords in prose prevents partial matches (e.g., "explore" matches but not "explored" triggering wrong mode)
- Next.js 15 async params pattern used: `{ params: Promise<{ id: string }> }` with `await params`
- Input validation uses allowlists matching schema CHECK constraints (not zod) for consistency with Plan 01's column definitions
- getDb() singleton created with MC_DB_PATH env var override and lazy schema initialization

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created db/index.ts connection module**
- **Found during:** Task 2 (API route creation)
- **Issue:** Plan specified "Import db connection from a shared module (assume getDb() function exists)" but no such module existed
- **Fix:** Created mission-control/src/lib/db/index.ts with getDb() singleton, lazy initialization, WAL mode, MC_DB_PATH env var
- **Files modified:** mission-control/src/lib/db/index.ts
- **Verification:** All API routes import getDb() successfully
- **Committed in:** 75b291d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal -- created the assumed database module that routes depend on. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- EpisodeBuilder ready for Mission Control to call from task state machine hooks
- API routes ready for frontend to consume (list, create, update, events)
- Plan 06-03 (review widget) can use PATCH /api/episodes/:id for reaction labeling
- Plan 06-04 (dashboard) can use GET /api/episodes for episode listing and filtering

## Self-Check: PASSED

All 6 created files verified present. Both task commits (1cb32a9, 75b291d) verified in git log.

---
*Phase: 06-mission-control-integration*
*Completed: 2026-02-12*
