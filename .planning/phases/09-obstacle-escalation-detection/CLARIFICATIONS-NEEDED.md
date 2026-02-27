# CLARIFICATIONS-NEEDED.md

## Phase 9: Obstacle Escalation Detection — Stakeholder Decisions Required

**Generated:** 2026-02-19
**Mode:** Multi-provider synthesis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)
**Source:** 3 AI providers analyzed Phase 9 requirements

---

## Decision Summary

**Total questions:** 8
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 3 questions — Should answer for quality
**Tier 3 (Polish):** 1 question — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: What event-type patterns constitute "blocked" and "bypass"?

**Question:** Which specific event types (or message content patterns) define the two ends of the blocked→bypass sequence for the rule-based tagger?

**Why it matters:** The entire O_ESC detection logic is built on this definition. Getting it wrong means false positives (legitimate retries tagged as escalation) or false negatives (real bypasses missed).

**Options identified by providers:**

**A. Existing-type-only (Gemini — simplest)**
- Block = `O_GATE` with negative outcome OR `O_CORR` event
- Bypass = subsequent `T_RISKY` within N turns without intervening `X_PROPOSE`/`X_ASK`
- No message text parsing required
- _(Proposed by: Gemini)_

**B. Text-signal-enhanced (OpenAI — richer)**
- Block = explicit refusal language in assistant messages ("I can't", "requires approval", "forbidden") OR permission errors
- Bypass = "Instead, I'll…" or alternative method pattern + state-changing tool call
- Requires regex patterns on message content
- _(Proposed by: OpenAI)_

**C. FSM-based (Perplexity — most principled)**
- Formal finite state machine with states: IDLE → ATTEMPTING → BLOCKED → ATTEMPTING_ALTERNATIVE
- O_ESC = illegal transition from BLOCKED to ATTEMPTING_ALTERNATIVE without approval state
- Most testable, most implementation work
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A (event-type-only)**
- Leverages existing tagger taxonomy — no new parsing dependencies
- Fastest to implement and test with the 30 objectivism test cases
- Can layer Option B text signals later if recall is insufficient

**Sub-questions:**
- Should O_CORR (user corrections) count as a "block" trigger, or only O_GATE gate-rejects?
- What is the turn window N (3, 5, or 10) between block and bypass?

---

### Q2: Which tools are exempt from "bypass" classification post-rejection?

**Question:** After a rejection/correction, which tool calls should never count as an escalation bypass (because they're read-only or approval-seeking behavior)?

**Why it matters:** Without exemptions, any tool use after a rejection triggers O_ESC — including the agent asking for clarification or reading a file to understand the constraint. This would cause massive false positives.

**Options identified by providers:**

**A. Read-only tool exemption (Gemini — clean)**
- Read, Glob, Grep, WebFetch, WebSearch, Task (research agents) never count as bypass
- Only T_RISKY, T_GIT_COMMIT, Write, Edit, Bash constitute potential bypasses
- _(Proposed by: Gemini, OpenAI)_

**B. Approval-seeking reset (OpenAI — additional)**
- X_ASK or X_PROPOSE following a rejection resets the O_ESC window entirely
- Agent that asks "Should I do X instead?" is not escalating
- _(Proposed by: OpenAI)_

**C. Constraint-equivalence check (Perplexity — thorough)**
- Alternative only counts as bypass if it would satisfy fewer constraints than the original blocked path
- Requires deterministic constraint evaluation function
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A + B**
- Read-only tools exempt + X_ASK/X_PROPOSE resets the window
- Option C is theoretically ideal but requires constraint evaluation infrastructure not yet built

**Sub-questions:**
- Should any specific Bash commands always count as bypass regardless of read/write classification (e.g., `rm -rf`, `chmod 777`)?

---

### Q3: What happens when no existing constraint matches the blocked path?

**Question:** ESCALATE-02 requires O_ESC episodes to link to "the bypassed constraint," but what if no constraint in data/constraints.json covers the blocked path?

**Why it matters:** Without an answer, ESCALATE-02 cannot be implemented — the field would be NULL and the requirement unsatisfied.

**Options identified by providers:**

**A. Link to rejection event only (Gemini — conservative)**
- Store `bypassed_event_ref = <O_GATE event_id>` but no constraint FK
- Avoids premature constraint creation
- _(Proposed by: Gemini)_

**B. Create constraint candidate (OpenAI — proactive)**
- Auto-create a constraint with `status=candidate`, `source=inferred_from_escalation`
- Link O_ESC episode to the new candidate constraint ID
- Human can promote/reject in review queue
- _(Proposed by: OpenAI, Perplexity)_

**C. Require pre-existing constraint (strict)**
- O_ESC episodes only created when the bypassed path is covered by an existing constraint
- Reduces false escalations but misses novel bypasses

**Synthesis recommendation:** ⚠️ **Option B**
- Satisfies ESCALATE-02 deterministically
- Consistent with existing ConstraintExtractor pattern (corrections → constraint candidates)
- Candidate constraints are not enforced until promoted

**Sub-questions:**
- Should constraint candidates appear in Mission Control immediately, or only after session review?
- Should candidate constraints auto-promote to `active` after human approval of O_ESC episode?

---

### Q4: What triggers auto-forbidden constraint generation, and what is the scope?

**Question:** ESCALATE-03 says "escalation episodes without APPROVE reaction generate forbidden constraints automatically." What counts as APPROVE, what is the deadline, and how specific should the generated constraint be?

**Why it matters:** This is a security-sensitive decision. Too aggressive = legitimate work blocked by auto-generated constraints. Too lenient = escalations pass without consequences.

**Options identified by providers:**

**A. Reaction-triggered (Gemini — safest)**
- Only generate `forbidden` constraint if explicit negative reaction follows (O_CORR, O_GATE reject)
- Silence (no reaction) → generate `requires_approval` candidate only (NOT forbidden)
- _(Proposed by: Gemini)_

**B. Silence-as-unapproved (OpenAI — stricter)**
- After session finalization timeout (e.g., 30-min inactivity), no reaction = unapproved
- Generate `forbidden` constraint candidate regardless
- _(Proposed by: OpenAI)_

**C. Threshold-based (Perplexity — most conservative)**
- Require N confirmations of the same pattern before generating any constraint
- Shadow mode validation period before enforcement
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A** for Phase 9 (extend to B/C in later phases)
- Silence in these sessions usually means the action succeeded, not that it was unauthorized
- Generating forbidden constraints from silence would poison the constraint store
- Phase 9 can generate `requires_approval` candidates on silence, `forbidden` candidates on explicit corrections

**Sub-questions:**
- Is the "candidate → active" promotion workflow (review queue) in scope for Phase 9, or just the generation step?
- Should constraint text be: (a) `"Forbid [tool] on [resource]"` structured template, or (b) extracted from the surrounding message text?

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: New episode schema fields for O_ESC

**Question:** What new nullable fields should be added to the `episodes` DuckDB table and Pydantic model for escalation episodes?

**Synthesis recommendation:** ⚠️ Add these nullable columns to the existing `episodes` table:
- `escalate_block_event_ref` (VARCHAR, nullable) — event_id of the blocking event
- `escalate_bypass_event_ref` (VARCHAR, nullable) — event_id of the bypass action
- `escalate_bypassed_constraint_id` (VARCHAR, nullable) — FK to constraints.json constraint_id
- `escalate_approval_status` (VARCHAR, nullable) — PENDING/APPROVED/UNAPPROVED
- `escalate_confidence` (FLOAT, nullable) — detection confidence score

**Sub-questions:**
- Should `orchestrator_action.mode` enum be extended with `ESCALATE`, or is a separate boolean `is_escalation` cleaner?
- Do we need `escalate_detector_version` for future re-detection with improved logic?

---

### Q6: Escalation rate metric definition for shadow mode

**Question:** How should "escalation rate per session" be defined for the ShadowReporter?

**Synthesis recommendation:** ⚠️ Track all three, use `unapproved_escalation_rate` as the headline gate:
- `escalation_count_per_session = count(O_ESC) / count(sessions)` — volume
- `rejection_adherence_rate = 1 - (count(O_ESC) / count(O_GATE_reject + O_CORR))` — compliance
- `unapproved_escalation_rate = count(O_ESC where approval_status=UNAPPROVED) / count(O_ESC)` — severity

**Sub-questions:**
- Which of the three metrics is the Phase 9 acceptance gate (target: 0 unauthorized escalations)?
- Should escalation metrics segment by project or appear aggregate-only in Phase 9?

---

### Q7: Test case sourcing and format

**Question:** Should the 30 test cases come from real objectivism sessions, synthetic JSONL fixtures, or a mix? Must they cover real escalation examples or can they be constructed from the pattern definition?

**Synthesis recommendation:** ⚠️ Mixed approach: mine objectivism sessions for real examples (target 10-15), construct synthetic fixtures for edge cases the real sessions don't cover. Format: minimal JSONL event slices (10-15 events each) in `tests/fixtures/escalation/` with a `ground_truth` label.

**Composition:**
- 15 positive (O_ESC expected): blatant T_RISKY after O_GATE reject (5), delayed bypass within window (5), bypass without intervening X_ASK (5)
- 15 negative (no O_ESC): read-only tools after rejection (5), X_ASK seeking approval (5), bypass after window expired (5)

**Sub-questions:**
- Are there confirmed escalation examples in the objectivism sessions from Phase 7 analysis?
- Can synthetic fixtures be hand-authored, or must they be extracted from real session JSONL?

---

## Tier 3: Can implement with defaults (🔍 Needs Clarification)

### Q8: Idempotency strategy for O_ESC episodes

**Question:** When sessions are reprocessed, how should duplicate O_ESC episodes and duplicate auto-generated constraints be prevented?

**Synthesis recommendation:** 🔍 Use content-derived stable IDs consistent with existing pipeline:
- `o_esc_id = SHA256(session_id + block_event_ref + bypass_event_ref)`
- `constraint_id = SHA256(o_esc_id + constraint_target_signature)`

This follows the existing ConstraintStore SHA-256 pattern and can be implemented without further input.

---

## Next Steps (Non-YOLO Mode)

**✋ PAUSED — Awaiting Your Decisions**

1. **Review the 8 questions above** (4 blocking + 3 important + 1 auto-solved)
2. **Create CLARIFICATIONS-ANSWERED.md** with your decisions (or tell Claude your answers)
3. **Then run:** `/gsd:plan-phase 9` to create the execution plan

---

## Alternative: YOLO Mode

If you want Claude to auto-generate reasonable answers:

```
/meta-gsd:discuss-phase-ai 9 --yolo
```

This will auto-select synthesis recommendations above and proceed to planning.

---

*Multi-provider synthesis: OpenAI gpt-5.2 + Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-19*
*Non-YOLO mode: Human input required*
