# Project Research Summary

**Project:** Orchestrator Policy Extraction
**Domain:** ML policy learning from agent orchestration logs (episode extraction, preference modeling, graduated autonomy)
**Researched:** 2026-02-10
**Confidence:** HIGH

## Executive Summary

This project builds a system to extract machine-learnable training data from agentic orchestration logs and use it to learn orchestration policy that enables graduated autonomy. The core insight is that orchestrator decisions (mode, scope, gates, constraints) are the correct unit of learning -- not tool calls (executor-level) or commits (too coarse). Expert systems in this domain use trigger-based decision-point detection, hybrid analytical storage (DuckDB with JSON columns), and a staged progression from RAG baselines to preference models to learned policies.

The recommended approach follows a six-stage batch pipeline (normalize → tag → segment → populate → label → extract constraints) that processes historical session logs into structured episodes stored in DuckDB. These episodes feed a training pipeline that progresses from simple baselines (scikit-learn mode classifiers) through RAG retrieval (episode similarity search) to preference models (Bradley-Terry approval prediction) and ultimately learned policies (supervised learning + RL fine-tuning). The critical architectural invariant is strict separation of three episode layers: orchestrator (primary learning target), executor (subordinate, for Claude optimization), and deliverable (validation via commits).

The key risks are training the wrong policy (executor instead of orchestrator -- a fundamental genus violation), approval bias in training data (successful episodes overrepresented), and distribution shift when deploying learned policies (offline performance doesn't predict online behavior). Mitigation strategies include early schema validation, aggressive negative example mining, extensive shadow mode testing (50+ sessions before any autonomy), and DAgger-style interactive correction to fill distribution gaps. The governing execution harness enforces safety constraints regardless of policy confidence -- sandboxing, allowlists, approval gates, and branch/PR isolation are non-negotiable.

## Key Findings

### Recommended Stack

The stack follows a clear separation: Python data engineering (orjson, Pydantic, DuckDB, Polars) for episode extraction, established ML libraries (PyTorch, scikit-learn, Stable Baselines3, d3rlpy) for training, and async web frameworks (FastAPI, Redis, Streamlit) for real-time integration. The entire system builds on the Phase 0 decision to use DuckDB as the primary analytical store.

**Core technologies:**
- **orjson + Pydantic**: Fast JSONL parsing (3-5x faster than stdlib) with strict validation. Streaming line-by-line to avoid memory exhaustion on multi-GB sessions. Pydantic v2 provides Rust-backed validation and JSON Schema export.
- **DuckDB 1.4.4**: Primary analytical database with native JSON columns, Parquet export, and single-file deployment. MERGE statement (v1.4.0+) enables incremental updates. OLAP-optimized for episode queries with hybrid flat/nested schema.
- **regex + rule-based tagging**: Deterministic event classification (O_DIR, X_PROPOSE, T_TEST) using compiled patterns. Zero dependency, auditable, fast. Avoids LLM-based classification (non-deterministic, 100ms+ latency, expensive).
- **scikit-learn + PyTorch + SB3**: Staged ML pipeline. Scikit-learn baselines establish performance floor. PyTorch preference model (Bradley-Terry, 50-80K params) predicts approval. Stable Baselines3 for RL fine-tuning (PPO/DQN). d3rlpy for offline RL (Conservative Q-Learning) when online interaction is expensive.
- **FastAPI + Redis + Streamlit**: Real-time integration layer. FastAPI async endpoints, Redis Pub/Sub for fire-and-forget events, Streamlit for dashboard MVP. Bridges batch pipeline to Mission Control.

**Critical decisions from STACK.md:**
- **NOT Pandas for ETL** (3-10x slower, eager evaluation causes OOM) -- use Polars or DuckDB direct JSONL reads
- **NOT LLM for event tagging** (non-deterministic, slow, overkill) -- use compiled regex
- **NOT turn-level segmentation** (wrong unit, conflates orchestrator/executor) -- use decision-point triggers
- **NOT fine-tuning LLM as policy** (wrong paradigm for discrete action space) -- use classical RL

### Expected Features

Features divide into three categories: table stakes (system doesn't work without these), differentiators (enables training pipeline and autonomy), and anti-features (deliberately not building).

**Must have (table stakes):**
- **Episode extraction pipeline (6 stages)**: Event normalizer, tagger, decision-point segmenter, field populator, reaction labeler, constraint extractor. Without these, there is no training data.
- **Constraint management**: Extract durable orchestration rules from corrections/blocks ("avoid regex XML parsing", "require tests before auth changes"). Store with severity (warning/requires_approval/forbidden) and scope (file paths). Enforce via validator.
- **DuckDB episode database**: Primary storage with tables for episodes, sessions, commits, constraints, correlations. Supports analytical queries, incremental updates, Parquet export for ML training.
- **Schema validation + provenance tracking**: Every episode validates against JSON Schema. Every episode links to source JSONL lines, git commits, tool call IDs. Without provenance, episodes are unauditable.

**Should have (competitive):**
- **Preference model training**: Predicts approve/correct/block from (observation, proposed_action). Becomes substitute human feedback for graduated autonomy. Target: >=80% accuracy. Input for RL reward signal.
- **RAG baseline orchestrator**: Index episodes by observation context. Retrieve top-k similar past episodes. Recommend actions by frequency + success rate. Baseline before learned policy. Target: >40% top-1 accuracy, >70% top-3.
- **Shadow mode framework**: Run orchestrator recommendations alongside human decisions. Measure agreement rate. Gate before any autonomous operation. Target: >=70% agreement, zero dangerous recommendations.
- **Mission Control integration**: Structured task creation (mode/scope/gates/risk fields), review widget (reaction labels + constraint extraction), tool provenance via Gateway. Real-time episode capture vs. post-hoc parsing.

**Defer (v2+):**
- **Learned policy via RL**: Supervised learning on approved episodes, RL fine-tuning with preference model rewards. Only after RAG baseline + shadow mode validation.
- **Risk-tiered autonomy**: Low-risk (full autonomy), medium (preference approval), high (human required), critical (explicit gate). Requires preference model >=80% accuracy + constraint coverage >=95%.
- **Governing execution harness**: Sandboxing, command allowlists, branch/PR gates. The safety layer that enforces constraints regardless of policy confidence.

**Anti-features (deliberately excluded):**
- **Turn-level episodes**: Trains executor (Claude's tool calls), not orchestrator. Blurs orchestrator/executor distinction.
- **Commit-only correlation**: Hides orchestration decisions (sequencing, mistakes, recoveries, why alternatives were rejected).
- **Single unified ML model**: Too complex for available data. Hard to debug. Start modular (RAG + preference + policy).
- **Full autonomy immediately**: Catastrophic failure risk. Use staged promotion: shadow → read-only → write-in-branch → PR → limited merge.

### Architecture Approach

The architecture follows a clear data flow: batch episode extraction (6-stage pipeline) → DuckDB storage (hybrid schema) → training pipeline (RAG baseline → preference model → learned policy) → operational integration (Mission Control real-time capture + shadow mode). The critical architectural invariant is three-layer episode separation: orchestrator (primary), executor (subordinate), deliverable (validation).

**Major components:**
1. **Episode Builder Pipeline (6 stages)** — Processes heterogeneous logs (JSONL, git, terminal) through normalizer, tagger, segmenter, populator, reaction labeler, constraint extractor. Produces structured episodes with provenance. Trigger-based segmentation (not sliding window): start on O_DIR/O_GATE, end on X_PROPOSE/T_TEST/T_GIT_COMMIT/T_RISKY. Rule-based field population (mode inference, risk computation) with upgrade path to ML classifiers.

2. **DuckDB Storage Layer** — Hybrid schema: flat columns for fast queries (episode_id, project_id, timestamp, mode, reaction_label, risk), STRUCT/JSON for complex nested data (observation, action, outcome, provenance). Incremental INSERT via MERGE statement. Parquet export for ML training. Constraints table (append-only with deduplication). Multi-project registry isolates projects.

3. **Training Pipeline** — Staged progression: (1) scikit-learn baselines for mode prediction, (2) RAG baseline orchestrator with episode indexing (FAISS/BM25), (3) preference model (Bradley-Terry, 50-80K params) predicting P(approve | obs, action), (4) learned policy via supervised learning + RL fine-tuning. Each stage independently verifiable. Preference model trained offline on historical (obs, action, reaction) tuples.

4. **Validator (Genus-Based Multi-Layer)** — Five validation layers: schema validity (JSON Schema), evidence grounding (observation precedes action), non-contradiction (mode vs gates), constraint enforcement (diffs vs rules), episode integrity (reaction labels attach correctly). Prevents garbage episodes entering training.

5. **Mission Control Integration (Future)** — Real-time episode capture via structured task lifecycle: planning Q&A → execution via Gateway → review widget. Task contains orchestrator action fields (mode/scope/gates/risk). Review captures reaction labels + extracts constraints inline. Tool provenance recorded via WebSocket. Deterministic join keys (task_id) vs. probabilistic commit correlation.

**Key patterns:**
- **Trigger-based segmentation over sliding windows**: Respects actual decision structure. Decision points may take 30 seconds or 20 minutes.
- **Hybrid DuckDB schema**: Fast analytical queries on flat columns, full episode data in nested structures. No JSON parsing overhead for common filters.
- **Source adapter + canonical event**: Each data source has dedicated adapter. Rest of pipeline only sees canonical events. Decouples format changes from pipeline logic.
- **Three-layer episode architecture**: Orchestrator (primary learning target for OpenClaw), executor (subordinate data for Claude optimization), deliverable (validation via commits). Never train orchestrator on executor data.

### Critical Pitfalls

1. **Training the Executor Instead of the Orchestrator (Genus Violation)** — Capturing tool calls (Read/Edit/Bash) as the "action" instead of orchestrator directives (mode/scope/gates/constraints). This trains OpenClaw to "act like Claude" (tool micro-steps) instead of "act like the human" (strategic decisions). **Prevention**: Enforce three-layer architecture at schema level. Validator rejects episodes where orchestrator_action contains tool call signatures. **Warning signs**: Episode count equals tool call count; mode is always "Implement"; learned policy recommends tool calls.

2. **Decision-Point vs. Turn Confusion** — Segmenting at every user-assistant boundary instead of genuine decision points (new evidence, proposal, test result, risk boundary). Produces noisy episodes: many contain no decision, others split atomic decisions. **Prevention**: Trigger-based segmentation (O_DIR/O_GATE starts, X_PROPOSE/T_TEST/T_GIT_COMMIT ends). Validate episode density: ~3-5 per session, not 1:1 with turns. **Warning signs**: Episode count equals user message count; episodes lack decision-boundary triggers in provenance.

3. **Approval Bias / Survivorship Bias** — Training data dominated by successful episodes (approve reactions) because corrections are harder to label, mistakes are often erased during recovery, and abandoned sessions lack commits. Policy becomes overconfident, cannot handle failure or escalation. **Prevention**: Explicitly extract negative episodes from corrections. Target: >=20% negative examples (correct/block/redirect). Mine abandoned sessions. **Warning signs**: >85% approve, <10% correct/block; policy never recommends Explore or human gates.

4. **Reaction Label Noise** — Keyword-based labeler misclassifies human feedback. "Looks good, but change variable name" as "approve" (should be "correct"). Noisy labels corrupt preference model. **Prevention**: Assign confidence scores to every label. Manual validation set of 100+ episodes. Target: >=80% accuracy before using for training. Never train on low-confidence labels (<0.7). **Warning signs**: Manual spot-check reveals >20% mislabeled; preference model achieves >95% accuracy (overfitting to noise).

5. **Constraint Extraction False Positives** — Rules too broad or strict. "Don't use regex for XML" extracted as "avoid regex" (repo-wide) blocks valid regex for logs/URLs. **Prevention**: Always extract explicit scope. Default to files currently worked on, NOT repo-wide. "correct" reactions → requires_approval, "block" → forbidden. Constraint review step before activation. Test against historical approved episodes (if >10% would be flagged, too broad). **Warning signs**: Constraints block previously-approved work; scopes mostly repo-wide; validators flagged but humans override.

6. **Distribution Shift at Deployment** — Policy performs well offline but fails online because it encounters states not in training data (human never visited). Small errors compound exponentially. **Prevention**: Start with RAG baseline (degrades gracefully). Shadow mode for >=50 sessions before autonomy. DAgger-style interactive correction on mistakes. Harness forces escalation if confidence drops for 3 consecutive decisions. **Warning signs**: Offline accuracy >80%, shadow mode <60%; performance degrades rapidly after first autonomous decisions.

7. **Mode Inference Below Threshold** — Keyword-based classifier fails to reach 85% accuracy. "Investigate bug" as Explore (should be Triage), "clean up auth" as Implement (should be Refactor), multi-modal directives classified as only first/last mode. **Prevention**: Build manual validation set first (100+ labeled episodes). Measure confusion matrix. Accept multi-modal episodes. Fallback: lightweight LLM classifier (Claude Haiku) for ambiguous cases. **Warning signs**: One mode >50%; confusion matrix shows systematic errors; mode distribution doesn't match workflow intuition.

## Implications for Roadmap

Based on research, the project requires five major phases with a clear dependency chain: episode extraction foundation → constraint management → training infrastructure → Mission Control integration → graduated autonomy. Early phases focus on proving batch pipeline quality before adding real-time complexity. Shadow mode is the critical gate before any autonomous operation.

### Phase 1: Episode Builder Foundation
**Rationale:** Core pipeline (Stages A-C: normalize, tag, segment) must work before anything else. Unblocks all downstream work. Historical data processing proves schema and segmentation rules before investing in real-time capture.

**Delivers:** Canonical event model, source adapters (Claude JSONL + git), event normalizer, event tagger (keyword/heuristic), decision-point segmenter. Output: episode segments with provenance links to source logs.

**Addresses:** Event stream normalizer, event tagger, decision-point segmenter (table stakes from FEATURES.md). Uses: orjson + Pydantic + DuckDB (STACK.md). Implements: Episode Builder Pipeline stages A-C (ARCHITECTURE.md).

**Avoids:** Pitfall #2 (decision-point vs. turn confusion) by using trigger-based segmentation. Pitfall #7 (mode inference accuracy) starts here with keyword rules and manual validation set.

**Research needs:** MINIMAL. Patterns are standard (adapters, normalization, rule-based classification). Segments can be validated against manual spot-checks.

### Phase 2: Episode Population & Constraint Store
**Rationale:** Segments must be filled with structured fields (observation, action, outcome) and constraints extracted from corrections. Produces training-ready episodes in DuckDB. Constraint store is foundational for validation and enforcement.

**Delivers:** Field populator (Stage D: mode inference, risk computation, observation/action/outcome), reaction labeler (Stage E), constraint extractor (Stage F), DuckDB schema + loader, constraint store table. Output: populated episodes in DuckDB, constraint database.

**Addresses:** Episode field populator, reaction labeler, constraint extractor, constraint store (table stakes from FEATURES.md). Uses: PyYAML for config, DuckDB MERGE for incremental updates (STACK.md). Implements: Pipeline stages D-F + storage layer (ARCHITECTURE.md).

**Avoids:** Pitfall #1 (genus violation) by enforcing orchestrator-level action schema. Pitfall #4 (reaction label noise) with confidence scores and manual validation. Pitfall #5 (constraint false positives) with explicit scope inference and backtest against approved episodes.

**Research needs:** LOW. Mode inference keywords and reaction labeling heuristics will need tuning against manual validation set. Constraint scope inference may need iteration.

### Phase 3: Validation Infrastructure
**Rationale:** Episodes must be trustworthy before training. Genus-based multi-layer validation catches garbage data early. Exports to Parquet enable ML pipelines. This is the quality gate for all downstream work.

**Delivers:** Schema validator (JSON Schema), evidence grounding validator, non-contradiction checker, constraint enforcement validator, episode integrity checker. Parquet + JSONL export. Manual validation set (100+ labeled episodes). Quality metrics dashboard.

**Addresses:** Schema validation, causal ordering validation, episode integrity check (table stakes from FEATURES.md). Evidence grounding, non-contradiction (differentiators from FEATURES.md). Uses: jsonschema library (STACK.md). Implements: Validator component (ARCHITECTURE.md).

**Avoids:** Multiple pitfalls by catching errors before training. Pitfall #4 (reaction label noise) via validation set. Pitfall #7 (mode inference accuracy) measured here.

**Research needs:** MINIMAL. Validation patterns are straightforward. Focus is on thresholds (>=85% mode accuracy, >=80% reaction accuracy).

### Phase 4: Training Infrastructure (RAG Baseline)
**Rationale:** Simple retrieval-based orchestrator establishes performance floor before ML complexity. Proves episode quality is sufficient for recommendations. Provides explainability via provenance. RAG baseline is prerequisite for preference model (generates candidates to score).

**Delivers:** Feature engineering (observation/action → embeddings), episode indexing (FAISS or BM25), RAG retrieval policy (top-k similar episodes), recommendation ranking (frequency + success rate), explainability (source episode citation). Objective reward proxies (tests/lint/diff_risk).

**Addresses:** Episode indexing, RAG retrieval policy, recommendation explainability, objective reward proxy computation (differentiators from FEATURES.md). Uses: scikit-learn for baselines, FAISS/BM25 for retrieval (STACK.md). Implements: Training pipeline Stage 1 (ARCHITECTURE.md).

**Avoids:** Pitfall #3 (approval bias) by including both positive and negative examples in retrieval. Establishes baseline before ML complexity.

**Research needs:** MEDIUM. Retrieval approaches (BM25 vs. embeddings vs. hybrid) need comparison. Feature encoding for observation/action similarity needs experimentation. Target: >40% top-1, >70% top-3 accuracy.

### Phase 5: Shadow Mode & Preference Model
**Rationale:** Cannot deploy any autonomy until shadow mode proves >=70% agreement with human decisions. Preference model required for risk-tiered autonomy (predicts approval for medium-risk tasks). This is the gate before Phase 6+ (autonomy).

**Delivers:** Shadow mode framework (run recommendations alongside human, measure agreement), preference model training pipeline (Bradley-Terry, PyTorch, 50-80K params), reward signal for RL (preference + objective proxies), calibration (confidence matches actual approval rate). Integration testing on >=50 sessions.

**Addresses:** Preference model training, shadow mode framework (differentiators from FEATURES.md). Uses: PyTorch, training data export to Parquet (STACK.md). Implements: Training pipeline Stages 2-3 (ARCHITECTURE.md).

**Avoids:** Pitfall #6 (distribution shift) by extensive shadow mode testing. Measures divergence severity, not just agreement rate. Pitfall #4 (reaction label noise) caught here if preference model accuracy is too high (overfitting to noise).

**Research needs:** MEDIUM-HIGH. Preference model architecture (Bradley-Terry vs. IRPO), calibration techniques, shadow mode metrics (agreement, divergence severity, false positive rate). Budget 2-3 months for shadow mode.

### Phase 6+: Mission Control Integration & Graduated Autonomy (Future)
**Rationale:** Deferred until RAG baseline + shadow mode validation complete. Real-time capture adds complexity; prove batch pipeline first. Graduated autonomy only after preference model >=80% + shadow mode >=70% + constraint coverage >=95%.

**Delivers:** Structured task creation (mode/scope/gates/risk fields in Mission Control), review widget (reaction labels + inline constraint extraction), tool provenance via OpenClaw Gateway WebSocket, workflow state gates (epistemic states), governing execution harness (sandboxing, allowlists, branch/PR gates), risk-tiered autonomy (low/medium/high/critical), learned policy via RL fine-tuning.

**Addresses:** Mission Control integration, risk-tiered autonomy, governing execution harness (differentiators and v2+ from FEATURES.md). Uses: FastAPI + Redis + Streamlit, SB3 + d3rlpy for RL (STACK.md). Implements: Real-time capture + operational integration (ARCHITECTURE.md).

**Avoids:** Pitfall #8 (anti-pattern: Mission Control before batch pipeline). Pitfall #6 (distribution shift) with DAgger corrections and continuous shadow mode.

**Research needs:** HIGH. Mission Control schema changes, Gateway WebSocket integration, harness enforcement mechanisms, RL fine-tuning (SB3 PPO vs. d3rlpy CQL), graduated autonomy rollout strategy.

### Phase Ordering Rationale

**Why this order:**
1. **Foundation first (Phases 1-2)**: Episode extraction and constraint management are load-bearing for everything. Cannot train without episodes. Cannot enforce without constraints.
2. **Quality gate (Phase 3)**: Validation infrastructure prevents garbage from entering training. Must validate episode quality (>=85% mode accuracy, >=80% reaction accuracy) before ML investment.
3. **Simple before complex (Phase 4 before 5)**: RAG baseline establishes performance floor and provides explainability. Preference model only justified after RAG proves episode quality is sufficient.
4. **Shadow mode gate (Phase 5)**: Extensive testing before any autonomy. >=50 sessions, >=70% agreement, zero dangerous recommendations. Non-negotiable safety gate.
5. **Real-time last (Phase 6+)**: Mission Control integration deferred until batch pipeline proven. Real-time adds complexity (WebSocket, state sync, UI). Don't build it until schema and segmentation rules validated on historical data.

**Dependency chain:**
```
Phase 1 (pipeline A-C) → Phase 2 (pipeline D-F + storage) → Phase 3 (validation + export)
                                                                      ↓
                                                              Phase 4 (RAG baseline)
                                                                      ↓
                                                              Phase 5 (shadow mode + preference)
                                                                      ↓
                                                              Phase 6+ (MC integration + autonomy)
```

**Grouping rationale:**
- Phases 1-2: Batch extraction (can iterate on schema/segmentation)
- Phase 3: Quality gate (validates before training)
- Phases 4-5: Training pipeline (RAG → preference → shadow mode)
- Phase 6+: Operational deployment (real-time + autonomy)

**Pitfall mitigation by phase:**
- Phase 1: Addresses #2 (decision-point segmentation), starts #7 (mode inference)
- Phase 2: Addresses #1 (genus violation), #4 (reaction noise), #5 (constraint false positives)
- Phase 3: Validates #4 (reaction accuracy), #7 (mode accuracy), provides quality metrics
- Phase 4: Establishes baseline, avoids #3 (approval bias) via negative examples
- Phase 5: Gates #6 (distribution shift) via shadow mode, validates preference model
- Phase 6+: Enforces safety (#6) via harness, continuous monitoring

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 4 (RAG Baseline)**: Retrieval approaches (BM25, embeddings, hybrid), feature encoding for similarity, indexing at scale (5,000+ episodes). Experiment with retrieval libraries (FAISS, ChromaDB, DuckDB vector extension). Target metrics need refinement.
- **Phase 5 (Preference Model + Shadow Mode)**: Preference model architecture (Bradley-Terry vs. IRPO for scaling), calibration techniques (Platt scaling, isotonic regression), shadow mode metrics design (agreement, divergence severity, dangerous recommendation detection). Budget 2-3 months for shadow mode iteration.
- **Phase 6+ (Mission Control Integration)**: Schema changes required for structured tasks (mode/scope/gates/risk fields), OpenClaw Gateway WebSocket integration patterns, bidirectional sync (episodes back to MC for display), state gate enforcement. Requires Mission Control collaboration.
- **Phase 6+ (Graduated Autonomy)**: RL fine-tuning approach (SB3 PPO vs. d3rlpy CQL for offline RL), DAgger-style interactive correction implementation, harness enforcement mechanisms (sandboxing, allowlists, branch isolation), rollout strategy (shadow → read-only → branch → PR → merge).

**Phases with standard patterns (minimal research):**
- **Phase 1 (Episode Builder Foundation)**: Event normalization, adapters, rule-based tagging are well-established patterns. Validation via manual spot-checks.
- **Phase 2 (Population & Constraints)**: Field extraction from structured data, constraint storage in relational DB are straightforward. Iteration on heuristics expected, not architectural research.
- **Phase 3 (Validation Infrastructure)**: JSON Schema validation, assertion-based checks are standard. Manual validation set creation is labor-intensive but not technically complex.

**Research timing:**
- **Phase 0-1**: No research needed (infrastructure setup, basic extraction)
- **Phase 2-3**: Minimal research (heuristic tuning, validation thresholds)
- **Phase 4**: 1-2 weeks research on retrieval approaches before implementation
- **Phase 5**: 2-3 weeks research on preference model architecture + calibration
- **Phase 6+**: 3-4 weeks research on MC integration + RL approaches before design

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions verified via PyPI (2026-02-10). DuckDB, orjson, Pydantic, SB3, d3rlpy are all proven technologies with mature documentation. Stack decisions grounded in Phase 0 architectural choices. Alternative analysis comprehensive. |
| Features | MEDIUM-HIGH | Domain is novel (agentic orchestration policy learning), but features grounded in project design docs + RLHF/IRL literature + agentic RAG ecosystem. MVP definition clear (historical episode extraction). Anti-features well-justified (turn-level episodes, commit-only correlation rejected). Uncertainty around ML-based mode classifier timing (v0 vs. v1). |
| Architecture | HIGH | Grounded in authoritative project design documents (`AUTHORITATIVE_DESIGN.md`, episode schemas, `PHASE-0-DECISIONS.md`). Three-layer architecture (orchestrator/executor/deliverable) is core invariant. Six-stage pipeline well-specified. Patterns are standard (adapters, hybrid schemas, trigger-based segmentation). Build order clear. |
| Pitfalls | MEDIUM-HIGH | Critical pitfalls (#1 genus violation, #2 decision-point confusion, #6 distribution shift) verified against published research (Simchowitz 2025, RLHF limitations literature). Domain-specific pitfalls (#3 approval bias, #4 reaction noise, #5 constraint false positives) derived from first-principles analysis + project design risk register. Some pitfalls anticipatory (not yet observed in practice). Recovery strategies specified. |

**Overall confidence:** HIGH

The project has unusually strong design foundations (authoritative specification, JSON schemas, worked examples, Phase 0 decisions locked). Research uncertainty is concentrated in ML training approaches (Phases 4-5) where experimentation is expected. Core extraction pipeline (Phases 1-3) has high confidence because patterns are standard and design is detailed.

### Gaps to Address

**Gap 1: Mode inference accuracy on real data**
- **Issue**: Keyword-based mode classifier targets >=85% accuracy. Actual performance unknown until validated on manual set.
- **Mitigation**: Phase 2 includes manual validation set creation (100+ labeled episodes). If accuracy <80%, immediate pivot to LLM classifier (Claude Haiku) for ambiguous cases. Budget 1-2 weeks for iteration.
- **Decision point**: End of Phase 2. If accuracy >=85%, continue with keywords. If 80-85%, acceptable for v0. If <80%, upgrade path required.

**Gap 2: RAG retrieval approach (BM25 vs. embeddings vs. hybrid)**
- **Issue**: Unknown which retrieval method performs best for episode similarity. BM25 (keyword) vs. sentence-transformers (semantic) vs. hybrid have different strengths.
- **Mitigation**: Phase 4 includes small-scale comparison on first 500 episodes. Evaluate top-k accuracy for each approach. Start with simplest (BM25), upgrade if insufficient.
- **Decision point**: Early Phase 4. Experiment timebox: 1-2 weeks.

**Gap 3: Preference model architecture (Bradley-Terry vs. IRPO)**
- **Issue**: Bradley-Terry is O(n^2) pairwise comparisons. IRPO (Jan 2026 research) claims efficient pointwise scoring that scales better. Unknown which is better for our data size (1000s of episodes).
- **Mitigation**: Phase 5 research includes architecture comparison. Start with Bradley-Terry (well-understood, proven). Upgrade to IRPO if scaling issues or better performance observed.
- **Decision point**: Early Phase 5. Experiment before full implementation.

**Gap 4: Shadow mode agreement threshold**
- **Issue**: Target >=70% agreement is based on RLHF literature norms, not validated for orchestration domain. Threshold may be too low (safety-critical) or too high (blocks useful autonomy).
- **Mitigation**: Phase 5 shadow mode measures both agreement rate and divergence severity. Adjust threshold based on actual dangerous recommendation rate (target: zero). If 70% agreement but 5% dangerous recommendations, threshold is wrong.
- **Decision point**: During Phase 5 shadow mode testing. Iterative calibration.

**Gap 5: Mission Control schema changes coordination**
- **Issue**: Structured task creation (mode/scope/gates/risk fields) requires Mission Control schema changes. Unknown when MC team can support this.
- **Mitigation**: Phase 6+ is explicitly deferred until MC readiness confirmed. Batch episode extraction (Phases 1-5) independent of MC. Design MC integration as additive, not foundational.
- **Decision point**: Before Phase 6 planning. Coordinate with MC team 1-2 months in advance.

**Gap 6: Constraint store deduplication strategy**
- **Issue**: Multiple corrections may extract similar constraints ("avoid regex in XML parser" vs. "don't use regex for XML"). Deduplication logic not specified.
- **Mitigation**: Phase 2 constraint extractor includes fuzzy matching (edit distance, semantic similarity) to detect duplicates. Human review for proposed merges. Constraint IDs are stable (hash of normalized text + scope).
- **Decision point**: Phase 2 implementation. Experiment with deduplication approaches.

**Gap 7: Executor episode layer (subordinate data for Claude optimization)**
- **Issue**: Design specifies three layers (orchestrator/executor/deliverable). Executor episodes are "future work" but may be needed for comprehensive system.
- **Mitigation**: Focus Phases 1-5 on orchestrator episodes (primary learning target). Defer executor episodes to Phase 7+ or separate workstream. Extraction logic can be parallelized (different pipeline, same source logs).
- **Decision point**: After Phase 5 shadow mode. Revisit if Claude executor optimization becomes priority.

## Sources

### Primary (HIGH confidence)
- **Project design documents**: `docs/design/AUTHORITATIVE_DESIGN.md`, `docs/design/WHY_TURN_LEVEL - Improved.md`, `docs/design/Mission Control - supervisory control layer.md`, `docs/design/The Genus Method - Justification.md` — Canonical specifications for episode extraction, three-layer architecture, pipeline stages, validation, genus-based classification
- **Project schemas**: `data/schemas/orchestrator-episode.schema.json`, `data/schemas/constraint.schema.json` — JSON Schema Draft 2020-12 defining episode and constraint structures
- **Project decisions**: `.planning/PHASE-0-DECISIONS.md`, `.planning/DESIGN_INTEGRATION_REVIEW.md` — Infrastructure decisions (DuckDB, session backup, multi-project registry)
- **PyPI package index**: Version numbers verified via `pip index versions` on 2026-02-10 for all stack components
- **DuckDB official docs**: duckdb.org/docs/stable/ — JSON handling, MERGE statement, Python API, Parquet export, thread safety
- **Pydantic v2 migration guide**: Field validators, Rust-backed performance, JSON Schema export
- **Stable Baselines3 documentation**: Algorithm implementations, discrete action support, Gymnasium API
- **d3rlpy documentation**: Offline RL, DiscreteCQL for fixed datasets

### Secondary (MEDIUM confidence)
- **orjson benchmarks**: msgspec docs, community benchmarks — 3-5x performance vs. stdlib json, 8.9x memory efficiency
- **Bradley-Terry implementation patterns**: github.com/RLHFlow/RLHF-Reward-Modeling — Reward model training for RLHF
- **IRPO research**: arXiv:2601.00677v1 (Jan 2026) — Scaling Bradley-Terry via pointwise scoring for RLHF
- **IRL from demonstrations survey**: shadecoder.com/topics/inverse-reinforcement-learning (2025) — Inverse reinforcement learning patterns
- **Hybrid-AIRL**: arXiv:2511.21356 (2025) — Stable reward/policy learning from demonstrations
- **Active IRL**: NeurIPS 2024/98880 — Reducing demonstration costs
- **Agentic RAG ecosystem**: LangGraph (top-rated 2025-2026 framework), FAISS, BM25, hybrid vector-graph indexes
- **Amazon Bedrock AgentCore**: aws.amazon.com/blogs/aws/amazon-bedrock-agentcore (2025) — Quality evaluations and policy controls for AI agents
- **FastAPI WebSocket patterns**: oneuptime.com/blog/2026-02-02-fastapi-websockets/ — ConnectionManager, Redis integration
- **Redis Pub/Sub patterns**: oneuptime.com/blog/2026-01-26-redis-pubsub-implementation/ — Fire-and-forget model

### Tertiary (LOW confidence, needs validation)
- **Distribution shift in imitation learning**: Simchowitz et al. (2025), arXiv:2503.09722 — Exponential compounding error in continuous-action IL. Validation needed: applies to discrete action spaces?
- **RLHF limitations**: BlueDot Impact (2024), Lakera (2024) — Approval bias, sycophancy, feedback scalability. Validation needed: severity in orchestration domain?
- **PPO implementation study**: arxiv.org/html/2503.22575v2 — Cross-framework implementation discrepancies. Validation needed: SB3 specifically?

---
*Research completed: 2026-02-10*
*Ready for roadmap: yes*
