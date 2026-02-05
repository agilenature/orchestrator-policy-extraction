The *next phase* is where you stop treating “OpenClaw as a cool interface” and instead treat it as what it really is:

> a **privileged automation bus** that must be put inside an **execution envelope** (sandbox + allowlists + approvals + audit), then only *gradually* promoted from “advisor” → “operator” → “autopilot”.

OpenClaw’s own security docs basically say the same thing: **access control before intelligence**—assume the model can be manipulated and design so manipulation has limited blast radius. ([OpenClaw][1])

Below is a concrete, formal “Phase 2” plan after your deliverables (correlation pipeline, taxonomy, episode dataset, baseline policy, etc.). It’s written as engineering steps with explicit gates.

---

## Phase 2: Controlled delegation to OpenClaw

### 2.1 Choose the orchestration architecture (don’t skip this)

You have two viable designs:

**A) OpenClaw is the orchestrator, Claude Code is the executor**

* OpenClaw decides next steps and triggers Claude Code runs (e.g., via CLI calls) as a subordinate action.
* Benefit: preserves Claude Code’s codebase-native workflows and “agentic coding” features. Claude Code is explicitly designed to edit files, run commands, and create commits. ([Claude Code][2])
* Cost: you now have *two agentic layers*; you must strictly control what each is allowed to do.

**B) OpenClaw is the orchestrator and executor (Claude Code optional)**

* OpenClaw uses its own tools/skills to inspect/edit/run tests/commit.
* Benefit: simpler stack.
* Cost: you may lose Claude Code-specific workflow advantages (depending on your setup).

Given your stated goal (“OpenClaw controls Claude Code on my behalf”), you’re aiming at **A**.

---

## Phase 2 Deliverable 1: A governed execution envelope for OpenClaw

This is the *non-negotiable* prerequisite because OpenClaw is designed to run on your devices and can be connected to channels; the threat model includes executing shell commands, reading/writing files, and sending messages. ([GitHub][3])

### A. Run OpenClaw in a sandbox by default

OpenClaw supports running tools inside Docker to reduce blast radius. ([OpenClaw][4])
Key controls you should actively use:

* `agents.defaults.sandbox.mode: "all"` (every session sandboxed) ([OpenClaw][4])
* Start with `workspaceAccess: "ro"` (read-only mount) to force “advisor / inspector” behavior ([OpenClaw][4])
* Only later move to `"rw"` for controlled writing

### B. Put exec behind approvals + allowlists (no “full” by default)

OpenClaw’s `exec` tool supports **allowlist** enforcement and rejects chaining/redirections in allowlist mode. ([OpenClaw][5])
And it supports **approval-gated** exec flows with explicit lifecycle events. ([OpenClaw][6])

Practical interpretation:

* Early: approvals = “ask”, security = “allowlist”, *very small allowlist*
* Later: approvals “on-miss” or “ask” depending on risk

### C. Avoid third‑party skills as a default

This is not theoretical right now:

* There have been widespread reports of malware in OpenClaw “skills”/extensions on its marketplace/registry. ([The Verge][7])
* Security research points out there’s **no cryptographic signing/verification** and that workspace/managed skill precedence + watchers can increase risk (shadowing + hot reload). ([Snyk][8])
* Cisco’s AI security team even built a “Skill Scanner” tool and notes prior research finding vulnerabilities in agent “skills.” ([Cisco Blogs][9])

So your “Phase 2” stance should be:

* **No ClawHub/community skills in production**
* Only skills you own, review, pin, and scan

### D. Build auditability into the platform, not as an afterthought

OpenClaw stores session transcripts on disk under `~/.openclaw/.../sessions/*.jsonl` and explicitly says disk access is the trust boundary. ([OpenClaw][1])
That’s *good* for your project, because you already want trace correlation (like you did with Claude Code logs and git history).

---

## Phase 2 Deliverable 2: A “Tool Contract” between Orchestrator and Executor

To replace you, you must make your orchestration decisions **parseable** and **checkable**.

### Define a structured action schema (example)

Your orchestrator policy should output something like:

* **Goal**: what’s being achieved
* **Next actions**: list of actions in a controlled vocabulary (your “action taxonomy” deliverable)
* **Gates**: what must be true before proceeding (tests pass, diff size, specific files unchanged)
* **Rollback**: how to undo safely
* **Risk label**: low/meals)

This is what lets OpenClaw act as orchestrator without becoming a “vibes-based” agent.

---

## Phase 2 Deliverable 3: OpenClaw skill pack for orchestration (minimal, internal)

Assuming architecture **A** (OpenClaw → Claude Code), your first internal skills should be boring and deterministic:

1. **Repo state snapshot**

* `git status`, `git diff --stat`, current branch, last commits, failing tests summary

2. **Test runner**

* run your standard test command(s)
* return structured results

3. **Claude Code runner**

* invoke Claude Code in a controlled way (e.g., with a wrapper script so OpenClaw never calls arbitrary `claude` invocations)
* capture Claude output, produced diffs, and exit status

4. **Safe Git operations (WRAPPED)**
   This is crucial: OpenClaw’s exec allowlist is primarily about *binaries*; if you allowlist `git`, you may accidentally allow `git push`.
   So instead:

* allowlist only **your own wrapper binaries** like `safe-git-commit`, `safe-git-diff`, `safe-git-branch` that enforce subcommand + argument policy.

(That one design choice prevents an entire class of “oops” outcomes.)

OpenClaw’s docs explicitly describe how skills are enabled/disabled, injected per run, and how sandbox requirements interact with installed binaries. ([OpenClaw][10])

---

## Phase 2 Deliverable 4: Shadow-mode evaluation, then staged promotion

This is how you transition from “we have models” to “OpenClaw actually orchestrates.”

### Stage 1 — Shadow orchestrator (no execution)

* OpenClaw produces **next-step recommendations only**
* You execute manually
* You measure: agreement with your historical policy (offline) + usefulness (online)

Exit criteria:

* High alignment on *task sequencing* (not wording)
* Low rate of “missing critical checks”

### Stage 2 — Read-only operator

* Sandbox on
* `workspaceAccess: "ro"` ([OpenClaw][4])
* Allowlisted exec only for inspection + tests
* Claude Code runs allowed, but no file writes by OpenClaw itself

Exit criteria:

* Agent reliably gathers the *right evidence* before proposing edits
* It does not spam commands / derail

### Stage 3 — Write-in-branch operator (human-gated)

* `workspaceAccess: "rw"` but still sandboxed ([OpenClaw][4])
* Agent can create a feature branch + local commits *via wrappers*
* Pushing / PR creation requires approval (“ask”)

Exit criteria:

* Diffs are reviewable and match acceptance criteria
* Test pass rate is stable
* Rework cycles shrink vs your baseline

### Stage 4 — PR autopilot (review-gated)

* Agent opens PRs, runs CI, responds to review comments
* Merge remains human-controlled

Exit criteria:

* Sustained throughput improvements with no regression spike

### Stage 5 — Limited autonomous merge (only for low-risk classes)

* Only for predefined task types (formatting, mechanical refactors, doc updates)
* Hard guardrails: diff size caps, file allowlists, mandatory green CI

---

## Phase 2 Deliverable 5: Operational security configuration for OpenClaw

Because OpenClaw is a gateway that can expose a Control UI and connect devices/channels, lock down the “who can talk to it” layer.

OpenClaw’s docs emphasize:

* Control UI device pairing (remote requires approval) ([OpenClaw][11])
* Channel allowlists / mention gating concepts ([OpenClaw][12])

Practical rule:

* In Phase 2, prefer **local Control UI only** (dashboard) over messaging channels unless you truly need them. ([OpenClaw][13])

---

## What “done” looks like for this phase

At the end of Phase 2, you should be able to say:

1. OpenClaw runs in a sandboxed, least-privilege config (and you can prove it). ([OpenClaw][4])
2. OpenClaw can *reproduce your orchestration loop* in shadow + read-only modes using the same kind of event logs you already correlate for Claude Code.
3. You have internal skills/wrappers that make “allowed actions” a mechanical fact, not a hope. ([OpenClaw][10])
4. Promotion to write/PR modes is gated by measured outcomes, not enthusiasm.

---

You’re not missing anything — I *did* leave an implicit bridge unstated:

> Phase 2 is **operationalization**: turning your *analysis artifacts* (correlation, taxonomy, dataset, policies) into a **runtime control system** where OpenClaw can safely choose and execute actions.

Right now your deliverables are like a *scientific model* of orchestration. OpenClaw orchestration is the *engineering system* that uses that model to act.

Below is the explicit mapping you asked for.

---

## The missing bridge: an “Orchestrator Runtime” architecture

To have OpenClaw behave as the orchestrator, you need a runtime loop like this:

1. **Observe state** (repo snapshot, diffs, tests, context)
2. **Choose next action** (baseline or learned policy)
3. **Validate + gate** (governance harness: allowlists/approvals/risk rules)
4. **Execute** (OpenClaw triggers Claude Code / tools)
5. **Log + score** (correlation pipeline produces episodes; metrics update dataset)

Think of it as:

```
[Repo + Logs] -> (Correlation) -> Episode D
                 ^                 |
                 |                 v
(OpenClaw observes state) -> Policy chooses action -> Harness executes safely -> results logged
```

That’s where each deliverable plugs in.

---

## 1:1 mapping from your deliverables to “OpenClaw as orchestrator”

### 1) Correlation pipeline (L ↔ G)

**What it is (your work):** Align Claude Code interaction/tool events with git commits and repo changes. 

**What it becomes in Phase 2:**
The **flight recorder + evaluator** for OpenClaw orchestration.

* It answers: “When OpenClaw took action X, what diff did it produce, what tests ran, what commit happened, and what happened next?”
* Without this, you cannot do *controlled delegation* because you can’t measure outcomes or regressions reliably.
* It also lets you **compare** “Human-orchestrated episodes” vs “OpenClaw-orchestrated episodes” using the same metrics.

So: correlation isn’t “nice to have”; it’s what makes automation *auditable* and improvement *possible*. 

---

### 2) Orchestrator action taxonomy

**What it is:** A controlled vocabulary of “what the orchestrator does next.”

**What it becomes in Phase 2:**
The **action space** that OpenClaw is allowed to select from.

This is the key conceptual link you didn’t see because I didn’t spell it out:

* OpenClaw can only orchestrate if “possible next steps” are **finite, named, and checkable**.
* Each taxonomy item becomes either:

  * an OpenClaw **skill** (e.g., `run_tests`, `repo_snapshot`, `create_branch`, `request_claude_patch`), or
  * an **action template** OpenClaw fills (e.g., “ask Claude Code to draft migration mapping for module X”).

**Even more important:** the taxonomy is how you enforce *governance*:

* Every action gets a **risk class** and **required gates** (approval, test pass, diff size limit, etc.).

No taxonomy → OpenClaw becomes a free-form chat agent with shell access (not an orchestrator).

---

### 3) Episode dataset D

**What it is:** Labeled sequences of ((observation, action, outcome)). 

**What it becomes in Phase 2:**
The **memory + training ground** for the OpenClaw orchestrator.

It supports two practical implementations:

* **Retrieval orchestrator (RAG policy):** “In situations like this, what did the human do?”
* **Learned policy training:** behavior cloning / imitation learning on the same tuples.

Also: in Phase 2, D becomes your **regression test suite for orchestration**:

* You can run the policy offline on historical observations and check whether it proposes reasonable next actions (before letting it run on a real repo).

---

### 4) Baseline orchestrator

**What it is:** A simple rules/retrieval-based policy that works before ML.

**What it becomes in Phase 2:**
Your **Shadow Mode OpenClaw orchestrator** (the first safe deployment).

This directly corresponds to what I described as:

* “Shadow orchestrator (no execution)” and
* later “read-only operator.”

Baseline orchestrator is not academic — it is how you *first* let OpenClaw drive decisions without risking destructive actions.

**If you skip this and go straight to a learned policy**, you lose debuggability and you won’t know whether failures come from:

* poor model decisions,
* missing state,
* unsafe tools,
* or bad gating.

---

### 5) Learned orchestrator policy

**What it is:** A learned mapping (\pi(a\mid o)).

**What it becomes in Phase 2:**
The **action selector** that can graduate OpenClaw from “advisor” to “operator.”

But only after:

* your baseline is stable,
* your harness is strict,
* and your evaluation metrics are meaningful.

Crucial point: the learned policy does **not** replace the harness.
It only replaces the *human choice of next action*. Execution still stays behind guardrails.

---

### 6) Governing execution harness

**What it is:** The environment that enforces safety constraints.

**What it becomes in Phase 2 (this is the most direct link):**
It *is literally* the “sandbox + allowlists + approvals + wrappers + PR gates” I described.

This harness is the thing that makes OpenClaw orchestration not suicidal:

* If policy says “run tests,” harness ensures only approved commands run.
* If policy says “commit,” harness ensures only allowed branches, commit message format, no push to protected branches, etc.
* If policy says “refactor,” harness can enforce diff-size caps and require approvals.

So when you asked “how does this relate?” — the harness is the **implementation substrate** of Phase 2.

---

## A concrete example to show the relationship end-to-end

Say the repo is mid-modernization and tests start failing after a dependency bump.

### Observation (o_t)

* failing tests list + logs
* recent diff summary
* migration phase label
* last N turns context

### Taxonomy gives the allowed actions

* `RUN_TESTS_TARGETED`
* `ASK_CLAUDE_TRIAGE`
* `APPLY_PATCH`
* `RUN_TESTS_FULL`
* `COMMIT_FIX`
* `ESCALATE_TO_HUMAN`

### Baseline policy (shadow mode)

* retrieves similar episodes from D (“last time tests failed after bump, you did triage → patch → rerun”)
* proposes next action: `ASK_CLAUDE_TRIAGE`

### Harness checks and executes

* allows: read logs + run approved test command
* disallows: push/merge/destructive ops
* requires approval if action is “apply patch” or “commit”

### Correlation pipeline logs what happened

* ties the triage conversation + tool calls to the resulting diff/commit 
* produces a new episode appended to D (now including OpenClaw’s decision and outcome)

That is the closed loop.

---

## So what *exactly* is “the next phase” with your deliverables?

With your deliverables in hand, Phase 2 is:

1. **Compile the taxonomy into executable actions** (OpenClaw skills + action templates)
2. **Wrap every action with governance** (harness)
3. **Deploy the baseline policy in shadow mode** (decision support only)
4. **Promote to read-only execution** (inspection + tests)
5. **Promote to write-on-branch execution** (commits/PRs gated)
6. **Only then swap baseline → learned policy** as the action selector
7. **Use correlation pipeline to continuously measure, debug, and update D** 

---

## The one-sentence connection

* **Taxonomy** defines “what OpenClaw is even allowed to do.”
* **Policies** decide “which allowed thing to do next.”
* **Harness** decides “whether it may actually do it.”
* **Correlation + Dataset** decide “whether it worked and how to improve.”

That’s the full dependency chain.

If you want, I can express this as a single **systems diagram + interface contract** (JSON schema for observations/actions/outcomes) so it’s implementable immediately in your repo/tooling.


---

If you want, I can write the next artifact you’ll actually need: a **concrete Orchestrator Action Schema** (JSON/YAML) plus a **minimal OpenClaw config skeleton** that enforces: sandbox `"all"`, workspaceAccess `"ro"`, exec `security=allowlist`, and skills watcher constraints—so your first deployment is “safe by construction.” ([OpenClaw][4])

* [Reuters](https://www.reuters.com/world/china/china-warns-security-risks-linked-openclaw-open-source-ai-agent-2026-02-05/?utm_source=chatgpt.com)
* [The Verge](https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare?utm_source=chatgpt.com)
* [Tom's Hardware](https://www.tomshardware.com/tech-industry/cyber-security/malicious-moltbot-skill-targets-crypto-users-on-clawhub?utm_source=chatgpt.com)
* [businessinsider.com](https://www.businessinsider.com/openclaw-moltbot-china-internet-alibaba-bytedance-tencent-rednote-ai-agent-2026-2?utm_source=chatgpt.com)



[1]: https://docs.openclaw.ai/gateway/security "Security - OpenClaw"
[2]: https://code.claude.com/docs/en/overview "Claude Code overview - Claude Code Docs"
[3]: https://github.com/openclaw/openclaw "GitHub - openclaw/openclaw: Your own personal AI assistant. Any OS. Any Platform. The lobster way. "
[4]: https://docs.openclaw.ai/gateway/sandboxing "Sandboxing - OpenClaw"
[5]: https://docs.openclaw.ai/tools/exec "Exec Tool - OpenClaw"
[6]: https://docs.openclaw.ai/tools/exec-approvals "Exec Approvals - OpenClaw"
[7]: https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare?utm_source=chatgpt.com "OpenClaw's AI 'skill' extensions are a security nightmare"
[8]: https://snyk.io/articles/skill-md-shell-access/ "From SKILL.md to Shell Access in Three Lines of Markdown: Threat Modeling Agent Skills | Snyk"
[9]: https://blogs.cisco.com/ai/personal-ai-agents-like-openclaw-are-a-security-nightmare "Personal AI Agents like OpenClaw Are a Security Nightmare - Cisco Blogs"
[10]: https://docs.openclaw.ai/skills "Skills - OpenClaw"
[11]: https://docs.openclaw.ai/web/control-ui "Control UI - OpenClaw"
[12]: https://docs.openclaw.ai/ "OpenClaw - OpenClaw"
[13]: https://docs.openclaw.ai/start/getting-started "Getting Started - OpenClaw"



