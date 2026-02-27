# CONTEXT.md — Phase 13: Policy-to-Constraint Feedback Loop

**Generated:** 2026-02-20
**Phase Goal:** Close the feedback loop — when the trained policy recommends an action that a human subsequently blocks or corrects, that correction automatically propagates back into the constraint store and guardrail system. The policy becomes a source of new constraints, not just a consumer of them.
**Synthesis Source:** Multi-provider AI analysis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)
**Note:** OpenAI ran successfully (exit 0) but response content was not captured in output; synthesis based primarily on Gemini Pro and Perplexity Sonar Deep Research, which were in strong consensus on all 5 gray areas.

---

## Overview

Phase 13 closes the feedback loop between the policy's recommendations and the constraint system. Both providers identified the same 5 gray areas, which is an unusually strong signal. The gray areas cluster around: (1) how to detect "blocked" recommendations in an offline/shadow context, (2) how to wire the pre-surfacing check before recommendations reach humans, (3) how policy-feedback constraints coexist with human-sourced ones, (4) what the policy error rate metric actually counts, and (5) where the new pipeline steps slot in.

A critical architectural insight from both providers: **this project is batch/offline**, not real-time session serving. Phase 13 should implement the feedback loop within the existing shadow mode infrastructure (ShadowModeRunner + ShadowReporter), not by building a real-time streaming layer. The shadow runs already simulate policy recommendations against historical sessions — that's where the feedback detection belongs.

**Confidence markers:**
- ✅ **Consensus** — Both Gemini and Perplexity identified this as critical
- ⚠️ **Recommended** — One provider emphasized this as important
- 🔍 **Needs Clarification** — Worth resolving but lower stakes

---

## Gray Areas Identified

### ✅ 1. Feedback Trigger Detection — How to Identify a "Blocked" Policy Recommendation (Consensus)

**What needs to be decided:**
In shadow mode, the policy generates a recommendation against a historical session. The human's actual reaction exists in the session log. How do we determine that the human "would have blocked" the policy recommendation?

**Why it's ambiguous:**
The system is offline/batch. The policy wasn't running when the original session happened — the human reacted to the actual assistant action, not to a policy recommendation. We need a mapping rule: "does the historical human correction count as a block of the policy recommendation?"

**Provider synthesis:**
- **Gemini:** Proposed "Counterfactual Lookahead" — if policy recommendation is semantically similar to the historical assistant action AND the next human message is a correction/block, treat as "blocked." If they diverge, no inference is possible (avoid false positives).
- **Perplexity:** Proposed a three-tier real-time mechanism; however, noted that for the batch architecture, deferred batch aggregation is the right approach. The key signal is: human's next action being a correction or block (existing ReactionLabeler output).

**Synthesized recommendation:**
Use the existing `ReactionLabeler` output already computed during shadow evaluation. A policy recommendation is "blocked" when:
1. The recommendation is surfaced (passed pre-surfacing check — see GA #2)
2. The subsequent human reaction is `block` or `correct` (from ReactionLabeler)
3. The policy recommendation text and historical assistant action are in the same episode boundary

No semantic similarity threshold needed for Phase 13 — use episode co-location as the proxy for "same decision context." This avoids building a semantic similarity scorer.

**Open questions:**
- What if the policy recommendation is completely different from the historical action (policy chose mode B, human was correcting mode A)? Decision: If reaction is `block`/`correct` in the same episode, the feedback applies — the policy is operating in the same decision context and the correction is relevant.

**Confidence:** ✅ Both providers agreed this is blocking

---

### ✅ 2. Pre-Surfacing Constraint Check Architecture (Consensus)

**What needs to be decided:**
FEEDBACK-03 requires suppressing policy recommendations that conflict with active constraints *before* they reach the human. How is this check implemented? What triggers a "conflict"?

**Why it's ambiguous:**
The ConstraintStore contains natural language constraints with `detection_hints`. Recommendations are also natural language. A full semantic check is expensive. The project already has precedent for hint-based matching (AmnesiaDetector, EscalationDetector use case-insensitive substring containment). Does that generalize?

**Provider synthesis:**
- **Gemini:** Proposed RAG-based verification (embed recommendation → vector search → LLM entailment check). Acknowledged the O(N) problem for naive checks.
- **Perplexity:** Proposed an offline ConstraintViolationIndex (patterns compiled from constraints, stored in DuckDB, loaded at session start). Pattern matching is synchronous and cheap.

**Synthesized recommendation:**
Use the same **detection_hints substring matching** approach already established in Phases 9-10 (EscalationDetector, AmnesiaDetector). Specifically:
1. Load active constraints from ConstraintStore (those with status `active`)
2. Pre-compile detection_hints as case-insensitive patterns (same pattern as `AmnesiaDetector._build_hint_patterns`)
3. Check recommendation text against each constraint's hints
4. If match found AND constraint severity is `forbidden` or `requires_approval`: suppress and log as PolicyError
5. `warning` severity constraints: log but do not suppress

This reuses existing infrastructure and avoids building a vector-search + LLM entailment pipeline. The hint patterns are already designed for this kind of detection.

**Open questions:**
- What if a constraint has no detection_hints? Decision: Fall back to scope path matching (if the recommendation's implied scope overlaps with the constraint's scope paths, flag for review but don't hard-suppress — log as a `scope_overlap_warning`).

**Confidence:** ✅ Both providers agreed this architecture decision is blocking

---

### ✅ 3. Constraint Attribution and Deduplication (Consensus)

**What needs to be decided:**
When a policy-feedback constraint is extracted, how does it interact with the existing ConstraintStore? What if an equivalent `human_correction` constraint already exists? What SHA-256 ID scheme ensures distinctness?

**Why it's ambiguous:**
The ConstraintStore uses `SHA-256(text + scope_paths)` for dedup. If a `policy_feedback` constraint has the same text and scope as a `human_correction` constraint, they'd get the same SHA-256 ID under the current scheme. But FEEDBACK-02 requires they be distinguishable.

**Provider synthesis:**
- **Gemini:** Include `source` field in SHA-256 computation so `policy_feedback` constraints have distinct IDs from `human_correction` ones even for identical text. If a `human_correction` version already exists, sit alongside rather than replace.
- **Perplexity:** Agreed on distinct IDs. Proposed that when a `policy_feedback` constraint matches an existing `human_correction` constraint (by semantic similarity), increment a `confirmation_count` on the existing constraint rather than creating a duplicate. Human constraints take precedence in severity conflicts — never downgrade a `forbidden` to `requires_approval` based on policy feedback.

**Synthesized recommendation:**
1. **SHA-256 scheme:** Change to `SHA-256(text + JSON.dumps(sorted(scope_paths)) + source)` — this ensures `policy_feedback` constraints have distinct IDs from `human_correction` constraints even for identical text/scope.
2. **Dedup logic:** Before inserting a `policy_feedback` constraint, check for an existing constraint with `source: human_correction` and matching text (fuzzy match via shared detection_hints keywords, same as existing `ConstraintExtractor` prefix matching). If found: enrich the existing constraint's `examples` array with the policy feedback episode as a new reference (same as existing dedup enrichment in Plan 03-02). Do NOT create a separate entry — the human constraint already covers it.
3. **If no human constraint exists:** Insert as new entry with `source: policy_feedback`. Durability tracking (Phase 10) applies identically.
4. **Severity rule:** Never set `policy_feedback` constraint severity higher than the corresponding human constraint if one exists. Policy feedback can only *confirm* or *add new* constraints, not relax or escalate human-imposed ones.

**Open questions:**
- Should `policy_feedback` constraints be subject to the same `candidate`/`active` lifecycle? Decision: Yes — start as `candidate` with a `min_sessions` threshold (e.g., 3 sessions triggering feedback) before promoting to `active`.

**Confidence:** ✅ Both providers agreed this is a blocking data model decision

---

### ✅ 4. Policy Error Rate Metric Definition (Consensus)

**What needs to be decided:**
The exact formula for `policy_error_rate`. What counts as an error? What's the denominator? What DuckDB table holds this? Where does it appear in ShadowReporter?

**Why it's ambiguous:**
Two types of policy failure exist: (a) suppressed before surfacing (guardrail catch), (b) surfaced and then blocked by human. The requirement says "suppressed and logged as policy errors" — this implies the metric is about guardrail suppression. But shadow mode also reveals recommendations that weren't suppressed but got human corrections.

**Provider synthesis:**
- **Gemini:** `error_rate = (count(suppressed) + count(surfaced & blocked)) / total_recommendations_generated`. Both types count.
- **Perplexity:** Defined multi-dimensional metric — atomic PolicyError events with severity filter (only critical/high count toward rate). Rolling 100-session window with hysteresis for state transitions. Integrate into ShadowReporter as a new PASS/FAIL gate.

**Synthesized recommendation:**
Follow Gemini's simpler formula with Perplexity's ShadowReporter integration:
- **Numerator:** `count(policy_errors)` where policy_error = (1) suppressed by pre-surfacing check OR (2) surfaced AND subsequent human reaction = `block` or `correct`
- **Denominator:** `count(total_recommendations_attempted)` — all recommendations that the policy tried to generate (including those suppressed)
- **Window:** Rolling 100-session average (store per-session rate in DuckDB `policy_error_events` table)
- **PASS/FAIL gate:** `policy_error_rate < 0.05` — added to ShadowReporter alongside `amnesia_rate`, `escalation_rate`
- **DuckDB table:** `policy_error_events (error_id VARCHAR PRIMARY KEY, session_id VARCHAR, recommendation_id VARCHAR, error_type VARCHAR CHECK IN ('suppressed', 'surfaced_and_blocked'), constraint_id VARCHAR, detected_at TIMESTAMPTZ)`

**Open questions:**
- Should errors from `warning`-severity suppression count? Decision: No — only `forbidden` and `requires_approval` suppressions count as errors (parallel to the severity filter in `check-scope` command from Phase 11).

**Confidence:** ✅ Both providers agreed this metric definition is required before planning

---

### ✅ 5. Pipeline Integration Ordering (Consensus)

**What needs to be decided:**
Where do the new Phase 13 steps fit in the existing pipeline? Current Step 15 is ShadowReporter. The feedback loop needs to run after shadow evaluation (to capture blocked recommendations) but before reporting.

**Why it's ambiguous:**
The existing pipeline:
- Step 13: Escalation detection
- Step 14: Constraint durability evaluation
- Step 15: Stats computation / ShadowReporter

Phase 13 adds: (a) pre-surfacing check (runs during shadow evaluation, modifying ShadowModeRunner), (b) feedback extraction (after shadow evaluation, before reporting), (c) policy error rate computation (in ShadowReporter).

**Provider synthesis:**
- **Gemini:** Proposed sequential workflow: Retrieval → Generation → Guardrail (pre-surfacing check) → Shadow evaluation → Feedback extraction → Reporting.
- **Perplexity:** Confirmed same order. Emphasized that constraint store updates (from feedback) should be batched after shadow evaluation, not during it (prevents mid-run constraint table mutations that would invalidate earlier results in the same batch).

**Synthesized recommendation:**
Phase 13 pipeline modifications:
1. **ShadowModeRunner** (existing): Add pre-surfacing check inside `run_shadow_episode()` before returning recommendation. If suppressed, record `PolicyError(type='suppressed')` and return null/suppressed sentinel.
2. **New Step 14.5 (PolicyFeedbackExtractor):** After shadow evaluation (Step 14) completes for a session, detect surfaced-and-blocked recommendations → extract constraints with `source=policy_feedback` → write to ConstraintStore (candidate status) → write to `policy_error_events` (type='surfaced_and_blocked').
3. **ShadowReporter** (existing, Step 15): Add `policy_error_rate` computation from `policy_error_events` table. Add PASS/FAIL gate: `< 5%`.

No new top-level pipeline step needed — the feedback extraction is wired into ShadowModeRunner + ShadowReporter, which is where the policy operation lives.

**Open questions:**
- Should `ConstraintStore` updates from policy feedback be written per-session or batched? Decision: Per-session writes are safe since ConstraintStore uses JSON file with existing dedup logic. No batching needed at Phase 13 scale.

**Confidence:** ✅ Both providers agreed on ordering

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking):**
- [ ] Feedback trigger detection: use episode co-location + ReactionLabeler output (no semantic similarity scorer)
- [ ] Pre-surfacing check: use existing detection_hints substring matching (same as AmnesiaDetector)
- [ ] Constraint attribution: SHA-256 includes source field; dedup against human constraints via hint matching
- [ ] Policy error rate formula: (suppressed + surfaced_and_blocked) / total_attempted, rolling 100-session window
- [ ] Pipeline ordering: pre-surfacing inside ShadowModeRunner, feedback extraction as Step 14.5, metric in ShadowReporter

**Tier 2 (Important):**
- [ ] Candidate status for new policy_feedback constraints: start as `candidate`, promote after 3 sessions
- [ ] Severity authority: human_correction constraints always take precedence over policy_feedback severity
- [ ] Warning severity: log but don't suppress (only forbidden/requires_approval trigger suppression)

**Tier 3 (Polish):**
- [ ] PolicyError classification by type (suppressed vs surfaced_and_blocked) for debugging
- [ ] ShadowReporter state transitions (green/yellow/red) based on policy_error_rate thresholds

---

*Multi-provider synthesis by: OpenAI gpt-5.2 (ran but response not captured), Gemini Pro, Perplexity Sonar Deep Research*
*Generated: 2026-02-20*
