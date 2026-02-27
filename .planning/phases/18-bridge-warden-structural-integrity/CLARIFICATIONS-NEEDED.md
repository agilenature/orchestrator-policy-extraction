# CLARIFICATIONS-NEEDED.md

## Phase 18: Bridge-Warden Structural Integrity Detection — Stakeholder Decisions Required

**Generated:** 2026-02-24
**Mode:** Multi-provider synthesis (OpenAI, Gemini, Perplexity)
**Source:** 3 AI providers analyzed Phase 18 requirements

---

## Decision Summary

**Total questions:** 7
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 2 questions — Should answer for quality
**Tier 3 (Polish):** 1 question — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: How Should Structural Signals Be Detected?

**Question:** Should structural signal detection operate over raw text/message streams (NLP-based), over existing `flame_events` patterns (second-pass analysis), or over the axis_edges topology graph?

**Why it matters:** This determines whether Phase 18 introduces new text processing machinery or reuses Phase 15 infrastructure. NLP-based adds complexity and fragility; flame_event-based reuses proven infrastructure but is limited to what Phase 15 already detects.

**Options identified by providers:**

**A. Graph topology analysis (using axis_edges)**
- Detect signals as structural properties of the node graph (L-level edges, hub nodes, cycle detection)
- Pros: Formally rigorous; handles Spiral Reinforcement naturally via community detection
- Cons: axis_edges table is populated from conjunctive Level 5+ events only; sparse early in session
- _(Proposed by: Gemini)_

**B. Second-pass flame_event pattern analysis (Recommended)**
- Detect structural signals by querying existing flame_events for specific patterns: Gravity Check = L5+ flame_event with co-occurring L0-L2 for same axis within ±N prompts; Main Cable = L5+ with generalization_radius >= 2; Spiral = cross-reference to project_wisdom promotions
- Pros: Reuses Phase 15 infrastructure; no new text processing; consistent with existing architecture
- Cons: Limited to what flame_events capture; depends on Phase 15 detection quality
- _(Proposed by: Claude synthesis of both providers)_

**C. Raw NLP + entity anchoring**
- Analyze message text for entity references, dependency chains, abstract vs. concrete language
- Pros: Independent of Phase 15 quality; can catch structural failures Phase 15 misses
- Cons: Introduces NLP complexity; no proven implementation in this codebase
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option B** — Second-pass flame_event pattern analysis
- Consistent with deposit-not-detect principle: Phase 15 already deposits to flame_events; Phase 18 reads that deposit to compute structural properties.

**Sub-questions:**
- Should Gravity Check fire on ABSENCE of grounding (floating cable alert) or PRESENCE (positive signal), or both?
- What is the "co-occurrence window" for Gravity Check? (Proposed: ±3 prompts)
- Should Op-8 check ONLY ai_flame_events or also human flame_events?

---

### Q2: What is the Precise CTT Op-8 Check?

**Question:** How do you operationalize Top-Down Tension as a computation? Specifically: what is the definition of "floating cable" in AI reasoning, and what threshold triggers an Op-8 correction deposit?

**Why it matters:** Op-8 is BRIDGE-03 — it is the primary mechanism for AI self-correction and is the main deposit path into memory_candidates. An unclear definition produces either too many false positives (every AI abstraction flagged) or too few (system detects nothing).

**Options identified by providers:**

**A. Floating cable = AI L5+ flame_event with no co-occurring L0-L2 in same session**
- Post-response analysis. Correction deposit fires at session end if no grounding found within N prompts.
- Pros: Simple, computable, reuses flame_event data
- Cons: Session-end timing means correction arrives after the work; may miss transient grounding
- _(Proposed by: Gemini)_

**B. Floating cable = AI L5+ flame_event with flood_confirmed=False**
- Use existing Phase 15 field: if the AI produced a high-level principle without a Concretization Flood, it's floating.
- Pros: Direct reuse of existing schema field; no new detection needed
- Cons: flood_confirmed=True is set by Phase 15 Tier 2 only for Level 6+ events; many valid principles at Level 5 will always have flood_confirmed=False even when well-grounded
- _(Proposed by: Claude synthesis)_

**C. Tension Score = verified_instances / total_instances per principle**
- Compute what fraction of Main Cable principles have downstream verified instances in code/design
- Pros: Formally rigorous; matches Op-8 semantics precisely
- Cons: Requires "instance discovery" — finding code locations that instantiate principles — complex without code analysis
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Combination of A + B**
- Op-8 triggers on `ai_flame_events` at level >= 5 where no L0-L2 ai_flame_event references the same `ccd_axis` within the same session (Option A), with `flood_confirmed=False` used as an additional filter (Option B) rather than the sole trigger.
- Threshold: must look within same session, not just same prompt

**Sub-questions:**
- Should Op-8 corrections be deposited per-session (one per floating axis per session) or per-occurrence (one per floating flame_event)?
- The correction format in memory_candidates — should it carry the CCD-format (ccd_axis | scope_rule | flood_example) or a different format?

---

### Q3: What is the StructuralIntegrityScore Neutral Baseline?

**Question:** When a session has zero signals of a given type (no Main Cable events, no Dependency Sequencing events), should the score default to 0.0 (no evidence = poor), 0.5 (no evidence = neutral), or be excluded from the score calculation entirely?

**Why it matters:** A session focused entirely on implementation (no architectural principles expressed) should not score poorly. The score should reflect quality of structural reasoning WHEN abstractions are present — not penalize sessions that appropriately work at a concrete level.

**Options identified by providers:**

**A. Default to 0.0 for missing signals**
- Simple; rewards sessions that actively demonstrate structural reasoning
- Cons: Penalizes short sessions and implementation-focused sessions that don't need structural principles
- _(Proposed by: Gemini formula implicitly)_

**B. Default to 0.5 (neutral) for missing signals (Recommended)**
- Missing evidence = no claim either way; use midpoint rather than failure
- Consistent with TransportEfficiency backfill (trunk_quality starts at 0.5/pending)
- Pros: More fair; distinguishes "didn't demonstrate" from "demonstrated poorly"
- Cons: Can mask actual structural deficiencies in sessions that should have had Main Cables
- _(Proposed by: Claude synthesis)_

**C. Exclude from score when denominator = 0**
- Only compute score for the signals that fired; normalize over those only
- Pros: Most accurate; no phantom scores
- Cons: Score is incomparable across sessions with different signal compositions
- _(Proposed by: Perplexity formula implicitly)_

**Synthesis recommendation:** ✅ **Option B** — Default to 0.5 neutral for empty denominators, consistent with TransportEfficiency trunk_quality pattern.

**Sub-questions:**
- Should `structural_integrity_score` be nullable (like trunk_quality) when no L5+ events occurred at all?

---

### Q4: Phase 15 vs Phase 18 Separation Rule

**Question:** What is the exact architectural rule preventing double-counting between Phase 15 flame_event detection and Phase 18 structural integrity detection?

**Why it matters:** Spiral Reinforcement (Phase 18) and spiral tracking (Phase 15) overlap conceptually. If Phase 18 re-detects spirals independently, the two systems will diverge. If Phase 18 simply cross-references Phase 15's spiral promotion events, the two are cleanly separated.

**Options identified by providers:**

**A. Phase 18 is a pure second-pass reader — never writes to flame_events (Recommended)**
- structural_events writes only to structural_events. Consumes flame_events as read-only input.
- Spiral Reinforcement in structural_events = cross-reference to project_wisdom promotions from Phase 15 (not new detection).
- _(Proposed by: Both providers)_

**B. Phase 18 adds structural_role annotations to existing flame_events**
- Backfill existing flame_events with structural_role column indicating whether each event participates in a structural signal
- Pros: Enriches existing data; no new table required
- Cons: Mutates existing data (violates Phase 15 integrity); complex migration
- _(Proposed by: Gemini as question)_

**C. Separate structural detector with independent flame_event-like emission**
- Phase 18 emits its own version of flame_events to structural_events, with no linkage to Phase 15 events
- Pros: Clean independence
- Cons: True double-counting risk; no shared identity between the two signal streams
- _(Proposed by: Perplexity implicitly)_

**Synthesis recommendation:** ✅ **Option A** — Phase 18 is a pure second-pass reader. `structural_events` is additive with no mutations to Phase 15 tables.

**Sub-questions:**
- Is `contributing_flame_event_ids VARCHAR[]` sufficient for lineage, or do we need a separate lineage table?

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Op-8 Correction Format in memory_candidates

**Question:** Op-8 failures deposit to memory_candidates. Should these follow strict CCD format (ccd_axis | scope_rule | flood_example), use a distinct correction type, or a hybrid?

**Why it matters:** memory_candidates feeds the memory-review CLI and ultimately MEMORY.md. If Op-8 corrections appear as raw chunks rather than CCD-format entries, they won't produce axis-guided retrieval improvements.

**Options:**

**A. Strict CCD format with source_type='op8_correction'**
- Force Op-8 corrections into the same (ccd_axis | scope_rule | flood_example) format as all other candidates
- `ccd_axis` = the axis that was floating; `scope_rule` = rule about when grounding is required; `flood_example` = the ungrounded assertion as negative example
- _(Recommended by: Claude synthesis)_

**B. Constraint-type entry (not CCD format)**
- Store as a constraint prescription: "Principle X requires concrete grounding via Y"
- Different structure from CCD entries; filtered separately in review CLI
- _(Proposed by: Gemini)_

**Synthesis recommendation:** ⚠️ **Option A** — strict CCD format. This ensures Op-8 deposits integrate with the existing memory-review pipeline without new CLI plumbing.

---

### Q6: Wave Structure and Plan Count

**Question:** The roadmap specifies "~4 plans in 3 waves." What is the correct wave decomposition given the synthesis decisions above?

**Why it matters:** Wave decomposition determines implementation order and what constitutes each plan's deliverable.

**Proposed wave structure:**

**Wave 1 (Foundation — terminal deposit path first):**
- Plan 18-01: structural_events schema + DDL + models (StructuralEvent, StructuralIntegrityScore, StructuralConfig) + create_schema() integration
- Confirms deposit path: Op-8 failure → memory_candidates INSERT works end-to-end

**Wave 2 (Detection):**
- Plan 18-02: Four structural signal detectors (flame_event second-pass analysis) + StructuralIntegrityComputer + structural_events writer + pipeline Step 21
- Plan 18-03: CTT Op-8 validation layer + correction deposit function + integration tests

**Wave 3 (Profile + CLI):**
- Plan 18-04: 3D IntelligenceProfile extension + CLI extensions (bridge subcommand) + integration tests for BRIDGE-01 through BRIDGE-04

**Sub-questions:**
- Should Op-8 be a separate plan (18-03) or combined with detection (18-02)?

---

## Tier 3: Polish Decisions

### Q7: Three-Dimensional Profile Archetype Labels

**Question:** Should the three-dimensional IntelligenceProfile display include human-readable "archetype" labels (The Dreamer, The Technician, The Rhetorician) based on score quadrants?

**Why it matters:** Archetype labels provide cognitive shorthand but add implementation complexity and potential for misinterpretation.

**Options:**
- **A. Add archetype labels in v1** — Requires quadrant threshold definition, may be misleading with limited data
- **B. Display raw scores only in v1 (Recommended)** — Simpler; archetype strings can be added post-verification when enough data exists to validate thresholds

**Synthesis recommendation:** 🔍 **Option B** — Display raw scores only in v1.

---

## Next Steps (Non-YOLO Mode)

**✋ PAUSED — Awaiting Your Decisions**

1. Review these 7 questions
2. Provide answers (create CLARIFICATIONS-ANSWERED.md manually)
3. Then run: `/gsd:plan-phase 18`

---

## Alternative: YOLO Mode

```bash
/meta-gsd:discuss-phase-ai 18 --yolo
```

---

*Multi-provider synthesis: OpenAI gpt-5.2 + Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-24*
