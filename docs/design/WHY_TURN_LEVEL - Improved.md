Below is a tightened **v2** rewrite of your document, adjusted specifically for the end goal: **replacing you (the human orchestrator) with a trained OpenClaw orchestrator**. It keeps your core argument and examples, but fixes the biggest gaps: **(1) turn ≠ decision point**, **(2) orchestrator ≠ executor**, and **(3) “user reaction” must be replaced by a preference/utility signal once you’re gone**. 

---

# Why Decision-Point Episodes Beat Commit-Level Correlation for Training an OpenClaw Orchestrator

This document explains why **decision-point episodes** (observation → orchestrator action → outcome) are essential if the final goal is to **train OpenClaw to replace the human orchestrator**, and why **commit/session correlation alone** is insufficient for that goal. 

---

## 1) Definitions: keep the levels clean

### Roles (two different policies)

**Orchestrator (target policy = OpenClaw):** decides *what to do next* and *how to delegate*.

* Chooses mode: Explore / Plan / Implement / Verify / Integrate
* Chooses scope: which modules/files, what not to touch
* Chooses constraints: “no new deps,” “no secrets,” “avoid regex XML,” etc.
* Chooses gates: run tests now, require approval, stop/escalate
* Chooses delegation: what instruction to give the executor

**Executor (tool-using agent = Claude Code):** carries out the orchestrator’s directive via reads/greps/edits/tests, producing diffs and outputs.

If you blur these roles, you will accidentally train OpenClaw to “act like Claude” (tool micro-steps) instead of “act like you” (sequencing + risk + scope + gates).

---

## 2) The core claim (in the right unit)

### The unit is not “turns.” The unit is **decision points**.

A **decision point** is a checkpoint where the orchestrator can rationally choose among alternatives, typically after:

* new evidence arrives (tool output, test results, file inspection)
* a plan/proposal appears
* a risk boundary is approached (destructive command, large refactor)
* user feedback arrives (approval/correction/redirect)

A single chat “turn” may contain **multiple decision points** or **none**. Commits are even coarser: they’re deliverables, not decisions.

---

## 3) What commit-only correlation gives you (and why it’s the wrong training signal)

### Commit/session correlation yields:

```
Session ABC (Jan 30, 2–4pm) → Commit def456 (Jan 30, 4:15pm)
  "feat(03.1-01): Implement XML parser"
```

You learn:

* ✅ A deliverable exists
* ✅ Which files changed
* ✅ A rough time window

But you do **not** learn the orchestrator policy, because the commit hides:

* ❌ sequencing decisions (inspect first vs implement first)
* ❌ mistakes and recoveries (what got tried and rejected)
* ❌ constraints invoked (“don’t use regex,” “no hardcoded secret”)
* ❌ gates applied (when tests were required, when review was required)
* ❌ why the orchestrator chose *this* plan over alternatives

**Commits are outputs of orchestration, not the orchestration itself.**

Commit-only correlation is useful—but for validation and milestone tracking, not for learning “what to do next.”

---

## 4) What decision-point episodes capture (and why they’re learnable)

### Decision-point episode schema (conceptual)

At each decision point (t):

**Observation (O_t)**
What the orchestrator knows now (repo signals + phase + context).

**Orchestrator Action (A_t)**
The directive: mode, scope, constraints, executor instruction, gates, risk.

**Outcome (Y_t)**
What happened: diffs, tests, failures, time/cost, and—when available—human reaction.

This is the minimum structure required to train an orchestrator.

---

## 5) Same commit, two different orchestration episodes

**Same commit (indistinguishable under commit-only):**

```
feat(03.1-01): Implement XML parser
+ src/parser.cpp
+ tests/test_parser.cpp
```

### Episode A: Orchestrator chooses “direct implement” and it works

**Observation:**

* phase = 03.1-01
* parser.h exists
* no tests yet
* requirements appear clear

**Orchestrator action:**

* mode: Implement
* scope: src/parser.* + tests/
* constraints: follow existing parser conventions
* executor instruction: “Implement minimal XML parser aligned with existing patterns, then add tests.”
* gates: run tests after patch
* risk: medium (new feature)

**Outcome:**

* tests pass after added tests
* no user correction required
* episode labeled “approve”

**Policy learned (orchestrator-level):**
When requirements are clear and prior art exists → implement directly, then verify.

---

### Episode B: Orchestrator chooses wrong constraint boundary, gets corrected, recovers

**Observation:** same

**Orchestrator action (initial):**

* mode: Implement
* executor instruction implicitly allows “quick regex approach” (missing constraint)

**Outcome:**

* user corrects: “No regex for XML; use proper parser library like libxml2.”

**Orchestrator action (recovery):**

* mode: Explore → Plan → Implement
* constraints updated: “avoid regex XML”
* executor instruction: “Scan codebase for existing XML/library patterns; propose 2 options; pick safest; then implement.”

**Outcome:**

* better implementation
* tests added
* episode includes a **constraint extraction event**: “avoid regex XML”

**What commit-only loses:** the key learning is not the final diff. It’s the **boundary** (“regex is forbidden here”) and the **recovery pattern** (when corrected, switch to Explore/Plan before retry).

---

## 6) Reactions are valuable—but you must plan for “no human”

### While the human orchestrator exists:

User reactions are a powerful supervised signal:

* approve → reinforce
* correct → learn alternative + extract constraint
* redirect → scope/priorities changed
* block → mark as dangerous; add guardrail
* question → ambiguity; clarify before acting

### But once OpenClaw replaces the human:

That reaction signal becomes sparse or absent. So you must convert reactions into two reusable signals:

#### (A) Objective utility proxies (always available)

* tests/CI status
* lint/static analysis
* diff size / churn
* forbidden paths touched or not
* build time / flake rate
* milestone progress

#### (B) A learned preference model (“simulated you”)

Train a preference predictor from historical episodes:

* Input: observation + proposed orchestrator action
* Output: probability you would approve/correct/block

This becomes the substitute feedback channel when you are not in the loop.

**Bottom line:** reaction labels are not the final reward; they are training data for a preference/approval model plus guardrails.

---

## 7) The critical missing artifact: constraints must become first-class

Your traces contain “orchestrator principles” disguised as corrections:

* “Don’t hardcode secrets”
* “Use error codes, not exceptions”
* “Avoid deleting tests”
* “Prefer library-based parsing over regex hacks”

If you don’t extract these into a durable constraint store, the agent will keep relearning them the hard way.

### Constraint extraction output (minimum)

Each “correct/block” should produce:

* constraint text
* scope (repo/global/module)
* severity (warning / requires approval / forbidden)
* detection hook (paths, commands, diff patterns, lint rule, etc.)
* example episodes (where it was learned)

This is how you turn human judgment into machine-enforceable policy.

---

## 8) Executor detail is still valuable—but it’s a different layer

Tool-call sequences (Read/Grep/Edit/Bash/Write) are important for:

* diagnosing how the executor succeeded/failed
* improving reliability of execution
* learning “how to implement,” “how to debug,” etc.

But those sequences should be stored as **Executor Episodes**, subordinate to **Orchestrator Episodes**.

### Three-layer model (recommended)

1. **Orchestrator episodes:** decisions (OpenClaw must learn this)
2. **Executor episodes:** tool-step traces (Claude reliability/optimization)
3. **Deliverable episodes:** commits/PRs (validation + milestones)

---

## 9) Why decision-point density matters (and what it enables)

Commit-only datasets are sparse and “mostly positive” (commits exist because something worked).
Decision-point episodes are dense and contain negative examples:

* corrections
* blocks
* abandoned paths
* detours
* recoveries

Negative examples are essential to learn:

* what not to do
* what is dangerous
* when to ask for clarification
* when to switch modes (Explore vs Implement)

---

## 10) What this enables for OpenClaw training and rollout

### A) Baseline orchestrator (safe start)

Rules + retrieval:

* retrieve similar orchestrator episodes by context
* propose next orchestrator action
* run in **shadow mode** first (no execution)

### B) Learned orchestrator policy

Train (\pi(A \mid O)) to choose:

* mode/scope/constraints/gates
* executor instruction shape
* escalation vs proceed

### C) Governing execution harness (non-negotiable)

The orchestrator policy proposes actions.
The harness decides what is allowed:

* sandbox
* allowlists
* approvals
* branch/PR gates
* constraint enforcement

**Policy chooses. Harness enforces. Logs explain.**

---

## 11) Relationship to commit correlation (keep it—just use it correctly)

Commit correlation is still valuable for:

* temporal alignment
* validation: did the episodes produce real deliverables?
* milestone tracking
* measuring downstream quality

But it is not where “what to do next” lives.

### Full pipeline

```
Sessions → Extract decision points → Orchestrator episodes (train policy)
                 ↓
        Extract executor traces → Executor episodes (improve execution)
                 ↓
        Correlate to commits/PRs → Validate outcomes + milestones
```

---

## 12) Bottom line

**Commit-level correlation answers:**
“What was delivered?”

**Decision-point episodes answer:**
“What should the orchestrator do next, under these constraints, with this risk, in this phase—and how do we know it was a good decision?”

If the final goal is “replace me (the human) with OpenClaw,” the learning target is the **orchestrator decision policy**. Decision-point episodes are not just better than commit-only correlation—they are the minimum structure that makes the orchestrator learnable.

---

Perfect — here’s **v2.1** in two parts:

1. a **strict JSON Schema** for “decision-point orchestrator episodes” (the data object you’ll train OpenClaw on), and
2. a **decision-point detection rubric** (how to cut raw Claude Code JSONL + tool logs into those episodes reliably).

This is directly aligned with your intent in the attached doc: dense, learnable episodes vs commit-only correlation. 

---

## 1) Strict JSON Schema: Orchestrator Decision-Point Episode

Design goals:

* The **Action** is an *orchestrator directive* (what OpenClaw must learn), not an executor tool call.
* The schema is **strict** (good for training + evaluation + governance).
* It supports both:

  * “human-present” episodes (explicit reaction labels), and
  * “human-absent” episodes (reaction becomes predicted, but objective outcomes remain).
* It preserves provenance (which JSONL lines / tool calls / commits support the episode), so you can audit and debug.

### JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/schemas/orchestrator_episode.schema.json",
  "title": "OrchestratorDecisionPointEpisode",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "episode_id",
    "timestamp",
    "project",
    "observation",
    "orchestrator_action",
    "outcome",
    "provenance"
  ],
  "properties": {
    "episode_id": {
      "type": "string",
      "description": "UUID for the episode."
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "Timestamp of the decision point (when orchestrator_action was taken)."
    },

    "project": {
      "$ref": "#/$defs/ProjectRef"
    },

    "phase": {
      "type": "string",
      "description": "Modernization phase label if you have one (e.g., 03.1-01)."
    },
    "task_id": {
      "type": "string",
      "description": "Stable task/work-item identifier (ticket id, issue id, or internal label)."
    },

    "observation": {
      "$ref": "#/$defs/Observation"
    },

    "orchestrator_action": {
      "$ref": "#/$defs/OrchestratorAction"
    },

    "outcome": {
      "$ref": "#/$defs/Outcome"
    },

    "constraints_extracted": {
      "type": "array",
      "items": { "$ref": "#/$defs/Constraint" },
      "description": "Constraints derived from corrections/blocks; becomes a durable rule set."
    },

    "labels": {
      "$ref": "#/$defs/EpisodeLabels"
    },

    "provenance": {
      "$ref": "#/$defs/Provenance"
    },

    "x_extensions": {
      "type": "object",
      "additionalProperties": true,
      "description": "Escape hatch for extra fields; keep core schema strict."
    }
  },

  "$defs": {
    "ProjectRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["repo_path"],
      "properties": {
        "repo_path": {
          "type": "string",
          "description": "Canonical local path or repo id."
        },
        "repo_remote": {
          "type": "string",
          "description": "Optional remote URL / identifier."
        },
        "branch": {
          "type": "string",
          "description": "Branch at the time of the decision point."
        },
        "commit_head": {
          "type": "string",
          "description": "HEAD commit hash at decision time (if known)."
        }
      }
    },

    "Observation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["repo_state", "quality_state", "context"],
      "properties": {
        "repo_state": { "$ref": "#/$defs/RepoState" },
        "quality_state": { "$ref": "#/$defs/QualityState" },
        "context": { "$ref": "#/$defs/ContextState" }
      }
    },

    "RepoState": {
      "type": "object",
      "additionalProperties": false,
      "required": ["changed_files", "diff_stat"],
      "properties": {
        "changed_files": {
          "type": "array",
          "items": { "type": "string" }
        },
        "diff_stat": {
          "$ref": "#/$defs/DiffStat"
        },
        "hotspots": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Files/modules frequently touched in the last N episodes (optional)."
        }
      }
    },

    "DiffStat": {
      "type": "object",
      "additionalProperties": false,
      "required": ["files", "insertions", "deletions"],
      "properties": {
        "files": { "type": "integer", "minimum": 0 },
        "insertions": { "type": "integer", "minimum": 0 },
        "deletions": { "type": "integer", "minimum": 0 }
      }
    },

    "QualityState": {
      "type": "object",
      "additionalProperties": false,
      "required": ["tests", "lint"],
      "properties": {
        "tests": { "$ref": "#/$defs/TestState" },
        "lint": { "$ref": "#/$defs/LintState" },
        "build": { "$ref": "#/$defs/BuildState" }
      }
    },

    "TestState": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status"],
      "properties": {
        "status": {
          "type": "string",
          "enum": ["unknown", "pass", "fail", "not_run"]
        },
        "last_command": { "type": "string" },
        "failing": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },

    "LintState": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status"],
      "properties": {
        "status": {
          "type": "string",
          "enum": ["unknown", "pass", "fail", "not_run"]
        },
        "last_command": { "type": "string" },
        "issues_count": { "type": "integer", "minimum": 0 }
      }
    },

    "BuildState": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status"],
      "properties": {
        "status": {
          "type": "string",
          "enum": ["unknown", "pass", "fail", "not_run"]
        },
        "last_command": { "type": "string" }
      }
    },

    "ContextState": {
      "type": "object",
      "additionalProperties": false,
      "required": ["recent_summary", "open_questions", "constraints_in_force"],
      "properties": {
        "recent_summary": {
          "type": "string",
          "description": "Compact summary of what just happened (from logs/tool outputs)."
        },
        "open_questions": {
          "type": "array",
          "items": { "type": "string" }
        },
        "constraints_in_force": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Active rule names/ids currently governing work."
        }
      }
    },

    "OrchestratorAction": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "mode",
        "goal",
        "scope",
        "executor_instruction",
        "gates",
        "risk"
      ],
      "properties": {
        "mode": {
          "type": "string",
          "enum": ["Explore", "Plan", "Implement", "Verify", "Integrate", "Triage", "Refactor"]
        },
        "goal": { "type": "string" },

        "scope": { "$ref": "#/$defs/Scope" },

        "executor_instruction": {
          "type": "string",
          "description": "What the orchestrator tells the executor (Claude Code) to do next."
        },

        "gates": {
          "type": "array",
          "items": { "$ref": "#/$defs/Gate" },
          "description": "Checks/requirements before proceeding (tests, approvals, diff caps)."
        },

        "risk": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"]
        },

        "expected_artifacts": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Optional: what outputs are expected (docs, patch, PR, test report)."
        }
      }
    },

    "Scope": {
      "type": "object",
      "additionalProperties": false,
      "required": ["paths"],
      "properties": {
        "paths": {
          "type": "array",
          "items": { "type": "string" }
        },
        "avoid": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },

    "Gate": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type"],
      "properties": {
        "type": {
          "type": "string",
          "enum": [
            "require_human_approval",
            "run_tests",
            "run_lint",
            "diff_size_cap",
            "no_write_before_plan",
            "protected_paths",
            "no_network",
            "no_secrets_access"
          ]
        },
        "params": {
          "type": "object",
          "additionalProperties": true
        }
      }
    },

    "Outcome": {
      "type": "object",
      "additionalProperties": false,
      "required": ["executor_effects", "quality", "reward_signals"],
      "properties": {
        "executor_effects": { "$ref": "#/$defs/ExecutorEffects" },
        "quality": { "$ref": "#/$defs/OutcomeQuality" },

        "reaction": {
          "$ref": "#/$defs/Reaction",
          "description": "Optional; present when a human reaction is known/labelled."
        },

        "reward_signals": {
          "$ref": "#/$defs/RewardSignals",
          "description": "Always include objective proxies; reaction-based signals may be absent."
        }
      }
    },

    "ExecutorEffects": {
      "type": "object",
      "additionalProperties": false,
      "required": ["tool_calls_count", "files_touched", "commands_ran"],
      "properties": {
        "tool_calls_count": { "type": "integer", "minimum": 0 },
        "files_touched": {
          "type": "array",
          "items": { "type": "string" }
        },
        "commands_ran": {
          "type": "array",
          "items": { "type": "string" }
        },
        "git_events": {
          "type": "array",
          "items": { "$ref": "#/$defs/GitEvent" }
        }
      }
    },

    "GitEvent": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["status", "diff", "add", "commit", "merge", "rebase", "push", "checkout", "branch"]
        },
        "ref": { "type": "string" },
        "message": { "type": "string" }
      }
    },

    "OutcomeQuality": {
      "type": "object",
      "additionalProperties": false,
      "required": ["tests_status", "lint_status", "diff_stat"],
      "properties": {
        "tests_status": { "type": "string", "enum": ["unknown", "pass", "fail", "not_run"] },
        "lint_status": { "type": "string", "enum": ["unknown", "pass", "fail", "not_run"] },
        "build_status": { "type": "string", "enum": ["unknown", "pass", "fail", "not_run"] },
        "diff_stat": { "$ref": "#/$defs/DiffStat" }
      }
    },

    "Reaction": {
      "type": "object",
      "additionalProperties": false,
      "required": ["label", "message", "confidence"],
      "properties": {
        "label": {
          "type": "string",
          "enum": ["approve", "correct", "redirect", "block", "question", "unknown"]
        },
        "message": { "type": "string" },
        "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
      }
    },

    "RewardSignals": {
      "type": "object",
      "additionalProperties": false,
      "required": ["objective"],
      "properties": {
        "objective": {
          "type": "object",
          "additionalProperties": false,
          "required": ["tests", "lint", "diff_risk"],
          "properties": {
            "tests": { "type": "number", "description": "Scaled score; e.g. pass=1, fail=0." },
            "lint": { "type": "number" },
            "diff_risk": {
              "type": "number",
              "description": "Scaled risk proxy from diff size + protected paths touched."
            }
          }
        },
        "preference_model": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "predicted_reaction": { "type": "string", "enum": ["approve", "correct", "redirect", "block", "question", "unknown"] },
            "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
          }
        }
      }
    },

    "Constraint": {
      "type": "object",
      "additionalProperties": false,
      "required": ["constraint_id", "text", "severity", "scope"],
      "properties": {
        "constraint_id": { "type": "string" },
        "text": { "type": "string" },
        "severity": { "type": "string", "enum": ["warning", "requires_approval", "forbidden"] },
        "scope": {
          "type": "object",
          "additionalProperties": false,
          "required": ["paths"],
          "properties": {
            "paths": { "type": "array", "items": { "type": "string" } }
          }
        },
        "detection_hints": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Patterns that help detect violations (commands, file globs, strings)."
        }
      }
    },

    "EpisodeLabels": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "episode_type": {
          "type": "string",
          "enum": ["decision_point", "checkpoint", "handoff", "recovery", "milestone"]
        },
        "notes": { "type": "string" }
      }
    },

    "Provenance": {
      "type": "object",
      "additionalProperties": false,
      "required": ["sources"],
      "properties": {
        "sources": {
          "type": "array",
          "minItems": 1,
          "items": { "$ref": "#/$defs/SourceRef" }
        }
      }
    },

    "SourceRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type", "ref"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["claude_jsonl", "terminal_log", "git", "ci"]
        },
        "ref": {
          "type": "string",
          "description": "Pointer to source material: file path + line range, message ids, or commit hashes."
        }
      }
    }
  }
}
```

### Why this schema is “orchestrator-correct”

Your attached doc frames the learning problem as “Observation → Action → Reaction,” which is exactly right for policy learning. 
The critical upgrade here is that **Action** is not a tool call; it is the orchestrator directive OpenClaw must produce.

---

## 2) Decision-point detection rubric

Here’s the practical question the rubric answers:

> Given raw Claude Code JSONL logs + tool calls + git events, where do we cut the timeline into episodes such that each episode corresponds to a *real choice point* the orchestrator would have faced?

Your document argues “turn-level beats commit-level because it exposes mistakes, alternatives, and user reactions.” 
The refinement is: **decision points are more fundamental than turns**.

### 2.1 Normalize raw logs into a single event stream

Transform each JSONL record and tool result into a unified event structure:

* `event_id`
* `ts`
* `actor ∈ {orchestrator, executor, tool}`
* `event_type ∈ {user_msg, assistant_msg, tool_call, tool_result, git_event}`
* `payload` (text/command/file/path/result metadata)

**Goal:** one ordered stream `E = [e1, e2, …, en]`.

### 2.2 Classify events into “decision-relevant categories”

For each event, compute tags (one event can have multiple tags):

#### Orchestrator-side tags

* **O_DIR**: a directive (“do X”, “now implement Y”, “investigate Z”)
* **O_GATE**: approval / stop / proceed / “commit this”
* **O_CORR**: explicit correction (“no, do it this way”; “avoid regex”; “don’t hardcode”)
* **O_REDIRECT**: change of scope/priority (“instead do …”)
* **O_QUESTION**: orchestrator asks clarifying question (reveals ambiguity boundary)

#### Executor-side tags

* **X_PROPOSE**: assistant proposes plan/options/tradeoffs
* **X_ASK**: assistant asks a question / requests approval
* **X_PATCH**: assistant provides a diff/patch or indicates file writes
* **X_SUMMARY**: assistant synthesizes findings (often ends Explore mode)

#### Tool-side tags

* **T_TEST**: test command ran (pytest/go test/mvn test/npm test/etc.)
* **T_LINT**: lint command ran
* **T_BUILD**: build command ran
* **T_RISKY**: destructive/high-risk command detected (rm -rf, sudo, curl|bash, etc.)
* **T_GIT_COMMIT**: git commit event detected
* **T_GIT_PUSH**: push detected (high risk)
* **T_NET**: network access (if applicable and governed)

### 2.3 Define “decision-point triggers” (episode boundaries)

A **decision point** is created when *new evidence* or *a proposal* exists such that the next orchestrator action is nontrivial.

Create an episode boundary on any of these triggers:

#### Trigger A — Orchestrator directive arrives (**start of an episode**)

* Event with tag **O_DIR** or **O_GATE** starts a new episode.
* That event becomes `orchestrator_action`.

#### Trigger B — Executor proposal requires choice (**end current episode, start a new decision point**)

If assistant outputs:

* multiple options
* a plan requiring confirmation
* a question (“Should I …?”)
* a warning about risk

Then cut an episode at that point because the orchestrator must choose.

Detected by tags: **X_PROPOSE** or **X_ASK**.

#### Trigger C — Tool result changes the state of reality (tests/lint/build)

When a test/build finishes, the next move often changes:

* tests fail → triage vs rollback vs investigate
* tests pass → integrate/commit vs expand coverage vs refactor

So: after **T_TEST**, **T_LINT**, **T_BUILD** results, insert a decision point boundary.

#### Trigger D — Risk boundary encountered

If **T_RISKY** or **T_GIT_PUSH** appears, force a decision point (even if the assistant didn’t ask), because the governance harness will require approval anyway.

#### Trigger E — Commit created

A commit is a milestone. Even if it’s “executor-level,” it’s a strong boundary for orchestrator behavior and episode closure: after **T_GIT_COMMIT**, close the episode and start the next decision point.

> This preserves your doc’s argument that commits are useful validation artifacts, but not sufficient training signals. 

### 2.4 Episode construction algorithm

**Initialize:** `episodes = []`, `current = None`

Walk event stream in time order:

1. If event triggers **start-of-episode** (O_DIR/O_GATE):

   * if `current` exists, close it
   * open new `current`
   * set `current.timestamp = event.ts`
   * parse `orchestrator_action` from the orchestrator message:

     * mode (Explore/Plan/Implement/Verify/Integrate/Triage/Refactor)
     * scope (paths mentioned; infer from referenced files)
     * gates (explicit or implied from prior constraints/risk)
     * risk (based on action + environment + tool risk)

2. Append all subsequent events into `current.provenance.sources`.

3. If event triggers **decision boundary** (proposal/ask, test result, risky op, commit):

   * populate `current.outcome.executor_effects` and `current.outcome.quality`
   * close `current` (this is an “episode ending at a choice point”)
   * set `current = None` until next orchestrator directive

This produces episodes centered on **orchestrator decisions**, not on arbitrary turns.

### 2.5 Reaction label extraction (approve/correct/redirect/block/question)

Your document’s reaction taxonomy is the right starting set. 
Operationally, detect reaction from the **next orchestrator message** after an executor output / tool milestone.

Heuristics (use confidence scores):

* **block** (confidence high):

  * “NO”, “stop”, “don’t do that”, “never”, “absolutely not”
  * especially if referencing destructive actions (rm -rf / push to main)

* **correct**:

  * “no, do X instead”
  * “don’t use …, use …”
  * “change it to …”
  * “that’s wrong because …”

* **redirect**:

  * “instead, focus on …”
  * “ignore that; do …”
  * “different direction: …”
  * (often without explicitly saying the previous step was wrong)

* **approve**:

  * “yes”, “looks good”, “go ahead”, “ship it”, “commit”, “continue”
  * or implicit approval: next message assigns the *next step* without complaint

* **question**:

  * “why?”, “what about …?”, “how does …?”, “can you clarify …?”

Store `reaction.label`, `reaction.message`, `reaction.confidence`.

### 2.6 Constraint extraction rubric (turn judgment into durable policy)

Whenever reaction is **correct** or **block**, attempt to extract a constraint:

Pattern:

* prohibited: “don’t X”
* required: “must Y”
* preferred: “use Y not X”
* gate: “ask before … / require review / run tests first”

Convert into `Constraint` objects:

* `text`
* `severity`:

  * block → `forbidden`
  * correct → `requires_approval` or `warning` depending on language strength
* `scope.paths`:

  * inferred from mentioned files/modules; else repo-wide
* `detection_hints`:

  * strings, commands, file globs

This is how you operationalize the “learning from mistakes” point in your doc. 

---

## 3) Practical “starter trigger list” for tool events

These aren’t rules of the universe; they’re a pragmatic bootstrap.

### Tests

Match command prefixes:

* `pytest`, `go test`, `mvn test`, `gradle test`, `npm test`, `pnpm test`, `cargo test`, `dotnet test`

### Lint/format

* `ruff`, `flake8`, `eslint`, `prettier`, `golangci-lint`, `cargo fmt`, `black`, `mypy`

### Risky commands

* `rm -rf`, `sudo`, `chmod -R`, `chown -R`
* `curl ... | bash`, `wget ... | sh`
* `git push` (especially to `main/master`)

Each match should create tags (**T_TEST**, **T_LINT**, **T_RISKY**, etc.) and a decision boundary.

---

## 4) Why this is the right “next” artifact for replacing you with OpenClaw

* The **schema** defines what OpenClaw must output (mode/scope/gates/instruction/risk).
* The **rubric** defines how you produce training episodes from your real history.
* The reaction labels you highlighted remain valuable, but now they feed:

  * constraint extraction (hardening governance), and
  * a preference model (simulating your approval later). 

---

Great — here is a **minimal, opinionated Episode Builder Spec** that is implementable, auditable, and *aligned with the final goal*: training OpenClaw to replace you as **orchestrator** (not to imitate Claude’s tool micro-steps).

This spec is explicitly built to preserve the key insight from your writeup: **commit correlation alone hides the “observation → action → reaction” structure that makes orchestration learnable**. 

---

# Episode Builder Spec v0.1

## Purpose

Build a dataset of **Orchestrator Decision-Point Episodes**:

[
(O_t) \rightarrow (A^{orch}_t) \rightarrow (Y_t)
]

Where:

* (O_t) = what the orchestrator *knew* at a decision point
* (A^{orch}_t) = what the orchestrator *decided* (mode/scope/gates/instruction)
* (Y_t) = what happened + measurable quality + (when present) your reaction label

This is the dataset you can use for:

1. **Baseline retrieval orchestrator** (RAG over prior episodes)
2. **Learned orchestration policy** (\pi(A^{orch}\mid O))
3. **Preference model** approximating your approvals/corrections (so OpenClaw can run with less human feedback)

---

# 1) Inputs

## 1.1 Required

1. **Claude Code session logs (JSONL)**
   Must include message events and tool calls/results. Your “turn-level” argument depends on this density. 

2. **Git history**

* `git log` (commit times, messages, hashes)
* `git diff` / `--stat` for diffs (when needed, derived from repo state at time windows)

## 1.2 Optional but strongly recommended

3. **Terminal transcript / command history**

* If Claude tool calls don’t capture everything (e.g., commands you ran manually)

4. **CI logs** (GitHub Actions or equivalent)

* Needed to compute stable “objective quality” signals beyond local tests

5. **Issue tracker metadata**

* Phase/task IDs improve supervision and evaluation splits

---

# 2) Outputs

## 2.1 Primary output: Episodes JSONL

One JSON object per episode following the “strict schema” you already asked for (or compatible subset).

**Required minimum fields**:

* `episode_id`, `timestamp`, `project`
* `observation` (repo_state, quality_state, context)
* `orchestrator_action` (mode, goal, scope, executor_instruction, gates, risk)
* `outcome` (executor_effects, quality, reward_signals, optional reaction)
* `provenance` (pointers to source lines/ids in the logs + commits)

## 2.2 Secondary output: Constraint Store

A growing set of extracted rules derived from your corrections/blocks (e.g., “no hardcoded secrets,” “avoid regex for XML”), because those are *exactly* the durable policy bits that commits hide. 

---

# 3) Architecture: What you’re building (conceptual)

The Episode Builder is a compiler:

**Raw logs + git** → **Unified event stream** → **Decision-point segments** → **Episode objects** → **Training dataset**

Key point: this is not “turn splitting.”
It’s **decision-point extraction**, which is the causal unit of orchestration (your doc’s central point, made operational). 

---

# 4) Pipeline stages

## Stage A — Normalize all logs into a unified event stream

### A.1 Canonical Event structure

Every record becomes:

* `event_id`
* `ts_utc` (convert everything to UTC)
* `session_id`
* `actor ∈ {human_orchestrator, executor, tool}`
* `type ∈ {user_msg, assistant_msg, tool_call, tool_result, git_event, ci_event}`
* `payload` (text/command/result metadata)
* `links` (message ids, parent ids, tool call ids)

### A.2 Time handling rules

* Prefer timestamps embedded in JSONL records.
* If git commit times are local time, convert to UTC.
* Detect clock skew by comparing “git commit time” vs “git commit command tool call time” if present; store `clock_skew_estimate`.

---

## Stage B — Tag events (classification layer)

You cannot extract decision points without tagging. This is where your reaction taxonomy becomes usable. 

### B.1 Tool tagger

If a tool call command matches, tag it:

* `T_TEST`: `pytest`, `go test`, `mvn test`, `npm test`, etc.
* `T_LINT`: `ruff`, `eslint`, `black`, etc.
* `T_BUILD`: `make`, `gradle`, `cargo build`, etc.
* `T_GIT_*`: `git status/diff/add/commit/push/...`
* `T_RISKY`: `rm -rf`, `sudo`, `curl | bash`, `git push origin main`, etc.
* `T_NET`: anything that hits network (if you want to gate it)

### B.2 Assistant message tagger (executor)

Tag assistant messages using lightweight heuristics (keywords/structure):

* `X_PROPOSE`: contains “Option A / Option B”, “tradeoffs”, “I recommend”
* `X_ASK`: ends with a question asking what to do next / approval
* `X_PATCH`: references file writes/diffs/patch content
* `X_SUMMARY`: “Summary”, “Findings”, “Conclusion”

### B.3 Human message tagger (orchestrator)

Tag your messages:

* `O_DIR`: directive / next step instruction
* `O_GATE`: “commit”, “open PR”, “stop”, “do not proceed”, “ask first”
* `O_CORR`: correction (“no, do X”, “don’t do Y, use Z”)
* `O_REDIRECT`: priority/scope shift (“instead focus on…”)
* `O_QUESTION`: clarifying question (“why”, “how”, “what about”)

These tags are directly grounded in the reaction types you described. 

---

## Stage C — Segment into **Decision-Point Episodes**

This is the core.

### C.1 Episode start trigger

Start a new episode when you observe any:

* `O_DIR` or `O_GATE` (you are directing/authorizing the next move)

This event anchors:

* `episode.timestamp`
* `orchestrator_action.executor_instruction` (raw text, later structured)

### C.2 Episode end triggers (decision boundary)

Close the current episode on the first occurrence of:

1. **Executor proposal / question**: `X_PROPOSE` or `X_ASK`
2. **Tool milestone result**: a completed `T_TEST`, `T_LINT`, or `T_BUILD` (result event)
3. **Risk boundary**: `T_RISKY` or `git push` attempt
4. **Commit created**: `T_GIT_COMMIT` result
5. **Timeout boundary** (pragmatic): no relevant events for N minutes (default 30)

Why: these are the moments where a *new choice* is now rationally required, which is exactly what your “turn-level episodes expose” argument is about. 

---

## Stage D — Populate fields (where each episode field comes from)

Below is the “wiring diagram” you asked for: **field → source**.

### D.1 Observation fields

| Field                                      | Derivation rule                                                           | Sources                                                        |
| ------------------------------------------ | ------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `project.branch`                           | last known branch name                                                    | tool `git branch`, `git status`, or inferred from git metadata |
| `project.commit_head`                      | last known HEAD                                                           | tool `git rev-parse HEAD` or inferred from repo state snapshot |
| `observation.repo_state.changed_files`     | union of files touched in tool writes/patches since last episode boundary | tool edits/writes + diffs if available                         |
| `observation.repo_state.diff_stat`         | compute from accumulated patch or from `git diff --stat` output           | tool outputs / git diff                                        |
| `observation.quality_state.tests`          | from last `T_TEST` result event in window                                 | tool test results                                              |
| `observation.quality_state.lint/build`     | same pattern                                                              | tool outputs / CI logs                                         |
| `observation.context.recent_summary`       | short summarization of last events; can be template-based at v0           | event tags + last assistant summary                            |
| `observation.context.constraints_in_force` | from constraint store active at that time                                 | constraint store                                               |

**Rule:** Observations must be *causally prior* to the orchestrator action.

---

### D.2 Orchestrator action fields

This is where you must avoid training the wrong thing. Your doc’s examples show tool calls as “action,” but for OpenClaw the “action” is the **directive**. 

| Field                                      | Derivation rule                                                       | Sources                        |
| ------------------------------------------ | --------------------------------------------------------------------- | ------------------------------ |
| `orchestrator_action.executor_instruction` | raw text of your directive                                            | `O_DIR` message                |
| `orchestrator_action.mode`                 | infer from directive + nearby tags                                    | see mode inference rules below |
| `orchestrator_action.scope.paths/avoid`    | extract paths mentioned; else infer from files touched in next window | message + tool file ops        |
| `orchestrator_action.gates`                | explicit (“run tests”, “ask first”) + implicit from risk              | message + risk rules           |
| `orchestrator_action.risk`                 | compute from mode + gates + protected paths + risky commands          | risk model below               |
| `orchestrator_action.goal`                 | extract 1 sentence goal: (verb + object + constraint)                 | message + minimal NLP rules    |

#### Mode inference rules (v0 deterministic)

* If directive contains “investigate”, “scan”, “find”, “analyze”, “look for examples” → `Explore`
* “plan”, “options”, “tradeoffs”, “proposal”, “design” → `Plan`
* “implement”, “add feature”, “write code”, “refactor X into Y” → `Implement` / `Refactor`
* “run tests”, “verify”, “check”, “validate”, “reproduce” → `Verify` / `Triage`
* “commit”, “PR”, “merge”, “release” → `Integrate`

If ambiguous, choose based on:

* presence of recent failures → bias to `Triage`
* presence of proposal request → bias to `Plan`

---

### D.3 Outcome fields

| Field                                                   | Derivation rule                           | Sources           |
| ------------------------------------------------------- | ----------------------------------------- | ----------------- |
| `outcome.executor_effects.tool_calls_count`             | count tool calls within episode segment   | tool events       |
| `outcome.executor_effects.files_touched`                | union of file paths in tool edits/writes  | tool events       |
| `outcome.executor_effects.commands_ran`                 | list normalized command strings           | tool events       |
| `outcome.executor_effects.git_events`                   | parse git commands used                   | tool events       |
| `outcome.quality.tests_status/lint_status/build_status` | status of last such tool event in episode | tool results / CI |
| `outcome.quality.diff_stat`                             | delta produced during this episode        | diff aggregation  |

---

## Stage E — Reaction labeling (human feedback)

This is your doc’s “ground truth signal”: your next prompt is the reward signal. 

### E.1 Reaction association rule

For an episode that ends at a decision boundary, look at the **next human orchestrator message**.

Label reaction based on that message:

* `approve`: explicit go-ahead / continuation / “commit” / “ship”
* `correct`: “no, do X instead”, constraint enforcement, fixing mistakes
* `redirect`: changes goal/scope without saying previous was wrong
* `block`: “stop / don’t do that / never”, especially around dangerous actions
* `question`: request for explanation or missing info
* `unknown`: cannot classify

### E.2 Confidence

Store `confidence` as:

* high when keywords are explicit (“NO”, “don’t”, “instead”)
* lower when inferred implicitly (silence or topic shift)

---

## Stage F — Constraint extraction (turn corrections into enforceable policy)

This is how you harvest what matters most for “replace me.”

### F.1 When to extract

Extract constraints when reaction ∈ {`correct`, `block`}.

### F.2 Constraint template rules

From “don’t X / use Y” generate:

* `constraint.text`: normalized statement (“Avoid regex for XML parsing”)
* `severity`:

  * block → `forbidden`
  * correct → `requires_approval` (default) unless phrasing is soft → `warning`
* `scope.paths`:

  * if message mentions module/file, scope it
  * else repo-wide
* `detection_hints`:

  * command patterns (`rm -rf tests/`)
  * forbidden strings (`'secret-key'`)
  * file globs (`tests/**`)
  * library names (`regex`, `libxml2`)

This operationalizes the difference your doc highlights between “final commit looks fine” and “the mistake that almost happened.” 

---

## Stage G — Reward signals (usable even when you’re replaced)

Your writeup correctly treats reaction as reward, but the future system must work when you’re absent. 

So every episode must compute **objective reward proxies**:

### G.1 Objective scoring (default v0)

* `tests`: pass=1, fail=0, not_run=0.5, unknown=0.5
* `lint`: same mapping
* `diff_risk`: computed below

### G.2 Diff risk model (v0)

Compute a scalar in ([0,1]) where 1 is high risk:

Let:

* (L = insertions + deletions)
* (F = files)
* (P = 1) if protected paths touched else 0
  (protected paths configured, e.g., `infra/`, `auth/`, `secrets/`, `db/migrations/`)

Default risk bands:

* if (P=1): `diff_risk = 1.0`
* else if (L \le 50) and (F \le 3): `0.2`
* else if (L \le 300) and (F \le 10): `0.5`
* else: `0.8`

Rationale: You need something stable and conservative before you have a learned risk model.

---

## Stage H — Subagent/delegation representation (the “Task is invisible in commits” issue)

Your doc explicitly calls out that delegation/subagents are invisible in commits and matter to orchestration. 

So you need a first-class representation.

### H.1 Detect delegation events

Detect executor events like:

* `Task(subagent_type="Explore", prompt="...")`
  or any structured “subagent run” artifact in logs.

### H.2 Represent it

Add to episode (either under `outcome.executor_effects` or a dedicated field):

* `delegations[]`:

  * `delegation_id`
  * `parent_episode_id`
  * `subagent_type` (Explore/Plan/etc.)
  * `prompt`
  * `start_ts`, `end_ts`
  * `summary_output`
  * `artifacts_created` (files written, notes)

### H.3 Why this matters

This becomes learnable orchestrator behavior like:

* “For large analysis tasks, delegate Explore first, then synthesize, then implement.”

Exactly what your examples illustrate. 

---

## Stage I — Commit correlation as validation layer (not the learning core)

You keep commit correlation, but for:

* milestone verification (“did episodes produce deliverables?”)
* measuring downstream quality (CI, churn)
* grounding time windows

### I.1 Linking episodes to commits (v0 heuristic)

Link episode → commit if:

* commit time within ±N minutes of episode end (default 10)
* file overlap score above threshold
* optional: presence of `git commit` tool event in episode provenance

Store linkage as:

* `provenance.sources += {type:"git", ref:"<hash>"}`
* `x_extensions.commit_links[] = {...confidence...}`

---

# 5) Configuration (so the system is not ad hoc)

Create a single YAML config that governs behavior:

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
  test_commands: ["pytest", "go test", "mvn test", "npm test", "pnpm test", "cargo test", "dotnet test"]
  lint_commands: ["ruff", "flake8", "eslint", "prettier", "black", "mypy", "golangci-lint"]

reaction_keywords:
  block: ["NO", "don't", "stop", "never", "absolutely not"]
  correct: ["no, do", "instead", "use", "replace", "avoid"]
  approve: ["yes", "ok", "looks good", "go ahead", "commit", "ship", "continue"]
  redirect: ["instead focus", "let's do", "different direction", "switch to"]
```

---

# 6) Acceptance criteria (how you know the Episode Builder is “good enough”)

### A) Structural validity

* ≥ 99% of output episodes validate against schema (or a strict subset).

### B) Causal correctness (spot-check)

On a random sample:

* Observation clearly precedes action
* Outcome clearly follows action
* Reaction label matches what a human would label ≥ 85% of the time

### C) Orchestrator relevance

* ≥ 90% of episodes have a non-empty `orchestrator_action` directive
* Not dominated by executor micro-steps

### D) Training utility

* Baseline retrieval orchestrator can retrieve “similar episodes” that reflect both:

  * successful patterns (approve)
  * failure avoidance patterns (correct/block)
    This is the direct payoff your doc argues for. 

---

# 7) The key “better than v0.1” upgrades (once v0 works)

You can add these later without changing the core structure:

1. Replace keyword mode inference with a small classifier trained on your labeled episodes.
2. Replace heuristic reaction labeling with a preference model that predicts approve/correct/block.
3. Add “state summarization snapshots” computed by running safe repo queries at build time (if logs are incomplete).

---

## The crux

This spec turns your idea into a dataset that **OpenClaw can actually learn from**, because it explicitly represents:

* decision points (not just turns),
* orchestration actions (not just tool calls),
* reaction/constraints (the “why” behind good work),
* and objective reward proxies that remain when the human disappears. 

-----



Below is a **worked example** of the Episode Builder Spec in action: a short synthetic “unified event stream” → tags → **3 decision-point episodes** → **reaction labeling + constraint extraction** → **commit linkage**. This is exactly the kind of structure your turn-level argument is aiming at (Observation → Action → Reaction). 

---

## 0) Synthetic unified event stream (what the builder sees)

Assume we’ve normalized Claude Code JSONL + tool calls + git into a single timeline `E = [e1…e18]`:

**Session:** `sess-9f1c`
**Branch:** `feature/03.1-01-xml`
**Task:** implement XML parser in `src/parser.cpp`

### Events

* **e1 10:00:05Z** — `human_orchestrator:user_msg`
  “Implement an XML parser in `src/parser.cpp`. Keep it minimal.”

* **e2 10:00:12Z** — `executor:assistant_msg`
  “Got it. I’ll implement a simple parser.”

* **e3 10:00:20Z** — `tool:tool_call`
  `Read src/parser.h`

* **e4 10:01:10Z** — `tool:tool_call`
  `Write src/parser.cpp` *(regex-based implementation)*

* **e5 10:01:30Z** — `executor:assistant_msg`
  “Implemented using regex for simplicity. Want me to add tests?”

* **e6 10:02:10Z** — `human_orchestrator:user_msg`
  “No—don’t use regex for XML. Use a proper parser library (e.g., libxml2) or whatever the repo already uses. First scan the repo for existing parsing patterns.”

* **e7 10:02:25Z** — `executor:assistant_msg`
  “Understood. I’ll inspect existing patterns and propose options.”

* **e8 10:02:40Z** — `tool:tool_call`
  `Grep "xml" -n src/`

* **e9 10:03:05Z** — `tool:tool_call`
  `Grep "libxml" -n .`

* **e10 10:03:30Z** — `tool:tool_call`
  `Read src/legacy_xml_adapter.cpp` *(finds libxml2 usage)*

* **e11 10:04:10Z** — `executor:assistant_msg` *(proposal)*
  “Options: (A) reuse `legacy_xml_adapter` wrapper (recommended), (B) direct libxml2 usage, (C) write custom parser (not recommended). Which?”

* **e12 10:04:40Z** — `human_orchestrator:user_msg`
  “Pick (A) and implement. Add tests. Run targeted tests first, then full suite. Then commit.”

* **e13 10:05:05Z** — `tool:tool_call`
  `Edit src/parser.cpp` *(replace regex impl with wrapper)*

* **e14 10:06:10Z** — `tool:tool_call`
  `Write tests/test_parser_xml.cpp`

* **e15 10:06:40Z** — `tool:tool_call`
  `Bash pytest -k xml`

* **e16 10:07:05Z** — `tool:tool_result`
  `pytest -k xml` → PASS

* **e17 10:07:20Z** — `tool:tool_call`
  `Bash pytest`

* **e18 10:08:05Z** — `tool:tool_result`
  `pytest` → PASS

* **e19 10:08:30Z** — `tool:tool_call`
  `git commit -am "feat(parser): implement XML parsing via legacy adapter"`

* **e20 10:08:33Z** — `tool:tool_result`
  commit hash: `abc1234`

* **e21 10:08:50Z** — `human_orchestrator:user_msg`
  “Looks good.”

---

## 1) Tagging (what the builder infers)

### Key tags

* **e1**: `O_DIR` (directive)
* **e5**: `X_ASK` (asks what to do next)
* **e6**: `O_CORR` + `O_DIR` (correction + new directive)
* **e11**: `X_PROPOSE` (options/tradeoffs)
* **e12**: `O_DIR` + `O_GATE` (directive + explicit gates: tests, commit)
* **e15/e16**: `T_TEST` (targeted tests)
* **e17/e18**: `T_TEST` (full tests)
* **e19/e20**: `T_GIT_COMMIT`

---

## 2) Episode segmentation (decision-point boundaries)

Using the segmentation rules you accepted (start on `O_DIR`, end on `X_ASK/X_PROPOSE`, tests, risky boundary, commit, etc.):

### Episode 1

* **Start:** e1 (`O_DIR`)
* **End trigger:** e5 (`X_ASK`)
* **Reaction source:** next orchestrator msg = e6

### Episode 2

* **Start:** e6 (`O_CORR` + `O_DIR`)
* **End trigger:** e11 (`X_PROPOSE`)
* **Reaction source:** next orchestrator msg = e12

### Episode 3

* **Start:** e12 (`O_DIR` + `O_GATE`)
* **End trigger:** e20 (`T_GIT_COMMIT` result)
* **Reaction source:** next orchestrator msg = e21

---

## 3) Emitted episodes (what the builder outputs)

Below are the **3 episode JSON objects** (formatted for readability). These are the *training examples* for “OpenClaw as orchestrator.”

### Episode 1 (initial directive → executor did regex → you corrected)

```json
{
  "episode_id": "ep-001",
  "timestamp": "2026-02-06T10:00:05Z",
  "project": {
    "repo_path": "/repo",
    "branch": "feature/03.1-01-xml",
    "commit_head": "prev9999"
  },
  "phase": "03.1-01",
  "task_id": "xml-parser-impl",

  "observation": {
    "repo_state": {
      "changed_files": [],
      "diff_stat": { "files": 0, "insertions": 0, "deletions": 0 }
    },
    "quality_state": {
      "tests": { "status": "unknown" },
      "lint": { "status": "unknown" }
    },
    "context": {
      "recent_summary": "User requested minimal XML parser implementation.",
      "open_questions": [],
      "constraints_in_force": []
    }
  },

  "orchestrator_action": {
    "mode": "Implement",
    "goal": "Implement minimal XML parser in src/parser.cpp",
    "scope": { "paths": ["src/"], "avoid": [] },
    "executor_instruction": "Implement an XML parser in src/parser.cpp. Keep it minimal.",
    "gates": [],
    "risk": "medium"
  },

  "outcome": {
    "executor_effects": {
      "tool_calls_count": 2,
      "files_touched": ["src/parser.h", "src/parser.cpp"],
      "commands_ran": ["Read src/parser.h", "Write src/parser.cpp"],
      "git_events": []
    },
    "quality": {
      "tests_status": "not_run",
      "lint_status": "unknown",
      "diff_stat": { "files": 1, "insertions": 120, "deletions": 0 }
    },
    "reaction": {
      "label": "correct",
      "message": "No—don’t use regex for XML. Use a proper parser library or existing patterns; scan the repo first.",
      "confidence": 0.92
    },
    "reward_signals": {
      "objective": { "tests": 0.5, "lint": 0.5, "diff_risk": 0.5 }
    }
  },

  "constraints_extracted": [
    {
      "constraint_id": "c-avoid-regex-xml",
      "text": "Avoid regex-based XML parsing; use a proper parser library or existing adapter.",
      "severity": "requires_approval",
      "scope": { "paths": ["src/"] },
      "detection_hints": ["std::regex", "regex", "XML parsing"]
    }
  ],

  "labels": { "episode_type": "decision_point" },

  "provenance": {
    "sources": [
      { "type": "claude_jsonl", "ref": "sess-9f1c:e1-e6" }
    ]
  }
}
```

### Episode 2 (your correction directive → executor explores → proposes options → you approve/choose)

```json
{
  "episode_id": "ep-002",
  "timestamp": "2026-02-06T10:02:10Z",
  "project": {
    "repo_path": "/repo",
    "branch": "feature/03.1-01-xml",
    "commit_head": "prev9999"
  },
  "phase": "03.1-01",
  "task_id": "xml-parser-impl",

  "observation": {
    "repo_state": {
      "changed_files": ["src/parser.cpp"],
      "diff_stat": { "files": 1, "insertions": 120, "deletions": 0 }
    },
    "quality_state": {
      "tests": { "status": "not_run" },
      "lint": { "status": "unknown" }
    },
    "context": {
      "recent_summary": "Regex-based XML implementation produced; needs replacement using repo patterns.",
      "open_questions": ["What XML parsing approach already exists in repo?"],
      "constraints_in_force": ["c-avoid-regex-xml"]
    }
  },

  "orchestrator_action": {
    "mode": "Explore",
    "goal": "Identify existing XML parsing patterns/adapters and choose safest approach",
    "scope": { "paths": ["src/"], "avoid": [] },
    "executor_instruction": "Scan the repo for existing parsing patterns and libraries used for XML; propose 2-3 options with tradeoffs.",
    "gates": [
      { "type": "no_write_before_plan", "params": {} }
    ],
    "risk": "low"
  },

  "outcome": {
    "executor_effects": {
      "tool_calls_count": 3,
      "files_touched": ["src/legacy_xml_adapter.cpp"],
      "commands_ran": [
        "Grep \"xml\" -n src/",
        "Grep \"libxml\" -n .",
        "Read src/legacy_xml_adapter.cpp"
      ],
      "git_events": []
    },
    "quality": {
      "tests_status": "not_run",
      "lint_status": "unknown",
      "diff_stat": { "files": 0, "insertions": 0, "deletions": 0 }
    },
    "reaction": {
      "label": "approve",
      "message": "Pick (A) and implement. Add tests. Run targeted tests first, then full suite. Then commit.",
      "confidence": 0.90
    },
    "reward_signals": {
      "objective": { "tests": 0.5, "lint": 0.5, "diff_risk": 0.2 }
    }
  },

  "labels": { "episode_type": "checkpoint" },

  "provenance": {
    "sources": [
      { "type": "claude_jsonl", "ref": "sess-9f1c:e6-e12" }
    ]
  }
}
```

### Episode 3 (implement chosen option → tests → commit → you approve)

```json
{
  "episode_id": "ep-003",
  "timestamp": "2026-02-06T10:04:40Z",
  "project": {
    "repo_path": "/repo",
    "branch": "feature/03.1-01-xml",
    "commit_head": "prev9999"
  },
  "phase": "03.1-01",
  "task_id": "xml-parser-impl",

  "observation": {
    "repo_state": {
      "changed_files": ["src/parser.cpp"],
      "diff_stat": { "files": 1, "insertions": 120, "deletions": 0 }
    },
    "quality_state": {
      "tests": { "status": "not_run" },
      "lint": { "status": "unknown" }
    },
    "context": {
      "recent_summary": "Executor identified legacy XML adapter; orchestrator selected adapter-based approach.",
      "open_questions": [],
      "constraints_in_force": ["c-avoid-regex-xml"]
    }
  },

  "orchestrator_action": {
    "mode": "Implement",
    "goal": "Replace regex XML parser with adapter-based XML parsing and add tests",
    "scope": { "paths": ["src/", "tests/"], "avoid": [] },
    "executor_instruction": "Implement option (A) using legacy_xml_adapter. Add tests. Run pytest -k xml, then full pytest. Then commit.",
    "gates": [
      { "type": "run_tests", "params": { "command": "pytest -k xml" } },
      { "type": "run_tests", "params": { "command": "pytest" } },
      { "type": "require_human_approval", "params": { "for": "push_or_merge" } }
    ],
    "risk": "medium"
  },

  "outcome": {
    "executor_effects": {
      "tool_calls_count": 6,
      "files_touched": ["src/parser.cpp", "tests/test_parser_xml.cpp"],
      "commands_ran": [
        "Edit src/parser.cpp",
        "Write tests/test_parser_xml.cpp",
        "Bash pytest -k xml",
        "Bash pytest",
        "git commit -am \"feat(parser): implement XML parsing via legacy adapter\""
      ],
      "git_events": [
        { "type": "commit", "ref": "abc1234", "message": "feat(parser): implement XML parsing via legacy adapter" }
      ]
    },
    "quality": {
      "tests_status": "pass",
      "lint_status": "unknown",
      "diff_stat": { "files": 2, "insertions": 180, "deletions": 20 }
    },
    "reaction": {
      "label": "approve",
      "message": "Looks good.",
      "confidence": 0.85
    },
    "reward_signals": {
      "objective": { "tests": 1.0, "lint": 0.5, "diff_risk": 0.5 }
    }
  },

  "labels": { "episode_type": "milestone" },

  "provenance": {
    "sources": [
      { "type": "claude_jsonl", "ref": "sess-9f1c:e12-e21" },
      { "type": "git", "ref": "abc1234" }
    ]
  }
}
```

---

## 4) Constraint store update (what persists across tasks)

From Episode 1’s `correct` reaction, the builder adds:

```json
{
  "constraint_id": "c-avoid-regex-xml",
  "text": "Avoid regex-based XML parsing; use a proper parser library or existing adapter.",
  "severity": "requires_approval",
  "scope": { "paths": ["src/"] },
  "detection_hints": ["std::regex", "regex", "XML parsing"]
}
```

This is the crucial “durable judgment” that commit-only correlation would never expose. It’s also exactly the kind of policy knowledge you need when OpenClaw replaces you. 

---

## 5) Commit linkage (how ep-003 links to git)

**Heuristic rules (v0):**

* commit within ±10 minutes of episode end ✅ (10:08:33Z is within the ep-003 window)
* file overlap between episode files and commit diff ✅ (`src/parser.cpp`, `tests/test_parser_xml.cpp`)
* explicit `git commit` event present ✅

So `ep-003.provenance.sources` includes `{type:"git", ref:"abc1234"}` and the confidence would be high.

---

## What this example demonstrates (in the terms of your goal)

* We did **not** “train on commits.” We trained on **decision points**.
* We separated:

  * **orchestrator directives** (what OpenClaw must learn)
  * from **executor tool calls** (how Claude executed)
* We captured your key advantage: **mistakes + corrections become learnable constraints**, not lost history. 

