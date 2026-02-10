# Stack Research

**Domain:** ML policy learning from agent orchestration logs (episode extraction, preference modeling, RL)
**Researched:** 2026-02-10
**Confidence:** MEDIUM-HIGH (versions verified via PyPI; ML training stack recommendations based on ecosystem consensus, not project-specific benchmarks)

---

## Recommended Stack

### Layer 1: Session Log Analysis & Event Extraction

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| **orjson** | 3.11.7 | JSONL parsing | 3-5x faster than stdlib json, 8.9x memory efficiency. Rust-based, drop-in replacement for `json.loads()`. Processes Claude Code JSONL sessions without memory exhaustion. | HIGH |
| **Pydantic** | >=2.10 | Schema validation for events and episodes | Rust-backed v2 core gives ~5x validation speedup over v1. `@field_validator` decorators, discriminated unions for polymorphic event types (O_DIR, X_PROPOSE, T_TEST). Generates JSON Schema for episode format. | HIGH |
| **PyYAML** | 6.0.x | Config loading (risk model, tags, keywords) | Standard YAML parser for `data/config.yaml`. Lightweight, no alternatives needed. | HIGH |
| **re** (stdlib) | stdlib | Event tagging (keyword/pattern classification) | Compiled regex patterns for rule-based event tagging. Zero dependency. Deterministic, auditable, fast (microseconds/event). Sufficient for O_DIR/X_PROPOSE/T_TEST classification rules. | HIGH |
| **Polars** | >=1.35 | Bulk JSONL/Parquet processing | 3-10x faster than Pandas for ETL. Lazy evaluation with predicate pushdown. Use for initial bulk session processing; not needed for streaming. | MEDIUM |

**Architecture pattern:** Line-by-line streaming with orjson parse -> Pydantic validate -> regex classify -> state-machine segment.

### Layer 2: Episode Database (DuckDB)

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| **DuckDB** | 1.4.4 | Primary analytical database | Already decided (Phase 0). v1.4.0+ adds MERGE (upsert), database encryption, improved CTEs. Native JSON columns, Parquet export, single-file deployment. OLAP-optimized for episode queries. | HIGH |
| **DuckDB Python** | 1.4.4 | Python bindings | `duckdb.connect("ope.db")` persistent storage. Relation API for lazy query composition. Direct JSONL/Parquet reads via `read_json()`, `read_parquet()`. | HIGH |

**Key DuckDB patterns for this project:**

```sql
-- Episode table with JSON columns (matches AUTHORITATIVE_DESIGN.md schema)
CREATE TABLE episodes (
    episode_id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    session_id VARCHAR NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    phase VARCHAR,
    task_id VARCHAR,
    observation JSON,           -- {repo_state, quality_state, context}
    orchestrator_action JSON,   -- {mode, goal, scope, gates, risk}
    outcome JSON,               -- {executor_effects, quality, reaction, reward_signals}
    constraints_extracted JSON,  -- [{constraint_id, text, severity, scope}]
    provenance JSON,
    schema_version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT current_timestamp,
    updated_at TIMESTAMPTZ DEFAULT current_timestamp
);

-- Incremental upsert via MERGE (DuckDB 1.4.0+)
MERGE INTO episodes AS target
USING staging_episodes AS source
ON target.episode_id = source.episode_id
WHEN MATCHED AND target.updated_at < source.updated_at
    THEN UPDATE SET
        outcome = source.outcome,
        constraints_extracted = source.constraints_extracted,
        updated_at = source.updated_at,
        schema_version = source.schema_version
WHEN NOT MATCHED
    THEN INSERT *;

-- Parquet export for ML training
COPY (
    SELECT episode_id,
           orchestrator_action->>'$.mode' AS mode,
           orchestrator_action->>'$.risk' AS risk,
           outcome->>'$.reaction.label' AS reaction,
           observation, orchestrator_action, outcome
    FROM episodes
    WHERE outcome->>'$.reaction.label' IS NOT NULL
)
TO 'data/processed/training_episodes.parquet'
(FORMAT parquet, COMPRESSION zstd);
```

**Connection management:** Always use explicit `duckdb.connect("ope.db")` with context managers. Never share connections across threads; use `.cursor()` for thread-local query execution.

### Layer 3: ML Policy Learning

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| **PyTorch** | >=2.9 | Neural network foundation | Industry standard for custom models. Required by SB3, d3rlpy, imitation. Use for preference model (Bradley-Terry), policy networks, embeddings. | HIGH |
| **scikit-learn** | >=1.7 | Baseline classifiers, preprocessing | Start here: logistic regression, random forest, gradient boosting as baselines for mode prediction (approve/correct classifier). StandardScaler, OrdinalEncoder for features. Establishes performance floor before neural approaches. | HIGH |
| **Stable Baselines3** | 2.7.x | RL algorithms (PPO, DQN) | Most mature, best-documented RL library for discrete action spaces. PPO for policy gradient, DQN for value-based. Gymnasium-compatible. Correct implementation of tricky details (gradient clipping, target networks, replay). | HIGH |
| **Gymnasium** | 1.2.x | RL environment interface | Standard env API. Wrap orchestration problem as Gymnasium env: obs=episode observation, action={Explore,Plan,Implement,Verify,Integrate,Triage,Refactor}, reward=preference model output. | HIGH |
| **d3rlpy** | 2.8.x | Offline RL (behavioral cloning, CQL) | Purpose-built for learning from fixed datasets (our episode archive). Conservative Q-Learning prevents overestimation on out-of-distribution actions. Critical because online interaction with real orchestration is expensive. | HIGH |
| **imitation** | 1.0.x | Imitation learning (BC, GAIL, DAgger) | Behavioral cloning from expert demonstrations (approved episodes). scikit-learn-style `.fit()` API. Integrates with SB3 policies for BC->RL fine-tuning pipeline. | MEDIUM |

**Training progression (phased):**

```
Phase 1: scikit-learn baselines
  - LogisticRegression/GradientBoosting on (observation_features, mode) pairs
  - Establishes: "Can we predict mode from observation at all?"
  - Target: >70% accuracy on mode prediction

Phase 2: Preference model (PyTorch custom)
  - Bradley-Terry model: P(approve | observation, action) = sigmoid(r_chosen - r_rejected)
  - Train on (observation, action, reaction_label) triples from episodes
  - Loss: binary_cross_entropy_with_logits for numerical stability
  - Architecture: categorical embeddings + 2-3 FC layers (64-128 units) + scalar head
  - Target: >80% accuracy predicting approve/correct/block

Phase 3: Behavioral cloning (d3rlpy or imitation)
  - Clone expert policy from high-confidence approved episodes
  - Input: observation features -> Output: action (mode) distribution
  - Provides warm-start initialization for RL
  - Target: >60% agreement with expert decisions

Phase 4: RL fine-tuning (SB3 PPO)
  - Initialize from BC policy
  - Reward = preference_model_score + objective_proxies (tests, lint, diff_risk)
  - PPO with discrete action space (softmax output)
  - Shadow mode: compare recommendations to actual human decisions
  - Target: >70% agreement in shadow mode
```

### Layer 4: Real-Time Integration (Mission Control)

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| **FastAPI** | >=0.125 | API server + WebSocket/SSE | Async-native, Pydantic integration, auto-generated OpenAPI docs. WebSocket support for bidirectional Mission Control communication. BackgroundTasks for event pipeline processing. | HIGH |
| **uvicorn** | >=0.38 | ASGI server | Standard production server for FastAPI. Supports WebSocket protocol upgrade. | HIGH |
| **Redis** (+ redis-py) | redis-py 7.1.x | Lightweight event bus (Pub/Sub) | Fire-and-forget pub/sub for real-time episode events. Bridges FastAPI <-> Mission Control dashboard. No Kafka overhead. Single-team scale. Also serves as session cache. | MEDIUM |
| **Streamlit** | >=1.50 | Dashboard UI (prototype/MVP) | Fastest path to working dashboard. Python-only. Real-time via session state + WebSocket backend. Good for episode browser, constraint viewer, statistics. | MEDIUM |

**Integration architecture:**

```
Claude Code Session (JSONL)
        |
        v
  FastAPI Ingest Endpoint
        |
        +---> DuckDB (persist episode)
        |
        +---> Redis Pub/Sub (real-time event)
        |           |
        |           +---> WebSocket -> Mission Control Dashboard
        |           |
        |           +---> Background worker (constraint extraction)
        |
        +---> BackgroundTasks (update aggregate stats)
```

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **jsonschema** | >=4.20 | JSON Schema validation | Validate episodes against `orchestrator-episode.schema.json` during extraction |
| **numpy** | >=1.26 | Numerical operations | Feature vectors, reward computation, array operations in ML pipeline |
| **pyarrow** | >=14.0 | Parquet I/O, Arrow interop | Required by Polars. DuckDB uses for Parquet export. Arrow columnar format bridge. |
| **pytest** | >=8.0 | Testing | Test episode extraction, validation, classification rules |
| **ruff** | >=0.5 | Linting/formatting | Fast Python linter. Replace flake8+black+isort with single tool |
| **click** | >=8.1 | CLI framework | CLI for `scripts/extract-episodes.py`, `scripts/train-model.py` |
| **tqdm** | >=4.66 | Progress bars | Episode extraction progress (processing 100s of sessions) |
| **loguru** | >=0.7 | Structured logging | Better than stdlib logging. Structured output for pipeline debugging |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Package/env management | Faster than pip. Lock files for reproducibility. `uv pip install`, `uv venv` |
| **pyproject.toml** | Project config | Single config for deps, build, ruff, pytest. No setup.py/setup.cfg needed |
| **DBeaver / DuckDB CLI** | Database inspection | Query episodes interactively. DuckDB CLI: `duckdb data/ope.db` |
| **Jupyter** | Exploration | Episode analysis, model evaluation, feature exploration. Export to scripts for production |

---

## Installation

```bash
# Create virtual environment
uv venv .venv
source .venv/bin/activate

# Core pipeline (Phase 1: Episode Extraction)
uv pip install \
    orjson>=3.11 \
    pydantic>=2.10 \
    pyyaml>=6.0 \
    duckdb>=1.4.4 \
    polars>=1.35 \
    jsonschema>=4.20 \
    click>=8.1 \
    tqdm>=4.66 \
    loguru>=0.7

# ML training (Phase 4: Policy Learning)
uv pip install \
    torch>=2.9 \
    scikit-learn>=1.7 \
    stable-baselines3>=2.7 \
    gymnasium>=1.2 \
    d3rlpy>=2.8 \
    imitation>=1.0 \
    numpy>=1.26

# Real-time integration (Phase 3: Mission Control)
uv pip install \
    fastapi>=0.125 \
    uvicorn>=0.38 \
    redis>=7.0 \
    streamlit>=1.50

# Dev dependencies
uv pip install \
    pytest>=8.0 \
    ruff>=0.5 \
    ipykernel>=6.29
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative | Why Not Default |
|-------------|-------------|-------------------------|-----------------|
| **orjson** | msgspec | When you need validation-during-parse (combined parse+validate). 40% faster than orjson for schema-aware parsing. | Worse error messages, no FastAPI integration, breaking API changes. Pydantic validation post-parse is clearer. |
| **orjson** | ujson | When orjson Rust compilation fails on exotic platforms. | 2-3x slower than orjson. No memory efficiency advantage. |
| **orjson** | stdlib json | When zero dependencies is paramount. | 3-5x slower, 8.9x worse memory. Unacceptable for multi-GB sessions. |
| **DuckDB** | SQLite | If Mission Control needs concurrent writes from multiple processes. | Slower for OLAP queries. No native JSON column type. No Parquet export. Already decided against in Phase 0. |
| **DuckDB** | PostgreSQL | If you need concurrent multi-user writes, full-text search, or LISTEN/NOTIFY for real-time. | Requires running a server. Overkill for single-user analytical workload. Adds ops burden. |
| **Polars** | Pandas | If team is more familiar with Pandas API. | 3-10x slower, eager evaluation causes memory issues on large sessions. |
| **SB3** | CleanRL | When you need to deeply customize algorithm internals (single-file implementations). Good for research. | Less convenient API. Must implement more yourself. Use for understanding, not production. |
| **SB3** | TorchRL | When you need advanced composability (TensorDict, multi-task, hierarchical policies). | Steeper learning curve. Overkill for 5-7 discrete actions. Reserve for Phase 4+ if SB3 hits limits. |
| **d3rlpy** | Decision Transformer | If sequence modeling of episodes works better than value-based offline RL. | Requires more data. More complex. Try d3rlpy CQL first, Decision Transformer only if CQL underperforms. |
| **scikit-learn** | XGBoost/LightGBM | When gradient boosting baselines need more power. | Extra dependency. scikit-learn's GradientBoostingClassifier/HistGradientBoosting is usually sufficient at this scale. |
| **FastAPI** | Flask | If team prefers synchronous simplicity. | No native async, no WebSocket support, no auto-validation. FastAPI is strictly better for this use case. |
| **Streamlit** | Gradio | If dashboard is primarily for ML model inference/streaming outputs. | Less flexible layout. Worse for multi-page dashboards. Better for model demos. |
| **Streamlit** | React custom | When dashboard needs highly customized UI, specific visual design, or >10 concurrent users. | 5-10x more development time. Overkill for MVP. Migrate to React only if Streamlit hits limits. |
| **Redis Pub/Sub** | Kafka | If event volume exceeds 10K/sec or you need event replay/persistence guarantees. | Massive ops overhead. Requires JVM. Absurd for single-team scale. |
| **Redis Pub/Sub** | In-memory asyncio Queue | For single-process, single-server prototype. | No persistence, no cross-process communication. Fine for Phase 1 prototype. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Pandas for ETL** | Eager evaluation loads entire dataset into memory. Session files can be multi-GB. 3-10x slower than Polars for transforms. | Polars (lazy eval, predicate pushdown) or DuckDB direct JSONL reads |
| **LLM-based event classification** | Non-deterministic, slow (100ms+ per event vs microseconds), expensive, not reproducible. Overkill when events have regular JSON structure with predictable fields. | Compiled regex patterns + Pydantic field-based rules |
| **SpaCy for event tagging** | 50-100ms startup overhead for model loading. NLP tokenization unnecessary when classifying structured JSON fields. | stdlib `re` module with compiled patterns. Reserve SpaCy only if linguistic analysis of free-text messages is needed later. |
| **Kafka/RabbitMQ** | Massive operational overhead (JVM, Zookeeper, cluster management). You have one user and <100 events/second. | Redis Pub/Sub or in-memory asyncio queues |
| **MongoDB** | Document store without analytical query optimization. No columnar storage, no Parquet export, no SQL. Adds operational burden of running a server. | DuckDB (analytical queries, JSON columns, Parquet export, zero-ops) |
| **Turn-level segmentation** | Wrong unit. Turns are UI artifacts; decision points are the causal unit. Training on turns conflates orchestrator and executor actions. | Decision-point episode segmentation (O_DIR/O_GATE triggers) |
| **Fine-tuning an LLM as the policy** | Our action space is 7 discrete modes, not token generation. LLM fine-tuning (RLHF/DPO for text) is the wrong paradigm. Wasteful, slow, and doesn't match the problem structure. | Classical RL (SB3 PPO/DQN) + Bradley-Terry preference model on structured features |
| **Distributed RL (Ray RLlib)** | Dataset is ~1000s of episodes, not millions. Single-GPU PyTorch is sufficient. Distributed training adds complexity without benefit at this scale. | SB3 single-process training. Revisit only if dataset grows 100x. |
| **JSONL as primary storage** | Full re-scan for every query. No indexing, no joins, no aggregations without loading everything. | DuckDB database with JSONL as archival backup |
| **Hot-reloading DuckDB schema** | DuckDB is single-writer. Schema changes during active writes cause locks. | Batch schema migrations during maintenance windows. Use `schema_version` column for gradual migration. |

---

## Stack Patterns by Project Phase

**Phase 0.5 (Schema & Config):**
- Pydantic models defining episode schema
- PyYAML for config loading
- jsonschema for validating against JSON Schema
- No ML, no web server needed

**Phase 1 (Episode Builder):**
- orjson + Pydantic + re (stdlib) for extraction pipeline
- DuckDB for episode storage
- Polars for bulk session processing
- click + tqdm + loguru for CLI tooling
- pytest for validation

**Phase 2 (Constraint Store & Validator):**
- Add: jsonschema validation layer
- DuckDB constraints table
- scikit-learn baselines for mode prediction

**Phase 3 (Mission Control Integration):**
- Add: FastAPI + uvicorn + Redis
- Streamlit for dashboard MVP
- WebSocket/SSE for real-time updates
- SQLite for Mission Control episode tables (if MC uses SQLite internally)

**Phase 4 (Training Infrastructure):**
- Add: PyTorch + SB3 + d3rlpy + imitation + Gymnasium
- Custom Bradley-Terry preference model
- Gymnasium env wrapping orchestration problem
- Shadow mode comparison framework

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| duckdb 1.4.4 | Python >=3.9 | Stable release. MERGE statement requires 1.4.0+. |
| orjson 3.11.x | Python >=3.8 | Requires bytes input (`orjson.loads(line)` not string). |
| pydantic 2.12.x | Python >=3.8 | v2 only. Do NOT use Pydantic v1 patterns (`@validator` is deprecated; use `@field_validator`). |
| stable-baselines3 2.7.x | torch >=2.0, gymnasium >=1.0 | Requires Gymnasium (not old Gym). Uses new Gymnasium API. |
| d3rlpy 2.8.x | torch >=2.0 | Check GPU compatibility with your PyTorch build. |
| imitation 1.0.x | stable-baselines3 >=2.0 | Depends on SB3 for policy classes. Version must be compatible. |
| fastapi 0.128.x | pydantic >=2.0, uvicorn >=0.20 | Uses Pydantic v2 for request/response validation. |
| polars 1.38.x | Python >=3.9 | Rust-based. No Pandas dependency (standalone). |
| redis-py 7.1.x | Redis server >=6.0 | Async support via `redis.asyncio`. |

---

## Integration Points Between Stack Components

```
                    +-----------------+
                    |  Claude Code    |
                    |  JSONL Sessions |
                    +--------+--------+
                             |
                    [orjson parse]
                             |
                    [Pydantic validate]
                             |
                    [regex classify: O_DIR, X_PROPOSE, T_TEST]
                             |
                    [state-machine segment into episodes]
                             |
              +--------------+--------------+
              |                             |
     +--------v--------+          +--------v--------+
     |     DuckDB      |          |   Redis Pub/Sub |
     |  episodes table |          | (real-time push) |
     +--------+--------+          +--------+--------+
              |                             |
              |                    +--------v--------+
              |                    |    FastAPI       |
              |                    |   WebSocket/SSE  |
              |                    +--------+--------+
              |                             |
              |                    +--------v--------+
              |                    |   Streamlit /    |
              |                    | Mission Control  |
              |                    +-----------------+
              |
     +--------v--------+
     |  Parquet Export  |
     | (training data)  |
     +--------+--------+
              |
     +--------v--------+
     | scikit-learn     |    Phase 1-2: Baselines
     | (baselines)      |
     +--------+--------+
              |
     +--------v--------+
     | PyTorch          |    Phase 2: Preference model
     | (Bradley-Terry)  |
     +--------+--------+
              |
     +--------v--------+
     | d3rlpy / SB3     |    Phase 3-4: RL policy
     | (PPO / CQL)      |
     +-----------------+
```

**Data format at each boundary:**
- JSONL -> orjson -> `dict` (raw Python)
- `dict` -> Pydantic -> validated `BaseModel` instances
- Pydantic models -> DuckDB JSON columns (via `model_dump_json()`)
- DuckDB -> Parquet (via `COPY ... TO ... FORMAT parquet`)
- Parquet -> PyTorch `Dataset` (via custom loader or Polars)
- PyTorch tensors -> SB3/d3rlpy algorithms

---

## Sources

- DuckDB official docs (duckdb.org/docs/stable/) -- JSON handling, MERGE statement, Python API, Parquet export, thread safety [HIGH confidence]
- DuckDB v1.4.0 release announcement (duckdb.org/2025/09/16/announcing-duckdb-140.html) -- MERGE statement, encryption [HIGH]
- PyPI package index -- all version numbers verified via `pip index versions` on 2026-02-10 [HIGH]
- Pydantic v2 migration guide (pydantic.com.cn/en/migration/) -- `@field_validator` patterns [HIGH]
- orjson benchmarks (msgspec docs, community benchmarks) -- 3-5x performance vs stdlib [MEDIUM-HIGH]
- Stable Baselines3 paper (Raffin et al.) -- algorithm implementations, discrete action support [HIGH]
- d3rlpy documentation (d3rlpy.readthedocs.io) -- offline RL, DiscreteCQL [HIGH]
- imitation library (github.com/HumanCompatibleAI/imitation) -- behavioral cloning, GAIL [MEDIUM]
- FastAPI WebSocket patterns (oneuptime.com/blog/2026-02-02-fastapi-websockets/) -- ConnectionManager, Redis integration [MEDIUM]
- RLHF Reward Modeling (github.com/RLHFlow/RLHF-Reward-Modeling) -- Bradley-Terry implementation patterns [MEDIUM]
- PPO implementation study (arxiv.org/html/2503.22575v2) -- cross-framework implementation discrepancies [MEDIUM]
- Gymnasium API (gymnasium.farama.org) -- environment interface standard [HIGH]
- Redis Pub/Sub patterns (oneuptime.com/blog/2026-01-26-redis-pubsub-implementation/) -- fire-and-forget model [MEDIUM]

---
*Stack research for: ML policy learning from agent orchestration logs*
*Researched: 2026-02-10*
