# Orchestrator Policy Extraction

## What This Is

A system that learns orchestration policies from Claude Code session history to train OpenClaw as an autonomous orchestrator. It extracts decision-point episodes (observation → orchestrator action → outcome) from past sessions, builds a durable constraint store from human corrections, and enables graduated autonomy where OpenClaw replaces the human orchestrator while Claude Code remains the executor.

## Core Value

Episodes capture **how to decide what to do next** (orchestrator decisions: mode/scope/gates/constraints), not just what was delivered (commits), enabling policy learning that scales human judgment instead of human typing.

## Requirements

### Validated

✓ **Conceptual foundation established** — Phase 0 complete
- ✓ Decision-point episodes beat commit-only correlation (design validated)
- ✓ Orchestrator vs executor distinction clear (no category errors)
- ✓ Three-layer architecture defined (orchestrator/executor/deliverable)
- ✓ Genus-based validation framework specified
- ✓ Mission Control integration strategy documented
- ✓ Preference model + constraint extraction approach designed
- ✓ Episode schema (JSON Schema) complete
- ✓ Event tagging taxonomy (O_DIR, X_PROPOSE, T_TEST) defined
- ✓ Configuration structure (risk model, tags, keywords) specified
- ✓ Concrete vision documented (Month 1-7+ timeline with UI mockups)

### Active

Building toward these capabilities:

**Phase 0.5: Schema & Config Finalization**
- [ ] Create `data/schemas/orchestrator-episode.schema.json` from design spec
- [ ] Create `data/config.yaml` with risk model, event tags, reaction keywords
- [ ] Validate schema against worked examples from design docs

**Phase 1: Episode Builder (Core Pipeline)**
- [ ] Event stream normalizer (JSONL + git → unified events)
- [ ] Event tagger (O_DIR, X_PROPOSE, T_TEST classification)
- [ ] Episode segmenter (decision-point detection with start/end triggers)
- [ ] Field populator (observation, action, outcome derivation)
- [ ] Reaction labeler (approve/correct/redirect/block/question)
- [ ] Extract 100+ episodes from modernizing-tool project
- [ ] Achieve ≥85% mode inference accuracy on manual validation

**Phase 2: Constraint Store & Validator**
- [ ] Constraint extractor (corrections → durable rules with severity/scope)
- [ ] Validator (genus-based multi-layer checks: schema, evidence, consistency)
- [ ] Reward signal calculator (objective proxies: tests/lint/diff/risk)
- [ ] DuckDB database integration for episode storage
- [ ] Provenance tracking (links to source logs/commits)

**Phase 3: Mission Control Integration**
- [ ] Task structure enhancement (add orchestrator mode/scope/gates fields)
- [ ] Planning output structuring (emit orchestrator action JSON)
- [ ] Review widget (reaction labels + constraint extraction UI)
- [ ] Tool provenance recording via OpenClaw Gateway
- [ ] Episode tables in SQLite for real-time capture
- [ ] Real-time event streaming (no post-hoc correlation needed)

**Phase 4: Training Infrastructure**
- [ ] RAG baseline orchestrator (retrieve similar episodes, recommend actions)
- [ ] Preference model training (predict approve/correct/block from context)
- [ ] Shadow mode testing (compare recommendations to human decisions)
- [ ] Learned policy training (supervised + reinforcement learning)
- [ ] Graduated autonomy rollout (low/medium/high risk tiers)

### Out of Scope

- **Executor optimization** — Improving Claude Code's tool-call sequences (separate concern, not orchestrator learning)
- **Commit-only correlation as learning signal** — Useful for validation layer but insufficient for policy learning (hides decisions/mistakes/constraints)
- **Turn-level segmentation** — Wrong unit; decision points are the causal unit, not UI turns
- **Generic task automation** — This is specifically for learning orchestration policy, not general-purpose automation
- **Real-time deployment without validation** — Graduated autonomy only after shadow mode proves ≥70% agreement
- **Training on floating abstractions** — All decisions must be grounded in evidence and validated by genus-based checker

## Context

**Domain:** AI agent orchestration, machine learning from interaction traces, policy learning
**Existing work:**
- 5 design documents in `docs/design/` (integrated into AUTHORITATIVE_DESIGN.md)
- Historical Claude Code sessions from modernizing-tool and orchestrator-policy-extraction projects
- Phase 0 infrastructure decisions documented in `.planning/PHASE-0-DECISIONS.md`
- DuckDB chosen as primary storage (incremental updates, analytical queries)
- Session backup strategy: copy + commit to git (data loss prevention)

**Key insight from design evolution:**
- Original "turn-level" intuition was directionally correct but imprecise
- Decision-point episodes (not turns) are the correct unit
- Orchestrator actions (mode/scope/gates/constraints) not executor tool calls
- User reactions must convert to preference model + objective proxies for human-absent operation

**Projects in dataset:**
1. modernizing-tool (initial dataset, ~47 sessions, 299 turns, 119 commits)
2. orchestrator-policy-extraction (meta-project, captures this planning session)
3. personal-website (additional diversity)

## Constraints

- **Storage format**: DuckDB primary (not JSONL-only) — enables incremental updates and fast analytical queries
- **Session backup**: Always copy to git (not reference-in-place) — data loss prevention is critical
- **Orchestrator focus**: Episodes must capture orchestrator decisions (mode/scope/gates), not executor tool calls — prevents training the wrong policy
- **Evidence grounding**: All decisions validated against observation via genus-based checker — prevents floating abstractions
- **No human in loop eventually**: System must work with preference model + objective proxies, not requiring human reactions — enables autonomous operation
- **Constraint durability**: Corrections must extract into enforceable constraints (not ephemeral feedback) — prevents repeated mistakes
- **Mission Control dependency**: Phase 3 requires access to Mission Control repository (external blocker)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Decision-point episodes (not turn-level) | Turns are UI artifacts; decision points are causal units where orchestrator chooses among alternatives | ✓ Good — prevents category errors, aligns with policy learning |
| Orchestrator ≠ Executor separation | OpenClaw learns "what to do next" (mode/scope/gates), Claude Code executes tool calls | ✓ Good — clear learning target, no confusion |
| Three-layer architecture | Orchestrator episodes (primary), Executor episodes (secondary), Deliverable episodes (validation) | — Pending implementation |
| DuckDB + session backup to git | Incremental updates + data loss prevention + reproducibility | ✓ Good — proven in Phase 0 decisions |
| Mission Control as operationalization layer | Real-time capture beats post-hoc correlation; structured tasks = natural decision points | — Pending (requires repo access) |
| Preference model replaces human reactions | Reactions train predictor + extract constraints for autonomous operation | — Pending training |
| Genus-based validation | Prevents category errors (orchestrator/executor), ensures evidence grounding | — Pending validator implementation |
| Skip codebase mapping | Existing design docs provide sufficient context; no need to map code before building | — Pending (decision made during GSD init) |

---
*Last updated: 2026-02-10 after initialization with complete design context*
