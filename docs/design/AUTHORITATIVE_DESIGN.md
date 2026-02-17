# Orchestrator Training System — Authoritative Design Specification

**Version:** 2.0
**Date:** 2026-02-10
**Status:** Canonical Reference

---

## Executive Summary

This document specifies the complete system for training OpenClaw as an autonomous orchestrator to replace the human orchestrator. It integrates:

1. **Decision-point episode extraction** (the learning substrate)
2. **Three-layer architecture** (orchestrator/executor/deliverable separation)
3. **Genus-based validation** (ensuring conceptual coherence)
4. **Mission Control integration** (real-time capture + governance)
5. **Preference model development** (replacing human feedback)
6. **Constraint extraction** (durable policy from corrections)

**Core Insight:** Commit-level correlation captures *what was delivered* but hides *how to decide what to do next*. Decision-point episodes expose the orchestration process: observations, actions, outcomes, mistakes, corrections, and constraints.

---

## Part 1: System Genus & Essence

### 1.1 Genus (Proximate Category)

A **supervised governance-and-learning system for agentic orchestration**.

### 1.2 Differentia (What Makes It This System)

It **forces orchestration decisions to be explicit, validated, and logged as trainable episodes**, so governance and learning become the same pipeline.

### 1.3 Essence Label

**Orchestrator Training Cockpit**

### 1.4 What It Does

Three simultaneous outputs:

1. **Operational control** (today): Human-in-the-loop cockpit that structures work into tasks/workflow states, dispatches to agents, enforces gates
2. **Governance** (today + tomorrow): Explicit gates, risk levels, protected paths, allowlists, approval steps before state advancement
3. **Training data** (tomorrow): Every checkpoint becomes an episode with: observation, orchestrator decision, outcome, reaction labels, extracted constraints

---

## Part 2: Critical Distinctions (Avoiding Category Errors)

### 2.1 Orchestrator vs. Executor

**DO NOT CONFUSE THESE TWO POLICIES:**

| Aspect | Orchestrator (OpenClaw) | Executor (Claude Code) |
|--------|------------------------|------------------------|
| **Action space** | Mode, scope, constraints, gates, delegation | Tool calls: Read/Grep/Edit/Write/Bash |
| **Decision frequency** | Decision points (after new evidence, proposals, risks) | Every tool call |
| **Learning target** | What to do next (strategy) | How to implement (tactics) |
| **Training data** | Orchestrator episodes | Executor episodes (separate) |

If you blur these, you'll train OpenClaw to "act like Claude" (tool micro-steps) instead of "act like you" (sequencing + risk + scope + gates).

### 2.2 Decision Points vs. Turns

**The unit is not "turns." The unit is decision points.**

A decision point is a checkpoint where the orchestrator can rationally choose among alternatives, typically after:

- New evidence arrives (tool output, test results, file inspection)
- A plan/proposal appears
- A risk boundary is approached (destructive command, large refactor)
- User feedback arrives (approval/correction/redirect)

A single chat "turn" may contain multiple decision points or none. Commits are even coarser: they're deliverables, not decisions.

### 2.3 Reactions → Preference Model + Constraints

**While human present:**
- User reactions are powerful supervised signal (approve/correct/redirect/block/question)

**When OpenClaw replaces human:**
- Reaction signal becomes sparse/absent
- Must convert to:
  - **Objective proxies** (tests/CI/lint/diff/paths/build)
  - **Learned preference model** (trained from historical reactions to predict approval)
  - **Constraint store** (durable rules extracted from corrections)

---

## Part 3: Three-Layer Architecture

### Layer 1: Orchestrator Episodes (PRIMARY — OpenClaw Must Learn This)

**Observation (O_t):**
- Repo summary (changed files, diff stats, hotspots)
- Quality state (tests, lint, build status)
- Context (recent work, open questions, constraints in force)

**Orchestrator Action (A_t):**
- Mode: Explore / Plan / Implement / Verify / Integrate / Triage / Refactor
- Goal: What to achieve
- Scope: Which paths, what to avoid
- Constraints in force: Active rules
- Executor instruction: Directive to Claude Code
- Gates: Tests required, approval needed, etc.
- Risk: low/medium/high/critical

**Outcome (Y_t):**
- Executor effects (tool calls, files touched, commands ran, git events)
- Quality (tests/lint/build status, diff stats)
- Reaction (when human present): approve/correct/redirect/block/question
- Reward signals (objective proxies + preference model prediction)

**Constraints Extracted:**
- From corrections/blocks: durable rules ("avoid regex XML", "no hardcoded secrets")
- Severity: warning / requires_approval / forbidden
- Scope: paths affected
- Detection hints: patterns to detect violations

### Layer 2: Executor Episodes (SECONDARY — Claude Optimization)

Tool-call sequences (Read/Grep/Edit/Bash/Write) for:
- Diagnosing execution success/failure
- Improving reliability
- Learning implementation patterns

### Layer 3: Deliverable Episodes (VALIDATION — Milestones)

Commit/PR level correlation for:
- Temporal alignment
- Validation: did episodes produce real deliverables?
- Milestone tracking
- Measuring downstream quality

---

## Part 4: Episode Extraction Pipeline

### Stage A: Normalize Logs → Unified Event Stream

Transform JSONL records, tool results, git events into canonical events:
- `event_id`, `ts_utc`, `session_id`, `actor`, `type`, `payload`, `links`

### Stage B: Tag Events (Classification Layer)

**Orchestrator tags:**
- `O_DIR`: directive ("do X", "implement Y")
- `O_GATE`: approval/stop/proceed/commit
- `O_CORR`: correction ("no, do it this way", "avoid regex")
- `O_REDIRECT`: scope/priority change
- `O_QUESTION`: clarifying question

**Executor tags:**
- `X_PROPOSE`: proposes plan/options/tradeoffs
- `X_ASK`: asks question/approval
- `X_PATCH`: provides diff/patch
- `X_SUMMARY`: synthesizes findings

**Tool tags:**
- `T_TEST`: test command (pytest, go test, etc.)
- `T_LINT`: lint command (ruff, eslint, etc.)
- `T_BUILD`: build command
- `T_GIT_COMMIT`: commit created
- `T_GIT_PUSH`: push attempt
- `T_RISKY`: dangerous command (rm -rf, sudo, etc.)

### Stage C: Segment into Decision-Point Episodes

**Episode start triggers:**
- `O_DIR` or `O_GATE` (human directive)

**Episode end triggers (decision boundaries):**
1. Executor proposal/question (`X_PROPOSE`, `X_ASK`)
2. Tool milestone result (`T_TEST`, `T_LINT`, `T_BUILD` completed)
3. Risk boundary (`T_RISKY`, `T_GIT_PUSH`)
4. Commit created (`T_GIT_COMMIT`)
5. Timeout (30 minutes of idle)

### Stage D: Populate Episode Fields

**Mode inference** (deterministic v0):
- "investigate", "scan", "find" → Explore
- "plan", "options", "tradeoffs" → Plan
- "implement", "add feature", "write" → Implement/Refactor
- "run tests", "verify", "check" → Verify/Triage
- "commit", "PR", "merge" → Integrate

**Risk computation:**
- Protected paths touched → risk = 1.0 (critical)
- Lines ≤ 50, files ≤ 3 → risk = 0.2 (low)
- Lines ≤ 300, files ≤ 10 → risk = 0.5 (medium)
- Otherwise → risk = 0.8 (high)

### Stage E: Reaction Labeling

From next human message after episode boundary:
- **approve**: "yes", "looks good", "go ahead", "commit", "ship", or implicit (next task without complaint)
- **correct**: "no, do X instead", "don't use Y, use Z", "that's wrong"
- **redirect**: "instead focus on", "different direction" (without saying previous was wrong)
- **block**: "NO", "stop", "don't do that", "never" (especially for destructive actions)
- **question**: "why?", "what about?", "how does?"

### Stage F: Constraint Extraction

When reaction ∈ {correct, block}, extract:
- `text`: Normalized statement ("Avoid regex for XML parsing")
- `severity`: block → forbidden; correct → requires_approval (unless soft → warning)
- `scope.paths`: Module/file mentioned, else repo-wide
- `detection_hints`: Command patterns, forbidden strings, file globs, library names

---

## Part 5: Genus-Based Validation

### 5.1 Purpose

A validator that runs at decision points and workflow transitions to ensure decisions are:
- **Classified correctly** (genus identification)
- **Justified by evidence** (grounded in observation)
- **Consistent with constraints** (non-contradictory)
- **Auditably traceable** (provenance)

### 5.2 Validation Layers

**A. Schema-level validity:**
- mode ∈ {Explore, Plan, Implement, Verify, Integrate, Triage, Refactor}
- Explicit scope (paths + avoid)
- Explicit gates
- Explicit risk
- Concrete executor instruction (not "do the thing")

**B. Evidence grounding validity:**
- If Implement chosen: clear requirements stated? Relevant files inspected? Constraints loaded?
- If Integrate chosen: tests pass? Constraints satisfied? Approval gate met?

**C. Non-contradiction validity:**
- mode=Explore but write_allowed=true → flag (unless explicit override)
- gate=no_network but instruction says "look up docs online" → flag
- gate=no_write_before_plan but mode=Implement without plan artifact → flag

**D. Constraint enforcement validity:**
- Diffs against forbidden patterns
- Protected path touches
- Risky commands
- Dependency additions
- Secret leakage patterns

**E. Episode integrity validity (learning hygiene):**
- Observation precedes action
- Outcome follows action
- Reaction labels attached to correct boundary
- Provenance pointers exist

### 5.3 Mode Differentia (Enforced Requirements)

- **Explore**: Read-only by default; output reduces uncertainty
- **Plan**: Compare options/tradeoffs; decide constraints/gates before writing
- **Implement**: Produce changes within declared scope; respect constraints; requires post-change verification gates
- **Verify**: Run tests/lint/checks; aim is truth about correctness
- **Integrate**: Commit/PR/merge; requires stricter gates and approvals

---

## Part 6: Mission Control Integration (Operationalization)

### 6.1 What Mission Control Becomes

**Mission Control = Orchestrator Training Cockpit**

It sits above OpenClaw and:
1. **Creates decision points** (structured tasks + planning checkpoints)
2. **Collects ground-truth reactions** (approvals/corrections during review)
3. **Provides governance gates** (cannot progress task state unless gates satisfied)

### 6.2 Required Mission Control Upgrades

**A. Task Structure Enhancement**

Add required fields to tasks:
- `orchestrator_mode` (genus)
- `goal`
- `scope.paths / scope.avoid`
- `risk`
- `gates`
- `constraints_in_force`

**B. Planning Output = Structured Orchestrator Action**

Planning Q&A must output:
- mode, goal, scope, constraints_in_force, gates, risk, executor_instruction
- Not just prose

**C. Review Widget = Reaction + Constraint Extraction**

Review must capture:
- Reaction label (approve/correct/redirect/block/question)
- Confidence
- If correct/block: extract constraint (text, scope, severity, detection hints)

**D. Tool Provenance Recording**

Via OpenClaw Gateway connection, store per task/episode:
- Tool calls made
- Files touched
- Commands run
- Test results
- Commit hashes created

**E. Episode Tables in SQLite**

Add tables:
- `episodes` (full schema)
- `episode_events` (provenance)
- `constraints` (constraint store)
- `approvals` (gate decisions)
- `commit_links` (validation layer)

### 6.3 Workflow State Gates

Mission Control workflow becomes epistemic (states mean "we know X"):
- PLANNING → IN PROGRESS: requires valid Plan artifact (passes validator)
- IN PROGRESS → REVIEW: requires tests run + constraints check pass
- REVIEW → DONE: requires "approve" reaction or objective criteria threshold

---

## Part 7: JSON Schema (Strict)

See `data/schemas/orchestrator-episode.schema.json` for full schema.

**Core structure:**

```json
{
  "episode_id": "uuid",
  "timestamp": "2026-02-10T12:34:56Z",
  "project": { "repo_path", "branch", "commit_head" },
  "phase": "03.1-01",
  "task_id": "auth-xml-parser",

  "observation": {
    "repo_state": { "changed_files", "diff_stat", "hotspots" },
    "quality_state": { "tests", "lint", "build" },
    "context": { "recent_summary", "open_questions", "constraints_in_force" }
  },

  "orchestrator_action": {
    "mode": "Explore|Plan|Implement|Verify|Integrate|Triage|Refactor",
    "goal": "...",
    "scope": { "paths": [...], "avoid": [...] },
    "executor_instruction": "...",
    "gates": [ {"type": "run_tests", "params": {...}} ],
    "risk": "low|medium|high|critical"
  },

  "outcome": {
    "executor_effects": { "tool_calls_count", "files_touched", "commands_ran", "git_events" },
    "quality": { "tests_status", "lint_status", "diff_stat" },
    "reaction": { "label": "approve|correct|redirect|block|question", "message", "confidence" },
    "reward_signals": {
      "objective": { "tests": 0-1, "lint": 0-1, "diff_risk": 0-1 },
      "preference_model": { "predicted_reaction", "confidence" }
    }
  },

  "constraints_extracted": [
    { "constraint_id", "text", "severity", "scope", "detection_hints" }
  ],

  "provenance": {
    "sources": [ {"type": "claude_jsonl|terminal_log|git|ci", "ref": "..."} ]
  }
}
```

---

## Part 8: Configuration (Risk Model, Tags, Keywords)

`data/config.yaml`:

```yaml
episode_builder:
  idle_timeout_minutes: 30
  commit_link_window_minutes: 10

risk:
  protected_paths:
    - "infra/"
    - "db/migrations/"
    - "auth/"
    - ".github/workflows/"
  diff_thresholds:
    low: { lines: 50, files: 3, risk: 0.2 }
    medium: { lines: 300, files: 10, risk: 0.5 }
    high: { risk: 0.8 }
  risky_commands:
    - "rm -rf"
    - "sudo"
    - "curl * | bash"
    - "git push origin main"

tags:
  test_commands: ["pytest", "go test", "mvn test", "npm test", "cargo test"]
  lint_commands: ["ruff", "eslint", "prettier", "black", "mypy"]

reaction_keywords:
  block: ["NO", "don't", "stop", "never"]
  correct: ["no, do", "instead", "use", "avoid"]
  approve: ["yes", "ok", "looks good", "commit", "ship"]
  redirect: ["instead focus", "different direction"]
```

---

## Part 9: Training Pipeline (What You Build With Episodes)

### 9.1 Baseline Orchestrator (RAG-Based)

- Retrieve similar orchestrator episodes by context (observation similarity)
- Propose next orchestrator action
- Run in **shadow mode** first (no execution, just recommendations)

### 9.2 Learned Orchestrator Policy

Train π(A | O) to choose:
- mode, scope, constraints, gates, executor instruction shape
- Escalation vs proceed

### 9.3 Preference Model (Simulated Human)

Train from historical (observation, action, reaction) tuples:
- Input: observation + proposed orchestrator action
- Output: probability of approve/correct/block
- Becomes substitute feedback when human absent

### 9.4 Governing Execution Harness

**Policy chooses. Harness enforces. Logs explain.**

- Sandbox (file system, network)
- Allowlists (commands, paths)
- Approvals (risky operations gate)
- Branch/PR gates (no direct main commits)
- Constraint enforcement (validator)

---

## Part 10: Rollout Strategy

### Phase 1: Data Collection (Now)

- Extract decision-point episodes from existing sessions
- Build constraint store from corrections
- Validate episode quality (spot-check)

### Phase 2: Baseline Orchestrator (Shadow Mode)

- RAG over episodes
- Generate recommendations
- Compare to actual human decisions
- Measure agreement rate

### Phase 3: Preference Model Training

- Train on historical reactions
- Test prediction accuracy
- Use as approval proxy in low-risk scenarios

### Phase 4: Learned Policy Training

- Supervised learning: imitate high-confidence approved episodes
- Reinforcement: optimize objective + preference model signals
- Constrained by validator + harness

### Phase 5: Graduated Autonomy

- Low-risk tasks: full autonomy with objective gates
- Medium-risk: autonomy with preference model approval
- High-risk: human approval required (governance never bypassed)

---

## Part 11: Success Criteria

### Data Quality
- ≥99% episodes validate against schema
- ≥85% mode inference accuracy (spot-check)
- ≥80% reaction label confidence (manual review)
- Constraints extracted from ≥90% of corrections

### Orchestrator Quality
- Shadow mode agreement: ≥70% with human decisions (baseline)
- Preference model accuracy: ≥80% on held-out reactions
- Zero critical failures (harness catches all forbidden actions)
- Objective quality maintained or improved (tests, lint, build)

### Learning Efficiency
- 10x more episodes than commits (density)
- Negative examples ≥20% (corrections, blocks, redirects)
- Constraint coverage: ≥95% of rules in force applied correctly

---

## Part 12: What Commit-Only Correlation Misses (Why This Approach)

**Commit-only view:**
```
Session ABC → Commit def456 "feat: Implement XML parser"
```

**What you know:** Deliverable exists, files changed
**What you DON'T know:**
- ❌ Sequencing decisions (inspect first vs implement first)
- ❌ Mistakes and recoveries (regex tried and rejected)
- ❌ Constraints invoked ("avoid regex", "no hardcoded secrets")
- ❌ Gates applied (when tests required, when review needed)
- ❌ Why orchestrator chose this plan over alternatives

**Decision-point episodes capture:**
- ✅ Observation that led to decision
- ✅ Orchestrator action (mode, scope, constraints, gates)
- ✅ Outcome quality (tests, lint, diff)
- ✅ Reaction (approve/correct/redirect/block)
- ✅ Constraints extracted from corrections
- ✅ Provenance (links to logs, commits, tool calls)

**The difference:** Commits are outputs of orchestration. Episodes are the orchestration itself.

---

## Part 13: Implementation Priorities

### Priority 1 (Core Pipeline)
1. Event stream normalizer (JSONL + git → unified events)
2. Event tagger (O_DIR, X_PROPOSE, T_TEST, etc.)
3. Episode segmenter (decision-point detection)
4. Field populator (observation, action, outcome)
5. Reaction labeler (approve/correct/redirect/block/question)

### Priority 2 (Learning Infrastructure)
6. Constraint extractor (corrections → durable rules)
7. Validator (genus-based, schema + evidence + consistency)
8. Reward signal calculator (objective proxies)
9. Episode database (DuckDB tables)
10. Provenance tracker (source links)

### Priority 3 (Mission Control Integration)
11. Task structure enhancement (mode, scope, gates, constraints)
12. Planning output structuring (orchestrator action schema)
13. Review widget (reaction + constraint extraction UI)
14. Tool provenance recording (via OpenClaw Gateway)
15. Episode tables in SQLite

### Priority 4 (Training & Deployment)
16. RAG baseline orchestrator (retrieve + recommend)
17. Preference model training (reaction predictor)
18. Shadow mode testing (compare to human)
19. Learned policy training (supervised + RL)
20. Graduated autonomy rollout

---

## Appendices

### A. Glossary

- **Orchestrator**: The decision-making layer (OpenClaw target) that chooses mode, scope, constraints, gates
- **Executor**: The tool-using layer (Claude Code) that performs reads, edits, tests, etc.
- **Decision point**: A checkpoint where orchestrator can rationally choose among alternatives
- **Episode**: (Observation, Orchestrator Action, Outcome) triple capturing one decision point
- **Constraint**: Durable rule extracted from correction ("avoid regex XML", "no hardcoded secrets")
- **Gate**: Requirement before proceeding (run tests, get approval, check constraints)
- **Preference model**: ML model predicting human approval/correction from observation + proposed action
- **Governing harness**: Safety layer that enforces constraints, gates, allowlists regardless of policy

### B. Related Documents

- `WHY_TURN_LEVEL - Improved.md`: Full technical rationale for decision-point episodes
- `The Genus Method - Justification.md`: Philosophical grounding for validation approach
- `Mission Control - supervisory control layer.md`: Integration strategy
- `data/schemas/orchestrator-episode.schema.json`: Complete JSON schema
- `.planning/PHASE-0-DECISIONS.md`: Infrastructure architecture decisions

---

**End of Authoritative Design Specification v2.0**

This document supersedes all prior design documents and serves as the single source of truth for system architecture, episode extraction, validation, and training pipeline.
