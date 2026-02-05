## Formal problem statement: Orchestrator Policy Learning from Human–AI Software Modernization Traces

### 0) Observable setup (what exists in the world)

You have a modernization project repository **R** whose evolution is recorded in:

1. **Git artifact stream**

* A sequence of commits (C={c_1,\dots,c_N}) with timestamps, authorship metadata, commit messages, and diffs/patches ( \Delta(c_i)).

2. **Human–AI interaction stream**

* A sequence of Claude Code sessions stored as JSONL logs with per-message timestamps and tool executions (shell commands, file edits, etc.). 

3. **A human orchestrator (expert)**

* The orchestrator’s behavior is manifested by: prompts/decisions, acceptance/rejection of changes, selecting next tasks, deciding when to commit, branching/merging, and enforcing quality gates.

Your goal is to (a) analyze and (b) eventually automate the orchestration role via an agent (e.g., OpenClaw controlling Claude Code), while preserving quality/safety.

---

## 1) Core problem family and scope

This belongs to: **sequential decision-making in tool-mediated human–AI software engineering**, with two coupled subproblems:

1. **Trace correlation (descriptive):** align interaction events ↔ code changes.
2. **Orchestrator policy learning (prescriptive):** learn a decision policy that reproduces (or improves on) the orchestrator’s next-step choices.

---

## 2) Formal definitions

### 2.1 Data model

Let the project timeline be discretized into events.

**Interaction event log**
Let (L = {e_1,\dots,e_T}) where each event (e_t) has fields like:

* (t(e_t)): timestamp
* (type(e_t)\in{\text{user},\text{assistant},\text{tool_call},\text{tool_result}})
* (content(e_t)): message text or tool payload (e.g., command string, files touched) 

**Git event log**
Let (G = {g_1,\dots,g_N}) where each (g_i) is a commit with:

* (t(g_i)): commit timestamp
* (\Delta(g_i)): diff/patch, files changed, size
* (meta(g_i)): author, message, trailers, branch refs

**Repository state**
Let (S) denote the (very large) set of possible repo states.
Let (s(t)\in S) be the repo state at time (t) (conceptually the full tree + config + tests + issues).

---

## 3) Subproblem A: Trace correlation (who caused what, when)

### 3.1 Task statement

**Given** interaction log (L) and git log (G), **infer** a mapping:
[
M: G \rightarrow 2^{L}
]
that assigns to each commit (g_i) the subset of interaction events (M(g_i)\subseteq L) that causally contributed to it (or are most plausibly associated with it).

### 3.2 Output

For each commit (g_i):

* linked session(s) / window(s) of conversation events
* linked tool calls (build/test/git commands) that occurred before the commit
* confidence score (p(M(g_i)\mid L,G))

### 3.3 Objective (correlation quality)

Maximize alignment quality under constraints:

* **Temporal consistency:** events should precede the commit they explain
* **Command evidence:** git-related tool calls (e.g., status/add/commit) increase linkage probability 
* **File overlap:** files referenced/edited in tool calls should overlap files in (\Delta(g_i))

You can formalize this as maximizing:
[
\sum_i \log p(M(g_i)\mid L,G)
]
with a model that uses time windows + evidence features.

### 3.4 Why this matters

This step converts “chat + git history” into a **training dataset of labeled episodes** for policy learning.

---

## 4) Subproblem B: Orchestrator policy learning (learn to drive the workflow)

### 4.1 The decision problem

Model the modernization workflow as a **POMDP** (partially observable Markov decision process) because the “true” state of the repo/project is too large to observe directly; you only observe summaries, logs, diffs, test results, and conversation context.

Define:

* **Hidden state** (s_t \in S): full project situation at step (t)

* **Observation** (o_t \in O): what the orchestrator/agent “sees,” e.g.

  * current branch + diff summary
  * failing tests + logs
  * key files/modules touched recently
  * current migration phase label (if you have one)
  * last (k) interaction turns
  * constraints/policies (do-not-touch paths, safety rules)

* **Action space** (a_t \in A): orchestrator moves, e.g.

  1. instruct Claude Code to perform a specific task (an instruction template)
  2. request repo inspection / run a command
  3. apply/accept a patch
  4. create a commit with message + scope
  5. open/close a loop (triage, refactor, test-fix)
  6. escalate to human review / ask for clarification

* **Transition** (P(s_{t+1}\mid s_t,a_t)): induced by edits/tests/commits/tool calls

* **Termination**: task completion criteria met (e.g., phase deliverable satisfied; tests pass; migration milestone reached)

### 4.2 Policy to learn

You want an orchestration policy:
[
\pi(a_t\mid o_t)
]
that outputs the next orchestrator action given the observed context.

Two variants (choose explicitly):

**(i) Imitation objective (match the expert):**
[
\min_{\theta}; \mathbb{E}*{(o_t,a_t)\sim D}\left[ \ell(\pi*{\theta}(o_t), a_t) \right]
]
where (D) is your dataset of observed orchestrator decisions derived from (L) and correlated with (G). 

**(ii) Utility objective (optimize outcomes):**
Define a reward (r_t) and maximize expected return:
[
\max_{\pi}; \mathbb{E}\left[\sum_{t=1}^{T}\gamma^{t} r_t\right]
]
where reward proxies can include:

* tests passing
* fewer regressions
* smaller rework cycles
* higher review acceptance rate
* progress toward migration milestones

In practice, you often start with (i) and then move toward (ii) once your agent is safe and measurable.

---

## 5) Dataset construction (what training examples look like)

After trace correlation, define episodes (“cases”) (E_j), each with a sequence:
[
E_j = {(o_1,a_1,y_1),\dots,(o_T,a_T,y_T)}
]

Where:

* (o_t): observation snapshot (repo summaries + conversation context)
* (a_t): orchestrator action extracted from human prompt / gate decision
* (y_t): outcome labels (commit produced? tests passed? defect introduced? cycle length?)

**Key requirement:** the dataset must be **chronologically split** (train on early periods, test on later) to avoid leakage from repeated tasks and evolving conventions.

---

## 6) Constraints and safety specification (non-negotiables for an acting agent)

Because the orchestrator agent will execute tool calls, your problem is constrained optimization:

### 6.1 Hard constraints (C_{hard})

* No destructive commands outside a sandbox/worktree
* No secret exfiltration (no reading env secrets by default)
* No pushing to protected branches without review
* No large refactors without a quality gate (tests + lint + review)

### 6.2 Soft constraints (C_{soft})

* Prefer smaller diffs
* Prefer reversible steps
* Prefer added tests before risky changes

The deployed policy is therefore:
[
\pi^{*} = \arg\max_{\pi \in \Pi(C_{hard})}; \mathbb{E}[\text{utility}(\pi)] \quad \text{s.t. } C_{soft} \text{ minimized}
]

---

## 7) Evaluation (how you know you solved it)

### 7.1 Correlation evaluation (Subproblem A)

* Precision/recall of commit↔session links (on a hand-labeled subset)
* Time-alignment error distribution
* File-overlap score between tool-edited files and commit diffs

### 7.2 Orchestrator policy evaluation (Subproblem B)

Offline:

* Next-action accuracy (top-1 / top-k)
* Calibration (does confidence match correctness?)
* “Intervention prediction”: does it correctly predict when to escalate to human?

Online (in a sandbox repo or feature branches):

* Task success rate (milestones completed)
* Regression rate (tests fail later / bug reports)
* Human intervention rate (how often you must take over)
* Cycle time (time/steps to complete a phase)
* Diff risk profile (large diffs frequency, hot file churn)

---

## 8) Deliverables (what a complete solution produces)

1. **Correlation pipeline** that outputs a joined timeline ( (L \leftrightarrow G) ) with confidence scores 
2. **Orchestrator action taxonomy** (a controlled vocabulary of “what the orchestrator does”)
3. **Episode dataset** (D) suitable for supervised learning / retrieval
4. **Baseline orchestrator** (rules + retrieval)
5. **Learned orchestrator policy** (imitation or utility-optimized)
6. **Governed execution harness** (sandbox + allowlists + audit logs + PR gates)

---

### One-sentence formal statement (for papers / proposals)

> **Given** a repository’s git history and an AI coding assistant’s session/tool logs, **infer** a commit-aligned interaction trace and **learn** a constrained sequential policy that reproduces (or improves) the human orchestrator’s decisions to drive safe, measurable software modernization. 
