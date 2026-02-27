# CONTEXT.md — Phase 10: Cross-Session Decision Durability

**Generated:** 2026-02-20
**Phase Goal:** Track which constraints were read, honored, and violated in each session. A decision durability index gives each constraint a survival score (durability_score = sessions_honored / sessions_active). Sessions that violate active constraints are flagged as amnesia events.
**Synthesis Source:** Multi-provider AI analysis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)

---

## Overview

Phase 10 introduces cross-session memory into the pipeline: constraints extracted in past sessions must be "remembered" and checked against future sessions. The core challenge is not the data structure — the existing constraint store and DuckDB schema are well-positioned — but rather the **operational semantics**: what it means for a constraint to be "active," "relevant," "honored," or "violated" in a given session context.

All 3 providers converged on 4 blocking ambiguities and 3 important implementation decisions. The synthesis below organizes these by confidence tier.

**Confidence markers:**
- ✅ **Consensus** — All 3 providers identified this as critical
- ⚠️ **Recommended** — 2 providers identified this as important
- 🔍 **Needs Clarification** — 1 provider identified, potentially important

---

## Gray Areas Identified

### ✅ 1. Decisions vs. Constraints Entity Relationship (Consensus)

**What needs to be decided:**
The requirement introduces `data/decisions.json` storing "ACTIVE/SUPERSEDED scope, method, and architecture decisions." But constraints already exist in `data/constraints.json` with `active/candidate/retired` lifecycle. Are these two separate entities with parallel tracking, or one unified abstraction?

**Why it's ambiguous:**
- "Decisions" in the requirement feel like architectural principles (e.g., "use DuckDB for storage", "use decision-point episodes not turn-level")
- "Constraints" are behavioral rules (e.g., "never commit directly to main", "always extract constraints from block reactions")
- If both feed into durability/amnesia tracking, a single auditing engine is simpler; if they're distinct, they need separate lifecycle management
- Phase 9 already uses `active/candidate/retired` for constraints; `ACTIVE/SUPERSEDED` would be a second conflicting lifecycle

**Provider synthesis:**
- **OpenAI:** Treat constraints as canonical auditable unit; `decisions.json` entries should link to constraints via `source_decision_id`. Decisions are metadata that annotate constraints, not primary audit targets.
- **Gemini:** Don't create `decisions.json` as a separate source of truth. Extend `constraints.json` with a `type` field (`constraint` vs `architectural_decision`). If `decisions.json` is needed, make it a derived view.
- **Perplexity:** Use separate data models (ADR format for architectural decisions, SHA-256 for behavioral constraints) but track decision-constraint dependencies so superseding a decision cascades updates to dependent constraints.

**Proposed implementation decision:**
Extend `constraints.json` schema with `type: "behavioral_constraint" | "architectural_decision"`. Both use the existing `active/candidate/retired` lifecycle. Architectural decisions additionally carry `supersedes: [id]` linkage. No separate `decisions.json` file created — the requirement meant documenting key decisions in the constraint store, not a parallel registry.

**Open questions:**
- Should architectural decisions surface in `audit session` output separately from behavioral constraints?
- When an architectural decision is retired, should dependent behavioral constraints auto-retire?

**Confidence:** ✅ All 3 providers agreed this is blocking

---

### ✅ 2. "Honored" vs. "Violated" Operational Definition (Consensus)

**What needs to be decided:**
A concrete, evidence-grounded definition for `sessions_honored` that can be computed deterministically from the event stream. Without this, the durability score formula is undefined.

**Why it's ambiguous:**
- A session that never had the opportunity to violate a constraint (e.g., a documentation session for a "no direct commits" constraint) is not the same as a session that had the opportunity and complied
- Existing constraints have `hint_patterns` (regex patterns for detection) — these should drive violation detection
- Three logical states exist: HONORED (had opportunity, complied), VIOLATED (had opportunity, didn't comply), UNKNOWN/IRRELEVANT (never had opportunity)
- "Evidence grounding" is a project-wide constraint — violation claims must be anchored to specific event data

**Provider synthesis:**
- **OpenAI:** Three-state evaluation: `HONORED | VIOLATED | UNKNOWN`. Violated requires grounded evidence (specific event/tool output/quoted snippet). Otherwise UNKNOWN. Exclude UNKNOWN from denominator.
- **Gemini:** Honored = In Scope + Active + Not Violated. Use heuristic verification (grep hint_patterns against session events). If no heuristic possible, rely on explicit failure signals.
- **Perplexity:** Multi-level compliance hierarchy: Strong Violation (direct log evidence) > Procedural Block (system prevented action) > Approved Exception > Intentional Compliance > Implicit Compliance. Only sessions with Strong Violation or Unapproved Exception trigger amnesia events.

**Proposed implementation decision:**
Use 3-state evaluation: `HONORED | VIOLATED | UNKNOWN`.
- **VIOLATED**: At least one event in session matches a constraint's `hint_patterns` AND the constraint scope overlaps session scope. Evidence = the matching event(s).
- **HONORED**: Constraint scope overlaps session scope BUT no `hint_patterns` match found.
- **UNKNOWN/IRRELEVANT**: Constraint scope does not overlap session scope — excluded from durability calculation entirely.

This maps directly onto existing constraint schema (`hint_patterns`, `scope_paths`) without new infrastructure.

**Open questions:**
- Should escalation episodes (O_ESC mode) auto-qualify as VIOLATED for the bypassed constraint?
- Should UNKNOWN count against the score (conservative) or be excluded (optimistic)?

**Confidence:** ✅ All 3 providers agreed this is blocking

---

### ✅ 3. Durability Score Denominator: What Counts as "sessions_active" (Consensus)

**What needs to be decided:**
The formula `durability_score = sessions_honored / sessions_active` requires defining `sessions_active`. Naive counting (all sessions where constraint existed) produces meaningless inflated scores.

**Why it's ambiguous:**
- A constraint about "Python code quality" should not count a documentation-only session in its denominator
- Constraints extracted from past sessions will have zero historical data for sessions processed before they existed (cold start)
- Constraints added retroactively cannot be evaluated against sessions that ran before they were created — it would be unfair to flag those as violations

**Provider synthesis:**
- **OpenAI:** `sessions_active` = sessions where constraint is ACTIVE at session time AND constraint scope overlaps session scope. UNKNOWN counts in denominator (conservative — penalizes insufficient surfacing).
- **Gemini:** `sessions_active` = sessions after constraint creation date where session scope overlaps constraint scope. Sessions where scope doesn't overlap are excluded entirely from numerator and denominator.
- **Perplexity:** Add temporal lifecycle: `activation_timestamp` determines when measurement begins. Cold start sessions (before activation) are excluded. Grace period sessions (shortly after creation) also excluded. Track `sessions_excluded_due_to_cold_start` for transparency.

**Proposed implementation decision:**
`sessions_active` = sessions where:
1. Session `start_time >= constraint.created_at` (constraint existed)
2. Session scope paths intersect constraint scope_paths (using existing bidirectional prefix matching from Phase 5)
3. Constraint status was `active` at session time (use `status_history` for historical accuracy)

UNKNOWN sessions are excluded from both numerator and denominator (optimistic — avoids penalizing system for undetectable compliance).

Cold start: constraints without historical data show `durability_score = None` until first active session is processed.

**Open questions:**
- What's the minimum `sessions_active` count before showing a score vs. "insufficient data"? (Suggest: 3)

**Confidence:** ✅ All 3 providers agreed this is blocking

---

### ✅ 4. Temporal Versioning: Constraint State at Session Time (Consensus)

**What needs to be decided:**
`constraints.json` stores current state. To accurately compute "was this constraint active when this session ran?" we need point-in-time constraint status lookup.

**Why it's ambiguous:**
- A constraint retired last week should not flag sessions from 6 months ago as amnesia events
- A constraint that was `candidate` (not yet enforced) during a session should not retroactively generate violations
- Without temporal history, durability calculations drift as constraints change status

**Provider synthesis:**
- **OpenAI:** Append-only event log: `data/constraint_events.jsonl` with events `CREATED/UPDATED/SUPERSEDED/RETIRED` + timestamps. Replay to compute state at any time T. Keep `constraints.json` as materialized snapshot.
- **Gemini:** Add `status_history: [{status, timestamp}]` array to each constraint in `constraints.json`. When auditing a session at time T, find the status entry where `timestamp <= T`.
- **Perplexity:** Temporal constraint lifecycle with `activation_timestamp` and `activation_strategy`. Separate `ACTIVE` from "active at time T" — only the latter matters for historical computation.

**Proposed implementation decision:**
Add `status_history: list[{status: str, changed_at: str}]` to constraint schema. When a constraint's status changes, append to history. Keep existing `status` field as current state. Add `created_at` as the immutable creation timestamp. Constraint status at session time T = last history entry with `changed_at <= session.start_time`.

This is schema-only change to `constraints.json` and the `ConstraintStore` Python class — no new files.

**Open questions:**
- Should the initial `status_history` be backfilled for existing constraints (set created_at as first entry)?

**Confidence:** ✅ All 3 providers agreed this is blocking

---

### ⚠️ 5. Detection Method: Rule-Based vs. LLM-Based (Recommended)

**What needs to be decided:**
How does the system actually determine if a constraint was violated? The existing constraint schema has `hint_patterns` (regex) — use these, or build something more sophisticated?

**Why it's ambiguous:**
- Constraint violations can be subtle (e.g., "always ask before deleting files" may require understanding intent, not just pattern matching)
- LLM-based detection would be more accurate but introduces non-determinism and cost
- The "evidence grounding" project constraint requires anchor to specific observable data

**Provider synthesis:**
- **OpenAI:** Deterministic-first: rule-based detectors using hint_patterns for known constraint types. Optional embedding-based retrieval for evidence spans. No LLM in critical path.
- **Gemini:** Regex/keyword heuristics only for Phase 10 MVP. Don't attempt semantic violation detection. Block development stall on building "AI Judge."
- (Perplexity: multi-signal framework, but consistent with rule-based primary)

**Proposed implementation decision:**
Use existing `hint_patterns` (already on constraints) as the violation detection mechanism. Each constraint's `hint_patterns` is a list of regex patterns applied against event payload text in the session. If any pattern matches, candidate violation found. Cross-reference with scope matching for final verdict. No LLM calls in detection path.

**Confidence:** ⚠️ 2 providers strongly recommended

---

### ⚠️ 6. Session Scope Derivation (Recommended)

**What needs to be decided:**
The audit must surface constraints "relevant to current task scope." Where does "session scope" come from? User input? Derived from events?

**Why it's ambiguous:**
- Sessions are streams of events — scope emerges during execution (files opened, paths mentioned)
- Requiring user to specify `--scope` makes the audit cumbersome
- Automatic inference may miss scope or over-include

**Provider synthesis:**
- **Gemini:** Derive scope from set of file paths modified or read in session logs. Decision: derive dynamically from events.
- **Perplexity:** Multi-dimensional scope (files, operations, user, time, environment) but primary axis is file paths.

**Proposed implementation decision:**
Derive session scope from:
1. File paths in tool call payloads (Read/Edit/Write/Bash with file args)
2. Paths mentioned in classification tags (O_DIR messages often contain path context)
3. Fall back to repo-wide scope if no paths detected

This is consistent with how the existing `ConstraintExtractor` infers scope from corrections.

**Confidence:** ⚠️ 2 providers identified

---

### 🔍 7. DuckDB Tables for Evaluation State (Needs Clarification)

**What needs to be decided:**
Where to persist per-session evaluation results (HONORED/VIOLATED/UNKNOWN for each constraint × session pair)?

**Why it's ambiguous:**
- `constraints.json` grows unwieldy if per-session eval data is embedded in it
- DuckDB is already in the stack for episodes
- Recomputation from raw event stream may be expensive

**Provider synthesis:**
- **OpenAI:** Two DuckDB tables: `session_constraint_eval(session_id, constraint_id, eval, evidence_json, ...)` and `amnesia_events(session_id, constraint_id, ...)`. Recompute durability from these tables on demand.

**Proposed implementation decision:**
Add two tables to DuckDB: `session_constraint_eval` and `amnesia_events`. Computed lazily — run `audit session` command triggers evaluation for that session and stores results. Durability score computed on demand via SQL aggregation over `session_constraint_eval`.

**Confidence:** 🔍 1 provider (but aligns well with existing DuckDB patterns)

---

## Summary: Decision Checklist

**Tier 1 — Blocking (must resolve before planning):**
- [ ] Decisions vs. constraints entity model: unified `constraints.json` with `type` field?
- [ ] Honored/Violated/Unknown 3-state definition and evidence standard
- [ ] `sessions_active` denominator: scope-intersection + temporal validity
- [ ] `status_history` schema addition for point-in-time constraint state

**Tier 2 — Important (should resolve for quality):**
- [ ] Detection method: hint_patterns as primary violation detector confirmed?
- [ ] Session scope derivation: file paths from events vs. user-provided?

**Tier 3 — Implementation details (can decide during planning):**
- [ ] DuckDB table schema for `session_constraint_eval` and `amnesia_events`
- [ ] CLI contract: `audit session` arguments, output format, exit codes
- [ ] Minimum `sessions_active` count before showing confidence score

---

*Multi-provider synthesis by: OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research*
*Generated: 2026-02-20*
