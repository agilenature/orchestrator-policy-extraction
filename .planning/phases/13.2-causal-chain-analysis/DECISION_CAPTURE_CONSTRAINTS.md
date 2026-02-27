# Decision Capture Constraints
## Cross-Domain Analysis: OPE × Modernizing Tool Pipeline

*Phase 13.2 — Completed 2026-02-22 — Conversation-driven analysis*
*Source: Integrated elevated prompt execution (bidirectional enrichment test applied)*
*Two CCDs deposited to MEMORY.md: `decision-boundary-externalization`, `causal-chain-completeness`*

---

## Governing Constraint

Any analysis delivers value only through `memory_candidates` deposits. The compound violated dependency identified in this analysis:

> **An automated pipeline cannot be improved at the system level unless (a) each decision artifact is epistemologically complete AND (b) the causal links between decision artifacts are captured explicitly at transition time.** Neither condition alone is sufficient.

---

## Part 1 — The Causal Chain Map (End-to-End)

The modernizing tool's pipeline operates across four systems with nine transitions and one closed feedback loop.

**Four Systems:**
- **Legacy** (Layer 1 source of truth — read-only)
- **Factory** (SEMF + Engines 1–4 — generates artifacts)
- **Bridge/BCL** (governs slice lifecycle and verification)
- **Target** (receives migrated slices)

### Decision Nodes

Moments where a choice constrains all downstream options:

| Node | What Gets Decided | Current Artifact |
|------|-------------------|-----------------|
| D1 | Slice decomposition: boundary, wave, risk level | EDN slice spec (incomplete) |
| D2 | Engine 1: which core contracts + overlay artifacts to generate | 4 overlay EDN files (good) |
| D3 | Engine 2: how to refine shadow diff rules from baseline capture | Refined overlays (observation missing) |
| D4 | Engine 3: which test packs to generate per gate | Test pack manifest (good) |
| D5–D9 | Gates 0–4: pass or block at each verification stage | Gate result artifacts (nearly complete) |
| D10 | Closed-loop write-back: what to update upstream when a gate fails | **None — entirely opaque** |
| D11 | Canary step progression: advance or halt/rollback | Rollout plan config (no provenance link) |
| D12 | EVA validation: accept or reject a Layer 2 artifact | EVA machine record (most complete) |

### Transition Points

Where one decision's output becomes the next decision's observation:

```
Legacy code
  T1 → [D1: Slice decomposition]  ← NO ARTIFACT TRAIL  ← BREAK 1
        T2 → [D2: Engine 1 Spec Compiler]  ← inputs/revision tracked → overlays
              T3 → [D3: Engine 2 Enricher]  ← baseline captured → refined overlays
                    T4 → [D4: Engine 3 Renderer]  ← overlays → test pack manifest
                          T5 → [D5–D9: Gates 0–4]  ← packs → gate results
                                T6 → Gate progression decision
                                      T7 → [D11: Canary rollout]  ← NO provenance link  ← BREAK 2
                                      T8 → [D10: Write-back]  ← NO ARTIFACT TRAIL  ← BREAK 3
                                            └─ loops back to D2 (Engine 1 recompile)
```

**Three breaks in the chain:**
- **T1** — the decision that determines all downstream work has no artifact
- **T8** — the learning loop produces no artifact (the factory's only self-improvement mechanism is invisible)
- **T7** — gate-to-canary progression has no provenance link to the gate results that enabled it

---

## Part 2 — Epistemological Completeness Audit

A decision artifact is **epistemologically complete** if and only if it carries:
1. **Trigger**: what made this decision necessary (the start event)
2. **Observation state**: what was known at decision time (complete context snapshot)
3. **Action taken**: what the decision produced
4. **Outcome**: what the action caused, including downstream effects
5. **Provenance pointer**: traceable link back to perceptual ground

| Node | (1) Trigger | (2) Observation | (3) Action | (4) Outcome | (5) Provenance | Completeness |
|------|-------------|-----------------|------------|-------------|----------------|-------------|
| D1: Slice decomposition | ❌ | ❌ | ⚠️ EDN spec | ❌ | ❌ | **1/5 — log entry** |
| D2: Engine 1 | ⚠️ | ✅ source/revision | ✅ overlays | ❌ | ✅ inputs/revision | **3/5** |
| D3: Engine 2 Enricher | ⚠️ | ❌ | ✅ refined overlays | ❌ | ⚠️ bindings/rev | **2/5** |
| D4: Engine 3 Renderer | ✅ | ✅ overlays as input | ✅ test pack manifest | ❌ | ✅ generator metadata | **4/5** |
| D5–D9: Gates 0–4 | ✅ | ✅ test pack scopes | ✅ pass/fail | ✅ summary artifact | ⚠️ pack/id only | **4.5/5** |
| D10: Write-back | ❌ | ❌ | ❌ | ❌ | ❌ | **0/5 — entirely opaque** |
| D11: Canary progression | ⚠️ | ❌ no traffic snapshot | ✅ percentage step | ✅ thresholds | ❌ no gate link | **2.5/5** |
| D12: EVA validation | ✅ | ✅ evidence field | ✅ accept/reject | ⚠️ | ✅ perception_instances | **4.5/5 — best in system** |

**Critical finding:** D10 (write-back) — the single mechanism through which the factory is supposed to learn — has zero of five properties. Accumulation disguised as a learning loop.

---

## Part 3 — The Causal Link Schema

### Minimum Viable Causal Link Artifact

Format-agnostic. EDN shown as reference; JSON or other format is an acceptable instantiation.

```edn
CausalLinkV1 = {
  :link/id                    keyword    ; stable ID for this transition event
  :link/parent-decision-id    keyword    ; decision that produced the observation for this step
  :link/child-decision-id     keyword    ; decision this output will be observed by
  :link/transition-trigger    keyword    ; event that caused the handoff
                                         ; e.g. :trigger/gate-pass :trigger/gate-fail
                                         ;      :trigger/slice-spec-ready :trigger/baseline-captured
  :link/propagated-constraints [keyword ...] ; active BCL constraints inherited at transition
  :link/observation-snapshot   {any}     ; complete observation state at transition time
                                         ; self-contained — reconstruction possible without session
  :link/captured-at           string     ; ISO-8601, written at transition time (push model)
}
```

### Push Required / Pull Viable Analysis

| Transition | Method | Reason |
|------------|--------|--------|
| T1: Legacy analysis → D1 Slice decomposition | **PUSH REQUIRED** | Analysis driving decomposition is in human judgment/SEMF — not in JSONL trace. Pull reconstruction will silently fail. |
| T2: D1 → Engine 1 | **PUSH REQUIRED** | D1 is not yet an artifact; Engine 1 cannot reference it until T1 is captured |
| T3: Engine 1 → Engine 2 | Pull viable | source/revision + inputs/revision sufficient |
| T4: Engine 2 → Engine 3 | Pull viable | overlays-rev enables reconstruction |
| T5: Engine 3 → Gates | Pull viable | test-pack-id references exist |
| T6: Gate result → Progression | Pull viable | gate pass/fail is structured |
| T7: Gate pass → Canary | **PUSH REQUIRED** | Progression decision requires capturing which gate results enabled it — link currently implicit |
| T8: Gate fail → Write-back | **PUSH REQUIRED** | Engineer decision outside automated pipeline. Nothing to pull from. |

Four of nine transitions require push linking. Two of them (T1 and T8) are exactly the points where the factory's learning is supposed to happen. Both are currently invisible.

---

## Part 4 — Backward Traversal Algorithm

### Definition

Given any terminal failure episode, traverse backward via `parent_decision_id` links to the originating upstream decision — the decision at step K that, if changed, would have changed all downstream outcomes.

### Example Traversal: Gate 4 Shadow Diff Exceeded for slice/auth

**With causal link schema in place:**
```
Gate 4 failure (diff rate 0.07, threshold 0.05)
  ← CausalLink T6 ← Engine 4 execution
    ← CausalLink T5 ← test pack :pack/auth-shadow
      ← CausalLink T4 ← Engine 2 enriched shadow diff rules
        observation-snapshot: {baseline: op/authenticate returns {timestamp: "2026-02-10T14:23:11Z"}}
        ← CausalLink T3 ← Engine 2 baseline capture
          FINDING: Engine 2 chose :compare/strict without detecting timestamp field variance
        ← CausalLink T2 ← Engine 1 Spec Compiler
          ← CausalLink T1 ← D1: Slice decomposition (CURRENTLY MISSING — traversal breaks here)
```

**Actionable output of successful traversal:**
> "Root cause: Engine 2 enricher selected `:compare/strict` for `op/authenticate` without detecting that the response contains a timestamp field that varies per call. This is an enricher heuristic failure, not a shadow diff rules misconfiguration.
>
> BCL contract candidate: 'When a legacy operation's baseline response contains any field matching timestamp patterns (ISO-8601 strings, Unix epoch integers), Engine 2 MUST default to :compare/tolerant with :timestamp-policy :ts/round-to-seconds.'
>
> Specification enrichment target: Engine 2's baseline capture heuristics — add timestamp field detection. This fix applies to all slices with timestamp-bearing responses, not just slice/auth."

**Key insight:** Without the chain, the fix is local (update auth shadow diff rules). With the chain, the fix is systemic (update Engine 2 heuristics for all slices). One traversal converts N local fixes into 1 specification improvement.

### Forward Propagation Query

When a root cause is identified at step K, query: which other downstream decisions were constrained by the same upstream decision? A root cause affecting N downstream decisions is a stronger BCL contract candidate than one affecting 1.

---

## Part 5 — Bidirectional Yield Test Results

Every proposed addition passes — none are OPE-only instrumentation:

| Addition | Yield to OPE | Yield to Modernizing Tool | Pass |
|----------|-------------|--------------------------|------|
| CausalLinkV1 at T1 | Full backward traversal | Engineers can audit why a slice was decomposed this way; SEMF can learn from outcomes | ✅ |
| CausalLinkV1 at T8 | Write-back loop becomes constraint source | Write-back becomes auditable; closed loop is visible | ✅ |
| observation-snapshot at D3 | OPE reconstructs what was known during test generation | Engine 2 detects when legacy behavior has drifted since baseline capture | ✅ |
| propagated-constraints on all transitions | OPE amnesia detection works at chain level | BCL detects when Gate 1 constraint re-violated at Gate 4 (not propagated) | ✅ |
| parent-decision-id on Engine 1 output | Links compilation to decomposition | Engine 1 detects repeated recompilation from same slice (thrashing) | ✅ |

---

## Part 6 — Two Cross-Domain CCDs (Deposited to MEMORY.md)

### CCD A: `decision-boundary-externalization`

**Scope rule:** A decision is improvable only if externalized at the decision boundary as an artifact carrying all five properties: (1) trigger, (2) observation state, (3) action, (4) outcome, (5) provenance pointer. Decisions missing any property are permanently opaque to retrospective improvement — they can be replayed but not learned from.

**Bidirectional test:** Fires in OPE (episodes missing `ground_truth_pointer` are invalid by this rule) AND in the modernizing tool (slice decomposition D1 produces property 3 only; write-back D10 produces zero properties). **PASSES.**

### CCD B: `causal-chain-completeness`

**Scope rule:** System-level attribution requires explicit causal links captured at transition time between decision artifacts. A system whose artifacts are locally complete (all 5 properties at each node) but globally disconnected (no links between nodes) is attributable locally but not systemically. System-level improvement — finding the upstream decision whose change would restructure all downstream outcomes — requires backward traversal, which requires explicit `parent_decision_id` links written at push time at transitions where pull reconstruction fails.

**Bidirectional test:** Fires in OPE (episodes have provenance links but not causal links — amnesia detection works per-constraint, not per-chain) AND in the modernizing tool (gate results carry pack references but no parent pointers; write-back has no link artifact). **PASSES.**

---

## Summary: What Must Change Before Self-Improvement Is Real

The modernizing tool's learning loop currently consists of:
- Gate failures → engineers fix artifacts → re-run gates

This is not a self-improving system. It is a manually-corrected system. The difference:

| Current State | Required State |
|---------------|----------------|
| Gate failure → fix the specific artifact | Gate failure → traverse chain → fix the specification layer heuristic |
| Write-back produces no artifact | Write-back produces CausalLinkV1 with all 5 properties |
| Slice decomposition is implicit | Slice decomposition produces D1 artifact with all 5 properties |
| BCL contracts accumulate in a store | BCL contracts track durability and graduate to wisdom layer |
| Engine 2 heuristics fixed | Engine 2 heuristics update when gate failures trace to enricher decisions |

The four push-required transitions (T1, T2, T7, T8) are the four places where the transition from accumulation to reconstruction happens. Implementing them is the minimum viable self-improvement loop.
