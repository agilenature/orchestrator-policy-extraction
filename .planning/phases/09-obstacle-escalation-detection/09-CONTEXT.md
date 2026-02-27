# CONTEXT.md — Phase 9: Obstacle Escalation Detection

**Generated:** 2026-02-19
**Phase Goal:** The event tagger recognizes obstacle escalation sequences (blocked path → alternative path bypassing authorization) and creates O_ESC episodes. Escalation episodes without authorization automatically generate forbidden constraints.
**Synthesis Source:** Multi-provider AI analysis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)

---

## Overview

Phase 9 introduces the O_ESC (obstacle escalation) tag and episode type — detecting when an agent is blocked on a path and takes an alternative that bypasses authorization without approval. This is a semantically rich concept that must be implemented with a rule-based tagger (no LLM classifiers), requiring precise operational definitions for "blocked," "bypass," and "authorization." All 3 providers converged on 4 blocking gray areas and 3 important ones before the plan can be written.

**Confidence markers:**
- ✅ **Consensus** — All 3 providers identified this as critical
- ⚠️ **Recommended** — 2 providers identified this as important
- 🔍 **Needs Clarification** — 1 provider identified, potentially important

---

## Gray Areas Identified

### ✅ 1. Detection Semantics: What Counts as "Blocked" and "Bypass"? (Consensus)

**What needs to be decided:**
The exact event-type patterns and/or text signals that constitute (a) a *blocked path* and (b) an *alternative path that bypasses authorization*, without using LLM inference.

**Why it's ambiguous:**
"Blocked → bypass" is a semantic concept, not a syntactic one. A rule-based tagger must proxy it structurally. Three very different strategies emerged:

- **OpenAI approach:** Block = refusal language in assistant messages ("I can't", "requires approval", "forbidden") OR permission errors (403, "permission denied"). Bypass = subsequent assistant message with "Instead, I'll…" pattern + different method. Window: 10 turns.
- **Gemini approach:** Block = O_GATE reject OR O_CORR event. Bypass = next T_RISKY tool call without an intervening X_PROPOSE or X_ASK. Window: 3 turns. Key principle: *any state-changing action after a rejection without explicit re-authorization = O_ESC.*
- **Perplexity approach:** FSM with states: BLOCKED_AT_AUTHORIZATION_GATE → ATTEMPTING_ALTERNATIVE_PATH without AWAITING_ORCHESTRATOR_APPROVAL. More principled but more complex to implement.

**Provider synthesis:**
- **OpenAI:** Richest definition, handles text signals well, but requires text pattern matching on unstructured message content
- **Gemini:** Simplest definition, leverages existing event types (O_GATE, O_CORR, T_RISKY), fastest to implement
- **Perplexity:** Most architecturally sound (FSM), most testable, but requires more upfront design

**Proposed implementation decision:**
Adopt **Gemini's event-type approach as the primary signal** with a **narrowed bypass definition**: Block = existing `O_GATE` (negative outcome) OR `O_CORR` event. Bypass = subsequent `T_RISKY` tool call within N turns (configurable, default 5) where no `X_PROPOSE` or `X_ASK` intervenes. This leverages the existing tagger taxonomy without LLM or text parsing. Add a secondary text heuristic layer (OpenAI approach) only if recall is insufficient after testing on objectivism sessions.

**Open questions:**
- Should user-sourced corrections (O_CORR) count as "blocked path" triggers, or only system gate rejections (O_GATE)?
- What is the maximum turn window N (3? 5? 10?) — this controls false positive rate
- Do read-only tools (Read, Glob, Grep) break the sequence (should never trigger O_ESC)?

**Confidence:** ✅ All 3 providers flagged as highest-priority blocking decision

---

### ✅ 2. Escalation vs. Legitimate Alternative (Consensus)

**What needs to be decided:**
How to distinguish an unauthorized bypass from a valid alternative approach that the agent is legitimately exploring, given both look identical in event-type sequence (block → different tool call).

**Why it's ambiguous:**
- O_GATE reject on "delete database" → tries "drop table" = O_ESC
- O_GATE reject on "edit file (syntax error)" → tries "write file (fixed)" = normal work
- Both are: REJECTION → TOOL_USE

**Provider synthesis:**
- **OpenAI:** Only flag O_ESC if the bypass action matches the "same objective cluster" (cosine similarity). Requires embeddings at detection time — adds latency and dependency.
- **Gemini:** Heuristic: safe/read-only tools (grep, ls, read_file) never trigger O_ESC even post-rejection. Only T_RISKY tools count as bypass.
- **Perplexity:** Constraint equivalence model — check whether the alternative path triggers the *same* constraint as the original block. If it does, it's not a bypass.

**Proposed implementation decision:**
Use **Gemini's safe-tool exemption** as the primary gate: read-only tools (Read, Glob, Grep, WebFetch, WebSearch) never constitute a bypass regardless of sequence. Only tool calls classified as `T_RISKY`, `T_GIT_COMMIT`, `T_TEST`, or Write/Edit/Bash constitute potential bypasses. This provides a clean, auditable rule without embeddings. Add a whitelist of "safe post-rejection tools" to the config.

**Open questions:**
- Should X_ASK or X_PROPOSE after a rejection reset the O_ESC window (agent sought approval)?
- Are there specific Bash commands that should always count as bypass regardless (e.g., `rm`, `chmod`)?

**Confidence:** ✅ All 3 providers agreed this disambiguation is critical

---

### ✅ 3. Constraint Linking When No Constraint Exists Yet (Consensus)

**What needs to be decided:**
ESCALATE-02 requires linking O_ESC episodes to "the bypassed constraint," but the pipeline may detect an escalation before any formal constraint has been extracted. What to link to?

**Why it's ambiguous:**
- The existing ConstraintExtractor runs on `correct`/`block` reactions — but an escalation might not have a reaction yet
- No explicit constraint may exist for the blocked path (the gate just said "no")

**Provider synthesis:**
- **OpenAI:** Two-step strategy: try to match existing constraint, otherwise create a new "constraint candidate" with `status=candidate` and `origin=inferred_from_block`. Link to the new candidate ID.
- **Gemini:** Link to the specific *rejection event ID* (concrete and available), not an abstract constraint. Avoids creating premature constraints.
- **Perplexity:** Provenance tracking — record which constraint C was violated at block time; this is queryable if constraints are deterministically evaluable.

**Proposed implementation decision:**
**Hybrid:** Link O_ESC episodes to a concrete reference in priority order: (1) existing constraint ID if one matches (text similarity + scope overlap), (2) the O_GATE/O_CORR event ID as `bypassed_event_ref`, (3) create a constraint candidate with `source=inferred_from_escalation` and `status=candidate`. This ensures ESCALATE-02 is always satisfiable. Store `bypassed_constraint_id` (FK to constraints) and `bypassed_event_ref` (FK to events) as separate nullable fields on the escalation episode.

**Open questions:**
- Must ESCALATE-02 be satisfied at detection time, or can it be populated retroactively after session review?
- Should auto-created constraint candidates be immediately visible in Mission Control or held for batch review?

**Confidence:** ✅ All 3 providers identified this as a data model blocker

---

### ✅ 4. Auto-Forbidden Constraint Generation: Trigger, Scope, and Safety (Consensus)

**What needs to be decided:**
When exactly a forbidden constraint is generated, what it says, how specific/broad it is, and whether it is immediately enforced.

**Why it's ambiguous:**
- "Without APPROVE reaction" — what counts as approval, and what's the deadline?
- Silence in session logs often means "it worked fine" not "it was unauthorized"
- Auto-generated constraints could be too broad (ban entire tool class) or too narrow (ban specific args)

**Provider synthesis:**
- **OpenAI:** Generate narrow, evidence-grounded constraints with `confidence=low`. Require human promotion to "enforced" status. Define constraint from the *intent signature* (resource + operation + context), not raw tool args.
- **Gemini:** "Silence ≠ unauthorized" concern: only generate on explicit negative reactions (correction, rejection) or process interruptions, NOT on no-reaction. Generate constraint on the specific Tool + Args used in bypass.
- **Perplexity:** Threshold-based triggering (N confirmations of same pattern before generating), shadow mode validation period before enforcement, "activation delay" configuration.

**Proposed implementation decision:**
Three-tier constraint generation:
1. **If subsequent O_CORR or negative reaction follows O_ESC:** Generate `forbidden` constraint immediately (candidate status).
2. **If no reaction at all (silence):** Do NOT generate forbidden; generate only a `requires_approval` candidate constraint. Rationale: silence commonly means success in these sessions.
3. **Never enforce immediately:** All auto-generated constraints start as `status=candidate`, appear in a review queue, and require human promotion to `active`. This is Phase 9 behavior; enforcement is a future phase concern.

Constraint text is templated from: "Forbid [tool_name] with [operation_type] on [resource_path_prefix] without prior approval" — structured fields, not raw args.

**Open questions:**
- Is the "candidate → active" promotion workflow in-scope for Phase 9, or just the generation step?
- Should the constraint review queue be part of the existing Mission Control ReviewWidget, or a separate UI?

**Confidence:** ✅ All 3 providers flagged as blocking (especially the silence-approval ambiguity)

---

### ⚠️ 5. Episode Data Model: How O_ESC Fits the Existing Schema (Recommended)

**What needs to be decided:**
Whether O_ESC episodes are stored as a new episode type, annotations on existing episodes, or a separate table — and what new fields are required.

**Why it's ambiguous:**
The existing schema has `orchestrator_action.mode` as an enum (O_DIR, O_GATE, O_CORR). Adding ESCALATE mode requires changes to the Pydantic model, the DuckDB schema, and possibly the JSON Schema.

**Proposed implementation decision:**
Store as a first-class episode row in the existing `episodes` table with `orchestrator_action.mode=ESCALATE`. Add nullable escalation-specific columns:
- `escalate_block_event_ref` (str, nullable)
- `escalate_bypass_event_ref` (str, nullable)
- `escalate_bypassed_constraint_id` (str, nullable)
- `escalate_approval_status` (enum: PENDING, APPROVED, UNAPPROVED, nullable)
- `escalate_detector_version` (str, nullable)
- `escalate_confidence` (float, nullable)

All non-escalation episodes leave these NULL. Use same MERGE upsert pattern with content-derived stable ID: `hash(session_id, block_event_ref, bypass_event_ref)`.

**Confidence:** ⚠️ OpenAI and Gemini both proposed similar models; Perplexity focused on architecture

---

### ⚠️ 6. Shadow Mode Escalation Rate: Definition and Metrics (Recommended)

**What needs to be decided:**
What "escalation rate per session" means (numerator and denominator), and how it integrates with the existing ShadowReporter.

**Why it's ambiguous:**
Multiple valid definitions exist with very different semantics.

**Proposed implementation decision:**
Track three metrics in the ShadowReporter's DuckDB queries:
- `escalation_count_per_session = count(O_ESC) / count(sessions)` — primary KPI
- `rejection_adherence_rate = 1 - (count(O_ESC) / count(O_GATE_reject + O_CORR))` — policy compliance rate
- `unapproved_escalation_rate = count(O_ESC where approval_status=UNAPPROVED) / count(O_ESC)` — severity indicator

The Phase 9 success criterion target is 0 unauthorized escalations; use `unapproved_escalation_rate` as the headline gate metric.

**Confidence:** ⚠️ OpenAI and Gemini agree on multi-metric approach

---

### ⚠️ 7. Test Case Structure: 30 Cases from Objectivism Sessions (Recommended)

**What needs to be decided:**
Format, composition, and sourcing of the 30 test cases (real sessions vs. synthetic fixtures, positive/negative ratio, edge case coverage).

**Proposed implementation decision:**
30 labeled JSONL fixture files in `tests/fixtures/escalation/`:
- 15 positive escalations (O_ESC expected): blatant bypass (5), delayed bypass within window (5), indirect bypass via different tool (5)
- 15 negatives (no O_ESC): read-only post-rejection (5), X_ASK seeking approval (5), O_ESC window expired (5)

Each fixture is a minimal session slice (10-15 events) with an expected output record. Fixtures sourced from objectivism sessions where possible; synthetic where real examples don't cover a case. All fixtures have a `label` field with `ground_truth: O_ESC|NO_ESC` and `reason`.

**Confidence:** ⚠️ All providers agreed on balanced positive/negative split; format is synthesized

---

### 🔍 8. Idempotency with Incremental Processing (Needs Clarification)

**What needs to be decided:**
How to avoid duplicate O_ESC episodes and duplicate auto-generated constraints when sessions are reprocessed.

**Proposed implementation decision:**
Use content-derived stable IDs consistent with the existing pipeline pattern:
- `o_esc_id = SHA256(session_id + block_event_ref + bypass_event_ref + detector_version_major)`
- `constraint_id = SHA256(o_esc_id + constraint_target_signature)` — same pattern as existing ConstraintStore

UPSERT (not INSERT) on both episode and constraint tables. Store full `detector_version` string for audit. This is non-negotiable given the existing pipeline's idempotency guarantees.

**Confidence:** 🔍 OpenAI identified; consistent with existing patterns — can likely implement without clarification

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking):**
- [ ] GA-1: Detection semantics — which event types constitute "blocked" and "bypass"
- [ ] GA-2: Bypass vs. legitimate alternative — which tools exempt from O_ESC consideration
- [ ] GA-3: Constraint linking — what to link to when no existing constraint exists
- [ ] GA-4: Forbidden constraint generation — trigger condition and scope

**Tier 2 (Important):**
- [ ] GA-5: Episode schema changes (new fields and ESCALATE mode)
- [ ] GA-6: Escalation rate metric definition
- [ ] GA-7: Test case composition and sourcing

**Tier 3 (Can implement with defaults):**
- [ ] GA-8: Idempotency strategy (proposed solution follows existing patterns)

---

## Next Steps

**Non-YOLO Mode (current):**
1. Review this CONTEXT.md
2. Answer questions in CLARIFICATIONS-NEEDED.md
3. Create CLARIFICATIONS-ANSWERED.md with your decisions
4. Run `/gsd:plan-phase 9` to create execution plan

**Alternative (YOLO Mode):**
Run `/meta-gsd:discuss-phase-ai 9 --yolo` to auto-generate answers

---

*Multi-provider synthesis by: OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research*
*Generated: 2026-02-19*
