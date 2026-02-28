# Orchestrator Policy Extraction

## What This Is

A system that extracts orchestrator decision-point episodes from Claude Code session history, builds a durable constraint store from human corrections, and deploys a live governance layer that intercepts sessions in real-time. v1.0 delivered the full pipeline: JSONL ingestion through DuckDB episode storage, RAG baseline with shadow mode, Mission Control real-time capture, OPE Governance Bus with PreToolUse/SessionStart hooks, DDF 3D Intelligence Profiling (Sacred Fire + Bridge-Warden), Premise Registry + Genus Gate, and ReactiveX concurrent processing.

## Core Value

Episodes capture **how to decide what to do next** (orchestrator decisions: mode/scope/gates/constraints), not just what was delivered (commits), enabling policy learning that scales human judgment instead of human typing.

## Requirements

### Validated

**Conceptual foundation (Phase 0):**
- ✓ Decision-point episodes beat commit-only correlation (design validated)
- ✓ Orchestrator vs executor distinction clear (no category errors)
- ✓ Three-layer architecture defined (orchestrator/executor/deliverable)
- ✓ Genus-based validation framework specified
- ✓ Episode schema (JSON Schema) + YAML config complete
- ✓ Event tagging taxonomy (O_DIR, X_PROPOSE, T_TEST) defined

**Episode extraction pipeline (Phases 1–6) — v1.0:**
- ✓ EXTRACT-01: JSONL + git → unified canonical event stream — v1.0
- ✓ EXTRACT-02: Event tagger (O_DIR, O_GATE, O_CORR, X_PROPOSE, X_ASK, T_TEST, T_LINT, T_GIT_COMMIT, T_RISKY) — v1.0
- ✓ EXTRACT-03: Episode segmenter with start/end triggers + 30min TTL — v1.0
- ✓ EXTRACT-04: Episode field population (observation, orchestrator_action, outcome) — v1.0
- ✓ EXTRACT-05: Reaction labeler (approve/correct/redirect/block/question) with confidence — v1.0
- ✓ EXTRACT-06: Constraint extractor from correct/block reactions — v1.0
- ✓ DATA-01: DuckDB hybrid schema with incremental MERGE — v1.0
- ✓ DATA-02: JSON Schema validation (orchestrator-episode.schema.json) — v1.0
- ✓ DATA-03: YAML config (risk model, tags, reaction keywords, mode inference) — v1.0
- ✓ DATA-04: Provenance tracking (JSONL file + line ranges, git commits, tool call IDs) — v1.0
- ✓ CONST-01 through CONST-04: Constraint extraction, storage, severity, scope — v1.0
- ✓ VALID-01 through VALID-03: Genus-based validator, gold-standard workflow, quality metrics — v1.0
- ✓ TRAIN-01 through TRAIN-02: RAG baseline + shadow mode testing — v1.0
- ✓ MC-01 through MC-04: Mission Control real-time capture, tool provenance, review widget, SQLite — v1.0

**Live governance + intelligence (Phases 9–27) — v1.0:**
- ✓ ESCALATE-01 through ESCALATE-03: O_ESC tagging, escalation episodes, auto-forbidden constraints — v1.0
- ✓ AMNESIA-01 through AMNESIA-03: Decision durability index, cross-session amnesia detection, session audit CLI — v1.0
- ✓ WISDOM-01 through WISDOM-03: project_wisdom table, RAG wisdom retrieval, scope enforcement — v1.0
- ✓ GOVERN-01 through GOVERN-02: Governance document ingest (pre-mortems, DECISIONS.md), stability check integration — v1.0
- ✓ FEEDBACK-01 through FEEDBACK-03: Policy feedback loop, policy-sourced constraints, policy error rate metric — v1.0
- ✓ IDTRANS-01 through IDTRANS-05: Identification transparency — 35-point review pool, verdict routing, trust accumulation, Harness invariants — v1.0
- ✓ PREMISE-01 through PREMISE-06: PAG PreToolUse hook, staining, foil, Ad Ignorantiam, BtQ detection — v1.0
- ✓ DDF-01 through DDF-10: DDF substrate — O_AXS classification, Tier 1/2 markers, epistemological origin, spiral tracking, IntelligenceProfile — v1.0
- ✓ BRIDGE-01 through BRIDGE-04: Bridge-Warden structural integrity — 4 signal types, Op-8 validation, AI floating cable detection, 3D profile — v1.0
- ✓ ASSESS-01 through ASSESS-03: Candidate Assessment System — scenario generator, live session, assessment report — v1.0
- ✓ TOPO-01 through TOPO-05: Topological edge generation — axis_edges, ConjunctiveFlame, PAG FrontierChecker — v1.0
- ✓ LIVE-01 through LIVE-05: OPE Governance Bus — PreToolUse hook, SessionStart briefing, stream processor, inter-session bus, governing daemon — v1.0
- ✓ QUERY-01 through QUERY-04: Unified discriminated query interface — docs/sessions/code/all, cross-project via DuckDB ATTACH — v1.0
- ✓ Autonomous Loop Mode-Switch detection (EBC drift, STATE.md injection, /project:autonomous-loop-mode-switch) — v1.0
- ✓ GENEXT-01 through GENEXT-02: CLAUDE.md GENUS field, session_start genus hint — v1.0
- ✓ GENORACLE-01 through GENORACLE-03: /api/genus-consult bus endpoint, GenusOracleHandler, /genus-first bus path — v1.0
- ✓ REFRAME-01: /reframe global skill with three-tier capability detection + reasoning protocol selection — v1.0
- ✓ RXA-01 through RXA-05: ReactiveX v4 adoption — embedder, batch runner, stream processor, behavioral parity regression — v1.0

### Active

For v2.0 — OpenClaw integration and graduated autonomy:

**Preference Modeling:**
- [ ] PREF-01: Bradley-Terry preference model (50-80K params), approve/correct/block prediction
- [ ] PREF-02: ≥80% prediction accuracy on held-out validation set before autonomous approvals
- [ ] PREF-03: Calibration metrics (ECE, reliability diagrams)

**Learned Policy:**
- [ ] POLICY-01: Discrete RL policy (SB3 PPO, 7-mode action space) via behavioral cloning + fine-tuning
- [ ] POLICY-02: ≥70% shadow mode agreement on medium-risk tasks before autonomous deployment
- [ ] POLICY-03: Policy rollback mechanism if performance degrades

**Graduated Autonomy:**
- [ ] AUTO-01: Fully autonomous low-risk tasks (diff <50 lines, no protected paths)
- [ ] AUTO-02: Medium-risk tasks with preference model approval (confidence ≥85%)
- [ ] AUTO-03: Human approval required for high-risk tasks (protected paths, large diffs)

**Advanced Features:**
- [ ] ADV-01: Constraint deduplication with fuzzy matching + human review
- [ ] ADV-02: Retrieval approach experiments (BM25, embeddings, hybrid)
- [ ] ADV-03: DAgger correction loop for continual learning

**OpenClaw Integration:**
- [ ] Run ID injection at dispatch time (OPE_RUN_ID from OpenClaw)
- [ ] Cross-repo causal chain via run_id spanning multiple project sessions
- [ ] Builder/operator structural separation via OpenClaw Control Plane

### Out of Scope

- **Executor optimization** — Improving Claude Code's tool-call sequences (separate concern, not orchestrator learning)
- **Turn-level segmentation** — Decision points (evidence-triggered boundaries) are the correct causal unit
- **Commit-only correlation as learning signal** — Hides decisions, mistakes, corrections essential for policy learning
- **Executor-level tool call optimization** — This project trains orchestrator mode/scope/gates, not executor sequences
- **Cross-domain generalization** — Narrow scope: learns from one user's orchestration patterns
- **Real-time deployment without shadow mode** — Distribution shift in imitation learning is mathematically proven; shadow mode non-negotiable

## Context

**Domain:** AI agent orchestration, machine learning from interaction traces, live session governance, epistemological intelligence profiling

**Shipped v1.0 (2026-02-28):**
- 85,116 lines of Python
- 108 plans across 27 phases (32 entries with decimal insertions)
- 480 commits, 714 files, 23 days from first commit to completion
- Tech stack: Python + DuckDB + Pydantic + Starlette (governance bus) + ReactiveX v4 + Next.js (Mission Control review widget) + sentence-transformers (RAG)

**Projects in dataset:**
1. modernizing-tool (initial dataset, ~47 sessions, 299 turns, 119 commits)
2. orchestrator-policy-extraction (meta-project, captures this planning session)
3. personal-website (additional diversity)

**Known issues / technical debt for v2.0:**
- REQUIREMENTS.md traceability table has "Pending" status for requirements completed after Phase 13 (now resolved in archive)
- DAgger correction loop (ADV-03) requires shadow mode production data not yet available
- OpenClaw Control Plane not yet installed — builder/operator boundary is documented but not enforced structurally

## Constraints

- **Storage format**: DuckDB primary (not JSONL-only) — enables incremental updates and fast analytical queries
- **Session backup**: Always copy to git — data loss prevention is critical
- **Orchestrator focus**: Episodes must capture orchestrator decisions (mode/scope/gates), not executor tool calls
- **Evidence grounding**: All decisions validated against observation via genus-based checker — prevents floating abstractions
- **No human in loop eventually**: System must work with preference model + objective proxies for autonomous operation
- **Constraint durability**: Corrections must extract into enforceable constraints — prevents repeated mistakes
- **Bus fail-open**: PAG hook and session_start must fail open when bus unavailable — no blocking of sessions

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Decision-point episodes (not turn-level) | Turns are UI artifacts; decision points are causal units | ✓ Good |
| Orchestrator ≠ Executor separation | OpenClaw learns "what to do next"; Claude Code executes | ✓ Good |
| DuckDB + session backup to git | Incremental updates + data loss prevention | ✓ Good |
| Mission Control as real-time capture layer | Structured tasks = natural decision points; beats post-hoc correlation | ✓ Good |
| Genus-based validation | Prevents category errors, ensures evidence grounding | ✓ Good |
| Staging table upsert pattern (DuckDB) | CREATE TEMP → UPDATE → INSERT → DROP for DuckDB idempotency | ✓ Good |
| Word-boundary regex for mode inference | Prevents 'PR' matching 'production' in O_DIR keyword detection | ✓ Good |
| O_CORR as start trigger (not just O_DIR/O_GATE) | Corrections open new episodes — needed for feedback loop | ✓ Good |
| Unix socket + uvicorn/starlette for bus (p99=1.6ms) | Locked after spike: lightweight, no external deps, <200ms gov signal | ✓ Good |
| Bus fail-open | PAG and session_start must not block sessions if bus down | ✓ Good |
| TENTATIVE_END / CONFIRMED_END state machine | X_ASK is never an end trigger (mid-episode); defers episode_level signals until CONFIRMED_END | ✓ Good |
| Two-tier fidelity: event_level vs episode_level signals | Escalation/policy_violation fire immediately; amnesia deferred to CONFIRMED_END | ✓ Good |
| PAG staining: invalid parent node stains children | Prevents Stolen Concept fallacy at write boundaries | ✓ Good |
| GENUS field enforcement with fundamentality criterion | Two citable instances + causal explanation — mechanism vs symptom distinction | ✓ Good |
| CCD format for MEMORY.md entries | (ccd_axis | scope_rule | flood_example) enables axis-based retrieval vs surface similarity | ✓ Good |
| ReactiveX adoption: behavioral parity is the gate | Not test coverage — identical DuckDB outputs for identical inputs before/after adoption | ✓ Good |
| External operator pattern (cold observable wrapping) | Stateful StreamProcessor wrapped in cold observable via create_stream_processor_operator() | ✓ Good |
| ops.concat_map (not flat_map) for ordered stateful processors | flat_map reorders; ordered processing required for state machine | ✓ Good |
| Deposit-not-detect as governing axis | Every Phase 15–18 component evaluated: does it deposit to memory_candidates? | ✓ Good |
| Reconstruction-not-accumulation for AI intelligence | MEMORY.md = Layer 1 canon; memory_candidates = Layer 2 pending; session context = ephemeral | ✓ Good |

---
*Last updated: 2026-02-28 after v1.0 milestone*
