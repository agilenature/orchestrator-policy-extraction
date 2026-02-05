Let’s name the *thing you’re actually doing* by anchoring it to the observable facts you already have:

* A **human orchestrator** (you) makes *sequencing decisions* (what to ask, when to inspect, when to refactor, when to commit, when to stop).
* An **AI coding system** (Claude Code) executes/assists (reads code, proposes edits, runs commands, drafts plans).
* You have **objective traces** of that joint activity: Git commits + diffs + timestamps, and Claude Code session logs (JSONL transcripts / tool calls). 

From there, the “type of problem” falls into a small set of well-known genera.

## 1) The genus: Sequential decision-making in human–AI collaboration

**Genus proximum (closest category):** *Human–AI teaming / human-in-the-loop agent orchestration* — i.e., designing and analyzing how control and authority are distributed between a human and an AI system over time. This is explicitly discussed as “interaction paradigms” and “level of automation” in human–AI team research. ([National Academies][1])

**Differentia (what makes your case specific):**

* The interaction isn’t just chat. It’s **tool-mediated software work** with durable artifacts (commits, branches, tests).
* You want not merely to *study* the interaction, but to **abstract the human orchestrator into an agent** (OpenClaw or similar) that can reproduce the orchestration behavior.

So your problem is not “code migration” per se. It’s:

> **Learning (and governing) an orchestration policy from human–AI interaction traces.**

A compact label you can use:

### **Orchestrator Policy Learning (OPL)**

(also describable as **Human–AI Workflow Mining**)

## 2) Sweeping the territory: opposites and the “eclectic” middle

This helps prevent floating abstractions (“automation”, “agents”) that hide real differences.

### Pole A: Fully manual orchestration

You do everything: plan, prompt, verify, run commands, commit.
AI is essentially a *calculator with prose*.

### Pole B: Fully autonomous orchestration

Agent decides goals/subgoals, runs tools, commits, opens PRs.
Human only audits outcomes.

### The eclectic middle (where most successful systems land)

**Mixed-initiative orchestration**:

* Human sets goals + constraints + acceptance criteria.
* Agent proposes next actions and executes low-risk steps.
* Human gates high-risk steps (large refactors, schema changes, releases).

That middle is not “half automation” in a vague sense; it’s a *division of cognitive labor* guided by risk and context. This aligns with human–AI interaction guidance work that emphasizes appropriate timing, controllability, and expectation management. ([Microsoft][2])

## 3) What problem family does it belong to?

You can legitimately place your work in **three overlapping problem families** (each has established solution types):

### A) Mining Software Repositories + process discovery

You are correlating:

* version control history (commits/diffs)
* conversational/tool-use logs

That’s squarely in the spirit of **Mining Software Repositories (MSR)**: extracting actionable knowledge from software-repository data. ([2018.msrconf.org][3])

When you treat your Claude/Git traces as an **event log** and try to discover “what process is actually being followed,” that’s classic **process mining** (process discovery + conformance checking). ([apromore.com][4])

**Name for this slice:** *Human–AI Dev Process Mining.*

### B) Human–AI collaboration analysis (HCI/SE)

There’s growing research explicitly about how developers collaborate with AI assistants and what interaction modes emerge. ([ACM Digital Library][5])

**Name for this slice:** *Human–AI Collaboration in Software Engineering.*

### C) Learning from demonstrations (policy learning)

If your endgame is: “Given a situation like X, the orchestrator usually does Y next,” you are describing **imitation learning / learning from demonstrations**: learning a policy from expert traces. ([underactuated.mit.edu][6])
And if you later let the agent act, then correct it on the states it actually visits, you’re in the territory of algorithms like **DAgger** (dataset aggregation) to reduce “drift.” ([CMU School of Computer Science][7])

**Name for this slice:** *Orchestrator Imitation Learning.*

## 4) What solutions exist?

Here are the solution “bins” that map cleanly to your goal (replacing yourself, gradually, with an orchestrator agent).

### Solution bin 1: Make the interaction legible (instrumentation + alignment)

Before “learning,” you need a coherent timeline.

What you already have (or can standardize):

* Claude Code conversation logs stored locally as JSONL under `~/.claude/projects/` (and an index file exists in `~/.claude/history.jsonl` per some reports). ([Uncommon Stack][8])
* Git history is your ground-truth artifact stream.
* Tools like **cchistory** exist to extract executed commands from Claude Code logs into a shell-history-like stream. ([GitHub][9])
* Claude Code can add/adjust commit attribution trailers (e.g., `Co-Authored-By`) and this is configurable. ([Claude Code][10])

**Practical alignment trick (high leverage):**

* Stamp a **session-id** (or orchestrator “case id”) into commits/PRs (trailer or branch naming), so correlation is not guesswork-by-time-window.

This is the foundation for everything else. Without it, you’ll build stories, not models.

### Solution bin 2: Process mining the workflow (discover the playbook you already follow)

Treat each modernization “phase” or “task” as a **case** and events as:

* prompt issued
* AI response type (explain / plan / patch / refactor)
* tool call (grep, test, build, format)
* diff size
* tests pass/fail
* commit

Then do:

* **Process discovery:** “What paths happen repeatedly?”
* **Conformance checking:** “When do we deviate, and why?” ([apromore.com][4])

Output: a **playbook** that is *descriptive* (what you do) before it’s *prescriptive* (what an agent should do).

This often beats jumping straight to ML, because it forces you to define:

* states
* transitions
* acceptance criteria

### Solution bin 3: Codify orchestration as a rules+templates system (fastest path to delegation)

This is the “engineering” approach:

* If repo state is *unknown*: first run inventory scans.
* If tests failing: triage loop.
* If migration phase N: generate mapping tables + test harness first.

It’s not glamorous, but it’s controllable, debuggable, and safe.

A lot of “agent orchestration” succeeds by being **a constrained decision tree with good retrieval**, not by being a mysterious learned policy.

### Solution bin 4: Retrieval-based orchestrator (RAG over your own traces)

Instead of “train a model,” you:

1. Index prior sessions (prompts, tool calls, diffs, outcomes).
2. At runtime, retrieve the top-k similar situations.
3. Ask the LLM/agent to propose next steps consistent with the retrieved exemplars.

This yields something very close to “your style” without requiring immediate fine-tuning. It’s also audit-friendly: you can show *which prior episodes* justified an action.

### Solution bin 5: Imitation learning / supervised fine-tuning on orchestration traces

When you *do* want an agent that behaves like you, you can frame it as:

* **Observation/state:** repo metadata, current diff, failing tests, phase label, last N turns, open TODO list
* **Action:** next instruction to Claude Code / next tool call / next gating decision
* **Reward proxy:** tests green, smaller rework rate, fewer “quick remedy commits,” shorter time-to-merge, etc.

Start with **behavior cloning** (supervised learning on state→action). ([NVIDIA][11])
Then mitigate drift with an interactive correction scheme (DAgger-style) where the agent acts and you label the “right move” on the states it encountered. ([CMU School of Computer Science][7])

### Solution bin 6: Governance and safety controls (especially if OpenClaw is the orchestrator)

Because the orchestrator will have the power to run commands, touch secrets, and push commits, your “solution” is incomplete without authority boundaries.

OpenClaw specifically has had **very recent, widely reported security concerns** tied to third‑party “skills”/extensions and the risks of giving an agent broad device permissions. ([Reuters][12])

Concrete controls consistent with your goal (business-grade modernization pipelines):

* run orchestration in **sandboxed worktrees/containers**
* **no secrets** in the agent’s readable filesystem by default
* explicit allowlists for commands
* mandatory PR review gates for high-impact diffs
* immutable audit logs (conversation + tool calls + commit mapping)

This is not “paranoia”; it’s the practical consequence of giving an acting system causal power in your environment.

## 5) Keeping the levels clean (metaphysics → epistemology → ethics → politics)

This is the anti-confusion checklist:

* **Metaphysics (what exists):** transcripts, tool calls, diffs, commits, test results.
* **Epistemology (how you know):** induction over repeated episodes; correlation is not causation unless you anchor it with IDs and state snapshots.
* **Ethics (what you’re optimizing):** speed vs correctness vs auditability vs risk. You can’t “learn the orchestrator” without specifying what counts as success for *your life and work* (e.g., reliable modernization that transfers to COBOL-scale constraints).
* **Politics (authority boundaries):** who/what is allowed to run commands, access repos, push changes, touch credentials.

If you don’t separate these, “agentic orchestration” collapses into floating slogans.

## A crisp way to say it in one line

If someone asks you what you’re building, a precise answer is:

> “I’m doing **human–AI dev process mining** to extract and then automate an **orchestration policy** (mixed-initiative at first, increasingly autonomous) for legacy modernization.”

If you want, I can also turn this into:

* a **formal problem statement** (state/action/reward, datasets, evaluation metrics), and/or
* a **reference architecture** for “Claude Code execution + orchestrator agent + audit trail + safety gates” using the exact artifacts you already have (JSONL + git).

- [Reuters](https://www.reuters.com/world/china/china-warns-security-risks-linked-openclaw-open-source-ai-agent-2026-02-05/?utm_source=chatgpt.com)
- [The Verge](https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare?utm_source=chatgpt.com)
- [Business Insider](https://www.businessinsider.com/openclaw-moltbot-china-internet-alibaba-bytedance-tencent-rednote-ai-agent-2026-2?utm_source=chatgpt.com)
- [The Wall Street Journal](https://www.wsj.com/tech/ai/openclaw-ai-agents-moltbook-social-network-5b79ad65?utm_source=chatgpt.com)
- [techradar.com](https://www.techradar.com/pro/moltbot-is-now-openclaw-but-watch-out-malicious-skills-are-still-trying-to-trick-victims-into-spreading-malware?utm_source=chatgpt.com)

[1]: https://www.nationalacademies.org/read/26355/chapter/8?utm_source=chatgpt.com "Chapter: 6 Human-AI Team Interaction"
[2]: https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/articles/how-to-build-effective-human-ai-interaction-considerations-for-machine-learning-and-software-engineering/?utm_source=chatgpt.com "How to build effective human-AI interaction"
[3]: https://2018.msrconf.org/?utm_source=chatgpt.com "MSR 2018 - Mining Software Repositories"
[4]: https://apromore.com/process-mining-101?utm_source=chatgpt.com "Process Mining 101"
[5]: https://dl.acm.org/doi/10.1145/3643690.3648236?utm_source=chatgpt.com "Human-AI Collaboration in Software Engineering"
[6]: https://underactuated.mit.edu/imitation.html?utm_source=chatgpt.com "Ch. 21 - Imitation Learning - Underactuated Robotics"
[7]: https://www.cs.cmu.edu/~sross1/publications/Ross-AIStats11-NoRegret.pdf?utm_source=chatgpt.com "A Reduction of Imitation Learning and Structured Prediction to ..."
[8]: https://kentgigger.com/posts/claude-code-conversation-history?utm_source=chatgpt.com "Claude Code's hidden conversation history (and how to ..."
[9]: https://github.com/eckardt/cchistory?utm_source=chatgpt.com "eckardt/cchistory: Like the shell history command ..."
[10]: https://code.claude.com/docs/en/settings?utm_source=chatgpt.com "Claude Code settings - Claude Code Docs"
[11]: https://www.nvidia.com/en-us/glossary/imitation-learning/?utm_source=chatgpt.com "What is Imitation Learning? | NVIDIA Glossary"
[12]: https://www.reuters.com/world/china/china-warns-security-risks-linked-openclaw-open-source-ai-agent-2026-02-05/?utm_source=chatgpt.com "China warns of security risks linked to OpenClaw open-source AI agent"




