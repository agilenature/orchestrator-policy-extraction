# Feature Research

**Domain:** Episode extraction & policy learning for agentic orchestration
**Researched:** 2026-02-10
**Confidence:** MEDIUM-HIGH (domain is novel; features derived from design docs + RLHF/IRL literature + agentic RAG ecosystem)

---

## Feature Landscape

### Table Stakes (System Doesn't Work Without These)

These features are non-negotiable for the system to produce usable training data and enforce learned policy. Missing any one breaks the core loop: capture episodes, learn from them, enforce what was learned.

#### Category 1: Episode Extraction

| Feature | Why Essential | Complexity | Notes |
|---------|---------------|------------|-------|
| **Event stream normalizer** | Raw JSONL + git + terminal logs are heterogeneous; nothing downstream works without a canonical event format (`event_id`, `ts_utc`, `session_id`, `actor`, `type`, `payload`) | MEDIUM | Must handle clock skew between git timestamps and JSONL timestamps. DuckDB can query JSONL directly for exploration, but normalization is required for reliable segmentation. |
| **Event tagger (O_DIR, X_PROPOSE, T_TEST, etc.)** | Decision-point detection depends entirely on classified events. Without tags, you cannot segment episodes or detect boundaries. | MEDIUM | Keyword/heuristic-based v0 is sufficient. Three tag families: orchestrator (O_DIR, O_GATE, O_CORR, O_REDIRECT, O_QUESTION), executor (X_PROPOSE, X_ASK, X_PATCH, X_SUMMARY), tool (T_TEST, T_LINT, T_BUILD, T_GIT_COMMIT, T_RISKY). Configurable via `data/config.yaml`. |
| **Decision-point episode segmenter** | The core unit of the system. Start on O_DIR/O_GATE, end on X_PROPOSE/X_ASK/T_TEST result/T_RISKY/T_GIT_COMMIT/timeout. Without this, you have turns (wrong unit) or commits (too coarse). | HIGH | This is the hardest extraction component. Must handle: nested subagent sessions, overlapping boundaries, idle timeouts (30min default). The segmentation algorithm walks the event stream in order with explicit open/close state. |
| **Episode field populator** | Each episode needs observation (repo_state, quality_state, context), orchestrator_action (mode, goal, scope, gates, risk, executor_instruction), and outcome (executor_effects, quality, reward_signals). Without populated fields, episodes are empty shells. | HIGH | Mode inference is deterministic v0 (keyword rules). Risk computation uses diff thresholds + protected paths from config. Observation must be causally prior to action; outcome must follow action. |
| **Reaction labeler** | Ground-truth signal for preference model training. The human's next message after an episode boundary is the supervised label (approve/correct/redirect/block/question). | MEDIUM | Keyword heuristics with confidence scores. Implicit approval (next task without complaint) is common and needs handling. Target: >=80% accuracy on manual validation. |
| **Schema validation** | Episodes must validate against `orchestrator-episode.schema.json`. Invalid episodes corrupt training data. | LOW | JSON Schema Draft 2020-12. Already defined. Target: >=99% episodes validate. Strict `additionalProperties: false` prevents drift. |

#### Category 2: Constraint Management

| Feature | Why Essential | Complexity | Notes |
|---------|---------------|------------|-------|
| **Constraint extractor** | Corrections/blocks contain durable orchestration rules ("avoid regex XML", "no hardcoded secrets"). Without extraction, every lesson is ephemeral -- the core pain point this system solves. | MEDIUM | Triggered when reaction is "correct" or "block". Extracts: text, severity (warning/requires_approval/forbidden), scope (paths), detection_hints (patterns). Schema already defined in `constraint.schema.json`. |
| **Constraint store (persistence)** | Constraints must persist across sessions and be queryable. Without a store, extracted constraints are lost. | LOW | DuckDB table `constraints` with constraint_id, text, severity, scope, detection_hints, source_episode_id, created_at. Append-only with deduplication. |
| **Constraint enforcement in validator** | Constraints must be checkable against diffs/actions. Without enforcement, constraints are documentation, not policy. | MEDIUM | Pattern matching: forbidden strings in diffs, protected path touches, risky command detection. Must integrate with episode validation (Part 5 of design spec). |

#### Category 3: Data Infrastructure

| Feature | Why Essential | Complexity | Notes |
|---------|---------------|------------|-------|
| **DuckDB episode database** | Primary storage for episodes, constraints, correlations. Required for analytical queries, incremental updates, and training data export. | LOW | Decision already made (PHASE-0-DECISIONS.md). Tables: sessions, commits, correlations, episodes, constraints, update_log. Supports direct JSONL querying for exploration. |
| **Multi-project registry** | System must handle multiple projects (modernizing-tool, orchestrator-policy-extraction, future). Without registry, no project isolation or cross-project analysis. | LOW | `data/projects.json` already defined. Per-project directories in raw/ and processed/. |
| **Session backup (copy + git commit)** | Raw sessions are irreplaceable research data. Without backup, data loss is catastrophic and irreversible. | LOW | Decision already made: copy to `data/raw/PROJECT/sessions/`, commit to git. Three backup layers: original, local copy, GitHub. |
| **Provenance tracking** | Every episode must link back to source material (JSONL line ranges, commit hashes, tool call IDs). Without provenance, episodes are unauditable and debugging extraction errors is impossible. | MEDIUM | Required field in schema: `provenance.sources[]` with type (claude_jsonl/terminal_log/git/ci) and ref (pointer). Essential for spot-checking and validation. |

#### Category 4: Validation

| Feature | Why Essential | Complexity | Notes |
|---------|---------------|------------|-------|
| **Schema-level episode validation** | Mode must be in enum, scope must have paths, gates must be typed, risk must be enum. Without this, garbage episodes enter training. | LOW | JSON Schema validation. Already specified. |
| **Causal ordering validation** | Observation must precede action, outcome must follow action. Temporal violations produce misleading training signal. | LOW | Timestamp comparison within each episode. Simple but critical. |
| **Episode integrity check** | Reaction labels must attach to correct episode boundary. Provenance pointers must exist. Missing fields flagged. | MEDIUM | Part of genus-based validation (Part 5 of design spec). Layers: schema validity, evidence grounding, non-contradiction, constraint enforcement, episode integrity. |

---

### Differentiators (Quality Improvements, Competitive Advantage)

These features improve quality, enable the training pipeline, and move toward autonomous orchestration. Not required for v0 data collection, but required for the system to achieve its stated goals.

#### Category 1: Preference Modeling

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Preference model training pipeline** | Predicts approve/correct/block from (observation, proposed_action). Becomes substitute human feedback when orchestrator is absent. This is what makes graduated autonomy possible. | HIGH | Bradley-Terry or IRPO-style reward model. Input: observation + orchestrator_action. Output: probability distribution over reaction labels. Target: >=80% accuracy on held-out reactions. Recent research (IRPO, Jan 2026) shows pointwise scoring can scale efficiently beyond O(n^2) pairwise. |
| **Objective reward proxy computation** | Tests/lint/build/diff_risk scores provide always-available reward signal, even without human. Without this, the system cannot learn when human is absent. | LOW | Already specified: tests=pass/fail, lint=pass/fail, diff_risk=f(lines, files, protected_paths). Configurable thresholds in config.yaml. Simple but essential bridge to human-absent operation. |
| **Training data export (Parquet)** | ML pipelines need structured, efficient data formats. DuckDB exports to Parquet natively. | LOW | `COPY (SELECT * FROM episodes) TO 'training.parquet' (FORMAT PARQUET)`. Already supported by DuckDB decision. |

#### Category 2: RAG Orchestration

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Episode indexing (semantic + keyword)** | Enables retrieval of similar past episodes by observation context. Foundation for baseline orchestrator. | MEDIUM | Options: FAISS for vector similarity, BM25 for keyword. LangGraph (top-rated 2025-2026 RAG framework) supports complex flows with checkpointing. Index by: phase labels, file context (trigram), task keywords (TF-IDF or embeddings). Retrieval latency target: <500ms for top-k=10. |
| **RAG retrieval policy** | Given current observation, retrieve top-k similar episodes, extract actions, rank by frequency and success. This is the baseline orchestrator. | MEDIUM | Top-1 accuracy >40%, top-3 >70% on test set. Must include both positive (approved) and negative (corrected/blocked) examples. Explainability: each recommendation traceable to source episodes. |
| **Shadow mode framework** | Run orchestrator on new sessions without execution. Compare recommendations to actual human decisions. Measures agreement rate. Critical for validating the system before granting any autonomy. | MEDIUM | Logs recommendations vs actual actions. Metrics: agreement rate, reaction quality, false positive rate (dangerous recommendations). Target: >=70% agreement, zero dangerous recommendations. |
| **Recommendation explainability** | Each recommendation must cite source episodes with similarity scores and rationale. Without this, the human cannot trust or correct the system. | LOW | "In similar situations (phase X, files Y), you did Z" format. Retrieval provenance (episode IDs, similarity scores) included in every recommendation. |

#### Category 3: Advanced Validation

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Evidence grounding validation** | If mode=Implement, were requirements stated? Files inspected? Constraints loaded? Catches nonsensical decisions. | MEDIUM | Part of genus-based validation layer B. Requires cross-referencing observation against action fields. |
| **Non-contradiction validation** | mode=Explore but write_allowed=true? gate=no_network but instruction says "look up docs"? Catches logical inconsistencies. | MEDIUM | Part of genus-based validation layer C. Rule-based checks against known contradictions. |
| **Mode inference accuracy tracking** | Mode inference is heuristic v0. Must measure accuracy to know when to upgrade to ML classifier. | LOW | Spot-check sample against manual labels. Target: >=85% accuracy. Track accuracy over time to detect drift. |
| **Reaction confidence calibration** | Confidence scores must be calibrated (high confidence = correct label). Without calibration, confidence scores mislead preference model. | MEDIUM | Validate on manual review set. If 90%-confidence labels are wrong 30% of the time, recalibrate. |

#### Category 4: Mission Control Integration

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Structured task creation (mode/scope/gates/risk)** | Replace ad-hoc prose tasks with structured orchestrator actions. Planning becomes explicit action in (O, A, Y) episodes. Real-time capture is cleaner than post-hoc parsing. | MEDIUM | Add required fields to Mission Control tasks: orchestrator_mode, goal, scope.paths/avoid, risk, gates, constraints_in_force. |
| **Review widget (reaction + constraint extraction)** | Replace free-text review with structured reaction labels (approve/correct/redirect/block/question). If correct/block, extract constraint inline. | MEDIUM | UI captures: reaction label, confidence, constraint text/severity/scope/detection_hints. Ground-truth data collection at source. |
| **Tool provenance recording via Gateway** | Store per task/episode: tool calls, files touched, commands run, test results, commit hashes. Automatic outcome section population. | HIGH | Requires WebSocket connection to OpenClaw Gateway. Real-time event streaming. More complex than post-hoc parsing but produces higher quality episodes. |
| **Workflow state gates (epistemic states)** | PLANNING -> IN PROGRESS requires valid Plan artifact. IN PROGRESS -> REVIEW requires tests + constraints check. REVIEW -> DONE requires approve or threshold. | MEDIUM | Turns workflow into governance. States become epistemically meaningful, not just status tracking. |

#### Category 5: Graduated Autonomy

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Risk-tiered autonomy levels** | Low-risk: full autonomy with objective gates. Medium: autonomy with preference model approval. High: human required. Critical: human + explicit gate. | HIGH | Depends on preference model accuracy (>=80%) and constraint coverage (>=95%). Policy chooses, harness enforces. |
| **Governing execution harness** | Sandbox, allowlists, approval gates, branch/PR gates, constraint enforcement. Non-negotiable safety layer regardless of policy quality. | HIGH | OpenClaw-side: command allowlists, sandboxing, protected paths. Mission Control-side: approval workflows. The harness exists independently of the learned policy. |
| **Kill switch** | Immediate shutdown of autonomous operations. Non-negotiable for any autonomous system. | LOW | Simple but must work instantly and reliably. |

---

### Anti-Features (Deliberately NOT Building)

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| **Turn-level episodes (tool call granularity)** | Intuitive: every user-assistant exchange = episode. Finer granularity seems better. | Trains the executor (Claude's tool calls), not the orchestrator (OpenClaw's decisions). Blurs the critical orchestrator/executor distinction. Decision points are the correct unit, not turns. | Decision-point episodes with orchestrator actions (mode/scope/gates/instruction) as the training target. Executor tool calls stored separately as subordinate data. |
| **Commit-only correlation** | Simple to implement. Commits are concrete deliverables. | Hides orchestration decisions: sequencing, mistakes, recoveries, constraints, gates, why one plan was chosen over alternatives. Commits are outputs of orchestration, not the orchestration itself. | Commit correlation kept as validation layer (did episodes produce deliverables?), not as learning signal. |
| **Single unified ML model (end-to-end)** | Appealing: one model that learns everything. | Too complex for available data. Overfits. Hard to debug. Fails silently. | Start with RAG retrieval (baseline), add preference model (reaction prediction), then learned policy (supervised + RL). Each component independently verifiable. |
| **Full autonomy immediately** | Tempting once shadow mode shows high agreement. | Catastrophic failure risk. No system is safe enough for unbounded autonomy. Trust must be earned incrementally. | Staged promotion: shadow -> read-only -> write-in-branch -> PR autopilot -> limited merge. Each stage has go/no-go gates. |
| **Cross-domain generalization** | "What if OpenClaw can orchestrate any domain?" | Insufficient data. Different domains have different constraints, risk profiles, and workflow patterns. Generalization is a v3+ problem. | Start with software engineering tasks. Validate per-project before cross-project. Cross-domain is future work. |
| **Real-time everything** | "Capture every event as it happens, with zero latency." | Adds enormous complexity (WebSocket infrastructure, streaming parsers, real-time DuckDB writes) for marginal benefit in early phases. Post-hoc parsing works fine for historical data. | Real-time capture via Mission Control for new sessions (Phase 5+). Post-hoc batch parsing for historical data (Phase 1-4). Don't conflate the two. |
| **Custom ML infrastructure** | "Build our own training framework, custom embeddings, custom everything." | Maintenance burden. Reinventing wheels. Distracts from the actual problem (episode quality). | Use established tools: DuckDB for storage, scikit-learn/PyTorch for preference model, FAISS/BM25 for retrieval. Build the novel parts (episode extraction, constraint enforcement), use off-the-shelf for the rest. |
| **Per-task agent creation** | Mission Control default: create a specialized agent per task. | Fragments behavior. No consistent orchestrator policy to train. Each agent is a one-off. | One persistent OrchestratorAgent. Many tasks as training episodes. Consistent policy that evolves. |
| **LLM-based event classification** | "Use GPT-4 to classify every event." | Too slow for batch processing (thousands of events). Not reproducible (stochastic). Expensive. | Keyword/heuristic-based tagging (v0). Deterministic, fast, reproducible. Upgrade to small classifier trained on labeled data when keyword accuracy is insufficient. |

---

## Feature Dependencies

```
[Event Stream Normalizer]
    +--requires--> [Session Backup / Data Infrastructure]
    +--requires--> [Multi-Project Registry]
    |
    +--enables--> [Event Tagger]
                      |
                      +--enables--> [Decision-Point Segmenter]
                                        |
                                        +--enables--> [Episode Field Populator]
                                        |                 |
                                        |                 +--enables--> [Reaction Labeler]
                                        |                 |                 |
                                        |                 |                 +--enables--> [Constraint Extractor]
                                        |                 |                                   |
                                        |                 |                                   +--enables--> [Constraint Store]
                                        |                 |                                   |                 |
                                        |                 |                                   |                 +--enables--> [Constraint Enforcement]
                                        |                 |                                   |
                                        |                 |                                   +--enables--> [Preference Model Training]
                                        |                 |
                                        |                 +--enables--> [Schema Validation]
                                        |                 +--enables--> [Causal Ordering Validation]
                                        |                 +--enables--> [Episode Integrity Check]
                                        |
                                        +--enables--> [DuckDB Episode Database]
                                                          |
                                                          +--enables--> [Episode Indexing]
                                                          |                 |
                                                          |                 +--enables--> [RAG Retrieval Policy]
                                                          |                                   |
                                                          |                                   +--enables--> [Shadow Mode]
                                                          |                                   +--enables--> [Recommendation Explainability]
                                                          |
                                                          +--enables--> [Training Data Export]
                                                                            |
                                                                            +--enables--> [Preference Model Training]
                                                                                              |
                                                                                              +--enables--> [Risk-Tiered Autonomy]

[Constraint Enforcement] + [Preference Model] + [Shadow Mode]
    +--all required for--> [Governing Execution Harness]
                               |
                               +--enables--> [Risk-Tiered Autonomy]
                               +--enables--> [Graduated Autonomy Rollout]

[Structured Task Creation] + [Review Widget] + [Tool Provenance Recording]
    +--all part of--> [Mission Control Integration]
    +--enhances--> [Episode Quality] (real-time capture vs post-hoc parsing)
    +--enables--> [Workflow State Gates]
```

### Dependency Notes

- **Event Tagger requires Normalizer:** Cannot classify events that are not in canonical format.
- **Segmenter requires Tagger:** Episode boundaries are defined by tag combinations (O_DIR starts, X_PROPOSE/T_TEST ends).
- **Reaction Labeler requires Segmenter:** Must know episode boundaries to find the next human message.
- **Constraint Extractor requires Reaction Labeler:** Only fires when reaction is "correct" or "block".
- **Preference Model requires both Reaction Labels and Training Data Export:** Needs labeled (observation, action, reaction) tuples in exportable format.
- **RAG Policy requires Episode Indexing:** Cannot retrieve similar episodes without an index.
- **Shadow Mode requires RAG Policy:** Must have a baseline orchestrator to compare against human decisions.
- **Graduated Autonomy requires Preference Model + Constraint Enforcement + Harness:** All three safety layers must be operational before any autonomous execution.
- **Mission Control Integration enhances but does not replace batch extraction:** Historical data requires post-hoc parsing regardless. Mission Control adds real-time capture for new sessions.

---

## MVP Definition

### Launch With (v1) -- Historical Episode Extraction

Minimum viable product: extract episodes from existing sessions, validate quality, populate DuckDB.

- [x] **Session backup + data infrastructure** -- Foundation for everything. Already partially built.
- [ ] **Event stream normalizer** -- JSONL + git events into canonical format
- [ ] **Event tagger (keyword/heuristic v0)** -- Classify events into O_DIR, X_PROPOSE, T_TEST, etc.
- [ ] **Decision-point episode segmenter** -- Core algorithm: walk event stream, detect boundaries, emit episodes
- [ ] **Episode field populator** -- Observation, action (with mode inference), outcome fields
- [ ] **Reaction labeler** -- Classify next human message as approve/correct/redirect/block/question
- [ ] **Constraint extractor** -- From corrections/blocks, extract durable rules
- [ ] **Constraint store (DuckDB)** -- Persist extracted constraints
- [ ] **Schema validation** -- All episodes validate against orchestrator-episode.schema.json
- [ ] **DuckDB episode database** -- Store everything, enable analytical queries
- [ ] **Provenance tracking** -- Every episode links to source JSONL lines and git refs

### Add After Validation (v1.x) -- Baseline Orchestrator

Features to add once episode quality is validated (>=85% mode accuracy, >=80% reaction accuracy).

- [ ] **Episode indexing (semantic + keyword)** -- Index episodes for retrieval
- [ ] **RAG retrieval policy** -- Baseline orchestrator: retrieve similar episodes, recommend actions
- [ ] **Shadow mode framework** -- Run recommendations alongside actual decisions, measure agreement
- [ ] **Recommendation explainability** -- Each recommendation cites source episodes
- [ ] **Objective reward proxy computation** -- Tests/lint/diff_risk scores for human-absent operation
- [ ] **Constraint enforcement in validator** -- Check diffs against constraint store
- [ ] **Evidence grounding validation** -- Cross-reference observation against action fields
- [ ] **Training data export (Parquet)** -- Export episodes for ML pipelines

### Future Consideration (v2+) -- Learned Policy + Autonomy

Features to defer until RAG baseline demonstrates >=70% shadow mode agreement.

- [ ] **Preference model training pipeline** -- Train approval predictor from historical reactions
- [ ] **Mission Control integration (structured tasks, review widget, provenance)** -- Real-time capture
- [ ] **Workflow state gates** -- Epistemic state machine
- [ ] **Governing execution harness** -- Sandbox + allowlists + approval gates
- [ ] **Risk-tiered autonomy levels** -- Graduated autonomy by risk tier
- [ ] **ML-based mode classifier** -- Replace keyword heuristics when accuracy is insufficient
- [ ] **Reaction confidence calibration** -- Calibrate confidence scores against manual review

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Phase |
|---------|------------|---------------------|----------|-------|
| Event stream normalizer | HIGH | MEDIUM | P1 | 1 |
| Event tagger | HIGH | MEDIUM | P1 | 1 |
| Decision-point segmenter | HIGH | HIGH | P1 | 1 |
| Episode field populator | HIGH | HIGH | P1 | 1 |
| Reaction labeler | HIGH | MEDIUM | P1 | 2 |
| Constraint extractor | HIGH | MEDIUM | P1 | 2 |
| Constraint store | HIGH | LOW | P1 | 2 |
| Schema validation | HIGH | LOW | P1 | 1 |
| DuckDB database | HIGH | LOW | P1 | 0 |
| Provenance tracking | MEDIUM | MEDIUM | P1 | 1 |
| Episode indexing | HIGH | MEDIUM | P2 | 4 |
| RAG retrieval policy | HIGH | MEDIUM | P2 | 4 |
| Shadow mode | HIGH | MEDIUM | P2 | 5 |
| Explainability | MEDIUM | LOW | P2 | 4 |
| Objective reward proxies | HIGH | LOW | P2 | 2 |
| Constraint enforcement | HIGH | MEDIUM | P2 | 2 |
| Evidence grounding | MEDIUM | MEDIUM | P2 | 3 |
| Training data export | MEDIUM | LOW | P2 | 4 |
| Preference model pipeline | HIGH | HIGH | P3 | 6+ |
| Mission Control integration | HIGH | HIGH | P3 | 6+ |
| Workflow state gates | MEDIUM | MEDIUM | P3 | 6+ |
| Governing execution harness | HIGH | HIGH | P3 | 7+ |
| Risk-tiered autonomy | HIGH | HIGH | P3 | 7+ |
| ML mode classifier | MEDIUM | MEDIUM | P3 | 6+ |

**Priority key:**
- P1: Must have for v1 (episode extraction from historical data)
- P2: Should have for v1.x (baseline orchestrator + validation)
- P3: Future consideration for v2+ (learned policy + autonomy)

---

## Alignment with Design Decisions

| Design Decision | Features That Implement It |
|----------------|--------------------------|
| **Decision-point episodes (not turns)** | Segmenter uses O_DIR/O_GATE starts, X_PROPOSE/T_TEST/T_GIT_COMMIT ends. Mode inference from keywords. Risk from diff thresholds + protected paths. |
| **Orchestrator-first (not executor)** | Episode action field is orchestrator directive (mode/scope/gates/instruction), not tool calls. Tool calls stored in executor_effects (outcome), not as primary action. Anti-feature: turn-level episodes explicitly rejected. |
| **Three-layer architecture** | Layer 1: Orchestrator episodes (primary). Layer 2: Executor episodes (subordinate, for Claude optimization). Layer 3: Deliverable episodes (commits, for validation). Features focus on Layer 1. |
| **Genus-based validation** | Five validation layers: schema, evidence grounding, non-contradiction, constraint enforcement, episode integrity. Genus = correct mode classification. Differentia = what distinguishes one mode from another. |
| **DuckDB + session backup** | DuckDB for all analytical storage. Sessions copied and committed to git. Three backup layers. Incremental updates. |
| **Constraint extraction from corrections** | Constraint extractor fires on correct/block reactions. Produces constraint_id, text, severity, scope, detection_hints. Stored in constraint store. Enforced by validator. |
| **Preference model for human-absent operation** | Trained on (observation, action, reaction) tuples. Predicts approve/correct/block. Objective proxies (tests/lint/diff_risk) provide always-available signal. Together they substitute for absent human. |
| **Mission Control as training cockpit** | Structured tasks with orchestrator fields. Review widget captures reactions. Tool provenance via Gateway. Workflow gates enforce epistemic states. |

---

## Comparable Systems & Landscape

| System/Approach | What It Does | How We Differ |
|----------------|--------------|---------------|
| **RLHF reward models (OpenAI, Anthropic)** | Train reward models from human preferences on LLM outputs. Bradley-Terry pairwise comparisons. | We train on orchestration decisions (mode/scope/gates), not on text quality. Our "preferences" are approve/correct/block reactions to orchestrator actions, not text rankings. |
| **Inverse RL from demonstrations** | Infer reward functions from expert trajectories. Policy extraction via MaxEnt IRL, AIRL variants. | We use explicit reaction labels (supervised) rather than pure IRL (unsupervised reward inference). Constraints are first-class (extracted directly from corrections), not inferred latently. |
| **Agentic RAG (LangGraph, etc.)** | Dynamic retrieval with agent-controlled strategies. Multi-hop, graph-aware. | Our RAG retrieves orchestration episodes (not documents). Similarity is over (observation, action) tuples, not text chunks. Retrieval serves action recommendation, not question answering. |
| **Amazon Bedrock AgentCore** | Quality evaluations and policy controls for AI agents. Episodic memory capture. | AgentCore provides infrastructure; we provide the episode schema, constraint extraction, and preference model training specific to orchestration policy learning. |
| **OpenClaw Gateway + Mission Control** | Agent orchestration, task management, tool execution. | We add: episode extraction, constraint store, preference model, graduated autonomy. Mission Control becomes the training cockpit, not just a task dashboard. |

---

## Sources

- Project design documents: `docs/design/AUTHORITATIVE_DESIGN.md`, `docs/design/WHY_TURN_LEVEL - Improved.md`, `docs/design/Mission Control - supervisory control layer.md`
- Project schemas: `data/schemas/orchestrator-episode.schema.json`, `data/schemas/constraint.schema.json`
- Project decisions: `.planning/PHASE-0-DECISIONS.md`
- IRPO (Intergroup Relative Preference Optimization): arXiv:2601.00677v1 (Jan 2026) -- scaling Bradley-Terry for RLHF
- IRL from demonstrations survey: shadecoder.com/topics/inverse-reinforcement-learning (2025)
- Hybrid-AIRL: arXiv:2511.21356 (2025) -- stable reward/policy learning from demonstrations
- Active IRL with full trajectories: NeurIPS 2024/98880 -- reducing demonstration costs
- Agentic RAG ecosystem: LangGraph, FAISS, BM25, hybrid vector-graph indexes (Apple MLR 2025)
- Amazon Bedrock AgentCore: aws.amazon.com/blogs/aws/amazon-bedrock-agentcore (2025)

---
*Feature research for: Episode extraction & policy learning for agentic orchestration*
*Researched: 2026-02-10*
