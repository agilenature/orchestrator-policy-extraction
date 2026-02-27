# CLARIFICATIONS-NEEDED.md

## Phase 13: Policy-to-Constraint Feedback Loop — Stakeholder Decisions Required

**Generated:** 2026-02-20
**Mode:** Multi-provider synthesis (OpenAI, Gemini, Perplexity)
**Source:** 3 AI providers analyzed Phase 13 requirements

---

## Decision Summary

**Total questions:** 8
**Tier 1 (Blocking):** 5 questions — Must answer before planning
**Tier 2 (Important):** 2 questions — Should answer for quality
**Tier 3 (Polish):** 1 question — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: What constitutes a "blocked" policy recommendation in offline/shadow context?

**Question:** The policy runs in shadow mode against historical sessions. The human reacted to the *actual* assistant action, not the policy recommendation. How do we determine the policy recommendation was "blocked"?

**Why it matters:** This definition gates FEEDBACK-01. If the definition is too loose, the feedback loop generates spurious constraints. If too strict, it never triggers.

**Options identified by providers:**

**A. Episode co-location + reaction label (simplest)**
- If the human reaction in the same episode is `block` or `correct`, and the policy produced a recommendation, treat the recommendation as blocked.
- No semantic similarity check — episode co-location is the proxy for "same decision."
- _(Proposed by: Gemini's Direct Match Logic, simplified)_

**B. Semantic similarity threshold**
- Only flag a recommendation as blocked if it is semantically similar (cosine > threshold) to the historical assistant action AND the human reaction is `block`/`correct`.
- Prevents false positives when policy diverged from historical action.
- _(Proposed by: Gemini's Counterfactual Lookahead)_

**C. Explicit human rejection interface only**
- Only flag as blocked via an explicit UI rejection; implicit overrides do not count.
- _(Proposed by: Perplexity's real-time tier)_

**Synthesis recommendation:** ✅ **Option A — Episode co-location + reaction label**
- Fits existing batch architecture perfectly (ReactionLabeler output already exists)
- Avoids building a semantic similarity scorer for Phase 13
- Conservative: if the policy and historical action differ significantly, the constraint extracted will still be useful (the correction context is real)

**Sub-questions:**
- What if the episode has no reaction (timeout / unknown)? Decision needed: treat as no feedback triggered.

---

### Q2: How is the pre-surfacing constraint check implemented efficiently?

**Question:** Before surfacing a policy recommendation to the human, the system must check for conflicts with active constraints. What mechanism?

**Why it matters:** Getting this wrong either misses violations (too loose) or incurs prohibitive latency (too strict with LLM entailment).

**Options identified by providers:**

**A. Detection_hints substring matching (lowest cost)**
- Pre-compile `detection_hints` from each active constraint as case-insensitive patterns
- Check recommendation text against all hint patterns
- Same approach as AmnesiaDetector and EscalationDetector (already proven in Phases 9-10)
- _(Proposed by: synthesis of both providers)_

**B. RAG-based verification (higher accuracy)**
- Embed the recommendation → vector search ConstraintStore → retrieve top-K constraints → LLM entailment check
- Higher accuracy but requires LLM call per recommendation
- _(Proposed by: Gemini explicitly)_

**C. Pre-compiled ConstraintViolationIndex in DuckDB**
- Extract action-type + scope patterns from each constraint offline
- Query via SQL when checking a recommendation
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A — Detection_hints matching**
- Zero new infrastructure — reuses `AmnesiaDetector`'s approach verbatim
- Phase 13 is about closing the loop, not building new retrieval pipelines
- If hint coverage is insufficient, vector search can be added in a future gap-closure plan

**Sub-questions:**
- What severity thresholds trigger suppression? Proposed: `forbidden` and `requires_approval` → suppress; `warning` → log only.

---

### Q3: How is the SHA-256 constraint ID computed for policy_feedback constraints?

**Question:** The existing ConstraintStore uses `SHA-256(text + scope_paths)`. If a `policy_feedback` constraint has the same text/scope as a `human_correction` constraint, they'd collide. How to distinguish?

**Why it matters:** FEEDBACK-02 requires distinguishability. Getting the ID scheme wrong now causes hard-to-fix data integrity issues.

**Options identified by providers:**

**A. Include source in SHA-256**
- `SHA-256(text + JSON.dumps(sorted(scope_paths)) + source)`
- policy_feedback constraints get distinct IDs from human_correction ones even for identical text
- _(Proposed by: Gemini and Perplexity)_

**B. Separate constraint files**
- Keep `data/constraints.json` for human constraints and add `data/policy_feedback_constraints.json` for policy-sourced
- _(Not explicitly proposed, but implied by separation concerns)_

**C. Source as metadata field only, no ID change**
- Keep existing SHA-256 scheme; if ID collides with human constraint, just enrich examples
- Policy feedback never creates a separate entry, only enriches human ones
- _(Implied by dedup-only approach)_

**Synthesis recommendation:** ✅ **Option A — Include source in SHA-256**
- Clean and simple; single ConstraintStore JSON file unchanged structurally
- Enables auditing policy_feedback constraints independently from human_correction ones
- Durability tracking (Phase 10) applies identically to both

**Sub-questions:**
- Should `policy_feedback` constraints start as `candidate` status and require 3+ sessions before promotion to `active`? Proposed: Yes — same lifecycle as existing constraint promotion pattern.

---

### Q4: What is the exact policy_error_rate formula?

**Question:** What counts as a "policy error" in the numerator? What's the denominator? What's the rolling window?

**Why it matters:** This metric is the PASS/FAIL gate for FEEDBACK-03. The formula must be unambiguous before building the computation.

**Options identified by providers:**

**A. Suppressed-only (conservative)**
- Numerator: recommendations suppressed by pre-surfacing check only
- Denominator: total recommendations attempted
- _(Implied by strict reading of "suppressed and logged as policy errors")_

**B. Suppressed + surfaced-and-blocked (comprehensive)**
- Numerator: suppressed + surfaced recommendations where human reacted block/correct
- Denominator: total recommendations attempted
- _(Proposed by: Gemini's formula)_

**C. Weighted by severity**
- Multiply each error by a severity weight (forbidden=2, requires_approval=1)
- _(Proposed by: Perplexity's weighted variant)_

**Synthesis recommendation:** ✅ **Option B — Suppressed + surfaced-and-blocked**
- Captures the full failure surface: both "caught before surfacing" and "caught after surfacing"
- Only count `forbidden` and `requires_approval` violations (not `warning`)
- Rolling 100-session window (per Perplexity); per-session rates stored in DuckDB
- Severity weighting deferred — plain count is sufficient for Phase 13

---

### Q5: Where do new Phase 13 pipeline steps slot in?

**Question:** The current pipeline has Step 13 (escalation), Step 14 (durability), Step 15 (stats). Where do pre-surfacing check and feedback extraction fit?

**Why it matters:** Wrong ordering can cause mid-run constraint mutations or metrics computed before feedback is processed.

**Options identified by providers:**

**A. Modify ShadowModeRunner + add Step 14.5**
- Pre-surfacing check: inside `run_shadow_episode()` in ShadowModeRunner
- Feedback extraction: new Step 14.5 after existing Step 14, before Step 15
- ShadowReporter extended with policy_error_rate metric
- _(Consensus of both providers)_

**B. New top-level pipeline step (Step 16)**
- Add a discrete new step that runs all policy feedback logic after existing steps
- _(Alternative, less invasive but delays pre-surfacing check logic)_

**Synthesis recommendation:** ✅ **Option A — Modify ShadowModeRunner + Step 14.5**
- Pre-surfacing check belongs in ShadowModeRunner where recommendations are generated
- Feedback extraction naturally follows after durability evaluation (Step 14)
- Clean sequencing: escalation (13) → durability (14) → policy feedback (14.5) → stats/reporting (15)

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q6: What severity thresholds gate policy_feedback constraint promotion?

**Question:** Should `policy_feedback` constraints start as `candidate` and require N sessions before becoming `active`? What's N?

**Options:**
**A.** Promote immediately (no candidate threshold) — simpler, faster feedback integration
**B.** Require 3 sessions as `candidate` before promoting to `active` — same as implied by existing constraint lifecycle

**Synthesis recommendation:** ⚠️ **Option B — 3 sessions**
- Prevents noisy single-session feedback from polluting the active constraint set
- Consistent with existing `min_sessions_for_score` pattern (DurabilityConfig default: 3)

---

### Q7: How should deduplication handle a policy_feedback constraint that partially overlaps a human_correction constraint?

**Question:** If policy feedback extracts "don't modify database schema without migration" and an existing human constraint says "always use migration files for schema changes" — semantically same, different text. How to detect and handle?

**Options:**
**A.** Exact text match only (no fuzzy dedup against human constraints) — simple, conservative, may create duplicates
**B.** Detection_hints keyword overlap (2+ shared keywords = likely duplicate) — reuses existing approach from Plan 03-01
**C.** Full semantic similarity check (embedding cosine) — accurate but expensive

**Synthesis recommendation:** ⚠️ **Option B — detection_hints keyword overlap**
- Reuses existing ConstraintExtractor pattern
- Good enough for Phase 13 scale; full semantic dedup is a potential Phase 14 enhancement

---

## Tier 3: Polish Decisions (🔍 Needs Clarification)

### Q8: Should ShadowReporter include state transition labels (green/yellow/red) for policy_error_rate?

**Question:** Beyond the PASS/FAIL gate at 5%, should the report show a green (0-3%) / yellow (3-5%) / red (>5%) status similar to traffic lights?

**Options:**
**A.** Simple PASS/FAIL at 5% threshold — consistent with existing gate pattern
**B.** Three-level color status (0-3% green, 3-5% yellow, >5% red) — richer signal for humans reviewing the report

**Synthesis recommendation:** 🔍 **Option A for Phase 13, Option B as a nice-to-have**
- Existing ShadowReporter gates are all PASS/FAIL — don't introduce new UX patterns unless needed
- Yellow zone can be added as a future enhancement without changing the gate logic

---

## Next Steps (Non-YOLO Mode)

**✋ PAUSED — Awaiting Your Decisions**

1. **Review these 8 questions**
2. **Provide answers** (create CLARIFICATIONS-ANSWERED.md manually, or tell Claude your decisions)
3. **Then run:** `/gsd:plan-phase 13` to create execution plan

---

## Alternative: YOLO Mode

If you want Claude to auto-generate reasonable answers:

```bash
/meta-gsd:discuss-phase-ai 13 --yolo
```

This will:
- Auto-select recommended options (marked ✅ ⚠️ above)
- Generate CLARIFICATIONS-ANSWERED.md automatically
- Proceed to planning without pause

---

*Multi-provider synthesis: OpenAI + Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-20*
*Non-YOLO mode: Human input required*
