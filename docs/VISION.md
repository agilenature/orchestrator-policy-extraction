# Orchestrator Training System — Concrete Vision

**Version:** 1.0
**Date:** 2026-02-10
**Status:** North Star — What Success Looks Like

---

## The Problem We're Solving

**Today:** You manually orchestrate every Claude Code session:
- You decide: "First explore the codebase, then plan, then implement"
- You set constraints: "Don't hardcode secrets", "Avoid regex for XML", "Run tests before committing"
- You correct mistakes: "No, use library X not regex", "That's too risky, ask first"
- You enforce gates: "Run tests now", "Show me the diff before merging"

**Pain points:**
- Every lesson is ephemeral (next session, same mistake can happen again)
- Doesn't scale (you can't orchestrate 10 parallel tasks)
- 30+ minutes of your time per task, all manual direction
- Corrections are lost after the conversation

**The goal:** An AI orchestrator (OpenClaw) that replaces you as the decision-maker, while Claude Code remains the executor.

---

## Concrete Timeline: What You'll See and Do

### Month 1-2: Historical Learning

**What you do:**
```bash
# Run episode builder on past sessions
python scripts/build-episodes.py --project modernizing-tool

# Output shows:
# Processing 299 user-Claude turns from 47 sessions...
# Extracting decision points...
# Found 156 orchestrator decision points
# Extracted 23 constraints from corrections
# Generated 156 episodes
```

**What you get:**
A database (`data/ope.db`) with entries like:

```sql
SELECT * FROM episodes WHERE reaction_label = 'correct' LIMIT 1;

-- Episode #47
-- Observation: User asked "implement XML parser"
-- Orchestrator Action:
--   mode: Implement (inferred from "implement")
--   executor_instruction: "Write XML parser using regex"
-- Outcome:
--   reaction: CORRECT
--   message: "No, don't use regex for XML. Use libxml2."
-- Constraint Extracted:
--   text: "Avoid regex for XML parsing"
--   severity: requires_approval
--   scope: ["parsers/"]
```

**Tangible result:** Searchable database of "what worked" and "what didn't" from your own history.

---

### Month 3: RAG Baseline Orchestrator

**Scenario:** You start a new task: "Add user authentication to the API"

**Before (manual):**
You type to Claude: "Add user authentication. First search for existing auth patterns, then..."

**After (with system):**

```bash
$ orchestrator recommend "Add user authentication to the API"

📊 Retrieved 8 similar episodes from your history:
   - Episode #52: Added auth to modernizing-tool (approved)
   - Episode #119: Implemented JWT tokens (corrected: "use env vars")
   - Episode #134: Added password reset (blocked: "too risky, ask first")

🎯 Recommended orchestrator action:

Mode: Explore → Plan → Implement → Verify

Strategy (from episode #52, which you approved):
  1. Explore: Search codebase for existing auth patterns
     - Look for: authentication, authorization, JWT, session
     - Expected: Find if auth module exists

  2. Plan: Propose 2-3 options (library vs custom)
     - Include tradeoffs (security, maintenance, complexity)
     - Wait for your choice before implementing

  3. Implement: Based on your chosen approach
     - Scope: auth/, api/routes.py, tests/
     - Avoid: infra/, db/migrations/ (unless necessary)

  4. Verify: Run tests + security check
     - Gate: Tests must pass before commit
     - Gate: Manual review for auth code (high risk)

⚠️ Constraints from your corrections in similar work:
  ✓ NO hardcoded secrets (you corrected this in episode #119)
  ✓ Use environment variables for credentials
  ✓ Add token expiration (you requested this in episode #52)
  ✓ Ask before touching db/migrations/ (protected path)

Risk: HIGH (security-critical code)

Execute with these settings? [y/n/edit]
```

**What happens when you type 'y':**

```bash
$ orchestrator execute task-auth-001

[14:23] Mode: Explore
[14:23] Dispatching to Claude Code: "Search codebase for authentication patterns..."
[14:24] Claude: Grepping for 'authentication', 'jwt', 'session'...
[14:25] Claude: Found existing auth/ directory with JWT implementation
[14:25] Episode boundary: X_SUMMARY (executor finished exploration)

[14:25] Mode: Plan (auto-transition based on episode #52 pattern)
[14:26] Dispatching to Claude Code: "Propose 2 approaches for user auth..."
[14:27] Claude: "Option A: Extend existing JWT system..."
[14:27] Episode boundary: X_PROPOSE (executor waiting for decision)

[14:28] ⏸️  GATE: require_human_approval (risk: HIGH)
[14:28] Orchestrator paused for your review

Options proposed by Claude:
  A) Extend existing JWT (faster, less secure if session stolen)
  B) Add refresh tokens (more secure, more complex)

Your choice: [A/B/other]
```

You type `B`, system continues with your chosen approach.

**Tangible result:** The orchestrator made 3 decisions (Explore, Plan, wait for your choice) without you manually typing each step. Constraints were enforced automatically.

---

### Month 4: Preference Model (Learning Your Patterns)

**Scenario:** System completed a task and is waiting for your review

**What you see in Mission Control dashboard:**

```
┌─────────────────────────────────────────────────────────────┐
│ Task #1247: Implement password reset                       │
├─────────────────────────────────────────────────────────────┤
│ Status: REVIEW (awaiting your approval)                    │
│                                                             │
│ 🤖 Preference Model Prediction: APPROVE (confidence: 87%)  │
│    Reasoning: Similar to episode #52 (you approved)        │
│                Constraints satisfied ✓                      │
│                No protected paths touched ✓                 │
│                                                             │
│ 📊 Episode Summary:                                         │
│                                                             │
│ Observation:                                                │
│   - Branch: feature/auth                                    │
│   - Tests: PASS (12/12)                                     │
│   - Lint: PASS                                              │
│   - Files: auth/reset.py, tests/test_reset.py, routes.py   │
│   - Diff: +142 lines, -12 lines                            │
│                                                             │
│ Orchestrator Decision:                                      │
│   - Mode: Implement                                         │
│   - Scope: auth/, tests/, api/routes.py                     │
│   - Constraints applied:                                    │
│     ✓ no-hardcoded-secrets                                  │
│     ✓ use-env-vars                                          │
│     ✓ add-token-expiration                                  │
│   - Gates passed:                                           │
│     ✓ tests (12/12 pass)                                    │
│     ✓ lint (0 issues)                                       │
│     ✓ no-protected-paths                                    │
│                                                             │
│ Outcome Quality:                                            │
│   - Objective scores: tests=1.0, lint=1.0, risk=0.3        │
│   - Similar to approved episode #52 (87% match)             │
│                                                             │
│ Your Reaction: [Approve] [Correct] [Redirect] [Block]      │
│                                                             │
│ If Correct/Block: Extract constraint?                      │
│ Constraint text: ________________________________           │
│ Severity: [warning|requires_approval|forbidden]             │
└─────────────────────────────────────────────────────────────┘
```

**What happens when you click [Approve]:**
- Episode saved with `reaction: approve`
- Preference model learns: "87% confidence was correct"
- Next time similar task appears, confidence increases to ~92%
- Eventually: Low-confidence approvals become automatic

**What happens if you click [Correct]:**

```
You clicked: Correct

What should have been done differently?
> Should have used bcrypt for password hashing, not sha256

Extracting constraint...

New constraint:
  ID: constraint-028
  Text: "Use bcrypt for password hashing, not sha256"
  Severity: [warning|requires_approval|forbidden] ← you choose: forbidden
  Scope: Detected paths: auth/reset.py
        Apply to: [this file only | auth/ | entire repo] ← you choose: auth/

Detection hints (for automatic enforcement):
  - Forbidden: "hashlib.sha256" in auth/ files
  - Required: "bcrypt.hash" or "bcrypt.generate_password_hash"

Save constraint? [y/n]
```

You type `y`. **From this moment forward**, any future code that tries to use `sha256` in `auth/` will trigger:

```
❌ CONSTRAINT VIOLATION: constraint-028
   File: auth/new_feature.py
   Line: 42: hashed = hashlib.sha256(password)

   Forbidden: Use bcrypt for password hashing, not sha256
   Severity: FORBIDDEN

   This action cannot proceed. Revise code to use bcrypt.
```

**Tangible result:** You corrected Claude once. The system now prevents that mistake forever, across all future tasks.

---

### Month 5-6: Mission Control (Real-Time Capture)

**Scenario:** You're starting work for the day

**What you see when you open Mission Control:**

```
┌────────────────────────────────────────────────────────────┐
│ Mission Control - Orchestrator Training Cockpit           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ 📋 Your Tasks                                              │
│                                                            │
│ ┌──────────────────────────────────────────────────────┐  │
│ │ 🟢 ACTIVE                                            │  │
│ │ #1250: Refactor database queries for performance    │  │
│ │ Status: IN PROGRESS (Executor running benchmarks)   │  │
│ │ Mode: Refactor                                       │  │
│ │ Progress: ████████░░ 80%                             │  │
│ │ [View Live Stream] [Pause] [Review]                 │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                            │
│ ┌──────────────────────────────────────────────────────┐  │
│ │ 🔵 PLANNING                                          │  │
│ │ #1251: Add email notification system                │  │
│ │ Status: Awaiting planning output                    │  │
│ │ [Start Planning] [Cancel]                           │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                            │
│ ┌──────────────────────────────────────────────────────┐  │
│ │ 🟡 REVIEW                                            │  │
│ │ #1249: Update dependencies to latest versions       │  │
│ │ Status: Autonomous work completed (LOW risk)        │  │
│ │ Preference Model: APPROVE (94% confidence)          │  │
│ │ [Quick Approve] [Detailed Review] [Reject]          │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                            │
│ [+ New Task]                                               │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**You click [+ New Task]:**

```
┌────────────────────────────────────────────────────────────┐
│ Create New Task                                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Description:                                               │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ Add caching to API endpoints                          │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                            │
│ 🤖 AI Planning Assistant (analyzing...)                    │
│                                                            │
│ Based on your description, I recommend:                    │
│                                                            │
│ Orchestrator Mode: [Explore ▼]                             │
│   (First explore existing caching, then plan approach)    │
│                                                            │
│ Suggested Goal:                                            │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ Implement API response caching to reduce latency     │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                            │
│ Scope:                                                     │
│   Include: api/, cache/, tests/                            │
│   Avoid: db/, auth/ (read-only)                            │
│                                                            │
│ Constraints (from your past work):                         │
│   ☑ No new dependencies without approval                   │
│   ☑ Cache must be invalidated on data changes              │
│   ☑ Add performance benchmarks                             │
│                                                            │
│ Gates:                                                     │
│   ☑ Run tests after implementation                         │
│   ☑ Benchmark shows ≥20% latency improvement               │
│   ☐ Manual approval before merge                           │
│                                                            │
│ Risk: [MEDIUM ▼] (performance-critical but non-breaking)   │
│                                                            │
│ [Edit] [Generate Full Plan] [Execute Directly]            │
└────────────────────────────────────────────────────────────┘
```

**You click [Generate Full Plan]. System shows:**

```
Generated Plan (from similar episode #156, #203)

Phase 1: Explore (Estimated: 15min)
  - Search for existing caching code
  - Identify cache library used (Redis vs in-memory)
  - List all API endpoints
  - Identify hot paths (most-called endpoints)

Phase 2: Plan (Estimated: 20min)
  - Propose caching strategy:
    Option A: Redis (distributed, persistent, more complex)
    Option B: In-memory (simple, fast, lost on restart)
  - Wait for your choice
  - Design cache key format
  - Design invalidation strategy

Phase 3: Implement (Estimated: 1hr)
  - Add caching decorator to chosen endpoints
  - Implement cache invalidation on writes
  - Add tests for cache hits/misses/invalidation
  - Run benchmarks

Phase 4: Verify (Estimated: 15min)
  - Run full test suite
  - Check benchmark results (target: ≥20% improvement)
  - If gates pass → create PR
  - If gates fail → escalate to you

Total estimated time: ~2 hours
Success probability: 78% (based on similar episodes)

[Approve Plan] [Modify] [Cancel]
```

**You click [Approve Plan]. System executes:**

```
┌────────────────────────────────────────────────────────────┐
│ Task #1252: Add caching to API endpoints                  │
│ Status: EXECUTING                                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Current Episode: #1252-03                                 │
│ Mode: Implement                                            │
│ Phase: 3/4                                                 │
│                                                            │
│ 📡 Live Event Stream:                                      │
│                                                            │
│ 14:32 O_DIR: "Implement caching decorator for GET endpoints" │
│ 14:32 X_READ: cache/decorators.py                         │
│ 14:33 X_EDIT: api/endpoints.py (+23 lines)                │
│ 14:34 X_WRITE: tests/test_cache.py (new file)             │
│ 14:35 T_TEST: pytest tests/test_cache.py → PASS ✓         │
│ 14:36 X_ASK: "Cache TTL should be 300s or 600s?"          │
│ 14:36 ⏸️  PAUSED - Waiting for your input                 │
│                                                            │
│ Question from executor:                                    │
│ "Cache TTL should be 300s (5min) or 600s (10min)?"        │
│                                                            │
│ Your response: ___________________________________         │
│                                                            │
│ [Continue] [Pause] [Abort]                                 │
└────────────────────────────────────────────────────────────┘
```

**You type "600s" and click Continue. Later:**

```
✅ Task #1252: Completed

Final Episode Summary:
  - Mode sequence: Explore → Plan → Implement → Verify
  - Total time: 1h 47min (under estimate)
  - Episodes generated: 4
  - Gates passed: ✓ tests (18/18), ✓ benchmark (+31% faster)
  - PR created: #245

Awaiting your reaction: [Approve] [Correct] [Redirect]
```

**Tangible result:** Mission Control structured the work into decision points, enforced gates, captured episodes in real-time. No post-hoc log parsing needed.

---

### Month 7+: Graduated Autonomy

**Scenario:** You're working on a different project. System is running in background.

**Notification appears:**

```
🤖 Autonomous Task Completed

Task #1289: Update dependencies to latest versions
Risk: LOW (routine maintenance)
Mode: Verify → Implement → Verify

What I did:
  ✓ Scanned for outdated dependencies (7 found)
  ✓ Ran npm audit (0 vulnerabilities)
  ✓ Updated package.json
  ✓ Ran tests → PASS (42/42)
  ✓ Ran build → SUCCESS
  ✓ Created PR #251

All gates passed autonomously.
No human approval required (risk: LOW, confidence: 96%)

Review at your convenience: [View PR] [Dismiss]
```

**Tangible result:** System handled a low-risk task end-to-end. You review PR later, approve with one click. Your time: 30 seconds instead of 30 minutes.

---

## The Concrete Difference (Before vs After)

### Before (Current State - Manual Orchestration)

**Your day:**
- 9:00 AM: Start Claude session, manually type: "First, search for auth patterns..."
- 9:15 AM: Claude shows results, you manually type: "Good, now plan two approaches..."
- 9:30 AM: Claude proposes regex approach, you manually type: "No! Don't use regex for XML, use library X"
- 9:35 AM: Claude implements, you manually type: "Run tests before committing"
- 9:45 AM: Tests pass, you manually type: "Commit with message..."
- **30 minutes per task, all manual, lesson (no regex XML) is lost**
- Next week: Same "no regex XML" mistake happens again

### After (Orchestrator System Operational)

**Your day:**
- 9:00 AM: Open Mission Control, click "New Task", type: "Add auth"
- System auto-fills: Mode=Explore→Plan→Implement, Constraints=["no-hardcoded-secrets"], Gates=["run-tests"]
- 9:02 AM: Click "Execute", system runs autonomously
- 9:15 AM: System pauses: "Choose Option A or B?"
- You click "B"
- 9:30 AM: System completes, shows: "PR #245 ready for review"
- You click "Approve" (because preference model predicted correctly)
- **5 minutes of your time, constraints auto-enforced, episode captured for future learning**

**Metrics:**
- **Tasks per day:** 3 → 12 (4x throughput)
- **Time per task:** 30 min → 5 min (6x faster)
- **Mistakes that reach review:** 40% → 5% (8x fewer)
- **Lessons relearned:** Daily → Never (constraint store prevents repeats)

---

## Tangible Artifacts You'll Have

### 1. Episode Database (`data/ope.db`)
- 1000+ episodes from your history
- Searchable by observation (context), action (mode), outcome (approved/corrected)
- Queryable: "Show me all episodes where I corrected Claude about security"
- **Example query:**
  ```sql
  SELECT episode_id, orchestrator_action->>'mode', reaction_label, reaction_message
  FROM episodes
  WHERE observation->>'context' LIKE '%auth%'
    AND reaction_label = 'correct'
  ORDER BY timestamp DESC
  LIMIT 10;
  ```

### 2. Constraint Store (`data/constraints.json`)
- 50+ rules extracted from your corrections
- Auto-enforced in validator
- **Example entries:**
  ```json
  {
    "constraint_id": "constraint-001",
    "text": "No hardcoded secrets in code",
    "severity": "forbidden",
    "scope": { "paths": ["**/*.py", "**/*.js"] },
    "detection_hints": ["API_KEY =", "SECRET =", "PASSWORD ="]
  },
  {
    "constraint_id": "constraint-013",
    "text": "Use bcrypt for password hashing, not sha256",
    "severity": "forbidden",
    "scope": { "paths": ["auth/**"] },
    "detection_hints": ["hashlib.sha256", "hashlib.md5"]
  }
  ```

### 3. Mission Control Dashboard
- Task board with orchestrator modes visible
- Real-time episode capture
- Reaction UI for labeling approvals/corrections
- Preference model predictions
- Live event stream showing O_DIR, X_PROPOSE, T_TEST events

### 4. Preference Model (ML model - `models/preference_model.pkl`)
- Trained on your (observation, action, reaction) history
- Predicts: "Would David approve this decision?"
- Accuracy: 80-90% on held-out episodes
- Used for: Auto-approving low-risk tasks
- **Example prediction:**
  ```python
  model.predict({
    "observation": {
      "repo_state": {"changed_files": ["auth/login.py"]},
      "quality_state": {"tests": "pass", "lint": "pass"}
    },
    "action": {
      "mode": "Implement",
      "scope": ["auth/"],
      "constraints": ["no-hardcoded-secrets", "use-bcrypt"]
    }
  })
  # Output: {"reaction": "approve", "confidence": 0.87}
  ```

### 5. RAG Orchestrator (retrieval system)
- **Input:** "Add caching to API"
- **Output:**
  ```
  Based on 3 similar episodes:
  - Episode #156 (approved, 89% match): Used Redis with TTL=600s
  - Episode #203 (approved, 82% match): Cache at endpoint level
  - Episode #178 (corrected, 75% match): YOU SAID: "Add invalidation on writes"

  Recommended approach:
  - Use Redis (from #156)
  - Cache at endpoint level (from #203)
  - MUST add invalidation on writes (from correction #178)
  ```

---

## Success Metrics (How We Know It's Working)

### Data Quality Metrics
- ✅ Episode extraction accuracy: ≥85% (mode correctly inferred)
- ✅ Reaction label accuracy: ≥80% (approve/correct/block/redirect)
- ✅ Constraint extraction rate: ≥90% of corrections captured
- ✅ Episode density: 10x more episodes than commits

### Orchestrator Quality Metrics
- ✅ Shadow mode agreement: ≥70% with your decisions (baseline RAG)
- ✅ Preference model accuracy: ≥80% on held-out reactions
- ✅ Constraint enforcement: Zero forbidden actions reach execution
- ✅ Objective quality: Tests/lint/build maintained or improved

### Productivity Metrics
- ✅ Your time per task: Reduced by 60-80%
- ✅ Tasks per day: Increased by 3-4x
- ✅ Mistakes in review: Reduced by 80%
- ✅ Repeated lessons: Zero (constraints prevent)

### Autonomy Metrics (Month 7+)
- ✅ Low-risk tasks: 90% autonomous (no human intervention)
- ✅ Medium-risk tasks: 50% autonomous (preference model approval)
- ✅ High-risk tasks: 0% autonomous (always require human approval)
- ✅ Critical failures: Zero (harness catches all forbidden actions)

---

## OPE's Position in the Larger Ecosystem

OPE is not a standalone governance tool. It is the intelligence substrate of the Governing
Orchestrator — the Layer 7 supervisory component of a 9-project ecosystem governed by the
Reflexive Knowledge System (RKS) protocol.

**OPE's layer position:** Layer 7 (Meta/Supervisory) — the component that holds the GO's
intelligence: episodes, constraints, causal chains, and the CCDs that make the GO's decisions
improvable rather than repeatable.

**The ecosystem OPE governs:**

| # | Project | Role |
|---|---------|------|
| 1 | `orchestrator-policy-extraction` | GO intelligence substrate — this project |
| 2 | `reflexive-knowledge-system` | Universal knowledge substrate architecture |
| 3 | `eva` | Shared execution agent |
| 4 | `mark` | Shared code interaction agent |
| 5 | `canon` | Shared semantic retrieval layer |
| 6 | `knowledge-infrastructure` (MT) | Migration platform graph + parsers |
| 7 | `vb-canon` (MT) | Migration domain concept library |
| 8 | `modernization-governance` (MT) | Migration governance engine |
| 9 | `objectivism-library` | Standalone knowledge library |

The GO queries all 9 projects without project-specific code — using the four RKS protocol
operations (Conformance Probe, Epistemic Status Query, Knowledge Retrieval, Evidence Write).

**The long-term picture:** Every project the GO supervises is governed by the same query logic
because every project exposes the same four protocol operations. Adding a 10th project to the
ecosystem requires implementing the protocol in that project's repo — not modifying the GO.
The GO's query logic does not grow with the number of projects. This is what makes autonomous
governance possible at scale.

**v2.0 sequencing:** OPE's protocol compliance (exposing the four operations over its existing
DuckDB + JSONL infrastructure) is a prerequisite for the graduated autonomy described in the
sections below. The GO cannot autonomously decide whether to intervene in OPE without first
being able to query OPE's epistemic status via the protocol.

Full RKS architecture: `/Users/david/projects/reflexive-knowledge-system/design/`

---

## The North Star

**Ultimate success:** You spend 80% of your time on strategic decisions (architecture, requirements, tradeoffs) and 20% on tactical review. The orchestrator handles:
- Mode selection (Explore vs Implement vs Verify)
- Scope definition (which files, what to avoid)
- Constraint enforcement (no hardcoded secrets, use bcrypt)
- Gate checking (run tests, get approval)
- Risk assessment (low/medium/high/critical)

**You become the orchestrator of the orchestrator.** The system scales your judgment, not your typing.

---

**This is what we're building.**
