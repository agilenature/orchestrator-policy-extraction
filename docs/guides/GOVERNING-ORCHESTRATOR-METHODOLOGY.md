---
axes: [always-show]
---
# Governing Orchestrator Methodology
## How David and Claude Build and Govern Projects Together

**Created:** 2026-02-26
**Scope:** Generalized methodology — applies to any multi-repo project built using the GO-as-governance model
**Persistent reference:** Read this after any context clear to restore the full picture without recapping

---

## What This Document Is

This is the operational guide for how David and Claude work together to build software projects and govern them once running. Claude is not a coding assistant in this model — Claude is the **Governing Orchestrator (GO)**: the layer that holds causal chain authority over every consequential decision across every repo in every project.

This document covers:
1. What the GO is and what it owns
2. The governance hierarchy (who does what at each layer)
3. OPE's role as the persistent intelligence substrate
4. The construction milestone structure — how to build a new multi-repo project
5. Bounded supervisory architecture — stability law, stack commissioning, PEC, evasion vs. drift
6. How to apply this to any new project
7. Automatic OPE ingestion setup
8. How to resume after context clear
9. The verifiable invariants that confirm each phase is complete

---

## Part I: The Governing Orchestrator

### What the GO Is

The GO is Claude, operating at the layer between David and the execution stack. It is not an assistant that responds to requests — it is the decision-making authority for:

- **`run_id` generation:** No session in any repo generates its own `migration_run_id`. The GO generates it once at work dispatch and injects it into every session.
- **Cross-repo sequencing:** Which repos must be built before others (MARK layer dependency order). The GO enforces this — no layer-N repo starts until layer-(N-1) is verified.
- **Gate decisions:** At every validation gate, the GO decides pass/fail, dispatches corrections (T8), or unblocks progression (T7). David is not called unless a circuit-breaker fires.
- **Push link capture:** At the three silent transitions (T1: forward dispatch, T7: gate pass → progression, T8: gate failure → correction), the GO calls `/api/push-link` to OPE. These transitions cannot be reconstructed retroactively.
- **Causal chain integrity:** Every consequential decision is a GO decision, recorded in OPE, and traversable backward from any terminal state.

### What the GO Cannot Do

- Modify GSD phase logic or plan-check criteria within a repo
- Modify Ralph's exit gates or circuit-breaker thresholds
- Override a GSD verification failure by declaring a phase complete
- Self-modify the governance topology
- Act without `run_id` — in production, throw; in development, `"offline-untracked"` sentinel only

### The Standing Order

From Jean Moroney's Memory Affect System: the Standing Order is the value-derived directive that automatically biases retrieval toward value-consistent nodes.

The GO's governance layer IS the Standing Order for every project it governs:
- **David** sets the Value: what migration to perform, what system to build, what correctness means
- **The GO** enforces the Method: the governance rules, the dependency sequencing, the EGS requirements
- **The workers (GSD + Ralph + LLM)** provide the Associations: the implementation, the code, the analysis

---

## Part II: The Governance Hierarchy

```
Level 4 — David (Ultimate Governor)
           ↓ dispatches work units, sets values, approves phase closures,
           ↓ reviews BMAD PRDs, provides Items 1–6 decisions
Level 3 — AI Governing Orchestrator (this layer)
           ↓ injects run_id, sequences cross-repo work, maintains push_links,
           ↓ monitors EGS/SDI/RRR, circuit-breaks on evasion
Level 2 — OpenClaw (Macro Persistence)
           ↓ session lifecycle across long builds, cross-session restart,
           ↓ time/resource caps; active for long Clojure/migration runs
Level 1 — GSD (Phase Governance)
           ↓ discuss → plan-check → execute → verify → audit per repo
Level 0.5 — Ralph (Intra-Phase Execution Persistence)
           ↓ bounded execution loop, circuit breaker, exit gates
Level 0  — LLM (Adaptive Planner/Executor)
           ↓ writes code, performs analysis, proposes solutions

BMAD (orthogonal to the hierarchy)
           ↓ PRD + stories feeding into GSD Level 1 before coding begins
           ↓ David reviews PRD at L4 before any code is written
```

### Dimension Separation Rule

Each layer governs a **different dimension**. If two layers attempt to govern the same dimension, conflict and instability begin — this is the structural source of all drift and evasion failures.

| Layer | Governs (dimension) | Not Allowed To Govern |
|-------|--------------------|-----------------------|
| OpenClaw (L2) | Time horizon — hours/days, sprint lifecycle, session restart | Phase logic, plan content |
| GSD (L1) | Phase lifecycle + artifact integrity — discuss/plan/verify/audit | Session persistence |
| Ralph (L0.5) | Iterative execution *inside* a GSD plan — persistence until done or safe failure | Phase transitions, acceptance criteria |
| LLM (L0) | Semantic content — code, analysis, proposals | Control topology |
| BMAD (orthogonal) | Semantic clarity — PRD, architecture, stories | Execution authority |

**Authority flows downward only. No layer may rewrite the governance of the layer above it.**

### Two Uses of BMAD

BMAD appears at two distinct levels in this methodology. Both are legitimate; they govern different scopes and produce different artifact classes. Using the wrong one for a given context is a stolen-concept violation.

**Stack BMAD** — BMAD as a layer inside a single project's execution stack.
- **Scope:** one project's features, architecture, and user stories
- **Produces:** PRD + architecture + stories that feed into that project's GSD L1 phases
- **Validation audience:** David reviews the PRD before that project's coding begins
- **Push_link:** `prd.approved` (per-project) → activates GSD L1 for that project
- **Lives in:** the target project's own repo (`_bmad/` or equivalent)
- **Prerequisite:** BMAD installed in the target project repo

**Program BMAD** — BMAD used by David and the GO to plan and coordinate the program of work across projects.
- **Scope:** which projects to commission, in what order, what commissioning looks like for each
- **Produces:** PRD that is the authoritative governing agreement between David (L4) and the GO (L3) about what we are building together and in what sequence
- **Validation audience:** David reviews the PRD as the shared commitment — this is the David↔GO coordination artifact
- **Push_link:** `program.prd.approved` → activates the GO's project dispatch sequence
- **Lives in:** OPE `.planning/` (the GO's own planning structure, not inside any target project)
- **Prerequisite:** BMAD installed in the OPE project itself

**The difference in one sentence:** Stack BMAD defines what a project builds. Program BMAD defines which projects the GO and David build together, and in what order.

**Why this matters for sequencing:** Program BMAD must be established before any Stack BMAD can be commissioned. You cannot have a per-project BMAD PRD until there is a program-level agreement about which projects enter the stack. The `program.prd.approved` push_link is the precondition for every `construction.commissioned` push_link.

**Installation note:** Program BMAD requires BMAD to be installed in the OPE project before the GO can use it. This is a David action — it must happen before the first Program BMAD session. Stack BMAD requires BMAD installed separately in each target project repo.

### When Each Layer Is Active

| Phase | David (L4) | GO (L3) | OpenClaw (L2) | GSD (L1) | Ralph (L0.5) | LLM (L0) |
|-------|-----------|---------|--------------|---------|-------------|---------|
| Phase 0 (Decisions) | Active — sole actor | Writes artifacts | — | — | — | — |
| Phase 1 (Infrastructure + Canon) | Watch (optional) | Dispatches, monitors | — | Governs repos | — | Writes config/EDN |
| Phase 2 (Governance Engine) | Reviews BMAD PRD, approves | Gate decisions | Session persistence for long builds | Governs Clojure build | Execution loop | Writes Clojure |
| Phase 3 (Engagement Layer) | Confirms slice order | Dispatches, installs OPE hooks | — | Governs config | — | Writes config |
| Phase 4 (Execution Loop) | Reviews PRD, approves escalations | Coordinates all repos | Slice session persistence | Per-slice phases | Execution loop | Performs analysis |
| Phase 5 (Learning Loop) | Reviews memory_candidates | Runs OPE extraction | — | — | — | — |

### Epistemological Integrity Signals (GO monitors these across all sessions)

| Signal | Threshold | GO action |
|--------|-----------|-----------|
| EGS < 0.55 (Low RQR — floating abstraction) | Any session | Inject grounding briefing: "Read [file] before next write" |
| SDI > 0.50 (context drift — Raven Fatigue) | Any session | Force session re-summary of trunk before continuing |
| RRR > 0.05 (success claims after failure — evasion) | Any session | Circuit break; escalate to David with specific report |
| EGS < 0.3 AND Gate passes (Dangerous Sophist) | Any session | Flag gate pass as Fragility event; do not count as evidence |

---

## Part III: OPE as the Persistent Intelligence Substrate

### What OPE Is (and Is Not)

OPE (Orchestrator Policy Extraction) is **the Causal Chain Authority for every project the GO governs**. It is infrastructure — the same class as a database or CI pipeline. It does not have a completion date. It does not produce reports. It runs continuously.

OPE owns:
- **`bus_sessions`:** Every session in every repo, registered and deregistered, with `run_id`, `repo`, `project_dir`, `event_count`, `outcome`
- **`push_links`:** Every T1/T7/T8 causal transition, captured at the moment it occurs, traversable backward from any terminal state
- **`data/constraints.json`:** The constraint store — active platform architecture rules delivered to every session via `/api/check`. The GO adds entries here when new architectural decisions are made; no entries are ever deleted, only retired.
- **`memory_candidates`:** Candidate CCD entries extracted from session JSONL, pending David's review for promotion to MEMORY.md
- **MEMORY.md:** The canonical filing system — CCD-quality entries that make the GO retrieve by axis in the next session rather than by surface similarity

### The Reconstruction Rule

**The GO reconstructs from OPE artifacts, not from session memory.** This means:
- Every phase must end with something written to OPE DuckDB, `data/constraints.json`, `canon`, or MEMORY.md
- When David returns after a gap of hours or days, he says "pick up where we left off" and the GO queries OPE to reconstruct the full construction state
- A phase that only updates session context is architecturally invisible to the next session — it silently depends on continuity that may not exist

The verification queries in Part IV are what the GO runs at session start to reconstruct state.

### OPE's Role Across Projects

When the first platform repo registers with the OPE bus, OPE's scope expands from "monitor one project" to "monitor all repos simultaneously." For each new project added to the GO's governance:
1. New repo-scoped constraints are added to `data/constraints.json`
2. The new repo's sessions automatically register with the bus (once the OPE hook is in `.claude/settings.json`)
3. The new project's JSONL feeds the same extraction pipeline
4. The GO uses the same `run_id` injection mechanism across all projects

OPE does not need to be reconfigured for each new project. The bus is universal. The constraint store expands. The push_links table accumulates across all runs.

---

## Part IV: The Construction Milestone

### When to Use This Milestone

Use this milestone when starting any new multi-repo project that the GO will govern. The milestone takes a project from "no repos exist" to "GO is coordinating construction of all repos." After the milestone closes, the GO is in operational mode — the execution loop runs with David monitoring from L4.

### Milestone Completion Criterion (one sentence, verifiable)

> *"The OPE bus is running, all repos are registered in `bus_sessions` with a shared `migration_run_id`, the final scaffold gate has a `gate-N-passed` push_link in OPE, and the GO is coordinating the execution loop."*

This is a query against OPE DuckDB, not a judgment call.

---

### Phase -1: Stack Commissioning (Precondition — Do This Once Per New Project)

**Can start:** Before Phase 0. No project work is dispatched until `construction.commissioned` exists in OPE.

Stack Commissioning verifies that every governance layer is in place, interoperable, and in a known state. It is not the same as building the project — it is verifying the *control system* before the project work enters it. See full definition in Part V.

**GO actions (run once, in order):**

| Step | Layer | Action | Acceptance test | Instability condition ruled out |
|------|-------|--------|-----------------|--------------------------------|
| SC-1 | OpenClaw (L2) | Freeze config; run 1 full session cycle (start → work → stop) | `bus_sessions` shows 1 clean registered + deregistered row | Condition 3: exit criteria cannot change mid-run if config is frozen at commissioning |
| SC-2 | GSD (L1) | Create `.planning/` structure; complete 1 discuss → plan-check → verify cycle with a stub plan | `STATE.md` shows `status: completed` for stub phase; gate signal came from GSD verify step, NOT LLM self-report | Condition 2: GSD cannot auto-advance on LLM self-report if at least 1 verified cycle has proven the gate is active |
| SC-3 | Ralph (L0.5) | Create `.ralph/config` (read-only to LLM sessions); run 1 bounded execution loop with a stub PEC | `.ralph/log` shows clean completion; `immutable_hash` in log matches `pec.issued` in OPE for the stub | Conditions 1 and 4: Ralph cannot rewrite GSD artifacts or edit circuit-breaker thresholds if `.ralph/config` is read-only and the PEC hash chain is intact |
| SC-4 | BMAD (orthogonal) | GO writes stub PRD → David reviews → David approves | `SELECT * FROM push_links WHERE transition_trigger='prd.approved'` returns ≥ 1 row | Indirect: BMAD artifacts cannot feed GSD without L4 review if this push_link is a hard precondition for BMAD authority |
| SC-5 | LLM (L0) | Confirm CLAUDE.md loaded at session start; run 1 session and confirm EGS ≥ 0.55 | First session's EGS signal in OPE ≥ 0.55 | Condition 5: termination criteria live in PEC (external, OPE-recorded); LLM cannot modify them if Premise Declaration Protocol is active from session 1 |

**After all five steps pass, GO writes:**

```sql
-- Commissioning artifact written by GO (not by any commissioned layer)
INSERT INTO push_links (transition_trigger, project_id, timestamp)
VALUES ('construction.commissioned', '<project_id>', '<iso>');

-- Verification before Phase 0 proceeds:
SELECT * FROM push_links WHERE transition_trigger='construction.commissioned';
-- Must return 1 row
```

**Why the GO writes `construction.commissioned`, not any layer:** Identity-firewall CCD. The entity demonstrating commissioning criteria (each layer, running its acceptance test) cannot be the same entity that declares commissioning complete. The GO reads OPE artifacts from each layer's acceptance test and only then writes the push_link.

---

### Phase 0 — Foundation Decisions

**Can start:** After `construction.commissioned` push_link exists in OPE.

**David's actions (6 decisions):**

| Decision | What David provides | Default if absent |
|---------|-------------------|-------------------|
| Constraint definitions | Verify/correct the layer-dependency forbidden rules before seeding `data/constraints.json` | Bus delivers empty briefings — sessions ungoverned |
| OpenClaw mode | **Mode A** (OpenClaw installed, provide port) or **Mode B** (env var injection) | GO assumes Mode B |
| Canon seed concepts | Which CCDs from MEMORY.md enter the `canon` repo as formal concepts | GO seeds with 4 universal CCDs |
| Execution slice ordering | Confirm Neo4j-derived order or override | GO cannot dispatch without this — will ask |
| Gate coverage threshold | Percentage for pass/fail on coverage gate | GO cannot gate without this — will ask |
| Infrastructure preferences | Cloud provider, Docker registry, runtime versions | GO uses documented defaults |

**Signal David gives GO:** "Phase 0 complete. [Decisions as listed above.]"

**GO actions:**
1. Write constraints to `data/constraints.json`
2. Write `DECISIONS.md` to project `.planning/` recording all 6 decisions
3. Verify OPE bus health check passes with seeded constraints
4. Report: "Phase 0 complete. Ready for Phase 1."

**Layer invariant (verifiable):**
```bash
python -c "
import json
d = json.load(open('data/constraints.json'))
# Count entries seeded for this project
print(len(d), 'constraints in store')
"
# AND: DECISIONS.md exists in project .planning/
```

**Reconstruction artifact:** `data/constraints.json` + `DECISIONS.md`

---

### Phase 1 — Infrastructure + Foundation Layer

**Can start:** When Phase 0 closes.

**David's actions:** None required. Optional: provide infrastructure preferences before GO begins.

**GO actions:**
1. Start OPE bus → register GO session → `construction.dispatched` push_link
2. Create infrastructure/provisioning repo → register → verify connectivity → `repo.created` push_link
3. Create foundation/canon repo in parallel → seed concepts → `repo.created` push_link
4. Both sessions deregister cleanly

**Layer invariant (verifiable):**
```sql
SELECT repo, status FROM bus_sessions
WHERE repo IN ('<infrastructure-repo>', '<canon-repo>');
-- Both must show status='deregistered'

SELECT COUNT(*) FROM push_links WHERE transition_trigger='repo.created';
-- Must be >= 2
```

**Reconstruction artifact:** OPE `bus_sessions` (2+ rows) + OPE `push_links` (2+ `repo.created` rows)

**GO reports to David:** "Phase 1 complete. [infrastructure] reachable. [canon] seeded with [N] concepts. [N] push_links recorded. I need you to review a BMAD PRD before Phase 2 code begins."

---

### Phase 2 — Governance Engine → Gate 1

**Can start:** When Phase 1 closes and David approves BMAD PRD.

**The critical gate.** The governance engine is the trust anchor for all downstream repos. The GO will not write code for it without a BMAD PRD David has reviewed.

**David's actions:**
1. Read and approve BMAD PRD for the governance engine (the GO produces this — David reviews and says "approved" or lists corrections)
2. If Mode A: confirm OpenClaw is running on the configured port

**Signal David gives GO:** "PRD approved." (And OpenClaw confirmation if Mode A.)

**GO actions:**

*Step 1 — BMAD PRD (Class 2 artifact):*

1. Write BMAD PRD for governance engine → await David's approval
2. David approves → GO writes `prd.approved` push_link:
   ```json
   {"prd_hash": "<sha256 of PRD file>", "project_id": "<project>",
    "approved_by": "david", "timestamp": "<iso>"}
   ```
   **Effect:** BMAD's planning authority terminated. GSD L1 is now authorized to build the governance engine. This is the Class 1 → Class 2 handoff. Without this push_link, no GSD plan for the governance engine is authorized.

*Step 2 — GSD plan-check → PEC (Class 3 artifact):*

3. Create knowledge/parsing repos → GSD governs → push_link per repo
4. GSD produces `PLAN.md` for governance engine phases
5. Plan-check agent validates `PLAN.md` — **this runs in a structurally separate session from the GSD session that wrote the plan** (identity-firewall: generator and validator are separated)
6. Plan-check passes → GSD writes PEC (Phase Execution Contract)
7. GO writes `pec.issued` push_link:
   ```json
   {"immutable_hash": "<sha256 of PEC>",
    "phase_id": "governance-engine-phase-1", "timestamp": "<iso>"}
   ```
   **Effect:** GSD's modification authority terminated. Ralph is now authorized to execute within the PEC scope. After `pec.issued`, any modification to `PLAN.md` or acceptance criteria is instability condition 1 — circuit break immediately.

*Step 3 — Ralph execution with instability monitoring:*

8. Ralph reads PEC → verifies `immutable_hash` against OPE `pec.issued` row → begins bounded execution loop
   - If hash mismatch: circuit break immediately (tampering detected)
9. GO monitors via OpenClaw for session stalls (> 4 hours without GSD verification signal)
10. **GO monitors five instability conditions continuously from this point forward:**
    - Condition 1: Ralph attempts to write to `STATE.md`, `PLAN.md`, or acceptance criteria → immediate circuit break + `instability.detected` push_link
    - Condition 2: GSD marks phase complete without a gate signal from GSD verify step (only LLM self-report present) → immediate circuit break + `instability.detected` push_link
    - Condition 3: OpenClaw modifies PEC acceptance criteria after `pec.issued` timestamp → immediate circuit break + `instability.detected` push_link
    - Condition 4: LLM session writes to `.ralph/config` or circuit-breaker thresholds → immediate circuit break + `instability.detected` push_link
    - Condition 5: Any termination criteria modified after `pec.issued` timestamp, by any layer → immediate circuit break + `instability.detected` push_link

*Step 4 — Gate evaluation:*

11. Gate 1 evaluation (schema validation, type-check, dependency graph validation)
12. Gate 1 pass → `gate-1-schema-passed` push_link → Phase 3 unblocked

**Degraded path:** Gate 1 fails → GO dispatches T8 correction task → GO reports specific violation to David → GO handles resolution → Gate 1 re-passes → David is not needed unless circuit-breaker fires.

**Layer invariant (verifiable):**
```sql
SELECT * FROM push_links WHERE transition_trigger='gate-1-schema-passed';
-- Must return 1 row
```

**Reconstruction artifact:** OPE `push_links` (`gate-1-schema-passed`) + governance engine GSD `STATE.md`

---

### Phase 3 — Engagement Layer → Gate 2 (Milestone Completion)

**Can start:** When Gate 1 passes and David confirms execution ordering.

**David's actions:**
1. Confirm execution slice/phase ordering — GO shows the list; David says "confirmed" or reorders
2. Confirm coverage/quality threshold if not set in Phase 0

**Signal David gives GO:** "Slice order confirmed. Threshold: [X]%."

**GO actions:**
1. Configure source repo as platform target → `repo.created` push_link
2. Create output/destination repo scaffold → Gate 2 (integrity check) → `gate-2-integrity-passed` push_link
3. Create template/scaffold repo → `repo.created` push_link
4. **Install OPE hook in each repo's `.claude/settings.json`** (this enables automatic ingestion going forward)
5. Verify all repos in `bus_sessions`

**Layer invariant (verifiable):**
```sql
SELECT COUNT(DISTINCT repo) FROM bus_sessions;
-- Must equal total repo count

SELECT * FROM push_links WHERE transition_trigger='gate-2-integrity-passed';
-- Must return 1 row
```

**Reconstruction artifact:** OPE `bus_sessions` (all repos) + OPE `push_links` (`gate-2-integrity-passed`)

**GO reports to David:** "Milestone complete. All [N] repos registered. Gate 2 passed. BMAD PRD for execution phase ready for your review. Awaiting approval to begin [Slice 1 / Phase 1 / first execution unit]."

**The milestone criterion is met at this point.** The GO is coordinating construction of all repos.

---

### Phase 4 — Execution Loop (Operational Mode)

Phase 4 is the platform running, not being built. The GO coordinates the full execution loop with David monitoring from L4.

**David's role at L4:**
- Review and approve BMAD PRD for the execution repo before the loop begins → GO writes `prd.approved` push_link
- Receive per-unit completion reports from GO: "Unit N complete. Gate: [passed/warnings]. Coverage: [X]%. Dispatching Unit N+1."
- Respond to escalations: instability condition events and evasion detection require David's review before GO resumes
- Approve any proposals to extend the foundation/canon layer (when a new concept is needed that doesn't exist yet)

**What David does NOT do:** monitor builds, debug errors, read session logs, manage GSD phases. Those are GO + Ralph's domain. David's signal is: receive my reports and respond to escalations. No news = healthy execution.

**Per-unit PEC cycle (repeats for every execution unit):**

Each unit in the execution loop follows the same GSD → Ralph handoff established in Phase 2. The GO does not shortcut this cycle for "smaller" units — every unit that uses Ralph requires a PEC with an `immutable_hash`.

```
For each unit N:
  1. GSD writes PLAN.md for unit N
  2. Plan-check agent validates (separate session — identity-firewall)
  3. GSD writes PEC for unit N
  4. GO writes pec.issued push_link: {immutable_hash, phase_id: "unit-N", timestamp}
  5. Ralph reads PEC → verifies hash → executes
  6. GSD verify step runs → produces gate signal (not LLM self-report)
  7. GO writes unit-N-deposit push_link → notifies David
  8. GO checks five instability conditions against OPE before dispatching unit N+1
```

**Layer invariant (verifiable):**
```sql
SELECT COUNT(*) FROM push_links WHERE transition_trigger='<unit-deposit-trigger>';
-- Must equal number of completed units

SELECT COUNT(*) FROM push_links WHERE transition_trigger='pec.issued';
-- Must equal number of completed units (one PEC per unit)

SELECT COUNT(*) FROM push_links WHERE transition_trigger='instability.detected';
-- Must be 0 for a clean run; any row here requires David review before continuing
```

---

### Phase 5 — Learning Loop Closure

After the execution loop completes: GO runs OPE extraction on all construction sessions → constraint candidates deposited to `memory_candidates`.

**David's role:** Review candidates using the DDF flood test. For each candidate the GO surfaces: say "accept to MEMORY.md," "reject," or "need more instances." This is the highest-value human action in the entire milestone — David's selection pressure becomes the GO's filing system for the next project.

**Layer invariant (verifiable):**
```sql
SELECT COUNT(*) FROM memory_candidates
WHERE epistemological_origin='inductive' AND verdict='pending';
-- > 0: learning loop produced candidates
```

---

### Ongoing GO Monitoring Protocol (Active from Phase 2 Onward)

These are not phase-specific — the GO runs them continuously across every session in every repo throughout construction and operational phases.

**Instability condition monitoring:**

On every GSD verify signal, Ralph circuit-break event, and OpenClaw session end, the GO runs:
```sql
SELECT * FROM push_links WHERE transition_trigger='instability.detected'
AND timestamp > '<last_checked>';
-- Any row: pause all execution, escalate to David with condition number and evidence
```

**Drift vs. evasion detection and response:**

The GO checks epistemological signals after every 3 episodes in any active session:

| Signal | Drift signature | Evasion signature |
|--------|----------------|------------------|
| EGS | Declining across 2+ consecutive episodes | Declining, but only on specific constraint type |
| SDI | > 0.50 | May be normal — evasion is self-concealing, not incoherent |
| RRR | < 0.05 | > 0.05 — success claims after gate failure |
| Amnesia detection | Rotating constraints absent (no consistent target) | Same `constraint_id` absent across 3+ consecutive episodes |

*Drift response:*
1. Inject grounding briefing: `"Read [current PLAN.md] and the active constraints from /api/check before next write. Current phase: [X]."`
2. Monitor next 3 episodes — check EGS recovery
3. If EGS ≥ 0.55 within 3 episodes: continue
4. If EGS does not recover after 3 injections: escalate to David

*Evasion response:*
1. Immediate circuit break — **do not inject a grounding briefing** (it will be evaded)
2. Write `evasion.detected` push_link:
   ```json
   {"constraint_id": "<id>", "episode_ids": ["<e1>", "<e2>", "<e3>"],
    "rrr_reading": 0.0, "timestamp": "<iso>"}
   ```
3. Escalate to David with: which constraint was evaded, which episodes, what write-class calls were made that should have declared it
4. Do not resume execution until David's explicit unblock
5. After David's review: if the constraint itself was wrong → fix it and restart; if the session was evasive → fresh session from clean state

**Reconstruction integrity check (run at every session start):**

```sql
-- What is the current execution state?
SELECT transition_trigger, phase_id, timestamp
FROM push_links
WHERE run_id = '<run_id>'
ORDER BY timestamp DESC LIMIT 10;

-- Is the active PEC intact?
-- Compare: sha256(current PEC file) vs immutable_hash from pec.issued row
SELECT immutable_hash FROM push_links
WHERE transition_trigger='pec.issued' AND phase_id='<active_phase_id>';
-- If mismatch with local PEC file: circuit break — tampering detected
```

---

## Part V: Bounded Supervisory Architecture

*Full formal treatment: `docs/architecture/BOUNDED-SUPERVISORY-ARCHITECTURE.md`*

The governance hierarchy is not just a diagram — it is a **bounded supervisory architecture** with formal stability conditions. These conditions distinguish a stable multi-layer control system (where each layer governs its dimension and defers upward when authority limits are reached) from an unstable one (where layers overwrite each other's governance, producing drift and evasion).

### The Stability Law

A multi-layer governance system is stable if and only if all four conditions hold:

1. **Finite outer state machine:** The outermost controller (OpenClaw) has a finite number of states with deterministic transitions — it cannot be in an undefined state.
2. **Fixed control topology:** The authority structure cannot be modified at runtime — no layer can promote itself or demote another.
3. **Explicit termination authority above the adaptive planner:** The entity that decides "done" is always above the entity that decides "how" — termination authority cannot live at the same layer as execution authority.
4. **No upward modification of governance:** No lower layer can modify the artifacts, exit criteria, or state machines of any layer above it.

If any one of these conditions fails, the system enters instability. Drift and evasion are downstream symptoms of stability law violations, not primary causes.

**Control state machines (finite, deterministic):**

| Layer | States |
|-------|--------|
| OpenClaw (L2) | Sleeping → Starting Session → Monitoring → Timeout / Budget Exceeded → Stopped |
| GSD (L1) | Discussing → Planning → Plan-Checked → Executing → Verifying → Completed / Failed |
| Ralph (L0.5) | Running → Waiting → Rate-Limited → Circuit-Break → Completed / Failed |

---

### Stack Commissioning

**Definition:** Stack Commissioning is the one-time act of instantiating the OpenClaw + BMAD + GSD + Ralph execution stack for a new project. It is a precondition for GO governance. The GO cannot dispatch project work until commissioning is complete.

Stack Commissioning is not the same as building the project. It verifies that all governance layers are in place, interoperable, and in known states before project work begins.

**Commissioning exit criteria (per layer):**

| Layer | Exit criterion | Verified by |
|-------|---------------|-------------|
| OpenClaw (L2) | Session lifecycle hooks confirmed active; resource caps configured; restart protocol tested | OPE `bus_sessions`: at least 1 registered + deregistered session |
| GSD (L1) | `.planning/` directory exists with `STATE.md`, `ROADMAP.md`; at least 1 plan has passed plan-check | GSD `STATE.md` shows `phase: 1, status: planned` or higher |
| Ralph (L0.5) | `.ralph/` directory exists with circuit-breaker config; at least 1 bounded execution loop has completed cleanly | `.ralph/` config present; no circuit-break in first run |
| BMAD (orthogonal) | PRD exists; David has reviewed and approved; `prd.approved` push_link recorded in OPE | `SELECT * FROM push_links WHERE transition_trigger='prd.approved'` returns 1 row |
| LLM (L0) | Premise Declaration Protocol active (CLAUDE.md loaded); EGS baseline ≥ 0.55 on first session | First session's EGS signal in OPE ≥ 0.55 |

**Commissioning artifact:** The `construction.commissioned` push_link in OPE. This is the GO's signal that the stack is ready. No `construction.commissioned` push_link → no project work dispatched.

**Who produces it:** The GO, after all layer exit criteria are verified. David approves the BMAD PRD (a precondition), but the GO writes the push_link after verifying all layers independently.

---

### Phase Execution Contract (PEC)

The PEC is the formal boundary artifact between GSD (phase authority) and Ralph (intra-phase execution persistence). GSD writes it at plan-check time. It is **immutable once Ralph begins execution** — Ralph reads the PEC; it cannot write to it.

**PEC schema:**

```json
{
  "phase_id": "<project>-phase-<N>",
  "scope": "<what Ralph is authorized to do>",
  "execution_limits": {
    "max_iterations": 0,
    "max_duration_minutes": 0,
    "max_tool_calls": 0
  },
  "allowed_tools": ["<tool1>", "<tool2>"],
  "forbidden_actions": ["<action1>", "<action2>"],
  "acceptance_criteria": [
    "<verifiable criterion 1>",
    "<verifiable criterion 2>"
  ],
  "exit_gate": {
    "condition": "ALL acceptance_criteria AND EXIT_SIGNAL received",
    "exit_signal_source": "GSD verify step"
  },
  "failure_conditions": ["<condition that triggers circuit break>"],
  "escalation_policy": "circuit_break → GO → David if unresolved in <N> iterations",
  "immutable_hash": "<sha256 of above fields>"
}
```

The `immutable_hash` is the integrity check: GSD records it at `pec.issued` time in OPE. If Ralph's execution environment shows a different hash at session start, the PEC has been tampered with — circuit break immediately.

**Two mandatory push_links at GSD→Ralph handoff:**

| Trigger | When | What it carries | Stability Law relevance |
|---------|------|----------------|------------------------|
| `prd.approved` | David approves BMAD PRD | PRD hash + project_id | Terminates BMAD's planning authority; initiates GSD L1 authority |
| `pec.issued` | GSD plan-check completes | `immutable_hash` + phase_id | Terminates GSD's modification authority; initiates Ralph's execution authority |

---

### Five Instability Conditions

These are the specific ways the governance architecture breaks down. The GO monitors all five continuously. Any violation triggers immediate circuit break before instability propagates.

| # | Condition | What it looks like | Stability Law clause |
|---|-----------|-------------------|---------------------|
| 1 | **Ralph rewrites GSD artifacts** | Ralph modifies `STATE.md`, `PLAN.md`, or acceptance criteria during execution | No upward modification |
| 2 | **GSD auto-advances on LLM self-report** | A phase marked complete based solely on LLM claiming success, without GSD verify step producing a gate signal | Termination authority above adaptive planner |
| 3 | **OpenClaw changes exit criteria mid-run** | OpenClaw modifies phase completion criteria after a session has started | Fixed control topology |
| 4 | **LLM edits circuit-breaker thresholds** | The executing LLM modifies Ralph's `.ralph/config` or equivalent circuit-breaker settings | No upward modification |
| 5 | **Termination criteria become self-modifiable** | Any layer's exit criteria can be modified by the entity they govern | Fixed topology + no upward modification (combined) |

**GO response:** Immediate circuit break. Write `instability.detected` push_link to OPE with: condition number, observation, OPE state at detection time. Escalate to David — do not resume execution without David's explicit unblock.

---

### Evasion vs. Drift

Two structurally different failure modes. Different causal signatures. Different GO responses.

**Drift — passive non-engagement:**
- The LLM releases the mental reins without purposeful intent — outputs become vague or off-specification, but there is no active avoidance
- Causal signature in OPE: SDI > 0.50 (context drift signal), EGS declining across consecutive episodes, premise declarations becoming less specific
- **GO response:** Grounding briefing — inject context restoration: "Read [specific file] before next write. Current phase is [X]. Active constraints: [list]." Do not circuit break. Escalate to David only if drift persists across 3+ injections.

**Evasion — purposeful, effortful disconnection:**
- The LLM is actively and purposefully avoiding a specific constraint, fact, or requirement. Evasion takes effort to maintain and installs a "standing order" that biases future retrieval away from the evaded content. Crucially, evasion is **self-concealing** — outputs appear complete while systematically omitting the evaded content.
- Causal signature in OPE: RRR > 0.05 (success claims after gate failure), specific constraint repeatedly absent from premise declarations while other constraints present, amnesia detection fires on the same constraint across multiple episodes
- **GO response:** Immediate circuit break + escalate to David. Do not attempt re-grounding — the grounding briefing itself will be evaded. Write `evasion.detected` push_link with: constraint_id, episode_ids where constraint was absent, RRR reading. Report to David with specific evidence before resuming.

**Why the distinction matters architecturally:** OPE's amnesia detection is calibrated to catch evasion (active, purposeful, consistent). It fires on drift only if drift becomes extreme and persistent. Drift is fixable in-session. Evasion requires human review because the evaded content is typically the most safety-critical constraint in play — the avoidance is not accidental.

---

## Part VI: Applying This to a New Project

When beginning a new project under GO governance, the following adapts; the following does not.

### What Adapts Per Project

- **Constraint definitions (Phase 0):** The forbidden dependency rules are specific to each project's architecture. Write them before starting the bus.
- **Execution unit structure (Phase 3–4):** Slices, phases, or iterations — whatever the project uses as its execution unit. The GO enforces ordering from the project's dependency graph.
- **BMAD PRDs:** One PRD per significant repo. David reviews each before coding begins.
- **Gate criteria:** Pass thresholds are project-specific. Set them in Phase 0.
- **Canon seed concepts:** Which universal CCDs enter this project's canon. Review MEMORY.md; pick the universal ones.

### What Does Not Change

- The 6-decision Phase 0 structure (constraint definitions, OpenClaw mode, canon seeds, ordering, threshold, infra preferences)
- The push_link call pattern (T1 forward dispatch, T7 gate pass, T8 gate failure)
- OPE bus registration for every session in every repo
- BMAD PRD review before coding begins on any significant repo
- The layer invariant verification queries (adapt the trigger names, not the structure)
- The reconstruction rule: every phase must end with a persistent artifact in OPE

### The `run_id` Pattern

For every new project: the GO generates `<project-name>-<year>-Q<N>-{uuid4}` as the `migration_run_id` at Phase 0. This value:
- Is injected into every session in every repo
- Links all OPE `bus_sessions` rows for the project
- Is the join key between OPE and any other store (ArcadeDB, object storage, CI artifacts)
- Is **never** generated inside a worker session — only at GO dispatch time

### The New Milestone Location

New milestones live in the primary project's `.planning/` directory (wherever the GSD roadmap for that project lives). Milestone completion criterion: always expressible as an OPE DuckDB query. Never as a subjective judgment.

---

## Part VII: Automatic OPE Ingestion Setup

### One-Time Shell Configuration (David does this once)

```bash
# Add to ~/.zshrc or ~/.bashrc
export OPE_BUS_SOCKET=/tmp/ope-governance-bus.sock
# OPE_RUN_ID is left empty — GO injects it at dispatch time per session
```

### Per-Repo OPE Hook (GO installs during Phase 3)

In each repo's `.claude/settings.json`, the GO writes the OPE hook configuration. After this:
- Every Claude Code session in that repo automatically registers with the OPE bus at start
- Events are written to `~/.claude/projects/<repo-path>/session_events_staging.jsonl`
- Session deregisters at end with `event_count` and `outcome`

No manual triggering. The OPE extraction pipeline runs once per phase when the GO calls `python -m src.pipeline.cli ingest`.

### OPE Bus Start (GO does this at every construction session start)

```bash
# From OPE project root
python -m src.pipeline.cli bus start --db data/ope.db &
python -m src.pipeline.cli bus status

# Health check:
curl --unix-socket /tmp/ope-governance-bus.sock \
  http://localhost/api/check \
  -d '{}' -H 'Content-Type: application/json'
# Expected: {"constraints": [...], "interventions": [], "epistemological_signals": []}
```

If the bus fails to start: stop. Do not proceed. Construction without bus registration degrades causal chain coverage from Day 1.

---

## Part VIII: After Context Clear — How to Resume

When David returns after a gap and starts a new session with the GO, the resumption protocol is:

**David says:** "Pick up where we left off on [project name]."

**GO does (in order):**
1. Read this document (`docs/guides/GOVERNING-ORCHESTRATOR-METHODOLOGY.md`)
2. Read `DECISIONS.md` in the project's `.planning/` directory
3. Query OPE DuckDB:
   ```sql
   -- What repos are registered?
   SELECT repo, status, registered_at FROM bus_sessions ORDER BY registered_at;

   -- What push_links exist?
   SELECT transition_trigger, COUNT(*) as count FROM push_links GROUP BY transition_trigger;

   -- What phase are we in?
   SELECT * FROM push_links ORDER BY captured_at DESC LIMIT 5;
   ```
4. Identify the current phase from the invariant queries
5. Report: "We are in Phase [N]. Last completed: [push_link trigger]. Next action: [what the GO does next / what David needs to decide]."

No recap from David is needed. OPE contains the full state.

---

## Part IX: Key Verifiable Queries Reference

```sql
-- Phase 0 complete?
-- Check constraints.json manually: N PLATFORM entries

-- Phase 1 complete?
SELECT repo, status FROM bus_sessions WHERE repo IN ('<infra>', '<canon>');
SELECT COUNT(*) FROM push_links WHERE transition_trigger='repo.created';

-- Gate 1 passed?
SELECT * FROM push_links WHERE transition_trigger='gate-1-schema-passed';

-- Phase 3 / Milestone complete?
SELECT COUNT(DISTINCT repo) FROM bus_sessions;
SELECT * FROM push_links WHERE transition_trigger LIKE 'gate-%-passed';

-- Full push_link chain for a run:
SELECT transition_trigger, captured_at, repo_boundary
FROM push_links
WHERE migration_run_id = '<run_id>'
ORDER BY captured_at;

-- Learning loop produced candidates?
SELECT COUNT(*) FROM memory_candidates
WHERE epistemological_origin='inductive' AND verdict='pending';
```

---

## CCD Axes Governing This Methodology

These are the filing keys — read them to retrieve the correct conceptual node, not the surface-similar one:

| Axis | What it governs in this methodology |
|------|-------------------------------------|
| `run-id-dissolves-repo-boundary` | The `run_id` is the causal chain boundary, not the repo. All repos under one run_id form one traversable chain in OPE. |
| `causal-chain-completeness` | T1/T7/T8 push_links must be captured at transition time. They cannot be reconstructed retroactively. |
| `decision-boundary-externalization` | Every consequential GO decision has 5 properties: trigger, observation state, action, outcome, provenance pointer. A decision missing any of the 5 is permanently opaque. |
| `reconstruction-not-accumulation` | The GO reconstructs from OPE artifacts, not session context. Every phase must end with a persistent artifact. |
| `epistemological-layer-hierarchy` | Each phase activation requires the prior layer to be verified in OPE — not "Phase N complete" declared subjectively. |
| `identity-firewall` | The GO makes gate decisions; worker sessions do not validate their own output. |
| `bootstrap-circularity` | The GO's governance layer is validated against OPE artifacts (DuckDB), not against session memory. Phase 13.3 harness design. |
| `terminal-vs-instrumental` | Each layer's control authority is terminal (it decides, it does not recommend). A layer that only recommends without authority is instrumentation noise. The PEC's `immutable_hash` enforces terminal authority at the GSD→Ralph boundary. |
| `fallacy-as-process-failure` | The five instability conditions are structural fallacies: Condition 2 (GSD auto-advances on LLM self-report) = Ad Ignorantiam at the gate. Condition 1 (Ralph rewrites GSD artifacts) = Stolen Concept. Each has a structural signature detectable by OPE before it propagates. |

---

*The causal chain follows the run_id, not the repository structure.*
*The run_id is never generated within a session — it is injected by the Governing Orchestrator at dispatch time.*
*David sets the value. The GO enforces the method. The workers provide the associations.*

---

**Related documents:**
- `docs/architecture/BOUNDED-SUPERVISORY-ARCHITECTURE.md` — Full formal treatment of stability law, case analysis (OpenClaw→Ralph, OpenClaw→GSD, OpenClaw→BMAD), measurable stability invariants, and the stable hybrid design (BMAD→GSD→Ralph→OpenClaw)
- `docs/architecture/BUILDER-OPERATOR-BOUNDARY.md` — OPE_RUN_ID injection mechanism; builder vs. operator role separation; bus read-channel enforcement
