# Architecture Research

**Domain:** Episode extraction & policy learning for orchestrator training
**Researched:** 2026-02-10
**Confidence:** HIGH (grounded in project design docs + verified domain patterns)

## Standard Architecture

### System Overview

```
                        EPISODE EXTRACTION & POLICY LEARNING SYSTEM
 ============================================================================

 DATA SOURCES                    EPISODE BUILDER PIPELINE              STORAGE
 ============================================================================

 ┌──────────────┐
 │ Claude Code  │─┐
 │ Session JSONL│  │   ┌─────────┐  ┌─────────┐  ┌───────────┐
 └──────────────┘  │   │ Stage A │  │ Stage B │  │ Stage C   │
 ┌──────────────┐  ├──>│Normalize│─>│  Tag    │─>│ Segment   │──┐
 │ Git History  │──┤   │ Events  │  │ Events  │  │ Episodes  │  │
 └──────────────┘  │   └─────────┘  └─────────┘  └───────────┘  │
 ┌──────────────┐  │                                              │
 │ Terminal Logs│──┘   ┌─────────┐  ┌─────────┐  ┌───────────┐  │
 └──────────────┘      │ Stage D │  │ Stage E │  │ Stage F   │  │
                    ┌──>│Populate │─>│Reaction │─>│Constraint │──┤
                    │   │ Fields  │  │ Label   │  │ Extract   │  │
                    │   └─────────┘  └─────────┘  └───────────┘  │
                    │                                              │
                    └──────────────────────────────────────────────┘
                                                                   │
 ============================================================================
                                                                   v
 STORAGE LAYER           TRAINING PIPELINE           OPERATIONAL LAYER
 ============================================================================

 ┌─────────────┐    ┌────────────────────────┐    ┌──────────────────┐
 │  DuckDB     │    │ RAG Baseline           │    │ Mission Control  │
 │  ope.db     │───>│ Orchestrator           │    │ (Real-time       │
 │ ┌─────────┐ │    │ (episode retrieval     │    │  Episode Capture │
 │ │episodes │ │    │  + recommendation)     │    │  + Governance)   │
 │ ├─────────┤ │    ├────────────────────────┤    │                  │
 │ │sessions │ │    │ Preference Model       │    │ Task → Plan →    │
 │ ├─────────┤ │    │ (predict human         │    │ Execute → Review │
 │ │commits  │ │    │  approval/correction)  │    │ → Episode Stored │
 │ ├─────────┤ │    ├────────────────────────┤    └──────────────────┘
 │ │constr.  │ │    │ Learned Policy         │
 │ ├─────────┤ │    │ pi(A|O) via SL + RL   │
 │ │correlat.│ │    │ (graduated autonomy)   │
 │ └─────────┘ │    └────────────────────────┘
 └─────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Source Adapters** | Transform heterogeneous logs (JSONL, git, terminal) into canonical events | Python adapter per source type, each outputting CanonicalEvent dataclass |
| **Event Normalizer (Stage A)** | Merge all sources into single time-ordered event stream with canonical schema | Batch merge + sort by timestamp; UTC normalization; clock skew detection |
| **Event Tagger (Stage B)** | Classify events with semantic tags (O_DIR, X_PROPOSE, T_TEST, etc.) | Rule-based multi-pass tagger: tool tagger, assistant message tagger, human message tagger |
| **Episode Segmenter (Stage C)** | Cut event stream into decision-point episodes at trigger boundaries | Trigger-based state machine (not sliding window); triggers on O_DIR, X_PROPOSE, T_TEST, T_GIT_COMMIT, T_RISKY |
| **Field Populator (Stage D)** | Derive episode fields (observation, action, outcome) from events within segment | Rule-based extraction: mode inference from keywords, risk from diff heuristics, scope from file paths |
| **Reaction Labeler (Stage E)** | Classify human reaction to each episode (approve/correct/redirect/block/question) | Keyword matching with confidence scores; next human message after episode boundary |
| **Constraint Extractor (Stage F)** | Convert corrections/blocks into durable constraint rules | Pattern extraction ("don't X" -> forbidden, "use Y not X" -> requires_approval); scope + detection hints |
| **DuckDB Storage** | Primary analytical store for episodes, sessions, commits, constraints, correlations | Hybrid schema: flat columns for queryable fields + STRUCT/JSON for nested objects; incremental INSERT |
| **RAG Baseline Orchestrator** | Retrieve similar past episodes and recommend next orchestrator action | Embedding index over observations; BM25/FAISS retrieval; top-k ranking by frequency + success rate |
| **Preference Model** | Predict human approval probability given observation + proposed action | Small feedforward network (50-80K params); Bradley-Terry pairwise loss; offline batch training |
| **Learned Policy** | Choose orchestrator actions (mode/scope/gates/constraints) from observation | Supervised learning on approved episodes; RL fine-tuning with preference model rewards |
| **Mission Control** | Real-time episode capture via structured task/planning/review workflow | Next.js dashboard over SQLite; WebSocket connection to OpenClaw Gateway; episode tables |
| **Validator** | Ensure decisions are classified correctly, evidence-grounded, constraint-consistent | Genus-based multi-layer checks: schema validity, evidence grounding, non-contradiction, constraint enforcement |

## Recommended Project Structure

```
src/
├── pipeline/              # Episode Builder Pipeline (core)
│   ├── adapters/          # Source-specific parsers
│   │   ├── claude_jsonl.py    # Claude Code session JSONL adapter
│   │   ├── git_history.py     # Git commit/diff adapter
│   │   └── terminal_log.py    # Terminal transcript adapter
│   ├── normalizer.py      # Stage A: merge → canonical events
│   ├── tagger.py          # Stage B: event classification tags
│   ├── segmenter.py       # Stage C: decision-point episode boundaries
│   ├── populator.py       # Stage D: field derivation (observation, action, outcome)
│   ├── reaction.py        # Stage E: reaction label classification
│   ├── constraints.py     # Stage F: constraint extraction from corrections
│   ├── rewards.py         # Stage G: objective reward proxy calculation
│   └── runner.py          # Pipeline orchestration (session → episodes)
├── storage/               # DuckDB storage layer
│   ├── schema.py          # Table definitions (episodes, sessions, commits, constraints)
│   ├── loader.py          # JSONL → DuckDB incremental loading
│   ├── queries.py         # Analytical query library
│   └── export.py          # DuckDB → Parquet / JSONL export
├── training/              # ML training pipeline
│   ├── features.py        # Observation/action → model input encoding
│   ├── preference.py      # Preference model (Bradley-Terry + classifier)
│   ├── rag_policy.py      # RAG baseline orchestrator (retrieval + recommend)
│   ├── learned_policy.py  # Supervised + RL policy learning
│   └── evaluation.py      # Metrics: pairwise accuracy, per-class F1, shadow mode agreement
├── validator/             # Genus-based validation
│   ├── schema_check.py    # JSON schema validation
│   ├── evidence_check.py  # Evidence grounding (observation precedes action)
│   ├── consistency.py     # Non-contradiction (mode vs gates)
│   └── constraint_enforce.py  # Constraint violation detection
├── models/                # Canonical data models
│   ├── events.py          # CanonicalEvent dataclass
│   ├── episodes.py        # OrchestratorEpisode dataclass
│   ├── constraints.py     # Constraint dataclass
│   └── config.py          # Configuration loading (risk model, tags, keywords)
└── cli/                   # Command-line interface
    ├── build_episodes.py  # Process sessions → episodes
    ├── query_episodes.py  # Ad-hoc DuckDB queries
    ├── recommend.py       # RAG orchestrator recommendation
    └── validate.py        # Run validator on episode dataset
```

### Structure Rationale

- **pipeline/:** Separates each pipeline stage into its own module. Stages are composable and independently testable. The runner composes them in sequence. This matches the A-F stage design from the authoritative specification.
- **storage/:** Isolates DuckDB concerns from pipeline logic. Schema changes propagate through one module. Export formats (Parquet, JSONL) are secondary outputs.
- **training/:** Keeps ML code separate from data engineering. Feature encoding is shared between preference model and learned policy. Evaluation runs offline.
- **validator/:** Each validation layer (schema, evidence, consistency, constraints) is independent. Can be run at episode creation time or as batch validation.
- **models/:** Shared data models used across all modules. Frozen dataclasses enforce immutability during pipeline processing.

## Architectural Patterns

### Pattern 1: Batch Pipeline with Trigger-Based Segmentation

**What:** Process sessions as complete units in batch mode. Within each session, segment the event stream into episodes using trigger-based state machine (not sliding window, not fixed intervals).

**When to use:** Post-hoc processing of historical sessions. Scale is hundreds to low thousands of sessions.

**Trade-offs:**
- (+) Fully reproducible: same input always produces same episodes
- (+) Auditable: can trace any episode field back to source events via provenance
- (+) Simple debugging: process one session at a time, inspect intermediate outputs
- (-) Not real-time: episodes available only after session completes
- (-) Requires complete session data (no partial processing)

**Why trigger-based over sliding window:**
Sliding windows (5-minute, 10-minute) split atomic decisions arbitrarily. A single decision-point might take 30 seconds or 20 minutes. Triggers respect the actual decision structure: a directive starts an episode, a proposal/test-result/commit/risk-boundary ends it. This is deterministic and semantically grounded.

**Example:**
```python
class EpisodeSegmenter:
    """Trigger-based state machine for episode boundary detection."""

    START_TRIGGERS = {"O_DIR", "O_GATE"}
    END_TRIGGERS = {"X_PROPOSE", "X_ASK", "T_TEST_COMPLETE",
                    "T_LINT_COMPLETE", "T_BUILD_COMPLETE",
                    "T_RISKY", "T_GIT_COMMIT", "TIMEOUT_30M"}

    def segment(self, tagged_events: list[TaggedEvent]) -> list[EpisodeSegment]:
        episodes = []
        current = None

        for event in tagged_events:
            if event.tags & self.START_TRIGGERS:
                if current:
                    current.close(event.timestamp)
                    episodes.append(current)
                current = EpisodeSegment(start=event)

            if current:
                current.add_event(event)

            if current and (event.tags & self.END_TRIGGERS):
                current.close(event.timestamp)
                episodes.append(current)
                current = None

        return episodes
```

### Pattern 2: Hybrid DuckDB Schema (Flat Columns + Nested STRUCT)

**What:** Store frequently-queried episode fields as flat columns (project_id, timestamp, mode, reaction_label, risk) and complex nested objects as STRUCT or JSON columns (observation, action, outcome).

**When to use:** Analytical workloads where most queries filter/aggregate on a few fields, but full episode data must remain accessible.

**Trade-offs:**
- (+) Fast analytical queries on flat columns (DuckDB columnar scan)
- (+) No JSON parsing overhead for common filters (mode, reaction, project)
- (+) Full episode data preserved in nested fields
- (+) Easy export to Parquet with schema preservation
- (-) Schema migrations require ALTER TABLE for flat columns
- (-) Nested STRUCT queries are slower than flat column queries

**Example:**
```sql
CREATE TABLE episodes (
    -- Flat columns for fast filtering
    episode_id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    session_id VARCHAR NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    mode VARCHAR NOT NULL,          -- Explore/Plan/Implement/Verify/Integrate/Triage/Refactor
    reaction_label VARCHAR,         -- approve/correct/redirect/block/question/unknown
    risk VARCHAR NOT NULL,          -- low/medium/high/critical
    goal VARCHAR,

    -- Nested structures for full data
    observation STRUCT(
        repo_state STRUCT(
            changed_files VARCHAR[],
            diff_stat STRUCT(files INT, insertions INT, deletions INT),
            hotspots VARCHAR[]
        ),
        quality_state STRUCT(
            tests_status VARCHAR,
            lint_status VARCHAR,
            build_status VARCHAR
        ),
        context STRUCT(
            recent_summary VARCHAR,
            open_questions VARCHAR[],
            constraints_in_force VARCHAR[]
        )
    ),
    orchestrator_action JSON,       -- Full action object
    outcome JSON,                   -- Full outcome object
    constraints_extracted JSON,     -- Array of extracted constraints
    provenance JSON,                -- Source references

    -- Operational metadata
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Companion table for constraint store
CREATE TABLE constraints (
    constraint_id VARCHAR PRIMARY KEY,
    text VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,      -- warning/requires_approval/forbidden
    scope_paths VARCHAR[],
    detection_hints VARCHAR[],
    source_episode_id VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    active BOOLEAN DEFAULT true
);
```

### Pattern 3: Three-Layer Episode Architecture (Orchestrator / Executor / Deliverable)

**What:** Maintain strict separation between three episode types that serve different learning objectives. Never train the orchestrator policy on executor-level data.

**When to use:** Always. This is the core architectural invariant of the system.

**Trade-offs:**
- (+) Prevents the fundamental category error of training orchestrator on tool calls
- (+) Each layer has a clear consumer (OpenClaw, Claude, validation)
- (+) Layers can evolve independently
- (-) More complex extraction pipeline (must classify which layer an event belongs to)
- (-) Cross-layer correlation requires explicit linking

**Layer definitions:**

| Layer | Unit | Learning Target | Consumer | Storage |
|-------|------|-----------------|----------|---------|
| **Orchestrator** | Decision point | Mode/scope/gates/constraints policy | OpenClaw | Primary: `episodes` table |
| **Executor** | Tool-call sequence | Tool selection, implementation patterns | Claude Code | Secondary: `executor_traces` table (future) |
| **Deliverable** | Commit/PR | Outcome validation, milestone tracking | Humans + CI | Tertiary: `commits` + `correlations` tables |

### Pattern 4: Source Adapter + Canonical Event (Normalization)

**What:** Each data source (Claude JSONL, git history, terminal logs) has a dedicated adapter that transforms its format into a canonical event schema. The rest of the pipeline only sees canonical events.

**When to use:** Whenever ingesting heterogeneous log formats. This pattern decouples format changes from pipeline logic.

**Trade-offs:**
- (+) Adding new sources requires only a new adapter, no pipeline changes
- (+) Source-specific quirks (timestamp formats, encoding) handled at boundary
- (+) Canonical events are testable and debuggable
- (-) Lossy: some source-specific detail may not fit canonical schema
- (-) Requires maintaining adapter per source

**Canonical event schema:**
```python
@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str           # UUID or deterministic hash
    ts_utc: datetime        # Normalized to UTC
    session_id: str         # Session this event belongs to
    actor: str              # "human_orchestrator" | "executor" | "tool"
    event_type: str         # "user_msg" | "assistant_msg" | "tool_call" | "tool_result" | "git_event"
    payload: dict           # Source-specific details preserved as-is
    tags: frozenset[str]    # Semantic tags added by tagger (O_DIR, X_PROPOSE, T_TEST, etc.)
    links: dict             # Cross-references (parent message IDs, tool call IDs)
```

## Data Flow

### Episode Extraction Flow (Batch)

```
[Session JSONL Files]
        │
        v
[Source Adapters]──────────────────────────────────────────────┐
  │ claude_jsonl.py: Parse messages, tool_calls, tool_results  │
  │ git_history.py: Parse commits, diffs, branches             │
  │ terminal_log.py: Parse commands, outputs, exit codes       │
        │                                                       │
        v                                                       │
[Stage A: Normalizer]                                          │
  │ Merge all sources into single event stream                  │
  │ Sort by timestamp (UTC-normalized)                          │
  │ Detect clock skew between git and session timestamps        │
  │ Output: List[CanonicalEvent]                                │
        │                                                       │
        v                                                       │
[Stage B: Tagger]                                              │
  │ Pass 1 — Tool tagger: T_TEST, T_LINT, T_BUILD, T_RISKY    │
  │ Pass 2 — Executor tagger: X_PROPOSE, X_ASK, X_PATCH       │
  │ Pass 3 — Orchestrator tagger: O_DIR, O_GATE, O_CORR       │
  │ Output: List[TaggedEvent] (events with tag sets)            │
        │                                                       │
        v                                                       │
[Stage C: Segmenter]                                           │
  │ Start on: O_DIR or O_GATE                                   │
  │ End on: X_PROPOSE, X_ASK, T_TEST_COMPLETE, T_GIT_COMMIT,  │
  │         T_RISKY, 30min timeout                              │
  │ Output: List[EpisodeSegment] (event groups with boundaries) │
        │                                                       │
        v                                                       │
[Stage D: Populator]                                           │
  │ observation.repo_state ← files touched in prior events      │
  │ observation.quality_state ← last T_TEST/T_LINT results      │
  │ observation.context ← recent summary + constraints in force │
  │ orchestrator_action.mode ← keyword inference from O_DIR     │
  │ orchestrator_action.risk ← diff size + protected paths      │
  │ outcome.executor_effects ← tool calls within segment        │
  │ outcome.quality ← test/lint/build status at episode end     │
  │ Output: List[Episode] (partially populated)                 │
        │                                                       │
        v                                                       │
[Stage E: Reaction Labeler]                                    │
  │ Look at next human message after episode boundary            │
  │ Classify: approve/correct/redirect/block/question            │
  │ Assign confidence (high for explicit keywords, low for inferred) │
  │ Output: List[Episode] (with reaction labels)                │
        │                                                       │
        v                                                       │
[Stage F: Constraint Extractor]                                │
  │ Triggered when reaction in {correct, block}                  │
  │ Extract: text, severity, scope.paths, detection_hints        │
  │ Output: List[Episode] (with constraints_extracted) +         │
  │         Constraint Store updates                             │
        │                                                       │
        v                                                       │
[DuckDB Loader]                                                │
  │ INSERT episodes into DuckDB (incremental)                   │
  │ UPSERT constraints into constraint store                    │
  │ Link episodes to commits via temporal + file overlap         │
  │ Output: Updated ope.db                                      │
        │                                                       │
        v                                                       │
[Export / Analysis]                                             │
  │ Parquet export for ML training                              │
  │ JSONL export for human inspection                           │
  │ Analytical queries (episodes by mode, by reaction, etc.)    │
  └─────────────────────────────────────────────────────────────┘
```

### Real-Time Capture Flow (Mission Control, future)

```
[Human creates task in Mission Control]
        │
        v
[Planning Q&A outputs structured orchestrator_action]
  │ mode, goal, scope, constraints, gates, risk, executor_instruction
        │
        v
[Agent executes via OpenClaw Gateway]
  │ Tool calls streamed back via WebSocket
  │ Files touched, commands run, test results recorded
        │
        v
[Human reviews in Mission Control]
  │ Reaction: approve / correct / redirect / block / question
  │ If correct/block: extract constraint (text, severity, scope)
        │
        v
[Episode auto-generated from task lifecycle]
  │ task_id = join key (no probabilistic correlation needed)
  │ Episode stored directly in SQLite/DuckDB
  │ Constraint added to store
        │
        v
[Training pipeline picks up new episodes]
```

### Training Pipeline Flow

```
[Episode Dataset in DuckDB]
        │
        ├──────────────────────────────────┐
        v                                   v
[Feature Engineering]              [Constraint Store]
  │ Observation → embedding            │ Growing rule set
  │ Action → embedding                 │ Enforced at runtime
  │ (categorical + numeric features)   │ Updated from corrections
        │                                   │
        ├──────────────────────────────────┘
        v
[RAG Baseline Orchestrator]──────────> [Shadow Mode]
  │ Index episodes by observation           │ Compare recommendations
  │ Retrieve top-k similar                  │ to human decisions
  │ Rank by frequency + reaction            │ Measure agreement rate
  │ Return recommendation + provenance      v
        │                            [Agreement > 70%?]
        v                                  │ yes
[Preference Model Training]                v
  │ Input: (observation, action) pairs  [Learned Policy Training]
  │ Output: P(approve | obs, action)      │ Supervised: imitate approved episodes
  │ Bradley-Terry pairwise loss           │ RL: optimize objective + preference
  │ 50-80K param feedforward net          │ Constrained by validator + harness
  │ Offline batch, retrain on new data    │
        │                                  v
        v                            [Graduated Autonomy]
[Reward Signal for RL]                  │ Low risk: full autonomy
  │ Objective proxies: tests/lint/risk  │ Medium: preference approval
  │ Preference prediction: P(approve)   │ High: human approval required
  │ Combined reward = weighted sum      │ Critical: always human
```

### Key Data Flows

1. **Session → Episodes (batch extraction):** JSONL files are processed through the 6-stage pipeline (A-F), producing structured episode records and constraint store updates. Each episode links back to source events via provenance pointers.

2. **Task → Episode (real-time capture via Mission Control):** Structured tasks with orchestrator action schema flow through planning, execution, and review phases. The task lifecycle directly produces episode records with deterministic join keys (task_id).

3. **Episodes → Training data (ML pipeline):** Episodes are exported from DuckDB to Parquet, with feature engineering converting structured fields to model inputs. Preference model trains on (observation, action, reaction) tuples. RAG orchestrator indexes episodes for retrieval.

4. **Constraints → Enforcement (governance loop):** Corrections and blocks extract durable rules that flow into the constraint store. The validator checks new episodes against active constraints. Mission Control enforces constraints at task planning time.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| **1-5 projects, <1000 episodes** | Single Python process, DuckDB on local disk. No indexing needed. Process sessions sequentially. JSONL intermediate for debugging. |
| **5-20 projects, 1000-10000 episodes** | DuckDB handles this efficiently with columnar storage. Add Parquet exports for ML training. Consider multiprocessing for session-level parallelism. Constraint store fits in memory. |
| **20+ projects, 10000+ episodes** | DuckDB still sufficient (designed for GB-range analytics). Preference model retraining becomes slower (batch overnight). Consider separate embedding index (FAISS/ChromaDB) for RAG retrieval. Mission Control becomes primary data source (less batch processing). |

### Scaling Priorities

1. **First bottleneck: Episode quality, not volume.** At 500-1000 episodes, mode inference accuracy and reaction label quality matter more than processing speed. Invest in validation and manual spot-checks before scaling data collection.

2. **Second bottleneck: Preference model data requirements.** The preference model needs 500+ labeled episodes with balanced class distribution (not all "approve"). Actively seek correction/block examples. Class reweighting addresses imbalance.

3. **Third bottleneck: RAG retrieval relevance.** Simple BM25 works initially. Upgrade to vector embeddings (sentence-transformers) when keyword matching fails to retrieve semantically similar episodes.

## Anti-Patterns

### Anti-Pattern 1: Training Orchestrator on Executor Actions

**What people do:** Use Claude's tool calls (Read/Edit/Bash sequences) as the "action" in training episodes, treating the orchestrator as if it were learning to make tool calls.

**Why it's wrong:** This trains OpenClaw to "act like Claude" (tool micro-steps) instead of "act like the human" (strategic sequencing, risk assessment, constraint enforcement). The resulting policy would micro-manage tool selection rather than making high-level mode/scope/gate decisions.

**Do this instead:** The action space for orchestrator episodes is {mode, goal, scope, constraints, gates, risk, executor_instruction}. Tool calls belong in executor episodes (a separate, subordinate layer). The authoritative design spec (Part 2.1) is explicit about this distinction.

### Anti-Pattern 2: Sliding Window Segmentation

**What people do:** Cut the event stream into fixed-length time windows (5 minutes, 10 events, etc.) and treat each window as an episode.

**Why it's wrong:** A meaningful decision point might span 30 seconds or 20 minutes. Fixed windows split atomic decisions in half or merge unrelated decisions. The resulting episodes have inconsistent semantics and weak training signal.

**Do this instead:** Use trigger-based segmentation. Episodes start on orchestrator directives (O_DIR/O_GATE) and end on decision boundaries (proposals, test results, commits, risk events). This produces episodes that correspond to actual choice points where the orchestrator must decide what to do next.

### Anti-Pattern 3: Storing All Episodes as Flat JSON Blobs

**What people do:** Store complete episode JSON as a single TEXT column in the database, then use JSON_EXTRACT for every query.

**Why it's wrong:** Every analytical query (count by mode, filter by reaction, aggregate by project) requires parsing the full JSON blob. This is 10-100x slower than columnar access for the fields you query most often.

**Do this instead:** Hybrid schema: flat columns for frequently-queried fields (episode_id, project_id, timestamp, mode, reaction_label, risk) and STRUCT/JSON columns for complex nested data (observation, outcome, provenance). DuckDB's columnar engine scans only the columns needed per query.

### Anti-Pattern 4: Building Mission Control Integration Before Proving Batch Pipeline

**What people do:** Jump to real-time capture (Mission Control integration) before validating that the episode schema and extraction logic produce high-quality episodes from historical data.

**Why it's wrong:** Real-time capture adds complexity (WebSocket connections, UI, state management) while the fundamental question "can we extract meaningful decision-point episodes?" remains unanswered. If the episode schema or segmentation rules are wrong, real-time capture just produces bad data faster.

**Do this instead:** Build the batch Episode Builder first (Stages A-F). Process historical sessions. Manually validate 100+ episodes for mode accuracy (>85%), reaction label confidence (>80%), and constraint extraction completeness (>90%). Only then build Mission Control integration, using the validated schema and rules.

### Anti-Pattern 5: Monolithic Preference Model Before RAG Baseline

**What people do:** Jump directly to training an ML preference model before establishing whether simple retrieval-based recommendations work.

**Why it's wrong:** With 500-1000 episodes, an ML model may overfit or underperform relative to simple retrieval. You need the RAG baseline to (a) establish a performance floor, (b) provide explainable recommendations (episode provenance), and (c) generate candidate actions that the preference model can score.

**Do this instead:** Build RAG baseline first (retrieve similar episodes, rank by success). Then train preference model on historical data. Use preference model to re-rank RAG candidates. Only train a learned policy after both components are validated.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Mission Control** | REST API + WebSocket for real-time events | Requires adding episode tables + task schema enhancement. Dashboard is Next.js + SQLite. WebSocket connects to OpenClaw Gateway. Not yet available; batch pipeline is the interim path. |
| **OpenClaw Gateway** | WebSocket proxy for tool provenance | Streams tool calls, file touches, command outputs back to Mission Control. Each tool call becomes a provenance record. |
| **DuckDB** | Python duckdb library, local file storage | Primary analytical store. Single-writer (fine for batch updates). Export to Parquet for ML training. |
| **Claude Code Sessions** | Read JSONL from ~/.claude/projects/PROJECT-HASH/ | Session files are append-only JSONL. Copy to data/raw/ for reproducibility. Each line is a conversation event. |
| **Git Repositories** | Shallow clone + metadata extraction | Extract commit metadata (hash, message, files, timestamps) to JSON. Can discard .git after extraction. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **Pipeline stages (A-F)** | Function calls, List[DataClass] | Each stage receives and returns typed data. No shared mutable state. Stages are composable and independently testable. |
| **Pipeline → Storage** | DuckDB INSERT via Python API | Pipeline produces episode objects; storage layer handles schema mapping and incremental loading. |
| **Storage → Training** | DuckDB COPY TO Parquet | Training reads from exported Parquet files. No direct DuckDB queries during training (decoupled). |
| **Storage → Export** | DuckDB COPY TO JSONL / Parquet | Human inspection via JSONL. ML training via Parquet. Ad-hoc analysis via SQL. |
| **Constraint Store → Validator** | Direct read from DuckDB constraints table | Validator loads active constraints at episode creation time. Checks diffs against detection hints. |
| **Preference Model → Policy** | Reward signal (scalar) | Preference model outputs P(approve) as reward. Policy optimizes expected reward. Models are separate: preference is fixed during policy training. |

## Build Order (Dependencies)

The following build order reflects dependencies between components. Each step requires the prior steps to be functional.

### Phase 1: Core Pipeline (Stages A-C) — Unblocks everything

1. **CanonicalEvent model + Source Adapters** — Define the data model, then build adapters for Claude JSONL and git history. This is the input foundation.
2. **Event Normalizer (Stage A)** — Merge and sort. Depends on adapters.
3. **Event Tagger (Stage B)** — Classify events. Depends on normalized stream.
4. **Episode Segmenter (Stage C)** — Cut into episodes. Depends on tagged events.

### Phase 2: Episode Population (Stages D-F) — Produces training-ready episodes

5. **Field Populator (Stage D)** — Derive observation/action/outcome. Depends on segments.
6. **Reaction Labeler (Stage E)** — Add reaction labels. Depends on populated episodes.
7. **Constraint Extractor (Stage F)** — Extract durable rules. Depends on reaction labels.

### Phase 3: Storage + Validation — Makes episodes queryable and trustworthy

8. **DuckDB schema + loader** — Store episodes. Depends on episode objects.
9. **Validator** — Check episode quality. Depends on schema + constraint store.
10. **Export pipeline** — Parquet + JSONL. Depends on DuckDB schema.

### Phase 4: Training Infrastructure — Learns from episodes

11. **Feature engineering** — Encode episodes for ML. Depends on DuckDB schema.
12. **RAG baseline orchestrator** — Retrieve + recommend. Depends on episode index.
13. **Preference model** — Predict approval. Depends on labeled episodes (500+).
14. **Learned policy** — Optimize actions. Depends on preference model + RAG baseline.

### Phase 5: Operational Integration — Real-time capture

15. **Mission Control integration** — Real-time episodes. Depends on validated schema + rules from phases 1-3.
16. **Shadow mode** — Compare recommendations to human. Depends on RAG baseline.
17. **Graduated autonomy** — Progressive delegation. Depends on preference model + policy.

### Key dependency chain:
```
Adapters → Normalizer → Tagger → Segmenter → Populator → Reaction → Constraints
                                                    │
                                                    v
                                              DuckDB Schema
                                                    │
                                         ┌──────────┼──────────┐
                                         v          v          v
                                     Validator   Exporter   Feature Eng.
                                                               │
                                                    ┌──────────┼──────────┐
                                                    v          v          v
                                                RAG Base   Pref Model  Learned Policy
                                                    │
                                                    v
                                              Shadow Mode
                                                    │
                                                    v
                                           Mission Control Integration
```

## Sources

- **Project design documents (HIGH confidence):**
  - `docs/design/AUTHORITATIVE_DESIGN.md` — Canonical specification for episode extraction, three-layer architecture, pipeline stages, validation, training pipeline
  - `docs/design/WHY_TURN_LEVEL - Improved.md` — Full technical rationale, JSON schema, decision-point detection rubric, worked example
  - `docs/design/Mission Control - supervisory control layer.md` — Integration strategy for real-time capture
  - `data/schemas/orchestrator-episode.schema.json` — Strict JSON Schema for episode objects
  - `data/schemas/constraint.schema.json` — Constraint store schema
  - `.planning/PHASE-0-DECISIONS.md` — Infrastructure decisions (DuckDB, session backup, multi-project)

- **Domain research (MEDIUM confidence):**
  - Event processing pipeline patterns (batch, trigger-based segmentation, adapter pattern)
  - DuckDB schema design for analytical workloads (hybrid flat/nested, incremental INSERT, Parquet export)
  - Bradley-Terry preference model architecture for small-dataset RLHF
  - RAG-based retrieval for episode recommendation

---
*Architecture research for: Episode extraction & policy learning for orchestrator training*
*Researched: 2026-02-10*
