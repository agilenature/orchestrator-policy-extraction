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
**Plans:** TBD — to be planned via /gsd:plan-phase

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
**Plans:** TBD — to be planned via /gsd:plan-phase

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
**Plans:** TBD — to be planned via /gsd:plan-phase

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
**Plans:** TBD — to be planned via /gsd:plan-phase

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8

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
| 9. Obstacle Escalation Detection | 0/TBD | ⬜ Pending | — |
| 10. Cross-Session Decision Durability | 0/TBD | ⬜ Pending | — |
| 11. Project-Level Wisdom Layer | 0/TBD | ⬜ Pending | — |
| 12. Governance Protocol Integration | 0/TBD | ⬜ Pending | — |
