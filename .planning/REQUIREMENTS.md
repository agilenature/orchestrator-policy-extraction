# Requirements: Orchestrator Policy Extraction

**Defined:** 2026-02-10
**Core Value:** Episodes capture how to decide what to do next (orchestrator decisions: mode/scope/gates/constraints), not just what was delivered (commits), enabling policy learning that scales human judgment instead of human typing.

## v1 Requirements

Requirements for initial system capable of extracting episodes from historical data, building constraint store, and deploying RAG baseline orchestrator with shadow mode validation.

### Episode Extraction Pipeline

- [ ] **EXTRACT-01**: System normalizes Claude Code JSONL + git history into unified event stream with canonical structure (event_id, ts_utc, actor, type, payload, links)
- [ ] **EXTRACT-02**: System tags events with classification labels (O_DIR, O_GATE, O_CORR, X_PROPOSE, X_ASK, T_TEST, T_LINT, T_GIT_COMMIT, T_RISKY)
- [ ] **EXTRACT-03**: System segments event stream into decision-point episodes using start triggers (O_DIR, O_GATE) and end triggers (X_PROPOSE, X_ASK, T_TEST result, T_RISKY, T_GIT_COMMIT, 30min timeout)
- [ ] **EXTRACT-04**: System populates episode fields (observation, orchestrator_action, outcome) by deriving from event stream data within episode boundaries
- [ ] **EXTRACT-05**: System labels reactions (approve/correct/redirect/block/question) from human messages following episode boundaries with confidence scores
- [ ] **EXTRACT-06**: System extracts constraints from correct/block reactions, generating text, severity, scope, and detection hints

### Data Infrastructure

- [ ] **DATA-01**: System stores episodes in DuckDB database with hybrid schema (flat columns for queryable fields + STRUCT/JSON for nested data) supporting incremental updates
- [ ] **DATA-02**: System validates episodes against JSON Schema (orchestrator-episode.schema.json) ensuring structural correctness and required fields
- [ ] **DATA-03**: System loads configuration from YAML file (data/config.yaml) defining risk model, protected paths, event tag patterns, reaction keywords, mode inference rules
- [ ] **DATA-04**: System tracks provenance for each episode (source JSONL file + line ranges, git commits, tool call IDs) enabling audit and debugging

### Constraint Management

- [ ] **CONST-01**: System extracts constraints from corrections containing text description, severity level, scope paths, and detection hint patterns
- [ ] **CONST-02**: System stores constraints in version-controlled JSON file (data/constraints.json) with unique IDs and metadata
- [ ] **CONST-03**: System assigns severity levels (warning / requires_approval / forbidden) based on reaction type and keyword analysis
- [ ] **CONST-04**: System defines constraint scope (file-level, module-level, or repo-wide) inferred from mentioned paths or user specification

### Validation & Quality

- [ ] **VALID-01**: System validates episodes using genus-based multi-layer checks (schema validity, evidence grounding, non-contradiction, constraint enforcement, episode integrity)
- [ ] **VALID-02**: System provides manual validation workflow for creating gold-standard labeled episode set (target: 100+ episodes with verified mode/reaction labels)
- [ ] **VALID-03**: System calculates and tracks episode quality metrics (mode inference accuracy >=85%, reaction label confidence >=80%, constraint extraction rate >=90% of corrections)

### Training Infrastructure

- [ ] **TRAIN-01**: System provides RAG baseline orchestrator that retrieves top-k similar episodes by observation context and recommends orchestrator actions with explainable provenance
- [ ] **TRAIN-02**: System runs shadow mode testing (>=50 sessions, >=70% agreement threshold) comparing RAG recommendations to actual human decisions before allowing any autonomous operation

### Mission Control Integration

- [ ] **MC-01**: System captures episodes in real-time from Mission Control structured tasks (task creation, planning output, review reactions) without post-hoc log parsing
- [ ] **MC-02**: System records tool provenance (tool calls, files touched, commands run, test results, commits) streamed from OpenClaw Gateway during task execution
- [ ] **MC-03**: System provides review widget in Mission Control for labeling reactions (approve/correct/redirect/block/question) with optional constraint extraction workflow
- [ ] **MC-04**: System stores episodes in Mission Control's SQLite database (episodes, episode_events, constraints, approvals, commit_links tables) for dashboard integration

## v2 Requirements

Deferred to future release after v1 validation proves episode quality and RAG baseline effectiveness.

### Preference Modeling

- **PREF-01**: System trains Bradley-Terry preference model (50-80K params) to predict approve/correct/block probabilities from observation + proposed action
- **PREF-02**: System achieves >=80% prediction accuracy on held-out validation set before using for autonomous approvals
- **PREF-03**: System provides calibration metrics (ECE, reliability diagrams) to ensure confidence scores reflect true probabilities

### Learned Policy

- **POLICY-01**: System trains discrete RL policy (SB3 PPO, 7-mode action space) via behavioral cloning + fine-tuning with objective rewards
- **POLICY-02**: System achieves >=70% shadow mode agreement on medium-risk tasks before autonomous deployment
- **POLICY-03**: System provides policy rollback mechanism if autonomous performance degrades below threshold

### Graduated Autonomy

- **AUTO-01**: System executes low-risk tasks (diff <50 lines, no protected paths) fully autonomously using objective quality gates only
- **AUTO-02**: System executes medium-risk tasks with preference model approval (confidence >=85%) and human escalation fallback
- **AUTO-03**: System requires human approval for all high-risk tasks (protected paths touched, risky commands, large diffs >300 lines)

### Advanced Features

- **ADV-01**: System deduplicates extracted constraints using fuzzy matching (edit distance, semantic similarity) with human review workflow
- **ADV-02**: System experiments with retrieval approaches (BM25, embeddings, hybrid) to optimize RAG baseline recommendation quality
- **ADV-03**: System provides DAgger correction loop (aggregate human corrections from shadow mode into training data) for continual learning

## Out of Scope

Explicitly excluded to prevent scope creep.

| Feature | Reason |
|---------|--------|
| LLM fine-tuning as policy | Wrong paradigm -- discrete 7-mode action space requires classical RL (SB3), not token-level LLM training |
| Turn-level episode segmentation | Wrong unit -- decision points (evidence-triggered boundaries) are correct causal unit, not UI turns |
| Commit-only correlation as learning signal | Insufficient -- hides decisions, mistakes, corrections that are essential for policy learning. Useful only for validation layer. |
| Executor-level tool call optimization | Separate concern -- this project trains orchestrator (mode/scope/gates), not executor (Read/Edit/Bash sequences) |
| Cross-domain generalization | Narrow scope -- system learns from one user's orchestration patterns, not general-purpose task automation |
| Stream processing architecture | Over-engineered -- batch pipeline sufficient for hundreds of sessions; stream adds unnecessary complexity |
| Custom ML framework | Premature -- scikit-learn + PyTorch + SB3 are standard and sufficient; avoid NIH syndrome |
| Real-time deployment without shadow mode | Unsafe -- distribution shift in imitation learning is mathematically proven; shadow mode is non-negotiable |
| Single unified ML model | Wrong architecture -- RAG baseline, preference model, and RL policy are distinct stages with different purposes |

## Traceability

Mapping requirements to roadmap phases. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXTRACT-01 | Phase 1: Event Stream Foundation | Pending |
| EXTRACT-02 | Phase 1: Event Stream Foundation | Pending |
| EXTRACT-03 | Phase 1: Event Stream Foundation | Pending |
| EXTRACT-04 | Phase 2: Episode Population & Storage | Pending |
| EXTRACT-05 | Phase 2: Episode Population & Storage | Pending |
| EXTRACT-06 | Phase 3: Constraint Management | Pending |
| DATA-01 | Phase 2: Episode Population & Storage | Pending |
| DATA-02 | Phase 2: Episode Population & Storage | Pending |
| DATA-03 | Phase 1: Event Stream Foundation | Pending |
| DATA-04 | Phase 2: Episode Population & Storage | Pending |
| CONST-01 | Phase 3: Constraint Management | Pending |
| CONST-02 | Phase 3: Constraint Management | Pending |
| CONST-03 | Phase 3: Constraint Management | Pending |
| CONST-04 | Phase 3: Constraint Management | Pending |
| VALID-01 | Phase 4: Validation & Quality | Pending |
| VALID-02 | Phase 4: Validation & Quality | Pending |
| VALID-03 | Phase 4: Validation & Quality | Pending |
| TRAIN-01 | Phase 5: Training Infrastructure | Pending |
| TRAIN-02 | Phase 5: Training Infrastructure | Pending |
| MC-01 | Phase 6: Mission Control Integration | Pending |
| MC-02 | Phase 6: Mission Control Integration | Pending |
| MC-03 | Phase 6: Mission Control Integration | Pending |
| MC-04 | Phase 6: Mission Control Integration | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-02-10*
*Last updated: 2026-02-10 after roadmap creation (traceability populated)*
