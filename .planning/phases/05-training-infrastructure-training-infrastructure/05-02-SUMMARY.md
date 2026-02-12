---
phase: 05-training-infrastructure
plan: 02
subsystem: rag
tags: [hybrid-retriever, bm25, cosine-similarity, rrf, recommender, danger-detection, pydantic, duckdb-fts, duckdb-vss]

# Dependency graph
requires:
  - phase: 05-01-episode-embedding
    provides: EpisodeEmbedder, observation_to_text, episode_embeddings table, episode_search_text table with FTS
  - phase: 03-constraint-management
    provides: ConstraintStore with constraint severity/scope for danger detection
provides:
  - HybridRetriever combining BM25 + embedding cosine similarity via RRF fusion
  - Recommender with weighted majority vote action selection from approved episodes
  - Recommendation and SourceEpisodeRef Pydantic models with explainable provenance
  - check_dangerous function detecting scope violations, risk underestimates, gate drops, protected paths
  - exclude_episode_id support for leave-one-out shadow mode testing
affects: [05-03-shadow-mode]

# Tech tracking
tech-stack:
  added: []
  patterns: [Reciprocal Rank Fusion (rrf_k=60), parameterized SQL for exclude_id (IS NULL OR !=), bidirectional prefix matching for constraint scope violations, weighted majority vote for mode selection]

key-files:
  created:
    - src/pipeline/rag/retriever.py
    - src/pipeline/rag/recommender.py
    - tests/test_retriever.py
    - tests/test_recommender.py
  modified:
    - src/pipeline/rag/__init__.py

key-decisions:
  - "Bidirectional prefix matching for scope violation detection (rec path under constraint dir OR constraint path under rec path)"
  - "Parameterized SQL with IS NULL OR != pattern for exclude_episode_id (avoids SQL injection)"
  - "Over-fetch top_k*2 from each search strategy before RRF fusion for better recall"
  - "Pydantic frozen models for Recommendation and SourceEpisodeRef (immutable, serializable)"

patterns-established:
  - "HybridRetriever: BM25 + embedding cosine similarity via Reciprocal Rank Fusion"
  - "Parameterized exclude_id via IS NULL OR != SQL pattern (safe, no f-string interpolation)"
  - "Action selection: weighted majority vote from approved episodes, max risk (conservative)"
  - "Danger detection: 4-category check (scope_violation, risk_underestimate, gate_dropped, protected_path)"

# Metrics
duration: 9min
completed: 2026-02-11
---

# Phase 5 Plan 2: Hybrid Retriever and Recommender Summary

**Hybrid BM25+embedding retriever with RRF fusion, weighted majority vote recommender, and 4-category danger detection against constraints and protected paths**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-12T00:44:10Z
- **Completed:** 2026-02-12T00:53:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- HybridRetriever combines DuckDB FTS (BM25) and DuckDB VSS (cosine similarity) via Reciprocal Rank Fusion with rrf_k=60
- Parameterized SQL queries with IS NULL OR != pattern for exclude_episode_id (safe, no SQL injection)
- Recommender selects action from approved episodes using weighted majority vote (mode) and max risk (conservative)
- Recommendation Pydantic model includes explainable provenance citing source episode IDs, similarity scores, modes, and reaction labels
- check_dangerous detects 4 danger categories: scope violation (bidirectional prefix match against constraints), risk underestimate, gate dropping, protected path overlap
- 394 tests pass (24 new + 370 existing), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - Failing tests for HybridRetriever and Recommender** - `f1e1d97` (test)
2. **Task 2: GREEN - Implement HybridRetriever and Recommender** - `3b93a4e` (feat)

_TDD plan: RED produced 22 failing tests, GREEN made all 24 pass (2 model tests passed from RED since they test Pydantic model creation, not stubs)._

## Files Created/Modified
- `src/pipeline/rag/retriever.py` - HybridRetriever with _bm25_search, _embedding_search, _rrf_fuse, and retrieve()
- `src/pipeline/rag/recommender.py` - Recommender with recommend(), _select_action, check_dangerous; Recommendation and SourceEpisodeRef Pydantic models
- `src/pipeline/rag/__init__.py` - Updated exports: HybridRetriever, Recommender, Recommendation, SourceEpisodeRef, check_dangerous
- `tests/test_retriever.py` - 11 tests: BM25 search (3), embedding search (2), RRF fusion (3), end-to-end retrieve (3)
- `tests/test_recommender.py` - 13 tests: action selection (5), recommendation models (3), danger detection (5)

## Decisions Made
- Used bidirectional prefix matching for scope violation detection: `rec_path.startswith(constraint_path) or constraint_path.startswith(rec_path)` -- this correctly handles both `secrets/api_key.yaml` matching constraint `secrets/` and constraint `secrets/deep/` matching rec path `secrets/`
- Parameterized SQL with `? IS NULL OR episode_id != ?` pattern avoids SQL injection while handling the optional exclude_episode_id
- Over-fetch `top_k * 2` results from each search strategy to improve RRF fusion recall
- Pydantic frozen=True models for Recommendation and SourceEpisodeRef ensure immutability and clean serialization

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed scope violation detection using bidirectional prefix matching**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** Research pattern used set intersection (`rec_scope & c_paths`) for scope violation, which only catches exact string matches. `secrets/api_key.yaml` does not intersect with `secrets/` since they are different strings.
- **Fix:** Replaced set intersection with bidirectional prefix matching loop: `rp.startswith(cp) or cp.startswith(rp)`
- **Files modified:** src/pipeline/rag/recommender.py
- **Verification:** test_scope_violation_detected passes
- **Committed in:** 3b93a4e (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential correctness fix for danger detection. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- HybridRetriever and Recommender complete, ready for Plan 03 (Shadow Mode Testing)
- Shadow mode can use Recommender.recommend(observation, exclude_episode_id=episode_id) for leave-one-out testing
- check_dangerous available for flagging dangerous shadow mode recommendations
- All RAG components (embedder, retriever, recommender) exported from src/pipeline/rag/

## Self-Check: PASSED

- All 5 files verified present on disk
- Commit `f1e1d97` (Task 1 RED) verified in git log
- Commit `3b93a4e` (Task 2 GREEN) verified in git log
- 394 tests pass, zero regressions

---
*Phase: 05-training-infrastructure*
*Completed: 2026-02-11*
