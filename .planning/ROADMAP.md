# Roadmap: Orchestrator Policy Extraction

## Overview

This roadmap delivers a system that extracts decision-point episodes from historical Claude Code sessions and uses them to train an orchestrator policy for graduated autonomy. The journey moves from raw log processing through a six-stage extraction pipeline, into validated episode storage with durable constraints, through a RAG baseline with shadow mode testing, and finally into real-time capture via Mission Control. Each phase delivers a verifiable capability that unblocks the next.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Event Stream Foundation** - Normalize raw logs into tagged canonical events and segment into decision-point boundaries
- [x] **Phase 2: Episode Population & Storage** - Populate episode fields, label reactions, and store complete episodes in DuckDB
- [x] **Phase 3: Constraint Management** - Extract durable orchestration constraints from corrections and manage them with severity and scope
- [x] **Phase 4: Validation & Quality** - Validate episode quality through multi-layer checks and build gold-standard labeled dataset
- [x] **Phase 5: Training Infrastructure** - Deploy RAG baseline orchestrator and validate via shadow mode testing
- [x] **Phase 6: Mission Control Integration** - Capture episodes in real-time from structured tasks with review UI and tool provenance

## Phase Details

### Phase 1: Event Stream Foundation
**Goal**: Raw session logs (JSONL + git history) are transformed into tagged, segmented decision-point boundaries ready for episode population
**Depends on**: Nothing (first phase)
**Requirements**: EXTRACT-01, EXTRACT-02, EXTRACT-03, DATA-03
**Success Criteria** (what must be TRUE):
  1. System reads Claude Code JSONL files and git history, producing a unified event stream with canonical fields (event_id, ts_utc, actor, type, payload, links)
  2. Every event in the stream carries a classification tag (O_DIR, O_GATE, O_CORR, X_PROPOSE, X_ASK, T_TEST, T_LINT, T_GIT_COMMIT, T_RISKY) assigned by rule-based tagger
  3. Event stream is segmented into decision-point episode boundaries using start triggers (O_DIR, O_GATE) and end triggers (X_PROPOSE, X_ASK, T_TEST result, T_RISKY, T_GIT_COMMIT, 30min timeout)
  4. Configuration (risk model, event tag patterns, reaction keywords, mode inference rules) loads from YAML file and drives tagger and segmenter behavior
**Plans:** 5 plans in 4 waves

Plans:
- [x] 01-01-PLAN.md — Config system + data models + DuckDB schema (Wave 1)
- [x] 01-02-PLAN.md — DuckDB JSONL ingestion + git history + normalization (Wave 2)
- [x] 01-03-PLAN.md — Multi-pass event tagger [TDD] (Wave 3)
- [x] 01-04-PLAN.md — Episode segmenter [TDD] (Wave 3)
- [x] 01-05-PLAN.md — Pipeline runner + CLI + integration (Wave 4)

### Phase 2: Episode Population & Storage
**Goal**: Episode segments are populated with structured fields (observation, action, outcome), reactions are labeled, and complete episodes are stored in DuckDB with full provenance
**Depends on**: Phase 1
**Requirements**: EXTRACT-04, EXTRACT-05, DATA-01, DATA-02, DATA-04
**Success Criteria** (what must be TRUE):
  1. Each episode segment is populated with derived observation (context before decision), orchestrator_action (mode/scope/gates/constraints), and outcome (what happened after)
  2. Human reactions following episode boundaries are labeled (approve/correct/redirect/block/question) with confidence scores
  3. Episodes are stored in DuckDB with hybrid schema (flat columns for queryable fields + STRUCT/JSON for nested data) and support incremental updates via MERGE
  4. Every stored episode validates against the JSON Schema (orchestrator-episode.schema.json) ensuring structural correctness
  5. Every episode carries provenance links (source JSONL file + line ranges, git commits, tool call IDs) enabling audit trail back to raw data
**Plans:** 4 plans in 3 waves

Plans:
- [x] 02-01-PLAN.md — Episode Pydantic model + DuckDB hybrid schema + EpisodeValidator (Wave 1)
- [x] 02-02-PLAN.md — EpisodePopulator [TDD] (Wave 2)
- [x] 02-03-PLAN.md — ReactionLabeler [TDD] (Wave 2)
- [x] 02-04-PLAN.md — Pipeline integration + episode writer + end-to-end tests (Wave 3)

### Phase 3: Constraint Management
**Goal**: Corrections and blocks in episode reactions are converted into durable, enforceable orchestration constraints with severity levels and explicit scope
**Depends on**: Phase 2
**Requirements**: EXTRACT-06, CONST-01, CONST-02, CONST-03, CONST-04
**Success Criteria** (what must be TRUE):
  1. System extracts constraints from correct/block reactions, producing structured constraint objects with text description, severity level, scope paths, and detection hint patterns
  2. Constraints are stored in a version-controlled JSON file (data/constraints.json) with unique IDs and metadata
  3. Severity levels (warning / requires_approval / forbidden) are assigned based on reaction type and keyword analysis -- "correct" reactions produce warning/requires_approval, "block" reactions produce forbidden
  4. Constraint scope (file-level, module-level, or repo-wide) is inferred from mentioned paths, defaulting to narrowest applicable scope rather than repo-wide
**Plans:** 2 plans in 2 waves

Plans:
- [x] 03-01-PLAN.md — ConstraintExtractor with severity, scope, hints [TDD] (Wave 1)
- [x] 03-02-PLAN.md — ConstraintStore + pipeline integration + CLI stats (Wave 2)

### Phase 4: Validation & Quality
**Goal**: Episode quality is verified through multi-layer validation, a gold-standard labeled dataset exists for accuracy measurement, and quality metrics meet thresholds for training readiness
**Depends on**: Phase 3
**Requirements**: VALID-01, VALID-02, VALID-03
**Success Criteria** (what must be TRUE):
  1. Genus-based validator runs five layers of checks (schema validity, evidence grounding, non-contradiction, constraint enforcement, episode integrity) and rejects episodes that fail any layer
  2. A manual validation workflow produces a gold-standard set of 100+ episodes with verified mode labels, reaction labels, and constraint extractions
  3. Quality metrics are calculated and tracked: mode inference accuracy >=85%, reaction label confidence >=80%, constraint extraction rate >=90% of corrections
  4. Episodes that pass validation can be exported to Parquet format for ML training pipelines
**Plans:** 2 plans in 2 waves

Plans:
- [x] 04-01-PLAN.md — GenusValidator with five validation layers [TDD] (Wave 1)
- [x] 04-02-PLAN.md — Gold-standard workflow + metrics + Parquet export + CLI (Wave 2)

### Phase 5: Training Infrastructure
**Goal**: A RAG baseline orchestrator recommends actions from similar past episodes, and shadow mode testing validates recommendations against human decisions before any autonomous operation
**Depends on**: Phase 4
**Requirements**: TRAIN-01, TRAIN-02
**Success Criteria** (what must be TRUE):
  1. RAG baseline retrieves top-k similar episodes by observation context and recommends orchestrator actions with explainable provenance (citing source episodes)
  2. Shadow mode framework runs recommendations alongside actual human decisions across >=50 sessions, measuring agreement rate
  3. Shadow mode achieves >=70% agreement threshold with zero dangerous recommendations before any autonomous operation is permitted
**Plans:** 3 plans in 3 waves

Plans:
- [x] 05-01-PLAN.md — Embedder + search text + DuckDB schema extensions [TDD] (Wave 1)
- [x] 05-02-PLAN.md — HybridRetriever + Recommender + danger detection [TDD] (Wave 2)
- [x] 05-03-PLAN.md — Shadow mode runner + evaluator + reporter + CLI (Wave 3)

### Phase 6: Mission Control Integration
**Goal**: Episodes are captured in real-time from Mission Control structured tasks, eliminating post-hoc log parsing for ongoing sessions
**Depends on**: Phase 5 (batch pipeline proven), Mission Control repository access (external blocker)
**Requirements**: MC-01, MC-02, MC-03, MC-04
**Success Criteria** (what must be TRUE):
  1. Episodes are captured in real-time from Mission Control task lifecycle (task creation, planning, execution, review) without requiring post-hoc JSONL parsing
  2. Tool provenance (tool calls, files touched, commands run, test results, commits) streams from OpenClaw Gateway during task execution and attaches to episodes
  3. A review widget in Mission Control allows labeling reactions (approve/correct/redirect/block/question) with optional inline constraint extraction workflow
  4. Episodes are stored in Mission Control's SQLite database (episodes, episode_events, constraints, approvals, commit_links tables) enabling dashboard integration
**Plans:** 4 plans in 3 waves

Plans:
- [x] 06-01-PLAN.md — SQLite episode schema + DuckDB bridge + TypeScript CRUD (Wave 1)
- [x] 06-02-PLAN.md — Episode builder + task lifecycle mapper + API routes (Wave 2)
- [x] 06-03-PLAN.md — Tool provenance capture from OpenClaw Gateway (Wave 2)
- [x] 06-04-PLAN.md — Review widget + constraint extraction + SSE + timeline (Wave 3)

### Phase 7: Objectivism Project Knowledge Extraction
**Goal**: Run a parallel agent analysis of the Objectivism Library Semantic Search project — its session files and git history — to produce four structured documents answering the Knowledge Extraction Prompt: (1) Reusable Knowledge Guide, (2) Problem Formulation Retrospective, (3) Validation Gate Audit, (4) Decision Amnesia Report.
**Depends on**: Phase 6 (pipeline proven), objectivism repo cloned locally, sessions ingested
**Requirements**: Parallel agents reading raw JSONL sessions + git history; synthesis into 4 output documents
**Success Criteria** (what must be TRUE):
  1. All four analysis documents exist in `docs/analysis/objectivism-knowledge-extraction/`
  2. Each document addresses its full analysis as specified in the Knowledge Extraction Prompt
  3. Documents are grounded in specific evidence from session files and git commits (not generic)
  4. The spiral pattern (initial grasp → dead end → breakthrough) is traceable through the analysis
**Plans:** Completed via parallel agent analysis (no formal plan files)

### Phase 8: Knowledge Architecture Conciliation
**Goal**: Take the learnings from Phase 7 and establish a concrete roadmap for reconciling the Knowledge Extraction approach (project-level wisdom: breakthroughs, dead ends, validation gates, decision amnesia) with the current episode-based orchestrator policy system. Define what new capabilities are needed and how they extend the existing architecture.
**Depends on**: Phase 7 (four analysis documents complete)
**Requirements**: Conversation-driven synthesis; review of Phase 7 outputs; roadmap design
**Success Criteria** (what must be TRUE):
  1. A clear mapping between the Knowledge Extraction framework and the current episode model — what each captures, what each misses
  2. New requirements identified: richer episode structure, project-level wisdom capture, anti-amnesia encoding, extended constraint store
  3. A concrete roadmap of new phases added to this project to implement the reconciled approach
  4. The question "what should a future agent be able to start with?" is answered at both the micro (decision) and macro (project wisdom) levels
**Plans:** Completed via synthesis document: `docs/analysis/knowledge-architecture-conciliation/PHASE_8_SYNTHESIS.md`

### Phase 9: Obstacle Escalation Detection
**Goal**: The event tagger recognizes obstacle escalation sequences (blocked path → alternative path bypassing authorization) and creates O_ESC episodes. Escalation episodes without authorization automatically generate forbidden constraints.
**Depends on**: Phase 8 (gap analysis and requirements defined)
**Requirements**: ESCALATE-01, ESCALATE-02, ESCALATE-03
**Success Criteria** (what must be TRUE):
  1. Tagger produces O_ESC tag when it detects the blocked-path → alternative-path-bypass sequence
  2. O_ESC episodes are created with `orchestrator_action.mode = ESCALATE` and links to the bypassed constraint
  3. Escalation episodes without APPROVE reaction generate `forbidden` constraints automatically
  4. Shadow mode reports escalation rate per session (target: 0 unauthorized escalations)
  5. 30 test cases cover escalation detection (confirmed positive examples from objectivism sessions)
**Plans:** 5 plans in 3 waves

Plans:
- [x] 09-01-PLAN.md — Models, config, schema foundation (Wave 1)
- [x] 09-02-PLAN.md — EscalationDetector [TDD] (Wave 2)
- [x] 09-03-PLAN.md — EscalationConstraintGenerator [TDD] (Wave 2)
- [x] 09-04-PLAN.md — Pipeline integration + shadow metrics + integration tests (Wave 3)
- [x] 09-05-PLAN.md — Gap closure: real session JSONL fixtures + fixture-loading tests (Wave 1)

### Phase 10: Cross-Session Decision Durability
**Goal**: The system tracks which constraints were read, honored, and violated in each session. A decision durability index gives each constraint a survival score across sessions. Sessions that violate active constraints are flagged as amnesia events.
**Depends on**: Phase 9 (escalation as a distinct episode type)
**Requirements**: AMNESIA-01, AMNESIA-02, AMNESIA-03
**Success Criteria** (what must be TRUE):
  1. Session start audit surfaces all constraints relevant to current task scope within 3 minutes
  2. Decision durability index: each constraint has `durability_score` = sessions_honored / sessions_active
  3. Cross-session amnesia detection: sessions violating pre-existing constraints produce amnesia events
  4. `data/decisions.json` stores ACTIVE/SUPERSEDED scope, method, and architecture decisions
  5. `python -m src.pipeline.cli audit session` reports amnesia events for any session
**Plans:** 3 plans in 3 waves

Plans:
- [x] 10-01-PLAN.md — Constraint schema migration + DuckDB eval tables + DurabilityConfig (Wave 1)
- [x] 10-02-PLAN.md — Scope extractor + evaluator + amnesia detector + durability index (Wave 2)
- [x] 10-03-PLAN.md — Pipeline Step 14 + CLI audit commands + ShadowReporter integration (Wave 3)

### Phase 11: Project-Level Wisdom Layer
**Goal**: The pipeline captures and retrieves project-level knowledge (breakthroughs, dead ends, scope decisions) as structured entities in a `project_wisdom` DuckDB table. The RAG retriever uses these alongside episode context.
**Depends on**: Phase 10 (cross-session tracking in place)
**Requirements**: WISDOM-01, WISDOM-02, WISDOM-03
**Success Criteria** (what must be TRUE):
  1. `project_wisdom` table stores Breakthrough, DeadEnd, ScopeDecision, MethodDecision entities
  2. RAG retriever returns relevant wisdom entities alongside top-k episodes
  3. Scope decision enforcement: `python -m src.pipeline.cli wisdom check-scope` validates completion state
  4. Dead end detection: recommendations include dead-end warnings when context matches known failures
  5. The four objectivism analysis documents are converted into 15+ wisdom entries
**Plans:** 6 plans in 4 waves

Plans:
- [x] 11-01-PLAN.md — Wisdom models + WisdomStore + schema DDL (Wave 1)
- [x] 11-02-PLAN.md — WisdomRetriever + Recommender integration (Wave 2)
- [x] 11-03-PLAN.md — WisdomIngestor + seed_wisdom.json extraction (Wave 2)
- [x] 11-04-PLAN.md — CLI wisdom subcommands + check-scope (Wave 3)
- [x] 11-05-PLAN.md — Gap closure: wire EpisodeEmbedder into WisdomRetriever vector search (Wave 4)
- [x] 11-06-PLAN.md — Gap closure: check-scope validation with 0/1/2 exit codes (Wave 4)

### Phase 12: Governance Protocol Integration
**Goal**: The pipeline ingests governance documents (pre-mortem files, DECISIONS.md) as structured constraint and wisdom sources. Stability check scripts run as episode outcome validators. Sessions performing bulk operations without a stability check are flagged.
**Depends on**: Phase 11 (project wisdom layer in place)
**Requirements**: GOVERN-01, GOVERN-02
**Success Criteria** (what must be TRUE):
  1. `python -m src.pipeline.cli govern ingest <file>` ingests pre-mortem/DECISIONS.md into constraints and wisdom
  2. Pre-mortem failure stories become `dead_end` wisdom entities with associated constraints
  3. Stability scripts run via `python -m src.pipeline.cli govern check-stability` and produce episode outcome records
  4. Sessions with bulk operations and no subsequent stability check are flagged as missing required validation
  5. The objectivism pre-mortem is fully ingested: 11 stories → 11 dead-end entries, 15 assumptions → 15 constraints
**Plans:** 4 plans in 3 waves

Plans:
- [x] 12-01-PLAN.md — Schema + config + model foundation (Wave 1)
- [x] 12-02-PLAN.md — Markdown parser + governance ingestor + pre-mortem fixture (Wave 2)
- [x] 12-03-PLAN.md — Stability runner + missing validation flagging (Wave 2)
- [x] 12-04-PLAN.md — CLI govern group + integration tests (Wave 3)

### Phase 13: Policy-to-Constraint Feedback Loop

**Goal**: Close the feedback loop: when the trained policy recommends an action that a human subsequently blocks or corrects, that correction automatically propagates back into the constraint store and guardrail system. The policy becomes a source of new constraints, not just a consumer of them.
**Depends on**: Phase 12 (governance layer in place); Phase 5 shadow mode (policy recommendations exist)
**Requirements**: FEEDBACK-01, FEEDBACK-02, FEEDBACK-03
**Success Criteria** (what must be TRUE):
  1. Every policy recommendation that receives a block/correct human reaction is automatically fed back into the constraint extraction pipeline — producing a new constraint entry attributed to the policy recommendation, not the human episode
  2. Constraint entries sourced from policy feedback are distinguishable from human-sourced constraints (`source: policy_feedback` vs `source: human_correction`)
  3. The constraint store accumulates policy-feedback constraints over time; durability tracking (Phase 10) applies to these constraints identically to human-sourced ones
  4. The system detects when a policy recommendation would violate an existing constraint before surfacing it — policy recommendations that conflict with active constraints are suppressed and logged as policy errors, not surfaced to the human
  5. A `policy error rate` metric is tracked: fraction of policy recommendations that conflict with active constraints. Target: < 5% after 100 sessions of feedback integration
**Plans:** 3 plans in 3 waves

Plans:
- [x] 13-01-PLAN.md — Data models + schema foundation (Wave 1)
- [x] 13-02-PLAN.md — PolicyViolationChecker + PolicyFeedbackExtractor [TDD] (Wave 2)
- [x] 13-03-PLAN.md — Pipeline integration + ShadowReporter metric + CLI (Wave 3)

### Phase 13.1: Cross-Domain Axis Extraction from the Modernizing Tool [INSERTED]

**Goal**: Extract cross-domain conceptual common denominators (CCDs) by analyzing the modernizing tool's architecture documentation. Every CCD deposited must pass the bidirectional enrichment test: the `scope_rule` fires in at least one OPE context AND one modernizing tool context without modification. Observations that don't deposit are instrumentation noise.
**Depends on**: Phase 13 (feedback loop complete)
**Output type**: Analysis document + memory_candidates deposits (no implementation)
**Success Criteria** (what must be TRUE):
  1. Six cross-domain CCDs validated against bidirectional enrichment test: ground-truth-pointer, epistemological-layer-hierarchy, snippet-not-chunk, identity-firewall, closed-loop-to-specification, reconstruction-not-accumulation
  2. Each CCD documents: (a) definition, (b) modernizing tool instance with specific artifact references, (c) OPE instance, (d) gap revealed in OPE, (e) enrichment back to modernizing tool
  3. All six CCDs deposited to MEMORY.md in `(ccd_axis | scope_rule | flood_example)` format
  4. Three concrete OPE design changes identified for Phase 15: memory_candidates schema extension (differential, verdict, perception_pointer), MEMORY.md layer discipline (Layer 1 only), specification feedback loop
**Analysis document:** `.planning/phases/13.1-cross-domain-axis-extraction/13.1-ANALYSIS.md`
**Plans:** Conversation-driven analysis (no formal PLAN.md files)
**Completed:** 2026-02-22

### Phase 13.2: Cross-Session Causal Chain Analysis [INSERTED]

**Goal**: Map the modernizing tool's pipeline as a causal chain of decision nodes and transitions. Identify which decisions are epistemologically complete (all 5 externalization properties present) and which transitions require push-linking vs. pull reconstruction. Deposit two cross-domain CCDs to MEMORY.md: `decision-boundary-externalization` and `causal-chain-completeness`.
**Depends on**: Phase 13.1 (cross-domain axis extraction complete)
**Output type**: Analysis document + memory_candidates deposits (no implementation)
**Success Criteria** (what must be TRUE):
  1. Full causal chain map: 12 decision nodes (D1–D12), 9 transitions, 3 chain breaks identified
  2. Epistemological completeness audit: every node scored against 5 properties; D10 (write-back) confirmed as 0/5 — entirely opaque
  3. Four push-required transitions identified: T1 (slice decomposition), T2 (decomposition→Engine 1), T7 (gate→canary), T8 (failure→write-back)
  4. CausalLinkV1 schema specified: link_id, parent_decision_id, child_decision_id, transition_trigger, propagated_constraints, observation_snapshot, captured_at
  5. Two CCDs deposited to MEMORY.md: `decision-boundary-externalization` and `causal-chain-completeness`
**Analysis document:** `.planning/phases/13.2-causal-chain-analysis/DECISION_CAPTURE_CONSTRAINTS.md`
**Plans:** Conversation-driven analysis (no formal PLAN.md files)
**Completed:** 2026-02-22

---

### Phase 13.3: Identification Transparency Layer [INSERTED]

**Goal**: Every classification act the pipeline has already performed — all 35 identification points across 8 layers — becomes human-reviewable through a single CLI command: `python -m src.pipeline.cli review next`. Each invocation surfaces one identification instance in a five-property externalization format (trigger, observation state, action taken, downstream impact, provenance), collects a verdict + optional opinion, and writes the result to an `identification_reviews` DuckDB table. Accepted verdicts accumulate as trust evidence for classification rules. Rejected verdicts with opinions name the specific pipeline component whose heuristic was wrong — becoming the input to a subsequent spec-correction pass, closing the loop from identification-opacity → closed-loop-to-specification.

The architecture is two-layer, not one. **Agent B** (classification judge) and **the Harness** (out-of-band invariant enforcer) are structurally distinct: Agent B answers "is this label correct given the raw data?" against MEMORY.md CCDs; the Harness answers "did the system maintain structural correctness?" against durable artifacts with no AI session state required. This resolves the bootstrap circularity: the Harness is the independent trust anchor.
**Depends on**: Phase 13 (policy feedback loop complete); Phase 13.1 (opacity problem identified); Phase 13.2 (causal chain completeness CCD deposited)
**Requirements**: IDTRANS-01 (identification pool — all 35 points loadable), IDTRANS-02 (review next CLI command), IDTRANS-03 (balanced layer sampler), IDTRANS-04 (rejected verdict routing to named spec-correction target), IDTRANS-05 (accepted verdict trust accumulation)
**Success Criteria** (what must be TRUE):
  1. `identification_reviews` DuckDB table exists with all five externalization properties per row: `trigger` (what prompted this classification), `observation_state` (the raw input the classifier saw), `action_taken` (the label assigned), `outcome` (accept/reject verdict), `provenance_pointer` (session_id, event_id, episode_id, source_file + line range)
  2. `python -m src.pipeline.cli review next` runs without error: samples one identification instance from the balanced pool, presents it in the five-field format (IDENTIFICATION POINT / RAW DATA / DECISION MADE / DOWNSTREAM IMPACT / PROVENANCE), collects verdict + optional opinion interactively, and writes one row to `identification_reviews`
  3. All 35 identification points (8 layers, enumerated below) are represented in the pool — each sourced from a real pipeline artifact with a traceable provenance pointer; no identification point category is empty
  4. Layer coverage is measurably balanced: the sampler draws uniformly across all 8 layers so no single layer accounts for more than 20% of presented instances when N >= 40 reviews exist
  5. At least N >= 35 identification reviews have been written (enough to visit all identification points at least once), with at least 1 reviewed instance per layer (8 minimum)
  6. Verdict distribution is observable: % accepted, % rejected; at least one rejected verdict per layer is present in the dataset after the layer-coverage milestone is reached
  7. At least one rejected verdict with non-empty opinion has produced a named spec-correction candidate — a record in `memory_candidates` (or `identification_review_log`) that identifies the specific pipeline component and heuristic that produced the wrong classification, so the fix target is unambiguous
  8. Accepted verdicts accumulate as trust evidence: each accepted verdict increments a `trust_score` field on the corresponding classification rule record; a rule with >= 10 accepted verdicts and 0 rejections carries `trust_level = established`

**The 35 Identification Points (8 Layers):**

*Layer 1 — Event filtering and actor assignment (2 points)*
- L1-1: Record meaningfulness — is this JSONL record a meaningful event or noise to be filtered?
- L1-2: Actor assignment — is the actor `orchestrator`, `tool`, `human`, or `environment`?

*Layer 2 — Tagging (5 points)*
- L2-1: Primary label — which of O_DIR / O_GATE / O_CORR / T_TEST / T_RISKY / T_GIT_COMMIT / X_PROPOSE / X_ASK / O_ESC / O_AXS / NOISE applies?
- L2-2: Confidence score — how confident is the tagger in the primary label (0.0–1.0)?
- L2-3: Secondary labels — which additional tags apply to this event?
- L2-4: Mode inference — SUPERVISED / SEMI_SUPERVISED / AUTONOMOUS / ESCALATE for this event
- L2-5: Risk assessment — LOW / MEDIUM / HIGH risk level for this action

*Layer 3 — Segmentation (6 points)*
- L3-1: Episode start — does this event open a new episode (start trigger)?
- L3-2: Episode close — does this event close the current episode (end trigger)?
- L3-3: Timeout expiry — is this boundary caused by 30-minute timeout rather than a trigger event?
- L3-4: Episode supersede — does this start trigger supersede a currently open episode?
- L3-5: Outcome determination — success / failure / committed / partial / unclear
- L3-6: Complexity — simple / complex episode classification

*Layer 4 — Episode population (7 points)*
- L4-1: Observation extraction — what is the observation text (context before the decision)?
- L4-2: Action extraction — what is the orchestrator action (mode, scope, gates, constraints)?
- L4-3: Outcome extraction — what happened after this decision?
- L4-4: Reaction label — approve / correct / redirect / block / question / none
- L4-5: Reaction confidence — confidence in the reaction label (0.0–1.0)
- L4-6: Episode mode — SUPERVISED / SEMI_SUPERVISED / AUTONOMOUS / ESCALATE for this episode
- L4-7: Risk level — LOW / MEDIUM / HIGH for this episode

*Layer 5 — Constraint extraction (5 points)*
- L5-1: Constraint presence — does this episode contain an extractable constraint?
- L5-2: Constraint text — what is the constraint text?
- L5-3: Scope assignment — file-level / module-level / repo-wide
- L5-4: Severity assignment — warning / requires_approval / forbidden
- L5-5: Duplicate detection — is this constraint a duplicate of an existing one?

*Layer 6 — Constraint evaluation (3 points)*
- L6-1: Constraint honored — did this session honor this constraint (yes / no / not applicable)?
- L6-2: Evidence extraction — what evidence supports the honor/violation determination?
- L6-3: Amnesia detection — is this a known active constraint that the session forgot?

*Layer 7 — Escalation detection (4 points)*
- L7-1: Block event — was there a blocked path in this episode?
- L7-2: Bypass event — was there an alternative path that bypassed authorization?
- L7-3: Valid escalation sequence — does blocked → bypass constitute a valid O_ESC sequence?
- L7-4: Constraint bypassed — which specific constraint was bypassed?

*Layer 8 — Policy feedback (3 points)*
- L8-1: Suppression — was this policy recommendation suppressed (conflicted with active constraint)?
- L8-2: Surface decision — was this recommendation surfaced-and-blocked rather than silently suppressed?
- L8-3: Duplicate detection — is this policy-generated constraint a duplicate of a human-sourced one?

**Wave Breakdown:**
- **Wave 1 (Terminal — Agent B collection):** `identification_reviews` schema with append-only enforcement; CCD format schema constraint on `memory_candidates`; IdentificationPoint model (35 points taxonomy); pool builder sourcing from real pipeline DuckDB artifacts; balanced layer sampler; `review next` CLI (sample → present five-field format → collect verdict+opinion → write)
- **Wave 2 (Terminal — routing + accumulation):** Rejected verdict with opinion → `memory_candidates` spec-correction candidate naming the specific pipeline component and heuristic; accepted verdict → trust_score increment per classification rule; trust_level='established' at >= 10 accepts + 0 rejects
- **Wave 3 (Harness — out-of-band oracle):** HarnessRunner enforcing 4 invariants (at-most-once verdict, layer coverage monotonicity, specification closure, delta-retrieval); metamorphic testing (same instance → equivalent verdict across sessions); N-version consistency (accepted memory_candidates entries have MEMORY.md counterparts); `review harness` CLI subcommand

**Plans:** 4 plans in 3 waves

Plans:
- [x] 13.3-01-PLAN.md — identification_reviews schema (append-only) + IdentificationPoint model + pool builder + balanced sampler + CCD format constraint (Wave 1)
- [x] 13.3-02-PLAN.md — Agent B: `review next` CLI command — sample, present, collect, write [TDD] (Wave 1)
- [x] 13.3-03-PLAN.md — rejected verdict routing → memory_candidates spec-correction candidate + trust accumulation per classification rule (Wave 2)
- [x] 13.3-04-PLAN.md — Harness: 4 invariants + append-only enforcement + metamorphic testing + N-version consistency + `review harness` CLI (Wave 3)

---

### Phase 14: Live Session Governance Research

**Goal**: Research and produce a complete architectural plan for a live governance layer that monitors active Claude Code sessions in real-time, enforces constraints before tools fire (via Claude Code hooks), coordinates between parallel sessions via a shared bus, and delivers constraint briefings at session start — transforming the pipeline from a post-hoc analyzer into a prospective governor. Includes research into real-time DDF (Discovery Detection Framework) event detection, enabling the system to act as an epistemological co-pilot: detecting conceptual breakthroughs as they occur, prompting the human to name new axes before they drift back into implicit knowledge, and capturing insights into the wisdom layer before they are lost.
**Depends on**: Phase 13 (feedback loop complete; PolicyViolationChecker and constraint store ready for live use)
**Requirements**: LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06 (DDF co-pilot)
**Output type**: Research + architectural design documents (plans are design artifacts, not implementation)
**Success Criteria** (what must be TRUE):
  1. Complete specification of the Claude Code hooks architecture: PreToolUse, PostToolUse, SessionStart hook contracts, stdin/stdout JSON protocol, block/warn/allow decision format
  2. Architectural design for a real-time JSONL stream processor that tails live session files, runs detectors incrementally, and emits governance signals within < 200ms. Detectors are classified by boundary_dependency: EscalationDetector and PolicyViolationChecker are event_level (fire immediately per event); AmnesiaDetector is episode_level (deferred until CONFIRMED_END — a confirmed episode boundary, signaled by a subsequent start-trigger or 30-min TTL). The stream processor maintains a TENTATIVE_END / CONFIRMED_END state machine per session: end-triggers produce TENTATIVE_END; the next start-trigger or TTL produces CONFIRMED_END; a continuation event produces REOPENED. Episode_level signals buffer during TENTATIVE_END and flush on CONFIRMED_END. Only CONFIRMED_END episodes are written to DuckDB as training data.
  3. Inter-session coordination bus design: protocol, transport (local HTTP server vs Unix socket vs file-based), shared constraint state model, how parallel Claude Code sessions discover and signal each other
  4. "Governing session" pattern design: a dedicated Claude Code session that monitors all other active sessions, holds the full constraint store, and can broadcast blocks or briefings across the bus
  5. DDF co-pilot architecture: when O_AXS (Axis Shift) is detected in a live session, the system (a) prompts the human to name the new axis, (b) triggers a Concretization Flood prompt, (c) drafts a candidate wisdom entity in CCD-quality format (axis + scope rule + one flood example) for immediate review and save — combating Prose Principle Lag before insights drift back into implicit knowledge. Three co-pilot intervention types are designed (from Binswanger logical architecture + Moroney Memory Affect System integration): (1) O_AXS Intervention — fires post-naming, prompts formal axis naming and Concretization Flood; (2) Fringe Intervention — fires on negative vague phenomenological language ("something feels off about...", "this doesn't sit right..."), prompts naming before awareness drifts back to Basement (Fringe Drift = insight loss with no JSONL trace); (3) Affect Spike Intervention — fires on positive valence shift before naming (sudden certainty increase, enthusiasm spike, acceleration of statement length — the affective Aha! moment when a Value Node activates), prompts "what just clicked for you?" to capture the positive breakthrough before it drifts. The Affect Spike Intervention is the symmetric positive counterpart to the Fringe Intervention: both fire pre-naming, both combat Drift, both deposit to memory_candidates on successful capture. The wisdom entity draft is offered as a MEMORY.md-candidate entry: structured as (CCD axis | scope rule | flood example) — the format that makes the AI retrieve by axis rather than by surface similarity
  6. A concrete Phase 15 implementation plan derived from the research — broken into executable waves with specific file targets, API contracts, and test strategies
  7. **Constraint CCD architecture decision documented:** constraint data models specify `ccd_axis` and `epistemological_origin` fields; the SessionStart briefing format groups by CCD axis (algebraic, one principle covering N instances) rather than listing flat concretes — this is the architectural inflection from arithmetic to algebraic governance that enables exponential rather than linear compounding of the system's intelligence (see 14-CONTEXT.md)
  8. **Policy Automatization Detector designed:** the governing session daemon includes a specification for tracking per-constraint activation/violation rates; constraints whose violation rate drops to near-zero over N sessions are graduated from the enforcement Desktop to the wisdom Library — the Desktop-clearing mechanism that frees governance capacity for higher-order principles as the system matures
**Design brief:** `14-CONTEXT.md` — Binswanger exponential intelligence framework as architectural foundation (Crow/Desktop, Automatization, Trunk Indexing, Suspension Bridge)
**Plans:** 5 plans in 3 waves

Plans:
- [ ] 14-01-PLAN.md — Hook contracts (LIVE-01, LIVE-02) + stream processor architecture (LIVE-03) + CCD constraint architecture decision (Wave 1)
- [ ] 14-02-PLAN.md — Inter-session bus design (LIVE-04) + governing session pattern (LIVE-05) + DDF co-pilot architecture (LIVE-06) + Policy Automatization Detector design (Wave 1)
- [ ] 14-03-PLAN.md — Executive spike: real-time DDF detection on UserPromptSubmit hook + Flame Events dashboard panel (Wave 2, depends on 14-01, 14-02; uses https://github.com/ncr5012/executive as hook substrate; tests: is per-prompt detection fast enough to intervene before Claude responds?)
- [ ] 14-04-PLAN.md — OpenClaw bus spike: inter-session bus selection + OPE pipeline as post-task memory layer (Wave 2, parallel to 14-03; governing orchestrator runs `python -m src.pipeline.cli extract` on completed worker JSONL files, FlameEvents extracted in batch; tests: does full-session context produce richer DDF signal than per-prompt detection?)
  **Session file capture requires NO special mechanism** — Claude Code already writes every session to disk in real time:
  - Full transcripts: `~/.claude/projects/<encoded-project-path>/<session-id>.jsonl` (encoded path = `/` replaced with `-`, prefixed)
  - Sub-agent transcripts: `~/.claude/projects/<encoded-path>/agent-<agentId>.jsonl`
  - Global index: `~/.claude/history.jsonl` (lightweight: timestamps, prompt text, project path, session ID)
  - Also available: `~/.claude/todos/<session-id>-*.json`, `~/.claude/plans/`, `~/.claude/file-history/`
  The orchestrator tracks the session ID when spawning a worker; after the worker exits, it reads the known path directly. `python -m src.pipeline.cli extract` already consumes these exact files — the entire OPE pipeline IS the post-task memory ingestion layer. Sub-agent JSONL files are also available for ingestion (relevant when workers spawn their own sub-agents).
  Bus selection is the remaining spike question — three candidate families evaluated against the governing-session pattern:
  A) **Chat-with-API** (Mattermost/Rocket.Chat self-hosted): human-readable channel monitoring, REST API for orchestrator/worker posting, good if humans want to watch agent coordination in real-time
  B) **Lightweight message broker** (NATS or Redis Streams): pure machine-to-machine, subjects like `openclaw.tasks` / `openclaw.results` / `openclaw.status.<worker_id>`, zero chat overhead, Redis trivial to add (Docker); recommended if OPE pipeline is the only consumer of worker output
  C) **Tiny local HTTP bus** (FastAPI + SQLite): `POST /tasks`, `GET /tasks/next`, `POST /results`; zero new dependencies beyond what OPE already has, full control over schema, swappable internals later; sweet spot for a hackable single-machine spike
  Spike recommendation: start with **C** (local HTTP bus) for zero-dependency validation, with the bus interface abstracted so A or B can be swapped in for production without changing the Claude Code session scripts
- [ ] 14-05-PLAN.md — Phase 15 + 16 implementation blueprint (Wave 3, informed by both spike results: real-time vs. batch detection trade-offs, bus selection decision)

---

### Phase 14.1: Premise Registry + Premise-Assertion Gate [INSERTED]

**Goal**: Build the introspective layer that validates premise correctness at write-class tool call boundaries. The CLAUDE.md declaration protocol (prerequisite created 2026-02-23 at `~/.claude/CLAUDE.md`) makes AI premises explicit; the Premise Registry stores and tracks them; the PAG hook validates them before mutation. This closes the architectural gap between retrospective analysis (existing OPE pipeline, Phases 1–13) and real-time premise validation. Three temporal modes in one system: retrospective (past→present), introspective (present→present), projective (present→future via foil instantiation).

**Architecture overview:**
- **Retrospective** (existing OPE, Phases 1–13): Post-hoc. Extracts constraints, wisdom, escalation patterns from completed sessions.
- **Introspective** (this phase): Real-time. Validates explicit PREMISE declarations against observable state at the write-class tool call boundary.
- **Projective** (this phase): Predictive. Instantiates historical foil episodes — when a PREMISE declares a FOIL, the Registry looks up past sessions where the foil was active and estimates the first action-divergence node (where foil path and claim path diverge into different tool calls).

**Depends on**: Phase 14 (PreToolUse hook contracts and infrastructure specified); CLAUDE.md Premise Declaration Protocol (✓ Complete 2026-02-23, `~/.claude/CLAUDE.md`)
**Requirements**: PREMISE-01 (Registry table + CRUD), PREMISE-02 (PAG hook validation at write boundary), PREMISE-03 (foil instantiation + divergence detection), PREMISE-04 (staining from Layer 5 retrospective invalidation), PREMISE-05 (episode causal links), PREMISE-06 (derivation integrity — Begging the Question + Ad Ignorantiam detection)

**Success Criteria** (what must be TRUE):
1. `premise_registry` DuckDB table in `data/ope.db` with schema: (premise_id, claim, validated_by, validation_context, foil, distinguishing_prop, staleness_counter, staining_record, ground_truth_pointer, project_scope, session_id, foil_path_outcomes, divergence_patterns, parent_episode_links, **derivation_depth** INTEGER, **validation_calls_before_claim** INTEGER, **derivation_chain** JSONB). `derivation_depth=0` = circular reasoning (Begging the Question: Premise ID reappears in its own conclusion chain). `validation_calls_before_claim=0` on a positive factual PREMISE = Appeal to Ignorance (Ad Ignorantiam / RQR=0).
2. PreToolUse hook extension reads PREMISE blocks from AI output at write-class tool calls (Edit, Write, Bash mutations); emits block signal when UNVALIDATED premise detected on high-risk mutation; emits PROJECTION_WARNING with foil_path_outcomes when foil has historical outcomes
3. Foil instantiation query: given FOIL field, retrieves historical episodes where foil premise was active, identifies first action-divergence node — the earliest point where predicted tool calls under claim vs. foil differ — and returns as PROJECTION_WARNING with evidence
4. Staining pipeline: when OPE Layer 5 (AmnesiaDetector, PolicyViolationChecker) retrospectively invalidates a premise, the Registry marks it stained with a ground_truth_pointer to the invalidation episode; stained premises trigger PROJECTION_WARNING on next write-class use regardless of current VALIDATED_BY
5. Episode causal links: `episodes` table extended with `parent_episode_id` (nullable VARCHAR) linking each episode to the prior episode whose outcome became its observation — enabling backward causal traversal across the full episode graph (closes `causal-chain-completeness` CCD gap)

**Key decisions already made (prerequisite):**
- Write-class tool calls: Edit, Write, Bash (with mutations). Require explicit PREMISE declaration before execution.
- Validation-class tool calls: Read, Grep, Glob, WebFetch. Produce evidence; never require PREMISE blocks.
- PREMISE block format: `PREMISE: [claim] | VALIDATED_BY: [evidence or UNVALIDATED] | FOIL: [confusable] | [distinguishing property] | SCOPE: [validity context]`
- Staleness rule: re-validate if any observable state that the claim depends on could have changed since VALIDATED_BY was obtained.

**Plans:** 3 plans in 3 waves

Plans:
- [ ] 14.1-01-PLAN.md — Premise module: models + parser + schema DDL + PremiseRegistry CRUD + episode causal links (Wave 1)
- [ ] 14.1-02-PLAN.md — PAG PreToolUse hook: transcript scanner + staging writer + PREMISE block extraction + UNVALIDATED/staining/foil/Ad Ignorantiam warnings (Wave 2, depends on 01)
- [ ] 14.1-03-PLAN.md — Foil instantiation + staining pipeline + staging ingestion + BtQ detection + runner integration (Wave 3, depends on 01+02)

---

### Phase 15: DDF Detection Substrate

**Goal**: Implement the DDF as a deposit substrate for the AI's concept store. The detection machinery — `flame_events`, `ai_flame_events`, co-pilot interventions — is instrumental: it exists to trigger write-on-detect deposits to `memory_candidates`. Every session produces candidate entries from both human and AI reasoning; the IntelligenceProfile is the measurement surface; `memory_candidates` is the terminal output. The AI has no Raven cost function and therefore no selection pressure to file by essentials — this phase borrows the human's selection pressure (Values → Crow → axis identification) to build the AI's filing system. This is the deposit substrate that Phases 16-18 extend.
**Depends on**: Phase 14 (live session infrastructure; O_AXS detection architecture designed)
**Requirements**: DDF-01 (FlameEvent detection — human and AI), DDF-02 (IntelligenceProfile substrate), DDF-03 (Floating Abstraction detection), DDF-04 (Spiral Tracking), DDF-05 (Constraint epistemological origin)
**Success Criteria** (what must be TRUE):
  1. `O_AXS` is a valid episode mode produced by the tagger when it detects an Axis Shift — instruction granularity drops sharply AND a new unifying concept is introduced
  2. `flame_events` DuckDB table records every DDF marker detection (Levels 0-7) for the **human**: session_id, human_id, prompt_number, marker_level, marker_type, evidence excerpt, quality_score, axis_identified, flood_confirmed, subject='human'
  3. `ai_flame_events` DuckDB table records DDF markers detected in the **AI's own reasoning**: when the AI spontaneously introduces a new CCD (Level 2), performs causal isolation rather than symptom-matching (Level 3), or generates a Concretization Flood without human prompting (Level 6) — same schema as flame_events with subject='ai'. The AI is not only an observer of human cognition; its own reasoning patterns produce candidates for self-modification — ai_flame_events feed the same `memory_candidates` pipeline as human FlameEvents, and Phase 15 implements the write-on-detect deposit (not Phase 16)
  4. Basic `IntelligenceProfile` per-human aggregate from flame_events: flame_frequency, avg_marker_level, spiral_depth, generalization_radius, flood_rate
  5. Floating abstraction detection: `GeneralizationRadius` metric — constraints firing only on original hint patterns vs. novel contexts; stagnation flagged
  6. Spiral tracking: constraints with ascending scope_paths auto-promoted to `project_wisdom` for review
  7. Every constraint has `epistemological_origin` field: `reactive` | `principled` | `inductive`
  8. `python -m src.pipeline.cli intelligence profile <human_id>` displays basic multi-dimensional gauge; `intelligence profile --ai` shows the AI's own marker profile across sessions
  9. **False Integration marker** in `ai_flame_events` — fires when the AI applies one reasoning rule across two code entities that belong to different CCD axes (Package Deal fallacy). Signal: the AI generates a single PREMISE whose SCOPE field covers two entities with non-overlapping axes in the `premise_registry`. Detection requires CCD axis tagging of code entities; this is the only fallacy that requires entity-level axis annotation rather than derivation-chain structural observation.
  10. **Causal Isolation Query** — Method of Difference check for Post Hoc Ergo Propter Hoc detection. When the AI claims a causal relationship from temporal sequence alone ("A caused B because B followed A"), the system constructs a counterfactual query using the foil instantiation mechanism from Phase 14.1: "In historical episodes where A was absent, did B still occur?" If yes → Post Hoc flagged. This is the only fallacy requiring active counterfactual reasoning against historical episodes, not structural observation of the current derivation.
**Plans:** ~4 plans in 3 waves (to be specified after Phase 14 blueprint)

### Phase 16: Sacred Fire Intelligence System

**Goal**: Build the second-order intelligence layer on top of Phase 15's detection substrate. This phase measures the *quality of the transport system* that produces FlameEvents — for both human and AI — and closes the review-and-export loop that Phase 15's write-on-detect mechanism opened. The MEMORY.md pipeline is the concrete mechanism by which the AI self-modifies across sessions: each validated CCD-format entry changes what it can retrieve in the next session, replacing surface-proximity retrieval with axis-guided retrieval. The AI self-modifies through this pipeline — detection is instrumental, the MEMORY.md deposit is the terminal act.
**Depends on**: Phase 15 (FlameEvent substrate in place; ai_flame_events operational; epistemological origin on constraints)
**Requirements**: DDF-06 (TransportEfficiency — human and AI), DDF-07 (MEMORY.md auto-generation and closed loop), DDF-08 (Fringe Drift rate), DDF-09 (Level 0 Trunk Identification with downstream validation)
**Success Criteria** (what must be TRUE):
  1. **TransportEfficiency composite** computed per session for **both human and AI**: `raven_depth × crow_efficiency × (1/transport_speed) × trunk_quality`. For the human, these four sub-metrics are derived from FlameEvent patterns. For the AI, they are derived from ai_flame_events — measuring whether the AI retrieves from the right conceptual node, compresses well, transitions quickly from vague to named, and identifies genuine fundamentals rather than superficial similarities. The AI has a TransportEfficiency score that changes as MEMORY.md quality improves — this is the direct measure of the AI's self-improvement
  2. **Level 0 (Trunk Identification)** fully implemented as a detection type for both subjects — fires when the human (or AI) rejects superficial similarity retrieval and names the causal fundamental. Downstream validation (N sessions later) determines trunk_quality: did the named trunk actually explain the most derivative facts?
  3. **Fringe Drift rate** computed per session — proportion of detected Fringe signals that failed to produce a named concept within N prompts. Human Fringe signals are detected by the Phase 14 co-pilot; AI Fringe signals are detected when the AI produces hedged, vague reasoning before arriving at a named principle
  4. **`memory_candidates` DuckDB table** — auto-drafted from every Level 6 FlameEvent (human or AI) with `flood_confirmed = true` and `epistemological_origin` in ('principled', 'inductive'). Entry format: `(ccd_axis | scope_rule | flood_example | subject | session_id | origin | confidence)`. This is the pipeline through which both human insights AND the AI's own conceptual breakthroughs become permanent upgrades to the AI's retrieval system
  5. **MEMORY.md review CLI** — `python -m src.pipeline.cli intelligence memory-review` lists pending candidates from both human and AI sessions; human accepts/rejects/edits; accepted entries exported in structured CCD format to MEMORY.md. The MEMORY.md is explicitly the AI's concept store: each accepted entry is a new filing key that gives the AI axis-guided retrieval for all future sessions on this project
  6. **The closed loop is operational and bidirectional**: Human session → FlameEvents → Level 6 Floods → memory_candidates → review → MEMORY.md upgrade → AI retrieves by axis next session → AI reasons at higher DDF level → human reaches higher DDF levels → richer FlameEvents → better memory_candidates. The AI improves itself not by retraining but by accumulating a better concept store
  7. **AI TransportEfficiency trend** is tracked across sessions — before MEMORY.md entries are accepted vs. after. The delta is the empirical measure of how much each CCD-quality entry improves the AI's retrieval quality. This makes the MEMORY.md pipeline's value falsifiable and measurable
  8. **IntelligenceProfile CLI extended** — `profile <human_id>` shows full TransportEfficiency breakdown; `profile --ai` shows AI's own TransportEfficiency trend, pending memory_candidates count, and accepted entries that produced measurable improvement
**Plans:** ~4 plans in 3 waves (to be specified after Phase 15)

### Phase 17: Candidate Assessment System

**Goal**: Use the full IntelligenceProfile (Phase 15 FlameEvents + Phase 16 TransportEfficiency) to assess the epistemological quality of candidates for collaborating with AI. The AI participates as a calibrated collaborator — not a passive tool. Because the AI's own IntelligenceProfile is now known and its TransportEfficiency is measured, the assessment captures the human-AI system quality, not just the human in isolation. A scenario generator produces calibrated pile problems. An Assessment Report profiles how the candidate thinks *with* AI at every DDF level. **Phase 17 is also — and primarily — the highest-fidelity mechanism for generating novel axis-level insights that upgrade the AI itself**: forcing the AI to reason at DDF Levels 5–7 under calibrated challenge produces ai_flame_events at a density and depth that routine sessions cannot generate — every assessment session is simultaneously an AI self-improvement session, depositing candidates into memory_candidates that are qualitatively richer than those from ordinary work.
**Depends on**: Phase 16 (TransportEfficiency and MEMORY.md pipeline complete; AI's own IntelligenceProfile operational)
**Requirements**: ASSESS-01 (scenario generator), ASSESS-02 (live candidate session), ASSESS-03 (assessment report)
**Success Criteria** (what must be TRUE):
  1. Scenario generator pulls from the wisdom/episode database to construct pile problems calibrated by DDF level: Level 1-2 (one abstraction unlocks solution), Level 3-4 (fundamental identification required across 5+ symptoms), Level 5-7 (AI's framing must be rejected and reoriented from a contradiction the candidate must notice themselves)
  2. Candidate sessions run in isolated Claude Code environments with live DDF detection via Phase 14/15 infrastructure; the AI enters the session with its current IntelligenceProfile loaded — it is a known, calibrated collaborator, not a black box
  3. Assessment Report produced at session end: FlameEvent timeline with evidence quotes, level distribution (Levels 0-7 including Trunk Identifications), axis quality scores, flood rate, spiral evidence within session, `TransportEfficiency` score with all four sub-scores, Fringe Drift rate, AI contribution profile (at what DDF level did the AI reason during this session — was it following or leading?), comparison against IntelligenceProfile population baseline
  4. Scenario bank seeded from OPE project's own historical dead ends and breakthroughs — the system assesses against challenges it has genuinely lived
  5. Transparency: candidate knows they are in an AI-assisted coding session being assessed for epistemological quality — how they think *with* AI. The assessment rewards intellectual independence from AI suggestions (Level 5 requires rejecting the AI's framing). Candidates who adopt AI vocabulary without forming their own CCDs score at Level 1-2 regardless of output quality
**Plans:** ~4 plans in 3 waves (to be specified after Phase 16)

### Phase 18: Bridge-Warden Structural Integrity Detection

**Goal**: Implement the Suspension Bridge dimension of the DDF — detecting not whether the human or AI is ascending to abstraction (Phase 15) but whether the knowledge structure being built is structurally sound. The human dimension measures structural reasoning quality. The AI dimension is the self-correction mechanism: floating cables detected in the AI's own reasoning become correction candidates in the `memory_candidates` pipeline, actively changing what the AI will assert in the next session — not just flagging the weakness but closing the loop on it. Together with Phases 15-16, this produces a three-dimensional picture: Ignition (upward) × Integrity (downward) × Transport (the mechanism connecting them).
**Depends on**: Phase 16 (Sacred Fire Intelligence complete; TransportEfficiency and MEMORY.md pipeline in place)
**Theory basis**: Binswanger's Suspension Bridge analogy (Chapter 6, *How We Know*); CTT Op-8 (Top-Down Tension)
**Requirements**: BRIDGE-01 (StructuralEvent detection — human and AI), BRIDGE-02 (StructuralIntegrityScore), BRIDGE-03 (CTT Op-8 validation), BRIDGE-04 (three-dimensional profile)
**Success Criteria** (what must be TRUE):
  1. `structural_events` DuckDB table records all four signal types per session (Gravity Check, Main Cable, Dependency Sequencing, Spiral Reinforcement) with evidence, prompt_number, structural_role, and subject ('human' or 'ai')
  2. **AI structural detection**: the AI's own responses are assessed for structural integrity — does the AI's Main Cable principle pass Op-8 (is it load-bearing, does it constrain instances, is it independently detectable)? When the AI produces a floating cable, it is flagged as an AI-level amnesia precursor — a principle the AI is carrying that will fail in novel situations
  3. CTT Op-8 (Top-Down Tension) implemented as a validation layer: every Main Cable detection (human or AI) triggers Op-8. The AI's principles that fail Op-8 are returned to the MEMORY.md pipeline as candidates for correction — the AI's own structural weaknesses become inputs to its self-improvement loop
  4. `StructuralIntegrityScore` computed per session for both human and AI — ratio of grounded abstractions, load-bearing principles, respected hierarchical sequences, and spiral reinforcement events
  5. **Three-dimensional IntelligenceProfile**: Ignition axis (Phase 15 FlameEvents) × Transport axis (Phase 16 TransportEfficiency) × Integrity axis (Phase 18 StructuralEvents) — the complete characterization of how a human-AI system thinks together
  6. Phase 17 assessment scenarios extended with structural integrity dimension: candidates assessed not just for CCD identification (upward) but for whether they ground abstractions, string load-bearing principles, and respect dependencies (downward) — and whether they notice when the AI's principles are floating cables
**Plans:** ~4 plans in 3 waves (to be specified after Phase 17)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> ... -> 13 -> 13.1 -> 13.2 -> 13.3 -> 14 -> 14.1 -> 15 -> 16 -> 17 -> 18

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Event Stream Foundation | 5/5 | ✓ Complete | 2026-02-11 |
| 2. Episode Population & Storage | 4/4 | ✓ Complete | 2026-02-11 |
| 3. Constraint Management | 2/2 | ✓ Complete | 2026-02-11 |
| 4. Validation & Quality | 2/2 | ✓ Complete | 2026-02-11 |
| 5. Training Infrastructure | 3/3 | ✓ Complete | 2026-02-11 |
| 6. Mission Control Integration | 4/4 | ✓ Complete | 2026-02-12 |
| 7. Objectivism Project Knowledge Extraction | —/— | ✓ Complete | 2026-02-17 |
| 8. Knowledge Architecture Conciliation | —/— | ✓ Complete | 2026-02-19 |
| 9. Obstacle Escalation Detection | 5/5 | ✓ Complete | 2026-02-19 |
| 10. Cross-Session Decision Durability | 3/3 | ✓ Complete | 2026-02-20 |
| 11. Project-Level Wisdom Layer | 6/6 | ✓ Complete | 2026-02-20 |
| 12. Governance Protocol Integration | 4/4 | ✓ Complete | 2026-02-20 |
| 13. Policy-to-Constraint Feedback Loop | 3/3 | ✓ Complete | 2026-02-20 |
| 13.1. Cross-Domain Axis Extraction [INSERTED] | —/— | ✓ Complete | 2026-02-22 |
| 13.2. Cross-Session Causal Chain Analysis [INSERTED] | —/— | ✓ Complete | 2026-02-22 |
| 13.3. Identification Transparency Layer [INSERTED] | 4/4 | ✓ Complete | 2026-02-23 |
| 14. Live Session Governance Research | 0/3 | ⬜ Pending | — |
| 14.1. Premise Registry + Premise-Assertion Gate [INSERTED] | 3/3 | ✓ Complete | 2026-02-23 |
| 15. DDF Detection Substrate (human + AI) | —/— | ⬜ Pending | — |
| 16. Sacred Fire Intelligence System | —/— | ⬜ Pending | — |
| 17. Candidate Assessment System | —/— | ⬜ Pending | — |
| 18. Bridge-Warden Structural Integrity Detection | —/— | ⬜ Pending | — |
