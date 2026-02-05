# Orchestrator Policy Extraction (OPE)

## Problem Statement

**Goal:** Learn orchestration policies from Claude Code session traces and git commits to enable safe, staged delegation to autonomous agents (OpenClaw).

**Vision:** Build a system that:
1. Correlates Claude Code session events with git commits across multiple projects
2. Extracts turn-level orchestration episodes (observation → action → reaction)
3. Learns policies for predicting effective next actions
4. Enables safe delegation through staged promotion (shadow → read-only → write-in-branch → PR autopilot)

## Multi-Project Scope

This is a **multi-project dataset** that will grow over time. Initial projects:

1. **modernizing-tool** - C++ codebase modernization project
   - Sessions: Jan 30 - Feb 3, 2026 (21 parent sessions, 27 subagents)
   - Commits: Feb 3-5, 2026 (119 commits, 53% Claude co-authored)
   - Rich orchestration patterns: phase-based workflow, test-driven development

2. **orchestrator-policy-extraction** (this project) - Meta-learning opportunity
   - Will capture our OWN orchestration decisions
   - Provides diverse interaction types (planning, architecture, implementation)
   - Bootstraps dataset with complex multi-phase project patterns

3. **[Future projects]** - To be added following instrumentation guide

## Core Innovation: Turn-Level Granularity

Instead of coarse commit-level correlation, we extract fine-grained episodes:

```
Episode = {
  observation: {
    conversation_context,
    file_state,
    phase_label,
    test_status,
    error_logs,
    current_task
  },
  claude_action: {
    tool_call: "Read/Edit/Bash/Task/...",
    parameters: {...},
    reasoning: "..."
  },
  user_reaction: {
    type: "approve/correct/redirect/block/question",
    message: "...",
    follow_up_action: {...}
  }
}
```

This captures **orchestration decision-making**, not just deliverables.

## Key Technical Insights

### 1. Session-Commit Correlation: Hash Extraction (95%+ Precision)
- Extract file hashes from session tool calls (Read/Edit/Write)
- Match against commit diffs
- Temporal proximity scoring
- **No manual labeling required** for high-confidence links

### 2. User Reactions as Policy Signal
- User's NEXT prompt is the ground truth for "what should happen next"
- Reactions reveal orchestration quality (corrections = policy failure)
- Rich taxonomy: approval, correction, redirection, blocking, clarification

### 3. Multi-Project Architecture
- Project registry for metadata tracking
- Per-project and cross-project analysis capabilities
- Instrumentation guide for consistent future data capture

## Success Criteria

### Phase 1 (Infrastructure & Extraction)
- ✅ Multi-project data infrastructure established
- ✅ Session-commit correlation achieves >90% precision
- ✅ Turn-level episodes extracted from all projects
- ✅ Reaction taxonomy validated (>85% inter-rater agreement)

### Phase 2 (Policy Learning)
- ✅ RAG-based baseline orchestrator built
- ✅ Shadow mode evaluation shows >70% action agreement with humans
- ✅ No dangerous action recommendations

### Phase 3 (Deployment)
- ✅ OpenClaw integration with sandboxing
- ✅ Staged promotion ladder implemented
- ✅ Read-only operator achieves 80%+ reliable evidence gathering

## Non-Goals

- ❌ Single unified ML model (start with RAG retrieval)
- ❌ Full autonomy immediately (staged promotion ladder)
- ❌ Cross-domain generalization (start with software engineering tasks)
- ❌ Real-time orchestration (offline learning, online evaluation)

## Risks & Mitigations

| Risk | Probability | Mitigation |
|------|-------------|------------|
| Insufficient training data | MEDIUM | Multi-project approach; continue collecting data |
| Policy doesn't generalize | MEDIUM | Start single-project, validate before expanding |
| OpenClaw sandbox escape | LOW | Strict allowlists, approval gates, extensive testing |
| Maintenance burden | MEDIUM | Keep simple (RAG > custom ML), automate data ingestion |

## Meta-Learning Opportunity 🔄

This project's own Claude Code sessions will become part of the dataset:
- Planning sessions (like this one!)
- Architecture decisions
- Implementation iterations
- Debugging and corrections

This creates a diverse dataset capturing different orchestration modes.

## Related Documents

- `ROADMAP.md` - Detailed phase breakdown with milestones
- `INSTRUMENTATION.md` - Guide for adding new projects to dataset
- `data/projects.json` - Project registry
- `.planning/phases/` - GSD phase plans and verification reports
