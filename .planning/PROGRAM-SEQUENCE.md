# Program Sequence Document

**Purpose:** Cross-project execution tracker governing work across OPE and the Modernizing Tool.
**Governing rule:** This document is the canonical routing source. Do not embed routing logic in individual project GSD documents — link here instead.
**Update protocol:** When you complete a step, say "Step N done" and I will verify against the `ai_verification` criteria, mark it complete, and tell you what to run next.

> **Related:** `.planning/STATE.md` (OPE current state) | `modernizing tool/.planning/STATE.md` (MT current state)

---

## Axis: terminal-vs-instrumental

Deposit-bearing steps (those that produce durable artifacts or unlock later waves) take priority over detection/scaffolding steps. When time is constrained, cut wave-end polish; never cut a step that is the unblock condition for the next wave.

---

## Execution Sequence

### WAVE 1 — Parallel (all three can start simultaneously)

---

#### Step 1 — OPE Phase 13.3 · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | OPE (`/Users/david/projects/orchestrator-policy-extraction`) |
| **Phase/Plan** | Phase 13.3 — Identification Transparency Layer (4 plans: 13.3-01 through 13.3-04) |
| **Human action** | Run `/gsd:execute-phase 13.3` in OPE project |
| **AI verification** | Confirm 4/4 plans complete, 889+ tests passing, Agent B two-layer validation architecture live (Agent B judge + Harness oracle), no regressions |
| **Unblocks** | No later step is blocked on this — OPE Phase 15 proceeds after Phase 14 (Step 9), not directly after 13.3. But 13.3 must complete before Phase 14 planning is unblocked per STATE.md. |
| **Blocked by** | Nothing |

---

#### Step 2 — OPE Plan 14-01 · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | OPE |
| **Phase/Plan** | Phase 14, Plan 14-01 — Single-session hook contracts (LIVE-01/02/03) |
| **Human action** | Run `/gsd:execute-phase 14` in OPE (plan 14-01 only — subsequent plans are blocked) |
| **AI verification** | Confirm plan 14-01 complete: PreToolUse/PostToolUse hook contracts defined (LIVE-01/02/03), single-session EGS enforcement architecture in place. Verify plan 14-02 is still blocked (do not continue past 14-01). |
| **Unblocks** | Step 6 (OPE 14-02) partially — 14-01 output is a required input to 14-02 |
| **Blocked by** | Nothing (single-session hook contracts have no cross-session dependencies) |

---

#### Step 3 — MT Phase 06.2 Initial Execution · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | Modernizing Tool (`/Users/david/projects/modernizing tool`) |
| **Phase/Plan** | Phase 06.2 — Multi-Repo Platform Architecture Strategy |
| **Human action** | Run `/gsd:plan-phase 06.2` then `/gsd:execute-phase 06.2` in MT project. **Note:** The OpenClaw section of the output document (`platform-repo-strategy.md`) should be marked `[TBD — pending Step 4 OpenClaw spike]` — do not block execution on it. |
| **AI verification** | Confirm `platform-repo-strategy.md` exists in `.planning/phases/06.2-*/`. Verify it contains: per-repo Configuration Blueprint table (6 repos), BMAD→GSD→Ralph→OpenClaw stack per repo, cross-repo dependency sequencing. Verify OpenClaw section is explicitly marked TBD with a pointer to Step 4. |
| **Unblocks** | Step 7 (MT repo creation — human manually creates repos using the strategy doc) |
| **Blocked by** | Nothing (OpenClaw section is intentionally deferred) |

---

### WAVE 2 — Sequential after Wave 1

---

#### Step 4 — OPE Plan 14-04 · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | OPE |
| **Phase/Plan** | Phase 14, Plan 14-04 — OpenClaw Integration Spike |
| **Human action** | Run `/gsd:plan-phase 14-04` then execute it. This is the spike that installs OpenClaw, validates the WebSocket interface, and produces the `run_id` injection protocol findings. |
| **AI verification** | Confirm: OpenClaw installed and operational; `run_id` injection protocol documented; cross-session bus registration protocol tested; WebSocket interface validated (not REST). Output: a spike findings document usable by Step 5. |
| **Unblocks** | Step 5 (MT Phase 06.2 finalization), which in turn unblocks Step 6 (OPE 14-02) |
| **Blocked by** | Steps 1 (Phase 13.3 must be complete per STATE.md), 2 (14-01 hook contracts are prerequisite for 14-04 cross-session architecture) |

> **Inversion note:** 14-04 feeds Phase 06.2 finalization — 14-04 is NOT blocked by Phase 06.2. The dependency arrow runs Step 4 → Step 5, not the reverse.

---

#### Step 5 — MT Phase 06.2 Finalization · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | Modernizing Tool |
| **Phase/Plan** | Phase 06.2 finalization — update `platform-repo-strategy.md` OpenClaw section |
| **Human action** | Open `platform-repo-strategy.md` and fill in the `[TBD]` OpenClaw section using Step 4 spike findings: `run_id` injection protocol, bus registration pattern, WebSocket interface spec, per-repo OpenClaw config. |
| **AI verification** | Confirm: `platform-repo-strategy.md` OpenClaw section no longer marked TBD; contains: `run_id` injection at dispatch time (not generated within sessions), bus registration protocol for all 6 repos, WebSocket interface spec, push link requirements at T1/T7/T8 transitions. Verify `GOVERNING-ORCHESTRATOR-ARCHITECTURE.md` cross-references are consistent with finalized doc. |
| **Unblocks** | Step 6 (OPE 14-02 — needs OpenClaw interface finalized), Step 7 (MT repo creation — strategy doc now complete) |
| **Blocked by** | Step 4 (OpenClaw spike findings) |

---

### WAVE 3 — Sequential after Wave 2

---

#### Step 6 — OPE Plan 14-02 · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | OPE |
| **Phase/Plan** | Phase 14, Plan 14-02 — Multi-session bus + Governor + DDF co-pilot |
| **Human action** | Run `/gsd:execute-phase 14` (plan 14-02, picking up from 14-01 which was done in Step 2). |
| **AI verification** | Confirm: multi-session inter-session bus operational; governing session architecture live; DDF co-pilot intervention types (O_AXS, Fringe Drift, Affect Spike) implemented; cross-session `run_id` registration working; `wisdom_layer_schema` integrated. |
| **Unblocks** | Step 8 (OPE 14-03 executive spike) |
| **Blocked by** | Steps 4 (needs OpenClaw interface — `run_id` injection, bus registration protocol), 5 (needs finalized cross-repo session coordination spec) |

---

#### Step 7 — MT Repo Creation · `[ HUMAN ONLY — READY ]`

| Property | Value |
|----------|-------|
| **Project** | Modernizing Tool |
| **Phase/Plan** | Manual: create the 6 platform repos per `platform-repo-strategy.md` |
| **Human action** | Manually create GitHub repos: `platform-core`, `migration-workbox`, `migration-cobol`, `project-template`, `sales-website`, `infrastructure`. Apply per-repo Configuration Blueprint (BMAD→GSD→Ralph→OpenClaw) from the finalized strategy doc. |
| **AI verification** | Confirm (via human report): 6 repos created; each repo has `.planning/` initialized with PROJECT.md, ROADMAP.md, STATE.md; OpenClaw registration config present; initial GSD config applied per blueprint. |
| **Unblocks** | Step 11 (MT platform-core Phase 1) |
| **Blocked by** | Step 5 (strategy doc must be complete and OpenClaw section filled in before repos are structured) |

---

### WAVE 4 — Sequential after Wave 3

---

#### Step 8 — OPE Plan 14-03 · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | OPE |
| **Phase/Plan** | Phase 14, Plan 14-03 — Executive spike (end-to-end governing session test) |
| **Human action** | Run `/gsd:execute-phase 14` (plan 14-03, the executive spike). This test fires a complete governing session lifecycle end-to-end. |
| **AI verification** | Confirm: governing session can observe cross-session events; RRR circuit-breaker fires on evasion signal; EGS enforcement blocks ungrounded tool calls; DDF co-pilot interventions fire at correct thresholds; full multi-session trace recorded in DuckDB. |
| **Unblocks** | Step 9 (OPE 14-05 blueprint) |
| **Blocked by** | Step 6 (needs multi-session bus and governing session from 14-02) |

---

### WAVE 5 — Sequential after Wave 4

---

#### Step 9 — OPE Plan 14-05 · `[ SUPERSEDED ]`

| Property | Value |
|----------|-------|
| **Project** | OPE |
| **Phase/Plan** | Phase 14, Plan 14-05 — Live governance blueprint (architecture completion doc) |
| **Human action** | Run `/gsd:plan-phase 14-05` then execute it. This produces the authoritative blueprint for Phase 15's DDF detection substrate. |
| **AI verification** | Confirm: Phase 14 blueprint document produced; all five metrics (TCI/EGS/SDI/RRR/SAS) mapped to concrete implementations; `ai_flame_events` schema finalized; `memory_candidates` write-on-detect conditions specified with EGS conditioning; Phase 15 handoff package complete. |
| **Unblocks** | Step 10 (OPE Phase 15 — needs Phase 14 blueprint) |
| **Blocked by** | Step 8 (executive spike must validate the architecture before it is blueprinted) |

---

### WAVE 6 — Parallel (all three can start once their blockers clear)

---

#### Step 10 — OPE Phase 15 · `[ COMPLETE ]`

| Property | Value |
|----------|-------|
| **Project** | OPE |
| **Phase/Plan** | Phase 15 — DDF Detection Substrate |
| **Human action** | Run `/gsd:plan-phase 15` then `/gsd:execute-phase 15`. |
| **AI verification** | Confirm: `ai_flame_events` table live; write-on-detect to `memory_candidates` firing at Level 6 + High EGS (per `deposit-not-detect` CCD); EGS/SAS quadrant tagging on flame events; Fragility detection (Low EGS/High SAS) capturing Dangerous Sophist events; `memory_candidates` CLI review workflow (Agent B judge) operational. |
| **Unblocks** | Phase 16 (MEMORY.md review CLI and TransportEfficiency metrics) |
| **Blocked by** | Step 9 (needs Phase 14 blueprint for `ai_flame_events` schema and write-on-detect conditions) |

---

#### Step 11 — MT Platform-Core Phase 1 · `[ BLOCKED on Step 7 ]` `[ BLOCKED on OPE Phase 19 ]`

| Property | Value |
|----------|-------|
| **Project** | Modernizing Tool — `platform-core` repo |
| **Phase/Plan** | platform-core Phase 1 — first vertical slice of the modernization tool under governing orchestrator |
| **Human action** | Navigate to `platform-core` repo; run `/gsd:plan-phase 1` then `/gsd:execute-phase 1`. Register session with OpenClaw bus (inject `run_id` per GOVERNING-ORCHESTRATOR-ARCHITECTURE.md protocol). |
| **AI verification** | Confirm: first vertical slice complete; session registered with bus and `run_id` injected at dispatch time; push link at T1 (slice decomposition) captured; OPE/DuckDB can ingest session events via shared `run_id`; causal chain traversable from MT → OPE. |
| **Unblocks** | Step 12 (platform-core Phase 2) |
| **Blocked by** | Step 7 (repos must exist with OpenClaw config before slice execution) |

---

#### Step 12 — MT Platform-Core Phase 2 · `[ BLOCKED on Step 11 ]`

| Property | Value |
|----------|-------|
| **Project** | Modernizing Tool — `platform-core` repo |
| **Phase/Plan** | platform-core Phase 2 — second vertical slice |
| **Human action** | Continue in `platform-core`; run `/gsd:plan-phase 2` then `/gsd:execute-phase 2`. Verify `run_id` continuity from Step 11 (causal chain must traverse both phases). |
| **AI verification** | Confirm: T7 push link (gate pass → canary) captured if applicable; T8 push link (gate failure → write-back) captured if applicable; cross-phase causal chain reconstructable in OPE's DuckDB using `run_id` as grouping key; no repo-boundary fragmentation in decision graph. |
| **Unblocks** | Subsequent platform-core phases (governed by their own sequence) |
| **Blocked by** | Step 11 (Phase 1 must complete before Phase 2 can be planned — slice decomposition from Phase 1 informs Phase 2 scope) |

---

## Dependency Graph

```
Step 1 (OPE 13.3)  ─────────────────────────────────────► Step 4 (OPE 14-04)
Step 2 (OPE 14-01) ─────────────────────────────────────► Step 4 (OPE 14-04)
Step 3 (MT 06.2 initial) ────────────────────────────────► Step 7 (MT repos) [via Step 5]

Step 4 (OPE 14-04) ─────────────────────────────────────► Step 5 (MT 06.2 finalization)
Step 5 (MT 06.2 final) ─────────────────────────────────► Step 6 (OPE 14-02)
Step 5 (MT 06.2 final) ─────────────────────────────────► Step 7 (MT repos)

Step 6 (OPE 14-02) ─────────────────────────────────────► Step 8 (OPE 14-03)
Step 7 (MT repos)  ─────────────────────────────────────► Step 11 (MT Phase 1)

Step 8 (OPE 14-03) ─────────────────────────────────────► Step 9 (OPE 14-05)
Step 9 (OPE 14-05) ─────────────────────────────────────► Step 10 (OPE Phase 15)
Step 11 (MT Phase 1) ───────────────────────────────────► Step 12 (MT Phase 2)
```

**Critical path:** Step 1 → Step 4 → Step 5 → Step 6 → Step 8 → Step 9 → Step 10

---

## Status Log

> **Update 2026-02-25:** Phases 13.3 through 19 all completed. Document reconstructed to reflect actual execution (diverged from original plan at Step 9 — Phase 14 architecture produced a DDF substrate instead of live governance implementation in Phase 15). LIVE-01 through LIVE-05 were deferred to Phase 19 and delivered there: Governance Bus server, stream processor, governing daemon, PAG hook wiring, SessionStart hook, and integration tests. Phase 19 completed 2026-02-25 (5 plans, 3 waves, 1680+ tests total).

| Step | Status | Completed | Notes |
|------|--------|-----------|-------|
| 1 — OPE Phase 13.3 | ✓ `COMPLETE` | 2026-02-23 | 4/4 plans, 176 tests |
| 2 — OPE Phase 14-01 | ✓ `COMPLETE` | 2026-02-24 | Hook contracts, stream processor arch |
| 3 — MT Phase 06.2 initial | ✓ `COMPLETE` | 2026-02-25 | `platform-repo-strategy.md` exists; OpenClaw identity resolved via OpenClaw-SEMF-Integration-Analysis.md |
| 4 — OPE Phase 14-04 OpenClaw spike | ✓ `COMPLETE` | 2026-02-24 | Bus transport LOCKED (Unix socket + uvicorn/starlette, p99 1.6ms); OPE pipeline validated as post-task memory layer |
| 5 — MT Phase 06.2 finalization | ✓ `COMPLETE` | 2026-02-25 | OpenClaw identity resolved (local-first framework, not REST API); connection map finalized; OPE bus confirmed as parallel infrastructure |
| 6 — OPE Phase 14-02 | ✓ `COMPLETE` | 2026-02-24 | Multi-session bus design + governor + DDF co-pilot architecture documented |
| 7 — MT repo creation | `READY` | — | Human-only; Step 5 complete; OPE Phase 19 bus complete; repos can be created |
| 8 — OPE Phase 14-03 | ✓ `COMPLETE` | 2026-02-24 | Phase 15 implementation blueprint (9 plans, 5 waves) produced |
| 9 — OPE Phase 14-05 | ✓ `SUPERSEDED` | 2026-02-24 | Phase 14 blueprint embedded in 14-03; Phase 15 pivoted to DDF substrate (LIVE-01–05 deferred to Phase 19) |
| 10 — OPE Phase 15 | ✓ `COMPLETE` | 2026-02-24 | DDF Detection Substrate (DDF-01–10), 7 plans; LIVE-01–05 NOT included — deferred to Phase 19 |
| — — OPE Phase 14.1 | ✓ `COMPLETE` | 2026-02-23 | Premise Registry + PAG hook (3 plans, 134 tests) — inserted between 14 and 15 |
| — — OPE Phase 16 | ✓ `COMPLETE` | 2026-02-24 | Sacred Fire Intelligence System (4 plans) |
| — — OPE Phase 16.1 | ✓ `COMPLETE` | 2026-02-24 | Topological Edge-Generation (4 plans) |
| — — OPE Phase 17 | ✓ `COMPLETE` | 2026-02-24 | Candidate Assessment System (4 plans) |
| — — OPE Phase 18 | ✓ `COMPLETE` | 2026-02-25 | Bridge-Warden Structural Integrity (5 plans, 1661 tests) |
| **NEW** — OPE Phase 19 | ✓ `COMPLETE` | 2026-02-25 | Control Plane Integration — bus server + stream processor + governing daemon + PAG hook wiring + integration tests (5 plans, 3 waves). Bus operational; cross-session run_id grouping validated. |
| 11 — MT platform-core Phase 1 | `BLOCKED` | — | Needs Step 7 (repo creation) AND OPE Phase 19 bus running for run_id registration |
| 12 — MT platform-core Phase 2 | `BLOCKED` | — | Needs Step 11 |

### Current Action
**OPE Phase 19 COMPLETE.** Next action: MT Step 7 (repo creation).

The OPE Governance Bus is operational. Cross-session run_id grouping is validated by integration tests. The bus CLI (`python -m src.pipeline.cli bus start|status`) is available.

### Next Cross-Project Action
Step 7 is now READY (human-only):
- Human creates the 6 platform repos per `platform-repo-strategy.md`
- MT sessions in those repos can register with OPE bus using `OPE_RUN_ID`
- OPE's `bus_sessions` table will track all MT sessions under their `run_id`
- Cross-repo causal chain reconstruction becomes possible via `run_id` join
- **Cross-project dependency note:** Phase 19 bus must be operational before MT sessions register OPE_RUN_ID -- this is now satisfied

---

## How to Use This Document

**When you complete a step:** Tell me "Step N done" and I will:
1. Verify against the `ai_verification` criteria for that step
2. Mark it `COMPLETE` in the Status Log
3. Identify which steps are now unblocked
4. Tell you exactly what command to run next (or what human action to take)

**To resume after a context reset:** Read this document. The Status Log shows current state. Find the first `READY` step and execute it.

**This document is Layer 1 (canon).** Do not track cross-project sequencing anywhere else — not in individual project STATE.md files, not in session context. If you update routing logic, update it here.

---

*Created: 2026-02-23 | Updated: 2026-02-25 | Governing project: OPE | Covers: OPE Phases 13.3, 14, 14.1, 15, 16, 16.1, 17, 18, 19 + MT Phases 06.2, platform-core 1-2*
