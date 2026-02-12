---
phase: 05-training-infrastructure
plan: 01
subsystem: rag
tags: [sentence-transformers, embeddings, duckdb-fts, duckdb-vss, bm25, cosine-similarity]

# Dependency graph
requires:
  - phase: 02-episode-population-storage
    provides: episodes table with observation STRUCT and orchestrator_action JSON
  - phase: 04-validation-quality
    provides: 352-test baseline for regression checking
provides:
  - EpisodeEmbedder class generating 384-dim embeddings via all-MiniLM-L6-v2
  - observation_to_text() function extracting searchable text from episode observations
  - episode_embeddings DuckDB table with FLOAT[384] and model provenance
  - episode_search_text DuckDB table with BM25 FTS index
  - rebuild_fts_index() for post-ingestion FTS index refresh
affects: [05-02-hybrid-retriever, 05-03-shadow-mode]

# Tech tracking
tech-stack:
  added: [sentence-transformers 5.2.2, transformers 5.1.0, safetensors]
  patterns: [DuckDB FTS PRAGMA create_fts_index, DuckDB VSS FLOAT[384] arrays, STRUCT-to-dict conversion for observation extraction]

key-files:
  created:
    - src/pipeline/rag/__init__.py
    - src/pipeline/rag/embedder.py
    - tests/test_embedder.py
  modified:
    - src/pipeline/storage/schema.py

key-decisions:
  - "FTS index install/load in rebuild_fts_index() rather than create_schema() to avoid extension dependency on schema creation"
  - "VSS extension loaded in create_schema() with try/except for already-installed scenarios"
  - "HNSW index not created in schema (requires data); will be created by HybridRetriever in Plan 02"
  - "observation_to_text uses DuckDB STRUCT quality_state field names (tests_status, lint_status) matching the schema"

patterns-established:
  - "DuckDB STRUCT to dict conversion via _struct_to_dict() recursive helper"
  - "Idempotent embedding with LEFT JOIN exclusion pattern"
  - "FTS index rebuild with overwrite=1 after batch ingestion"

# Metrics
duration: 5min
completed: 2026-02-11
---

# Phase 5 Plan 1: Episode Embedding Infrastructure Summary

**384-dim episode embeddings via sentence-transformers all-MiniLM-L6-v2 with DuckDB FTS + VSS storage tables and idempotent batch embedding**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-12T00:36:23Z
- **Completed:** 2026-02-12T00:41:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- EpisodeEmbedder generates 384-dim float embeddings from any text input via sentence-transformers
- observation_to_text() extracts and concatenates searchable text from episode observation STRUCT + orchestrator_action JSON with graceful None handling
- DuckDB schema extended with episode_embeddings (FLOAT[384], model provenance) and episode_search_text (BM25 FTS) tables
- embed_episodes() is idempotent -- skips already-embedded episodes using LEFT JOIN exclusion
- rebuild_fts_index() creates porter-stemmed BM25 index with English stopwords for full-text search
- 370 tests pass (18 new + 352 existing), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - Failing tests for EpisodeEmbedder and schema extensions** - `5339af5` (test)
2. **Task 2: GREEN - Implement EpisodeEmbedder with schema extensions** - `6c95ba7` (feat)

_TDD plan: RED produced 18 failing tests, GREEN made all pass._

## Files Created/Modified
- `src/pipeline/rag/__init__.py` - Module init exporting EpisodeEmbedder and observation_to_text
- `src/pipeline/rag/embedder.py` - EpisodeEmbedder class with embed_text(), embed_episodes(), observation_to_text(), rebuild_fts_index()
- `src/pipeline/storage/schema.py` - Extended with episode_embeddings and episode_search_text tables, VSS extension loading, drop_schema updates
- `tests/test_embedder.py` - 18 tests: observation text extraction (8), embedding generation (6), schema extensions (4)

## Decisions Made
- Used `INSTALL fts; LOAD fts;` in rebuild_fts_index() rather than in create_schema() to keep schema creation independent of FTS extension availability
- VSS extension loading wrapped in try/except cascade (INSTALL+LOAD, then LOAD-only fallback) for robustness
- HNSW cosine index deferred to Plan 02 (HybridRetriever) since it requires data to be present
- observation_to_text maps to DuckDB STRUCT field names (quality_state.tests_status) rather than Pydantic model names (quality_state.tests.status)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Episode embedding infrastructure complete, ready for Plan 02 (HybridRetriever)
- Plan 02 can build BM25 + cosine similarity hybrid retrieval on top of episode_search_text and episode_embeddings tables
- HNSW index creation should be added in Plan 02 after data is present
- sentence-transformers dependency installed (5.2.2) and verified working

## Self-Check: PASSED

- All 4 files verified present on disk
- Commit `5339af5` (Task 1 RED) verified in git log
- Commit `6c95ba7` (Task 2 GREEN) verified in git log
- 370 tests pass, zero regressions

---
*Phase: 05-training-infrastructure*
*Completed: 2026-02-11*
