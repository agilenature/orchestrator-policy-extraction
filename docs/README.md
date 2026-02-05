# Documentation Index

This directory contains all project documentation organized by type.

## Core Documents

### [PROJECT.md](PROJECT.md)
**Formal problem statement and project goals**
- Problem definition: Learn orchestration policies from Claude Code sessions
- Multi-project scope (modernizing-tool + orchestrator-policy-extraction + future)
- Turn-level granularity approach (observation → action → reaction)
- Success criteria, risks, and non-goals

### [ROADMAP.md](ROADMAP.md)
**Detailed phase-by-phase implementation plan**
- 7 phases (0-6 defined, 7+ future)
- Phase 0: Data Infrastructure (IN PROGRESS)
- Phases 1-2: Correlation & Extraction
- Phases 3-5: Taxonomy, RAG Orchestrator, Evaluation
- Phase 6: Instrumentation & Growth
- Phase 7+: OpenClaw Integration (future)
- Timeline: ~12 weeks for Phases 0-6

---

## Design Documents (`design/`)

### [design/WHY_TURN_LEVEL.md](design/WHY_TURN_LEVEL.md)
**Comprehensive explanation: Turn-level vs. commit-level correlation**
- Why turn-level episodes are superior for policy learning
- Concrete examples with same commit, different orchestration patterns
- 7 key advantages (granularity, reactions, error correction, etc.)
- Comparison tables and policy learning examples
- The bottom line: Commits are destinations, episodes are journeys

**Future documents:**
- `design/architecture.md` - Overall system architecture
- `design/data-model.md` - Episode and taxonomy schemas
- `design/correlation-algorithm.md` - Hash-based matching details

---

## Guides (`guides/`)

### [guides/INSTRUMENTATION.md](guides/INSTRUMENTATION.md)
**Step-by-step guide for adding new projects to the dataset**
- Prerequisites: Git hooks for session ID tracking
- 7-step onboarding process
- Validation checklist
- Troubleshooting section
- Templates for git hooks and metadata

**Future guides:**
- `guides/CONTRIBUTING.md` - How to contribute to the project
- `guides/DATA_COLLECTION.md` - Best practices for session data
- `guides/RUNNING_PIPELINE.md` - How to run correlation and extraction

---

## Research Documents (`research/`)

These documents capture the initial research and planning that led to the current approach.

### [research/feasibility-assessment.md](research/feasibility-assessment.md)
**Original feasibility assessment from planning phase**
- Data availability analysis
- Correlation challenge identification
- Episode extraction feasibility
- Risk assessment and go/no-go recommendation

### [research/formal-problem-statement.md](research/formal-problem-statement.md)
**Initial problem formulation**
- Subproblem A: Trace correlation
- Subproblem B: Policy learning
- Mathematical formulation

### [research/fundamental-issue.md](research/fundamental-issue.md)
**Core challenge description**
- The need for orchestration policy learning
- Why this matters for AI-assisted development

### [research/delegation-to-openclaw.md](research/delegation-to-openclaw.md)
**Phase 7+ planning: Safe autonomous delegation**
- Staged promotion ladder (shadow → read-only → write → PR → merge)
- Sandboxing and security considerations
- Governance architecture

---

## Navigation

**Getting Started:**
1. Read [../README.md](../README.md) for project overview
2. Read [PROJECT.md](PROJECT.md) for detailed goals
3. Skim [ROADMAP.md](ROADMAP.md) for phase breakdown

**Understanding the Approach:**
1. Read [design/WHY_TURN_LEVEL.md](design/WHY_TURN_LEVEL.md) for core innovation
2. Review [research/](research/) documents for context

**Adding Data:**
1. Follow [guides/INSTRUMENTATION.md](guides/INSTRUMENTATION.md)

**Implementation Status:**
- See [../.planning/STATE.md](../.planning/STATE.md) for current progress
- See [../.planning/PHASE-0-STATUS.md](../.planning/PHASE-0-STATUS.md) for Phase 0 details

---

## Document Status

| Document | Status | Last Updated |
|----------|--------|--------------|
| PROJECT.md | ✅ Complete | 2026-02-05 |
| ROADMAP.md | ✅ Complete | 2026-02-05 |
| design/WHY_TURN_LEVEL.md | ✅ Complete | 2026-02-05 |
| guides/INSTRUMENTATION.md | ✅ Complete | 2026-02-05 |
| research/*.md | ✅ Archived | 2026-02-05 |

---

## Contributing to Docs

**When adding new documents:**
1. Place in appropriate subdirectory (design/guides/research)
2. Update this README with link and description
3. Follow markdown best practices (headings, code blocks, tables)
4. Include examples and diagrams where helpful

**Document naming:**
- Use kebab-case: `my-document.md`
- Be descriptive: `hash-based-correlation.md` not `correlation.md`
- Include version if iterating: `architecture-v2.md`
