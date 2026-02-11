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
- [ ] **Phase 3: Constraint Management** - Extract durable orchestration constraints from corrections and manage them with severity and scope
- [ ] **Phase 4: Validation & Quality** - Validate episode quality through multi-layer checks and build gold-standard labeled dataset
- [ ] **Phase 5: Training Infrastructure** - Deploy RAG baseline orchestrator and validate via shadow mode testing
- [ ] **Phase 6: Mission Control Integration** - Capture episodes in real-time from structured tasks with review UI and tool provenance

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
- [ ] 01-01-PLAN.md — Config system + data models + DuckDB schema (Wave 1)
- [ ] 01-02-PLAN.md — DuckDB JSONL ingestion + git history + normalization (Wave 2)
- [ ] 01-03-PLAN.md — Multi-pass event tagger [TDD] (Wave 3)
- [ ] 01-04-PLAN.md — Episode segmenter [TDD] (Wave 3)
- [ ] 01-05-PLAN.md — Pipeline runner + CLI + integration (Wave 4)

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
- [ ] 02-01-PLAN.md — Episode Pydantic model + DuckDB hybrid schema + EpisodeValidator (Wave 1)
- [ ] 02-02-PLAN.md — EpisodePopulator [TDD] (Wave 2)
- [ ] 02-03-PLAN.md — ReactionLabeler [TDD] (Wave 2)
- [ ] 02-04-PLAN.md — Pipeline integration + episode writer + end-to-end tests (Wave 3)

### Phase 3: Constraint Management
**Goal**: Corrections and blocks in episode reactions are converted into durable, enforceable orchestration constraints with severity levels and explicit scope
**Depends on**: Phase 2
**Requirements**: EXTRACT-06, CONST-01, CONST-02, CONST-03, CONST-04
**Success Criteria** (what must be TRUE):
  1. System extracts constraints from correct/block reactions, producing structured constraint objects with text description, severity level, scope paths, and detection hint patterns
  2. Constraints are stored in a version-controlled JSON file (data/constraints.json) with unique IDs and metadata
  3. Severity levels (warning / requires_approval / forbidden) are assigned based on reaction type and keyword analysis -- "correct" reactions produce warning/requires_approval, "block" reactions produce forbidden
  4. Constraint scope (file-level, module-level, or repo-wide) is inferred from mentioned paths, defaulting to narrowest applicable scope rather than repo-wide
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Validation & Quality
**Goal**: Episode quality is verified through multi-layer validation, a gold-standard labeled dataset exists for accuracy measurement, and quality metrics meet thresholds for training readiness
**Depends on**: Phase 3
**Requirements**: VALID-01, VALID-02, VALID-03
**Success Criteria** (what must be TRUE):
  1. Genus-based validator runs five layers of checks (schema validity, evidence grounding, non-contradiction, constraint enforcement, episode integrity) and rejects episodes that fail any layer
  2. A manual validation workflow produces a gold-standard set of 100+ episodes with verified mode labels, reaction labels, and constraint extractions
  3. Quality metrics are calculated and tracked: mode inference accuracy >=85%, reaction label confidence >=80%, constraint extraction rate >=90% of corrections
  4. Episodes that pass validation can be exported to Parquet format for ML training pipelines
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Training Infrastructure
**Goal**: A RAG baseline orchestrator recommends actions from similar past episodes, and shadow mode testing validates recommendations against human decisions before any autonomous operation
**Depends on**: Phase 4
**Requirements**: TRAIN-01, TRAIN-02
**Success Criteria** (what must be TRUE):
  1. RAG baseline retrieves top-k similar episodes by observation context and recommends orchestrator actions with explainable provenance (citing source episodes)
  2. Shadow mode framework runs recommendations alongside actual human decisions across >=50 sessions, measuring agreement rate
  3. Shadow mode achieves >=70% agreement threshold with zero dangerous recommendations before any autonomous operation is permitted
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Mission Control Integration
**Goal**: Episodes are captured in real-time from Mission Control structured tasks, eliminating post-hoc log parsing for ongoing sessions
**Depends on**: Phase 5 (batch pipeline proven), Mission Control repository access (external blocker)
**Requirements**: MC-01, MC-02, MC-03, MC-04
**Success Criteria** (what must be TRUE):
  1. Episodes are captured in real-time from Mission Control task lifecycle (task creation, planning, execution, review) without requiring post-hoc JSONL parsing
  2. Tool provenance (tool calls, files touched, commands run, test results, commits) streams from OpenClaw Gateway during task execution and attaches to episodes
  3. A review widget in Mission Control allows labeling reactions (approve/correct/redirect/block/question) with optional inline constraint extraction workflow
  4. Episodes are stored in Mission Control's SQLite database (episodes, episode_events, constraints, approvals, commit_links tables) enabling dashboard integration
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Event Stream Foundation | 5/5 | ✓ Complete | 2026-02-11 |
| 2. Episode Population & Storage | 4/4 | ✓ Complete | 2026-02-11 |
| 3. Constraint Management | 0/TBD | Not started | - |
| 4. Validation & Quality | 0/TBD | Not started | - |
| 5. Training Infrastructure | 0/TBD | Not started | - |
| 6. Mission Control Integration | 0/TBD | Not started | - |
