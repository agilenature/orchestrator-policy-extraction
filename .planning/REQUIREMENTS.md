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

### Identification Transparency

- [ ] **IDTRANS-01**: System maintains an append-only `identification_reviews` DuckDB table recording human verdicts (accept/reject) against pipeline classification acts, with UNIQUE constraint on `identification_instance_id` enforcing at-most-once-per-instance semantics across all 35 identification points in 8 pipeline layers
- [ ] **IDTRANS-02**: System provides a `PoolBuilder` that sources `IdentificationPoint` instances per classification act type (35 total: 2×L1, 5×L2, 6×L3, 7×L4, 5×L5, 3×L6, 4×L7, 3×L8) from existing DuckDB tables, each carrying all five externalization properties (trigger, observation state, action taken, downstream impact, provenance pointer)
- [ ] **IDTRANS-03**: System provides a `review next` CLI command that presents one unreviewed identification instance in five-field format, collects verdict + optional opinion, writes one append-only row to `identification_reviews`, and routes rejected verdicts with opinions to named spec-correction candidates in `memory_candidates` via `VerdictRouter`
- [ ] **IDTRANS-04**: System provides trust accumulation for classification rules: accepted verdicts increment accept_count per (pipeline_component, point_id) pair, producing trust_level (unverified / provisional / established) in `identification_rule_trust` table with established threshold at ≥10 accepts and 0 rejects
- [ ] **IDTRANS-05**: System provides an out-of-band oracle Harness that enforces four structural invariants (at-most-once-verdict, layer-coverage-monotonic, specification-closure, delta-retrieval) against durable artifacts without AI session state, plus N-version consistency check between `memory_candidates` accepted entries and MEMORY.md, reporting violations at exit code 2

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

### Live Session Governance

- **LIVE-01**: System provides a Claude Code PreToolUse hook that intercepts proposed tool calls, checks them against active constraints via PolicyViolationChecker, and returns a block/warn/allow decision with reasoning within < 200ms
- **LIVE-02**: System provides a SessionStart hook that delivers a constraint briefing at the start of each session — surfacing active constraints relevant to the current project scope and flagging those with low durability scores
- **LIVE-03**: System provides a real-time JSONL stream processor that tails live session files, runs EscalationDetector and AmnesiaDetector on each event as it arrives, and emits governance signals without requiring a full batch pipeline run
- **LIVE-04**: System provides an inter-session coordination bus: a lightweight local service (HTTP or Unix socket) through which multiple parallel Claude Code sessions share constraint state, escalation alerts, and governance decisions
- **LIVE-05**: System supports a "governing session" pattern: a dedicated Claude Code instance that monitors all other active project sessions via the bus, maintains the authoritative constraint store, and can broadcast blocks or briefings to any active session

## Out of Scope

Explicitly excluded to prevent scope creep.

| Feature | Reason |
|---------|--------|
| LLM fine-tuning as policy | Wrong paradigm -- discrete 7-mode action space requires classical RL (SB3), not token-level LLM training |
| Turn-level episode segmentation | Wrong unit -- decision points (evidence-triggered boundaries) are correct causal unit, not UI turns |
| Commit-only correlation as learning signal | Insufficient -- hides decisions, mistakes, corrections that are essential for policy learning. Useful only for validation layer. |
| Executor-level tool call optimization | Separate concern -- this project trains orchestrator (mode/scope/gates), not executor (Read/Edit/Bash sequences) |
| Cross-domain generalization | Narrow scope -- system learns from one user's orchestration patterns, not general-purpose task automation |
| Stream processing architecture (v1) | Over-engineered for v1 batch pipeline -- Phase 14 research will determine if lightweight tailing suffices for live governance without full stream infrastructure |
| Custom ML framework | Premature -- scikit-learn + PyTorch + SB3 are standard and sufficient; avoid NIH syndrome |
| Real-time deployment without shadow mode | Unsafe -- distribution shift in imitation learning is mathematically proven; shadow mode is non-negotiable |
| Single unified ML model | Wrong architecture -- RAG baseline, preference model, and RL policy are distinct stages with different purposes |

## Traceability

Mapping requirements to roadmap phases. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXTRACT-01 | Phase 1: Event Stream Foundation | ✓ Complete |
| EXTRACT-02 | Phase 1: Event Stream Foundation | ✓ Complete |
| EXTRACT-03 | Phase 1: Event Stream Foundation | ✓ Complete |
| EXTRACT-04 | Phase 2: Episode Population & Storage | ✓ Complete |
| EXTRACT-05 | Phase 2: Episode Population & Storage | ✓ Complete |
| EXTRACT-06 | Phase 3: Constraint Management | ✓ Complete |
| DATA-01 | Phase 2: Episode Population & Storage | ✓ Complete |
| DATA-02 | Phase 2: Episode Population & Storage | ✓ Complete |
| DATA-03 | Phase 1: Event Stream Foundation | ✓ Complete |
| DATA-04 | Phase 2: Episode Population & Storage | ✓ Complete |
| CONST-01 | Phase 3: Constraint Management | ✓ Complete |
| CONST-02 | Phase 3: Constraint Management | ✓ Complete |
| CONST-03 | Phase 3: Constraint Management | ✓ Complete |
| CONST-04 | Phase 3: Constraint Management | ✓ Complete |
| VALID-01 | Phase 4: Validation & Quality | ✓ Complete |
| VALID-02 | Phase 4: Validation & Quality | ✓ Complete |
| VALID-03 | Phase 4: Validation & Quality | ✓ Complete |
| TRAIN-01 | Phase 5: Training Infrastructure | ✓ Complete |
| TRAIN-02 | Phase 5: Training Infrastructure | ✓ Complete |
| MC-01 | Phase 6: Mission Control Integration | ✓ Complete |
| MC-02 | Phase 6: Mission Control Integration | ✓ Complete |
| MC-03 | Phase 6: Mission Control Integration | ✓ Complete |
| MC-04 | Phase 6: Mission Control Integration | ✓ Complete |
| IDTRANS-01 | Phase 13.3: Identification Transparency | Pending |
| IDTRANS-02 | Phase 13.3: Identification Transparency | Pending |
| IDTRANS-03 | Phase 13.3: Identification Transparency | Pending |
| IDTRANS-04 | Phase 13.3: Identification Transparency | Pending |
| IDTRANS-05 | Phase 13.3: Identification Transparency | Pending |
| LIVE-01 | Phase 14: Live Session Governance Research | Pending |
| LIVE-02 | Phase 14: Live Session Governance Research | Pending |
| LIVE-03 | Phase 14: Live Session Governance Research | Pending |
| LIVE-04 | Phase 14: Live Session Governance Research | Pending |
| LIVE-05 | Phase 14: Live Session Governance Research | Pending |

**Coverage:**
- v1 requirements: 23 total (Phases 1–6, all complete)
- Identification transparency requirements: 5 (IDTRANS-01 through IDTRANS-05, Phase 13.3)
- Live governance requirements: 5 (LIVE-01 through LIVE-05, Phase 14)
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-02-10*
*Last updated: 2026-02-22 — added IDTRANS-01 through IDTRANS-05 for Phase 13.3; updated traceability statuses to reflect Phases 1–13 completion*
