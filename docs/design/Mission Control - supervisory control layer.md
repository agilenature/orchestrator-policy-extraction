  Mission Control

  - Description: Community-driven dashboard applications for managing OpenClaw agents. Multiple implementations exist, with ClawDeck being the officially recognized open-source dashboard.
  - Purpose: Provides real-time visibility into agent status, task management, resource consumption, and intuitive interfaces for controlling agents
  - GitHub: https://github.com/crshdn/mission-control and https://clawdeck.io
  

**Mission Control is almost exactly the missing “supervisory control layer”** for what you’re building: a human‑in‑the‑loop system that can *structure* orchestration decisions, gate risky actions, and continuously capture training data as episodes.

From the README, Mission Control already gives you: **task creation**, an **AI-guided planning Q&A**, **agent creation**, **auto-dispatch** to agents running in **OpenClaw Gateway**, and a **workflow board** (PLANNING → … → REVIEW → DONE), backed by **SQLite**, connected to OpenClaw over **WebSockets**. 
That aligns extremely well with your “decision‑point episodes beat commit correlation” approach, because tasks + planning + review are natural *episode boundaries and labels*. 

Here’s how it fits, and what you should change to make it *orchestrator-training-native*.

---

## Where Mission Control fits in the architecture

### What Mission Control becomes in your system

**Mission Control = Orchestrator Training Cockpit**

It sits “above” OpenClaw and does 3 crucial jobs:

1. **Creates decision points** (structured tasks + planning checkpoints)
2. **Collects ground-truth reactions** (your approvals/corrections during REVIEW)
3. **Provides governance gates** (you cannot progress a task state unless gates are satisfied)

That is exactly the scaffolding you need to replace you later with OpenClaw.

---

## Mapping your deliverables to Mission Control (1:1)

### 1) Orchestrator action taxonomy → Mission Control “Task Types”

Mission Control can enforce that every task is one of your taxonomy actions (Explore/Plan/Implement/Verify/Integrate/Triage/Refactor) instead of ad‑hoc free text.

**Concrete UI change**

* Add a required field: `orchestrator_mode`
* Add optional: `risk`, `gates`, `scope.paths`, `scope.avoid`, `constraints_in_force`

Now your “action taxonomy” becomes a **controlled input** rather than something you infer after the fact.

### 2) Episode dataset D → Mission Control’s SQLite as the episode store

Mission Control already stores tasks in SQLite. 
Add tables:

* `episodes`
* `episode_events`
* `constraints`
* `approvals`
* `commit_links`

So instead of “parse logs later and hope,” you do **event-sourcing** in real time:

* every time OpenClaw runs a tool, Mission Control records it (with provenance)
* every time you approve/correct in REVIEW, Mission Control records it as a label

This directly produces the decision-point episodes your approach requires. 

### 3) Correlation pipeline → Mission Control provides the join key

Right now, correlation is hard because commits/logs and chat logs don’t share a stable ID.

Mission Control can **mint** that ID:

* `task_id` and `episode_id` become your primary keys
* you stamp them into:

  * branch names, commit trailers, PR titles, or a `.mc/task.json` file

Then correlation becomes deterministic instead of probabilistic.

### 4) Baseline orchestrator + learned policy → “Orchestrator Agent” in OpenClaw

Mission Control should **stop creating a brand-new specialized agent per task** (good for generic automation, bad for learning *one consistent orchestrator*).

Instead:

* Create one persistent OpenClaw agent: **`OrchestratorAgent`**
* It uses your stable skill pack + tool contracts
* For each Mission Control task, it receives:

  * observation snapshot
  * the planned orchestrator action (or asks planning questions)
  * governance constraints

The policy can evolve over time, but the “agent identity” stays consistent — which is what you want for training.

### 5) Governing execution harness → split responsibility

You want governance in **two places**:

* **OpenClaw side (hard safety):** command allowlists, sandboxing, protected paths
* **Mission Control side (human gates):** approvals to move from IN PROGRESS → TESTING → REVIEW → DONE 

Mission Control is perfect for “approval workflow” because it already models the task lifecycle.

---

## How to adapt Mission Control so it trains the orchestrator (the key upgrades)

### Upgrade A: Make Planning output a *structured orchestrator action*

Mission Control’s “AI planning Q&A” is already there. 
Right now, it likely outputs a plan in natural language.

Change the planner’s output to your schema:

* `mode`
* `goal`
* `scope.paths / scope.avoid`
* `constraints_in_force`
* `gates`
* `risk`
* `executor_instruction` (what to tell Claude Code)

Now “planning” becomes the **explicit action** in your (Observation → Action → Outcome/Reaction) episode. 

### Upgrade B: Make REVIEW capture reaction labels explicitly

Instead of you writing “looks good” in free text, REVIEW should ask you:

* Approve / Correct / Redirect / Block / Question
* Optional comment
* If Correct/Block: “Extract a constraint?” (yes/no + text)

That turns your feedback into a clean supervised signal and a constraint store, exactly as your turn‑level approach argues is necessary. 

### Upgrade C: Record *tool provenance* through OpenClaw Gateway

Mission Control already connects to OpenClaw Gateway via WebSockets and proxies endpoints. 
Use that connection to store, per task/episode:

* tool calls made
* files touched
* commands run
* test results
* commit hashes created

This becomes your automatic episode “Outcome” section.

---

## The most important “blind spot” to avoid

Mission Control’s default concept is:

> “Create a task → create a specialized agent → dispatch.”

That is great for task completion.
But your goal is different:

> “Train one agent to replace the human orchestrator.”

So you should shift to:

* **One persistent OrchestratorAgent**
* Many tasks as training episodes
* Planning+review as the labeled supervision stream

Otherwise you’ll end up with fragmented behavior and no consistent policy to train.

---

## What I’d build first inside Mission Control (smallest useful increment)

1. Add fields to Task:

   * `mode`, `risk`, `scope`, `gates`, `constraints`
2. Add a new table: `episodes`
3. Add a simple REVIEW widget:

   * reaction label + optional constraint extraction
4. Modify dispatch:

   * send a single structured “orchestrator action” payload to OpenClaw (not just prose)
5. Save tool provenance streamed back from OpenClaw into the episode

That gives you a working loop:

**Task → Planned orchestrator_action → OpenClaw executes → Mission Control logs outcome → You label reaction → Episode stored**

Which is literally the training pipeline you outlined, but operationalized. 

---

If you want, paste (or upload) the Mission Control API route files under `src/app/api/` (especially the OpenClaw proxy endpoints). I can then propose the exact API payload shapes and database tables so Mission Control becomes a first-class “Episode Builder + Orchestrator Trainer” rather than only a task dashboard.
