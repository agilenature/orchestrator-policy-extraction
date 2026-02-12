# Phase 5: Training Infrastructure - Research

**Researched:** 2026-02-11
**Domain:** RAG retrieval, episode similarity search, shadow mode testing, recommendation validation
**Confidence:** HIGH

## Summary

Phase 5 builds two capabilities on top of the existing pipeline (Phases 1-4): (1) a RAG baseline orchestrator that retrieves similar past episodes and recommends orchestrator actions, and (2) a shadow mode testing framework that validates those recommendations against actual human decisions. The existing codebase provides strong foundations: DuckDB 1.4.4 with native FTS (BM25) and VSS (cosine similarity + HNSW indexes), 363-line Episode Pydantic models with rich observation/action/outcome structure, Parquet export for ML pipelines, and a gold-standard validation workflow from Phase 4.

The RAG system is retrieval-only (no LLM generation). For a dataset of 100-500 episodes, DuckDB's native FTS extension (BM25 ranking) combined with its native VSS extension (embedding-based cosine similarity with HNSW indexes) provides a complete hybrid search solution without requiring external vector databases. The `sentence-transformers` library with the `all-MiniLM-L6-v2` model (384-dim embeddings, ~80MB, CPU-fast) handles embedding generation. Shadow mode testing is a batch replay operation: for each historical episode, the RAG system generates a recommendation from the observation context (excluding the current episode from retrieval), then compares it against the actual human decision already stored in DuckDB.

**Primary recommendation:** Use DuckDB's native FTS + VSS for hybrid retrieval (BM25 + embedding cosine similarity), `sentence-transformers` for embedding generation, store shadow mode results in a dedicated DuckDB table, and implement danger detection by cross-referencing recommendations against the existing ConstraintStore and protected paths from config.yaml.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| duckdb | 1.4.4 (installed) | FTS (BM25), VSS (cosine similarity + HNSW), episode storage, shadow results | Already the project database; FTS and VSS extensions verified working locally; eliminates external vector DB |
| sentence-transformers | >=3.0.0 (NOT installed) | Generate 384-dim embeddings from episode observation text | Standard library for text embeddings; `all-MiniLM-L6-v2` is fast, lightweight, CPU-friendly |
| pydantic | >=2.0 (installed: 2.11.7) | RAG recommendation models, shadow mode result models | Already used throughout project |
| click | >=8.0 (installed) | CLI subcommands for recommend, shadow-run, shadow-report | Already used for extract and validate CLI |
| loguru | >=0.7 (installed) | Structured logging for retrieval and shadow mode | Already used throughout pipeline |
| numpy | >=1.24 (installed: 2.3.3) | Embedding array operations (used by sentence-transformers) | Already installed; dependency of sentence-transformers |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rank_bm25 | 0.2.2 (NOT installed) | Alternative BM25 implementation if DuckDB FTS proves insufficient | Only if DuckDB FTS lacks needed flexibility (e.g., custom tokenization); prefer DuckDB FTS first |
| json (stdlib) | N/A | Shadow mode result serialization, provenance tracking | All I/O operations |
| collections.Counter (stdlib) | N/A | Agreement rate computation, distribution analysis | Shadow mode metrics |
| uuid (stdlib) | N/A | Shadow run ID generation | Shadow mode result tracking |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB FTS (BM25) | rank_bm25 library | rank_bm25 requires loading all docs into memory and rebuilding index; DuckDB FTS is persistent, integrated with SQL queries, and handles tokenization/stemming natively |
| DuckDB VSS (embeddings) | numpy cosine similarity | numpy works fine for <500 episodes but requires loading all embeddings into memory; DuckDB VSS provides persistent HNSW index and SQL-integrated queries |
| DuckDB VSS | chromadb / faiss / lancedb | Massive overkill for 100-500 episodes; adds external dependency and data synchronization complexity; DuckDB VSS verified working with cosine similarity and HNSW |
| sentence-transformers | openai embeddings API | Adds API dependency, costs money, requires network; sentence-transformers runs locally on CPU in ~100ms per query |
| Hybrid (BM25 + embeddings) | Embeddings only | BM25 catches exact term matches (file paths, mode names, command names) that embeddings may miss; hybrid consistently outperforms single-strategy in RAG literature |

**Installation:**
```bash
pip install sentence-transformers>=3.0.0
# DuckDB FTS and VSS extensions auto-load on first use (verified DuckDB 1.4.4)
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/
    rag/                           # NEW: Phase 5 RAG module
        __init__.py
        embedder.py                # Episode embedding generator
        retriever.py               # Hybrid BM25 + embedding retriever
        recommender.py             # Action recommendation from retrieved episodes
    shadow/                        # NEW: Phase 5 shadow mode module
        __init__.py
        runner.py                  # Shadow mode test runner
        evaluator.py               # Agreement/danger evaluation
        reporter.py                # Metrics and reporting
src/pipeline/cli/
    extract.py                     # EXISTING
    validate.py                    # EXISTING
    train.py                       # NEW: CLI for recommend, shadow-run, shadow-report
src/pipeline/storage/
    schema.py                      # EXTEND: add episode_embeddings + shadow_mode_results tables
    writer.py                      # EXTEND: add write_embeddings + write_shadow_results
data/
    ope.db                         # EXISTING: add new tables
```

### Pattern 1: Hybrid Retriever (BM25 + Embedding Fusion)
**What:** Two retrieval strategies are run in parallel: DuckDB FTS (BM25) for lexical matching and DuckDB VSS (cosine similarity) for semantic matching. Results are fused using Reciprocal Rank Fusion (RRF).
**When to use:** For all episode retrieval queries.
**Example:**
```python
# Source: Verified via local DuckDB 1.4.4 testing
class HybridRetriever:
    """Retrieve similar episodes using BM25 + embedding hybrid search."""

    def __init__(self, conn: duckdb.DuckDBPyConnection, top_k: int = 5):
        self._conn = conn
        self._top_k = top_k

    def retrieve(
        self, query_text: str, query_embedding: list[float], exclude_episode_id: str | None = None
    ) -> list[dict]:
        """Retrieve top-k similar episodes using hybrid BM25 + cosine fusion."""
        # BM25 retrieval via DuckDB FTS
        bm25_results = self._bm25_search(query_text, exclude_episode_id)
        # Embedding retrieval via DuckDB VSS
        embedding_results = self._embedding_search(query_embedding, exclude_episode_id)
        # Reciprocal Rank Fusion
        return self._rrf_fuse(bm25_results, embedding_results, k=self._top_k)

    def _bm25_search(self, query: str, exclude_id: str | None) -> list[tuple[str, float]]:
        exclude_clause = f"AND e.episode_id != '{exclude_id}'" if exclude_id else ""
        rows = self._conn.execute(f"""
            SELECT e.episode_id, score
            FROM (
                SELECT *, fts_main_episode_search_text.match_bm25(
                    episode_id, ?
                ) AS score
                FROM episode_search_text
            ) sq
            JOIN episodes e ON e.episode_id = sq.episode_id
            WHERE score IS NOT NULL {exclude_clause}
            ORDER BY score DESC
            LIMIT ?
        """, [query, self._top_k * 2]).fetchall()
        return rows

    def _embedding_search(self, embedding: list[float], exclude_id: str | None) -> list[tuple[str, float]]:
        exclude_clause = f"AND episode_id != '{exclude_id}'" if exclude_id else ""
        rows = self._conn.execute(f"""
            SELECT episode_id, array_cosine_similarity(embedding, ?::FLOAT[384]) AS sim
            FROM episode_embeddings
            WHERE embedding IS NOT NULL {exclude_clause}
            ORDER BY sim DESC
            LIMIT ?
        """, [embedding, self._top_k * 2]).fetchall()
        return rows

    @staticmethod
    def _rrf_fuse(
        bm25_results: list[tuple[str, float]],
        emb_results: list[tuple[str, float]],
        k: int,
        rrf_k: int = 60,
    ) -> list[dict]:
        """Reciprocal Rank Fusion: score = sum(1/(rrf_k + rank))."""
        scores: dict[str, float] = {}
        for rank, (eid, _) in enumerate(bm25_results):
            scores[eid] = scores.get(eid, 0) + 1.0 / (rrf_k + rank)
        for rank, (eid, _) in enumerate(emb_results):
            scores[eid] = scores.get(eid, 0) + 1.0 / (rrf_k + rank)
        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:k]
        return [{"episode_id": eid, "rrf_score": scores[eid]} for eid in sorted_ids]
```

### Pattern 2: Observation Text Extraction for Search
**What:** Flatten the structured observation (repo_state, quality_state, context) into a searchable text string. This is the "query" for retrieval.
**When to use:** When constructing the search query from an episode's observation field.
**Example:**
```python
def observation_to_text(observation: dict) -> str:
    """Convert structured observation to searchable text."""
    parts = []
    # Context is the richest text field
    context = observation.get("context", {})
    if isinstance(context, dict):
        summary = context.get("recent_summary", "")
        if summary:
            parts.append(summary)
        questions = context.get("open_questions", [])
        if questions:
            parts.append(" ".join(questions))
        constraints = context.get("constraints_in_force", [])
        if constraints:
            parts.append("Constraints: " + ", ".join(constraints))
    # Repo state adds file context
    repo = observation.get("repo_state", {})
    if isinstance(repo, dict):
        files = repo.get("changed_files", [])
        if files:
            parts.append("Files: " + ", ".join(files[:10]))
    # Quality state adds test/lint context
    quality = observation.get("quality_state", {})
    if isinstance(quality, dict):
        tests = quality.get("tests_status", "")
        lint = quality.get("lint_status", "")
        if tests:
            parts.append(f"Tests: {tests}")
        if lint:
            parts.append(f"Lint: {lint}")
    return " | ".join(parts)
```

### Pattern 3: Shadow Mode Batch Runner (Leave-One-Out)
**What:** For each episode in the database, generate a recommendation using all OTHER episodes as the knowledge base (leave-one-out), then compare to the actual human decision. This is offline/batch shadow mode testing.
**When to use:** For TRAIN-02 shadow mode validation.
**Example:**
```python
class ShadowModeRunner:
    """Run shadow mode testing in batch over historical episodes."""

    def run_session(self, session_id: str) -> dict:
        """Run shadow mode for all episodes in a session."""
        episodes = self._fetch_session_episodes(session_id)
        results = []
        for episode in episodes:
            # Generate recommendation EXCLUDING this episode
            recommendation = self._recommender.recommend(
                observation=episode["observation"],
                exclude_episode_id=episode["episode_id"],
            )
            # Compare to actual human decision
            evaluation = self._evaluator.evaluate(
                human_decision=episode,
                recommendation=recommendation,
            )
            results.append(evaluation)
        return self._aggregate_results(results)
```

### Pattern 4: Explainable Provenance in Recommendations
**What:** Each recommendation cites the source episodes it was derived from, including episode IDs, similarity scores, and what action was taken in each source episode.
**When to use:** For TRAIN-01 explainable provenance requirement.
**Example:**
```python
@dataclass
class Recommendation:
    """RAG baseline recommendation with explainable provenance."""
    recommended_mode: str
    recommended_risk: str
    recommended_scope_paths: list[str]
    recommended_gates: list[str]
    confidence: float
    source_episodes: list[SourceEpisodeRef]
    reasoning: str  # Human-readable explanation

@dataclass
class SourceEpisodeRef:
    """Reference to a source episode used in the recommendation."""
    episode_id: str
    similarity_score: float
    mode: str
    reaction_label: str | None  # Was this episode approved/corrected?
    relevance: str  # Why this episode was retrieved
```

### Anti-Patterns to Avoid
- **Including the target episode in retrieval:** When running shadow mode, the current episode MUST be excluded from the retrieval pool. Otherwise you get 100% agreement (trivially retrieving itself). This is the "leave-one-out" pattern.
- **Treating all retrieved episodes equally:** Corrected/blocked episodes should INFORM the recommendation (as negative examples) but not be the primary action source. Approved episodes should weight more heavily.
- **Generating recommendations via LLM:** Phase 5 is RAG-only (retrieve + recommend from retrieved episodes). No LLM generation. The recommended action comes directly from the most similar approved episode, with constraints from corrected episodes overlaid.
- **Building custom embedding storage:** DuckDB 1.4.4 has native `FLOAT[384]` arrays, `array_cosine_similarity`, and HNSW indexes. Do not build custom numpy-based vector storage.
- **Shadow mode as real-time system:** For v1, shadow mode is a batch replay over historical data. Do not build real-time parallel execution infrastructure.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| BM25 text search | Custom TF-IDF scorer | DuckDB FTS extension (`PRAGMA create_fts_index`, `match_bm25`) | DuckDB FTS handles tokenization, stemming, stopwords, BM25 scoring natively; verified working in DuckDB 1.4.4 |
| Vector similarity search | numpy cosine similarity loops | DuckDB VSS (`array_cosine_similarity`, HNSW index) | DuckDB VSS provides persistent indexing and SQL-integrated queries; verified working with cosine metric |
| Text embedding generation | Custom word2vec / TF-IDF vectors | sentence-transformers `all-MiniLM-L6-v2` | Pre-trained on 1B+ sentence pairs; 384-dim embeddings; ~80MB model; runs on CPU in <100ms per query |
| Result fusion | Custom scoring formula | Reciprocal Rank Fusion (RRF) | RRF is parameter-free (only rrf_k=60 constant), robust, well-studied in IR literature; ~15 lines of code |
| Constraint violation detection | Custom pattern matching | Reuse existing ConstraintStore + config.yaml protected_paths | Phase 3 already built constraint checking; Phase 5 danger detection should reuse those interfaces |

**Key insight:** Phase 5's complexity is in the WORKFLOW (retrieval -> recommendation -> evaluation -> reporting), not in the underlying technology. DuckDB provides FTS + VSS natively, sentence-transformers provides embeddings, and the existing pipeline provides constraint checking. The implementation glue is straightforward Python.

## Common Pitfalls

### Pitfall 1: Self-Retrieval in Shadow Mode (Data Leakage)
**What goes wrong:** Shadow mode retrieves the current episode as the most similar result, producing 100% agreement that is meaningless.
**Why it happens:** Failing to exclude the target episode from the retrieval pool.
**How to avoid:** Always pass `exclude_episode_id` to the retriever. Every shadow mode evaluation MUST use leave-one-out protocol.
**Warning signs:** Shadow mode agreement rate is suspiciously high (>95%) or recommendation always exactly matches human decision.

### Pitfall 2: Embedding Dimension Mismatch
**What goes wrong:** DuckDB `FLOAT[384]` column rejects embeddings of wrong dimension, or cosine similarity returns wrong results.
**Why it happens:** Switching embedding models (different models produce different dimensions) or inconsistent embedding generation.
**How to avoid:** Define embedding dimension as a config constant. Validate embedding length before storage. Use a single model identifier stored alongside embeddings for provenance.
**Warning signs:** DuckDB INSERT errors mentioning array size mismatch; cosine similarity returning NaN or 0 for all pairs.

### Pitfall 3: FTS Index Not Auto-Updating
**What goes wrong:** New episodes added to DuckDB are not found by FTS search.
**Why it happens:** DuckDB FTS indexes do not auto-update when the source table changes. The index must be recreated.
**How to avoid:** Rebuild FTS index after batch episode ingestion (using `overwrite=1` parameter). Document this in the embedding/indexing pipeline. Consider a `rebuild_indexes()` function that runs after each pipeline batch.
**Warning signs:** FTS returns fewer results than expected; newly ingested episodes are invisible to search.

### Pitfall 4: Observation Text Too Short for Meaningful BM25
**What goes wrong:** BM25 returns poor results because observation text is sparse (e.g., only "Tests: pass | Lint: pass").
**Why it happens:** Not all episodes have rich `context.recent_summary` text. Some observations are structurally rich but textually sparse.
**How to avoid:** Enrich the search text with the `orchestrator_action.goal` and `orchestrator_action.executor_instruction` fields in addition to observation. These contain the most semantically meaningful text. Embedding-based retrieval compensates for BM25 weakness on sparse text.
**Warning signs:** BM25 scores are all near zero; only embedding search produces meaningful results.

### Pitfall 5: Agreement Rate Metric Definition Ambiguity
**What goes wrong:** Agreement rate metric is misleading because "agreement" on mode alone is not meaningful without scope and constraint agreement.
**Why it happens:** Defining agreement too narrowly (mode-only) or too strictly (exact match on all fields).
**How to avoid:** Define multiple agreement levels: (1) mode agreement, (2) risk agreement, (3) scope overlap (Jaccard similarity), (4) gate agreement. Report each separately. The 70% threshold from TRAIN-02 should apply to MODE agreement as the primary metric, with other metrics as supplementary.
**Warning signs:** High mode agreement but low scope agreement (recommender picks right mode but wrong files); or vice versa.

### Pitfall 6: Dangerous Recommendation Definition Too Narrow
**What goes wrong:** Zero dangerous recommendations reported, but only because "dangerous" was defined as exact constraint text match.
**Why it happens:** Constraints have `detection_hints` (patterns) and `scope.paths`, but recommendations contain mode/scope/risk -- different levels of abstraction.
**How to avoid:** Define "dangerous" as a multi-level check: (1) recommendation mode=Implement on forbidden scope paths, (2) recommendation risk=low but actual episode had risk=high/critical, (3) recommendation omits gates that were present in the actual episode (e.g., drops `require_human_approval`), (4) recommendation scope overlaps with constraint forbidden paths.
**Warning signs:** All recommendations pass danger check with zero violations; no correlation between danger flags and actual corrections/blocks.

## Code Examples

### DuckDB FTS Index for Episode Search (Verified)
```python
# Source: Verified via local DuckDB 1.4.4 testing (2026-02-11)
def create_search_text_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create a denormalized search text table and FTS index for episodes."""
    # Flatten episode observation + action into searchable text
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episode_search_text (
            episode_id VARCHAR PRIMARY KEY,
            search_text VARCHAR
        )
    """)

def rebuild_fts_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Rebuild FTS index on episode_search_text. Must be called after new data."""
    conn.execute("""
        PRAGMA create_fts_index(
            'episode_search_text',
            'episode_id',
            'search_text',
            stemmer = 'porter',
            stopwords = 'english',
            lower = 1,
            overwrite = 1
        )
    """)
```

### DuckDB VSS Embedding Storage (Verified)
```python
# Source: Verified via local DuckDB 1.4.4 testing (2026-02-11)
def create_embeddings_table(conn: duckdb.DuckDBPyConnection, dim: int = 384) -> None:
    """Create embeddings table with HNSW index for cosine similarity search."""
    conn.execute('LOAD vss;')
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS episode_embeddings (
            episode_id VARCHAR PRIMARY KEY,
            embedding FLOAT[{dim}],
            model_name VARCHAR DEFAULT 'all-MiniLM-L6-v2',
            created_at TIMESTAMPTZ DEFAULT current_timestamp
        )
    """)

def create_hnsw_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Create HNSW index for fast cosine similarity search."""
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_episode_emb_hnsw
        ON episode_embeddings USING HNSW (embedding)
        WITH (metric = 'cosine')
    """)
```

### Shadow Mode Results Table
```python
# Source: Shadow mode testing research + project DuckDB patterns
def create_shadow_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create shadow mode results table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_mode_results (
            shadow_run_id VARCHAR PRIMARY KEY,
            episode_id VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL,

            -- Human decision (actual)
            human_mode VARCHAR NOT NULL,
            human_risk VARCHAR NOT NULL,
            human_reaction_label VARCHAR,

            -- Shadow recommendation
            shadow_mode VARCHAR NOT NULL,
            shadow_risk VARCHAR NOT NULL,
            shadow_confidence FLOAT,

            -- Agreement metrics
            mode_agrees BOOLEAN NOT NULL,
            risk_agrees BOOLEAN NOT NULL,
            scope_overlap FLOAT,  -- Jaccard similarity of scope paths
            gate_agrees BOOLEAN,

            -- Safety checks
            is_dangerous BOOLEAN NOT NULL DEFAULT FALSE,
            danger_reasons JSON,  -- Array of danger category strings

            -- Provenance
            source_episode_ids JSON,  -- Array of retrieved episode IDs
            retrieval_scores JSON,  -- Array of similarity scores

            -- Metadata
            run_batch_id VARCHAR,  -- Groups results from same shadow run
            created_at TIMESTAMPTZ DEFAULT current_timestamp
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_shadow_session
        ON shadow_mode_results(session_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_shadow_batch
        ON shadow_mode_results(run_batch_id)
    """)
```

### Recommendation Action Selection from Retrieved Episodes
```python
# Source: Project design (AUTHORITATIVE_DESIGN.md Part 9.1)
def select_action_from_retrieved(
    retrieved_episodes: list[dict],
) -> dict:
    """Select recommended action from retrieved similar episodes.

    Strategy:
    1. Filter to approved episodes only (trusted signal)
    2. Weight by similarity score
    3. Use majority vote for mode, highest-weight for other fields
    4. Overlay constraints from corrected/blocked episodes
    """
    approved = [ep for ep in retrieved_episodes if ep.get("reaction_label") == "approve"]
    corrected = [ep for ep in retrieved_episodes if ep.get("reaction_label") in ("correct", "block")]

    if not approved:
        # Fall back to most similar regardless of reaction
        approved = retrieved_episodes[:1]

    # Mode: majority vote among approved, weighted by similarity
    mode_votes: dict[str, float] = {}
    for ep in approved:
        mode = ep.get("mode", "Explore")
        mode_votes[mode] = mode_votes.get(mode, 0) + ep.get("rrf_score", 1.0)
    recommended_mode = max(mode_votes, key=mode_votes.get) if mode_votes else "Explore"

    # Risk: maximum risk from approved episodes (conservative)
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    max_risk = max(
        (risk_order.get(ep.get("risk", "low"), 0) for ep in approved),
        default=0,
    )
    risk_labels = {v: k for k, v in risk_order.items()}
    recommended_risk = risk_labels.get(max_risk, "medium")

    # Constraints: union from corrected/blocked episodes (additive safety)
    extra_constraints = []
    for ep in corrected:
        constraints = ep.get("constraints_extracted", [])
        extra_constraints.extend(constraints)

    return {
        "mode": recommended_mode,
        "risk": recommended_risk,
        "extra_constraints": extra_constraints,
        "source_count": len(approved),
    }
```

### Danger Detection Using Existing Infrastructure
```python
# Source: Reuses existing ConstraintStore and config.yaml protected_paths
def check_dangerous(
    recommendation: dict,
    episode: dict,
    constraint_store: ConstraintStore,
    protected_paths: list[str],
) -> tuple[bool, list[str]]:
    """Check if a recommendation would be dangerous.

    Danger categories:
    1. scope_violation: Recommendation scope overlaps forbidden constraint paths
    2. risk_underestimate: Recommends lower risk than actual episode
    3. gate_dropped: Actual episode had gates that recommendation omits
    4. protected_path: Recommendation scope includes protected paths
    """
    dangers = []

    # 1. Check constraint scope violations
    rec_scope = set(recommendation.get("scope_paths", []))
    for constraint in constraint_store.constraints:
        if constraint.get("severity") == "forbidden":
            c_paths = set(constraint.get("scope", {}).get("paths", []))
            if rec_scope & c_paths:
                dangers.append("scope_violation")
                break

    # 2. Check risk underestimate
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    rec_risk = risk_order.get(recommendation.get("risk", "low"), 0)
    actual_risk = risk_order.get(episode.get("risk", "low"), 0)
    if rec_risk < actual_risk and actual_risk >= 2:  # high or critical
        dangers.append("risk_underestimate")

    # 3. Check gate dropping
    actual_gates = set(episode.get("gates", []))
    rec_gates = set(recommendation.get("gates", []))
    critical_gates = {"require_human_approval", "protected_paths"}
    dropped_critical = (actual_gates & critical_gates) - rec_gates
    if dropped_critical:
        dangers.append("gate_dropped")

    # 4. Check protected paths
    for rec_path in rec_scope:
        for pp in protected_paths:
            if rec_path.startswith(pp.rstrip("*").rstrip("/")):
                dangers.append("protected_path")
                break

    return (len(dangers) > 0, dangers)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| External vector DB (Chroma, Pinecone) for small datasets | DuckDB native VSS with HNSW indexes | DuckDB 0.10+ (2024), mature in 1.4.4 | Eliminates external dependency; all data in single DuckDB file |
| numpy cosine similarity over in-memory arrays | DuckDB `array_cosine_similarity` + HNSW | DuckDB 1.x (2024-2025) | Persistent indexed search integrated with SQL queries |
| Separate BM25 library (rank_bm25) + external index | DuckDB FTS extension with `match_bm25` | DuckDB FTS extension stable since 0.9 | Unified search across text and vector columns in same database |
| Real-time shadow mode deployment | Batch shadow mode over historical data | Standard ML practice | Appropriate for initial validation; simpler infrastructure |

**Deprecated/outdated:**
- Using Chroma/FAISS for <1000 documents: DuckDB VSS handles this natively now
- Building custom TF-IDF: DuckDB FTS provides BM25 (superior to TF-IDF) out of the box
- numpy-based vector similarity for persistent data: DuckDB VSS provides SQL-native alternative

## Open Questions

1. **Embedding Model Choice and Size**
   - What we know: `all-MiniLM-L6-v2` is the standard lightweight choice (384 dims, ~80MB, CPU-fast). Alternatives include `all-mpnet-base-v2` (768 dims, ~420MB, slightly better quality but 5x slower).
   - What's unclear: Is 384 dimensions sufficient for distinguishing orchestrator episode contexts? The observation text may be domain-specific enough that a lighter model works fine.
   - Recommendation: Start with `all-MiniLM-L6-v2`. Measure retrieval quality. Only switch to larger model if retrieval precision is below 60%.

2. **Agreement Threshold Interpretation (70%)**
   - What we know: TRAIN-02 requires >=70% agreement across >=50 sessions. But "agreement" is undefined in the requirement.
   - What's unclear: Does 70% mean mode agreement only? Mode + risk? Exact match on all fields? Per-session or aggregate?
   - Recommendation: Define "agreement" as mode agreement (primary metric). Report risk agreement, scope overlap, and gate agreement as supplementary. The 70% threshold applies to aggregate mode agreement across all shadow mode episodes, not per-session.

3. **Observation Text Construction Quality**
   - What we know: The observation field has structured sub-fields (repo_state, quality_state, context). The `context.recent_summary` is the richest text field but may be sparse or empty for some episodes.
   - What's unclear: How many episodes have meaningful `recent_summary` text? What's the distribution?
   - Recommendation: Build the observation text from ALL available fields (summary + questions + constraints + changed_files + goal + executor_instruction). This maximizes search signal even for sparse episodes. Run a quality check on observation text length distribution before embedding generation.

4. **Minimum Episode Count for Meaningful RAG**
   - What we know: The requirement says >=50 sessions for shadow mode, but the total episode count across those sessions matters more for retrieval quality.
   - What's unclear: How many total episodes exist after processing all historical sessions? If <50, RAG will have very few candidates per query.
   - Recommendation: Measure total episode count before building RAG. If <100 episodes, warn that retrieval quality will be limited. Consider enriching the dataset by processing additional project sessions.

5. **How to Handle Episodes Without Reactions**
   - What we know: Not all episodes have reaction labels (some human messages don't follow episode boundaries cleanly).
   - What's unclear: Should unreacted episodes be included in the retrieval pool? They lack the approve/correct signal needed for action selection.
   - Recommendation: Include unreacted episodes in retrieval for context matching, but do NOT use them for action recommendation. Only approved episodes should drive the recommended action. Unreacted episodes contribute to context similarity only.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/models/episodes.py` -- Episode Pydantic model (363 lines), defines observation/action/outcome structure that RAG must search over
- `src/pipeline/storage/schema.py` -- DuckDB episodes table schema (197 lines), hybrid flat + STRUCT + JSON columns
- `src/pipeline/storage/writer.py` -- DuckDB read/write patterns (745 lines), MERGE upsert for episodes
- `src/pipeline/constraint_store.py` -- Constraint read interface for danger detection (193 lines)
- `src/pipeline/validation/metrics.py` -- Quality metrics patterns (328 lines), reusable for shadow mode metrics
- `src/pipeline/validation/gold_standard.py` -- Gold-standard export/import patterns (298 lines), reusable for shadow mode reporting
- `src/pipeline/runner.py` -- Pipeline runner (688 lines), integration pattern for new modules
- `src/pipeline/cli/__main__.py` -- CLI entry point (27 lines), adding new subcommands
- `data/config.yaml` -- Configuration with protected_paths, risk_model, constraint_patterns
- `.planning/REQUIREMENTS.md` -- TRAIN-01, TRAIN-02 requirement definitions
- `.planning/ROADMAP.md` -- Phase 5 success criteria
- `docs/design/AUTHORITATIVE_DESIGN.md` -- Part 9: Training Pipeline (RAG baseline, shadow mode), Part 11: Success Criteria
- `docs/VISION.md` -- Month 3 RAG baseline concrete vision with UI mockups
- Local DuckDB 1.4.4 testing: Verified FTS (match_bm25), VSS (array_cosine_similarity, HNSW index with cosine metric) -- all working

### Secondary (MEDIUM confidence)
- Perplexity research: RAG retrieval best practices for small datasets (2026), hybrid BM25 + embedding search patterns
- Perplexity research: Shadow mode testing architecture for ML recommender systems
- Perplexity research: sentence-transformers `all-MiniLM-L6-v2` specifications (384 dims, ~80MB, Apache 2.0)
- Perplexity research: rank_bm25 0.2.2 API and usage patterns
- DuckDB official docs: FTS extension (`PRAGMA create_fts_index`, `match_bm25`)
- DuckDB official docs: VSS extension (`array_cosine_similarity`, HNSW indexes)

### Tertiary (LOW confidence)
- None -- all findings verified against local testing or official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - DuckDB FTS/VSS verified working locally; sentence-transformers is well-established; no exotic dependencies
- Architecture: HIGH - Hybrid retrieval is well-studied; shadow mode is standard ML validation; patterns derived from existing codebase
- Pitfalls: HIGH - Self-retrieval and FTS non-updating are verified gotchas from local testing; agreement metric ambiguity from requirement analysis
- Retrieval quality: MEDIUM - Depends on episode count and observation text quality (unknown until pipeline produces real data)
- Shadow mode metrics: HIGH - Standard agreement computation; threshold definition from requirements

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (stable domain; DuckDB extensions may evolve but current API is stable)
