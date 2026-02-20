---
phase: 11-project-level-wisdom-layer
verified: 2026-02-20T15:52:52Z
status: passed
score: 5/5 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "RAG retriever returns relevant wisdom entities alongside top-k episodes — _vector_search() now calls embed_text() and array_cosine_similarity"
    - "Scope decision enforcement: check-scope validates completion state with exit codes 0 (pass), 1 (violation), 2 (error)"
  gaps_remaining: []
  regressions: []
gaps: null
human_verification: null
---

# Phase 11: Project-Level Wisdom Layer Verification Report

**Phase Goal:** The pipeline captures and retrieves project-level knowledge (breakthroughs, dead ends, scope decisions) as structured entities in a `project_wisdom` DuckDB table. The RAG retriever uses these alongside episode context.
**Verified:** 2026-02-20T15:52:52Z
**Status:** passed
**Re-verification:** Yes — after gap closure (previous score 3/5, now 5/5)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `project_wisdom` table stores Breakthrough, DeadEnd, ScopeDecision, MethodDecision entities | VERIFIED | `schema.py` lines 310-340: CREATE TABLE IF NOT EXISTS project_wisdom with CHECK constraint on entity_type IN ('breakthrough','dead_end','scope_decision','method_decision'). All 4 types insert successfully. Included in drop_schema(). 34/34 store+ingestor tests pass. |
| 2 | RAG retriever returns relevant wisdom entities alongside top-k episodes | VERIFIED | `retriever.py` _vector_search() (lines 215-267) now calls `self._embedder.embed_text(query)` and executes `array_cosine_similarity(embedding, ?::DOUBLE[])` SQL. Falls back to BM25-only when embedder=None. TestVectorSearch (3 tests) and TestDualDeadEndDetection (4 tests) all pass. 22/22 retriever tests pass. |
| 3 | Scope decision enforcement: `python -m src.pipeline.cli wisdom check-scope` validates completion state | VERIFIED | `cli/wisdom.py` check-scope (lines 57-144) implements full 0/1/2 exit code protocol: sys.exit(0) for no violations, sys.exit(1) for violation found, sys.exit(2) for runtime error. Imports ConstraintStore and calls get_active_constraints(). Violation detection uses 2+ matching title words + severity in ('forbidden','requires_approval'). 5 new exit-code tests pass: test_check_scope_exit_0_no_violations, test_check_scope_exit_1_violation_found, test_check_scope_exit_2_runtime_error, test_check_scope_no_decisions_exit_0, test_check_scope_constraint_scope_mismatch_no_violation. |
| 4 | Dead end detection: recommendations include dead-end warnings when context matches known failures | VERIFIED | _is_dead_end_warning() uses dual agreement when vector_score is available: both BM25 abs(score)>=threshold AND vector_score>=0.3 must pass. Falls back to BM25-only when vector_score=None. WisdomRef.is_dead_end_warning propagates to EnrichedRecommendation.has_dead_end_warning. All 4 TestDualDeadEndDetection tests pass. |
| 5 | The four objectivism analysis documents are converted into 15+ wisdom entries in data/seed_wisdom.json | VERIFIED | 17 entries confirmed: 5 breakthrough, 4 dead_end, 4 scope_decision, 4 method_decision. All 4 source documents represented. No regressions — file unchanged from initial verification. |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pipeline/wisdom/models.py` | WisdomEntity, WisdomRef, EnrichedRecommendation models | VERIFIED | 157 lines. All 4 entity types via Literal type. Frozen Pydantic v2. `_make_wisdom_id()` is SHA-256 of entity_type+title. No regressions. |
| `src/pipeline/wisdom/store.py` | WisdomStore CRUD + search | VERIFIED | 370 lines. All CRUD + search_by_tags + search_by_scope + upsert. 29 store tests pass. No regressions. |
| `src/pipeline/storage/schema.py` | project_wisdom DDL in create_schema() | VERIFIED | Lines 310-340. CREATE TABLE IF NOT EXISTS project_wisdom with CHECK constraint. Included in drop_schema(). No regressions. |
| `src/pipeline/wisdom/retriever.py` | WisdomRetriever with BM25, vector search, dead end detection | VERIFIED | 365 lines. BM25 via DuckDB FTS, vector via array_cosine_similarity when embedder wired, RRF fusion, dual dead end detection, scope boosting. Previously PARTIAL — now fully implemented. All 22 retriever tests pass. |
| `src/pipeline/wisdom/ingestor.py` | WisdomIngestor for bulk JSON loading | VERIFIED | 159 lines. ingest_file() and ingest_list(). 5 ingestor tests pass. No regressions. |
| `src/pipeline/cli/wisdom.py` | wisdom CLI with ingest, check-scope, reindex, list | VERIFIED | 210 lines. Four subcommands. check-scope now implements full validation with 0/1/2 exit codes and ConstraintStore integration. Previously PARTIAL — now fully implemented. 13/13 CLI tests pass (8 original + 5 new exit-code tests). |
| `src/pipeline/cli/__main__.py` | wisdom_group registered | VERIFIED | wisdom_group imported and registered with cli.add_command. No regressions. |
| `data/seed_wisdom.json` | 15+ wisdom entries from 4 analysis docs | VERIFIED | 17 entries, all 4 entity types, all 4 source documents. No regressions. |
| `tests/test_wisdom_store.py` | Model + store tests | VERIFIED | 29 tests pass. No regressions. |
| `tests/test_wisdom_retriever.py` | Retriever + vector search + dual dead end tests | VERIFIED | 22 tests pass (up from 15 — 7 new tests added: TestVectorSearch x3, TestDualDeadEndDetection x4). All pass. |
| `tests/test_wisdom_ingestor.py` | Ingestor tests | VERIFIED | 5 tests pass. No regressions. |
| `tests/test_cli_wisdom.py` | CLI tests including exit code tests | VERIFIED | 13 tests pass (up from 8 — 5 new exit-code tests added). All pass. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/pipeline/wisdom/models.py` | all 4 entity types | Literal type constraint | WIRED | entity_type: Literal["breakthrough","dead_end","scope_decision","method_decision"] at line 67 |
| `src/pipeline/storage/schema.py` | project_wisdom table | create_schema() DDL | WIRED | Lines 310-340. CHECK constraint on entity_type. |
| `src/pipeline/wisdom/retriever.py` | `src/pipeline/wisdom/store.py` | WisdomStore._conn access | WIRED | Line 54: self._conn = store._conn. BM25 via fts_main_project_wisdom.match_bm25. |
| `src/pipeline/wisdom/retriever.py` | EpisodeEmbedder | embedder.embed_text(query) | WIRED (optional) | Lines 231-267: checks self._embedder is not None, calls embed_text(query), uses result in array_cosine_similarity SQL. Graceful fallback to BM25-only when embedder=None. Previously NOT_WIRED — now WIRED. |
| `src/pipeline/rag/recommender.py` | `src/pipeline/wisdom/retriever.py` | optional wisdom_retriever param | WIRED (opt-in) | wisdom_retriever param wires WisdomRetriever into Recommender._maybe_enrich(). Returns EnrichedRecommendation when set. |
| `src/pipeline/cli/wisdom.py` | `src/pipeline/wisdom/ingestor.py` | ingest command | WIRED | Lines 40-45: WisdomIngestor(store).ingest_file(path) |
| `src/pipeline/cli/wisdom.py` | `src/pipeline/constraint_store.py` | check-scope -> ConstraintStore | WIRED | Lines 80-93: imports ConstraintStore, calls get_active_constraints(). Violation detection at lines 97-123. sys.exit(1) at line 135. Previously NOT_WIRED — now WIRED. |
| `src/pipeline/cli/__main__.py` | `src/pipeline/cli/wisdom.py` | cli.add_command | WIRED | Line 26 import, line 39 registration |

---

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| `project_wisdom` DuckDB table with all 4 entity types | SATISFIED | All 4 types enforced via CHECK constraint |
| RAG retriever returns wisdom alongside episode results | SATISFIED | BM25 + vector (array_cosine_similarity when embedder wired) + RRF fusion. Wisdom enrichment wired into Recommender via wisdom_retriever param. |
| `wisdom check-scope` exits 0/1/2 for pass/violation/error | SATISFIED | sys.exit(0) no violations, sys.exit(1) violation found, sys.exit(2) runtime error. 5 exit-code tests pass. |
| Dead end warnings in recommendations when context matches failures | SATISFIED | Dual BM25+vector agreement when vector_score available. BM25-only fallback when vector_score=None. |
| 15+ seed wisdom entries from 4 objectivism analysis docs | SATISFIED | 17 entries across all 4 docs and all 4 entity types |

---

### Anti-Patterns Found

None. The two blocker anti-patterns from the initial verification have been resolved:

- `_vector_search()` stub removed: method now calls embed_text() and array_cosine_similarity SQL.
- `check-scope` validation gap closed: full 0/1/2 exit code protocol with ConstraintStore integration implemented.

---

### Human Verification Required

None. All checks are programmatically verifiable.

---

### Re-Verification Summary

Both gaps from the initial verification (2026-02-20) are closed:

**Gap 1 (Closed) — Vector search stub in WisdomRetriever._vector_search().**
The stub (always returning `[]`) has been replaced with a real implementation (lines 215-267 in retriever.py). The method now: (1) checks `self._embedder is not None`, (2) checks the table contains rows with embeddings, (3) calls `self._embedder.embed_text(query)` to generate a query vector, (4) executes `array_cosine_similarity(embedding, ?::DOUBLE[])` SQL to rank by cosine similarity, and (5) returns `(wisdom_id, similarity)` tuples. Graceful fallback to empty list when no embedder is wired or no embeddings exist. The EpisodeEmbedder is now accepted as an optional constructor parameter. Seven new tests in TestVectorSearch and TestDualDeadEndDetection confirm the implementation, all passing.

**Gap 2 (Closed) — check-scope lookup command now a validation command.**
The `check-scope` subcommand (lines 57-144 in cli/wisdom.py) now implements the full 0/1/2 exit code protocol. It loads the ConstraintStore from a configurable `--constraints` path, calls `get_active_constraints()`, and performs text-based violation detection: for each scope_decision, extracts title words longer than 3 characters, finds constraints whose text contains 2+ of those words, and flags violations when constraint severity is `forbidden` or `requires_approval` and scope paths overlap. Exits sys.exit(1) when any violation is found, sys.exit(2) on runtime errors (with SystemExit re-raise to prevent suppression). Five new CLI tests cover each exit code path, all passing.

No regressions detected in the 34 previously-passing store and ingestor tests.

Total passing tests for Phase 11: 69 (22 retriever + 13 CLI + 29 store + 5 ingestor).

---

_Verified: 2026-02-20T15:52:52Z_
_Verifier: Claude (gsd-verifier)_
