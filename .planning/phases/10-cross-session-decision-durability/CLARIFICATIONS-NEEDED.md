# CLARIFICATIONS-NEEDED.md

## Phase 10: Cross-Session Decision Durability — Stakeholder Decisions Required

**Generated:** 2026-02-20
**Mode:** Multi-provider synthesis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)
**Source:** 3 AI providers analyzed Phase 10 requirements

---

## Decision Summary

**Total questions:** 7
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 2 questions — Should answer for quality
**Tier 3 (Polish):** 1 question — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: Decisions vs. Constraints — Unified or Separate?

**Question:** Should `data/decisions.json` be a new separate file tracking architectural decisions (scope choices, method choices, DuckDB vs alternatives, etc.) — or should these be stored as a new `type` in the existing `constraints.json`?

**Why it matters:**
- Two parallel registries (constraints.json + decisions.json) with different lifecycles creates a dual-audit problem: both must be checked for each session
- Phase 9 already established `active/candidate/retired` lifecycle for constraints; the requirement mentions `ACTIVE/SUPERSEDED` which conflicts
- If architectural decisions generate behavioral constraints (e.g., "we use DuckDB" → "never use SQLite"), the link must be maintained somewhere

**Options identified:**

**A. Unified: Extend `constraints.json` with `type` field (Recommended)**
- Add `type: "behavioral_constraint" | "architectural_decision"` to schema
- Both types use same `active/candidate/retired` lifecycle
- Architectural decisions additionally carry `supersedes: [id]` linkage
- `decisions.json` is not created (or is a derived view only)
- _(Proposed by: OpenAI, Gemini)_

**B. Separate: Create `data/decisions.json` with its own schema**
- Decisions stored separately with ADR-format (context, decision, consequences, rationale)
- Decisions link to constraints they generate via `generated_constraints: [id]`
- Two separate CLI commands: `audit constraints` and `audit decisions`
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A — Unified in constraints.json**
- Aligns with existing Phase 9 infrastructure (no new file)
- Single audit engine
- Architectural decisions can carry the same scope/severity/hint_patterns fields

**Sub-questions:**
- Should architectural decisions (`type=architectural_decision`) appear in shadow mode reports?
- Should retiring an architectural decision auto-retire linked behavioral constraints?

---

### Q2: What Does "Constraint Honored" Mean?

**Question:** How do we define `sessions_honored` in a way that is deterministic, evidence-grounded, and computable from the event stream without requiring LLM judgment?

**Why it matters:**
- `durability_score = sessions_honored / sessions_active` — the metric is useless without a precise numerator definition
- "Evidence grounding" is a core project constraint — claiming a constraint was honored/violated requires anchoring to specific observable events
- Need a clear rule that unit tests can verify

**Options identified:**

**A. 3-State with hint_patterns (Recommended)**
- **VIOLATED**: A constraint's `hint_patterns` regex matches at least one event payload in the session AND constraint scope overlaps session scope. Evidence = matching event(s).
- **HONORED**: Constraint scope overlaps but no hint_patterns match found in session events.
- **UNKNOWN/IRRELEVANT**: Constraint scope does not overlap session scope — excluded from both numerator and denominator.
- _(Proposed by: OpenAI, Gemini, Perplexity — all converged on 3-state)_

**B. Binary with explicit "opportunity" detection**
- Only count session in denominator if system detected an "opportunity" to violate (e.g., file matching scope was actually edited)
- Harder to define "opportunity" without LLM interpretation
- _(Proposed by: none — rejected by all providers as too complex for Phase 10)_

**Synthesis recommendation:** ✅ **Option A — 3-state with hint_patterns**
- Leverages existing `hint_patterns` already on every constraint
- Deterministic and testable
- Evidence = specific event JSON, groundable

**Sub-questions:**
- Should O_ESC episodes (escalation bypass) auto-qualify as VIOLATED for the bypassed constraint? (Likely yes — Phase 9 already links escalation to bypassed_constraint_id)
- Should UNKNOWN sessions count in denominator (conservative) or be excluded (optimistic)? Synthesis suggests: **exclude** (optimistic — avoids penalizing undetectable compliance)

---

### Q3: Durability Score Denominator — What Is "sessions_active"?

**Question:** Which sessions count in the `sessions_active` denominator for a given constraint?

**Why it matters:**
- A constraint about Python import style should not count a session that only edited markdown files
- Counting all sessions inflates scores to near-100% (meaningless)
- A constraint added retroactively cannot fairly be measured against sessions from before it existed

**Options identified:**

**A. Scope-intersection + temporal validity (Recommended)**
- `sessions_active` = sessions where:
  1. `session.start_time >= constraint.created_at` (constraint existed)
  2. Session's derived scope_paths intersect constraint's scope_paths (bidirectional prefix matching, same as Phase 5)
  3. Constraint status was `active` at session time (point-in-time lookup)
- UNKNOWN/IRRELEVANT sessions excluded from denominator
- _(Proposed by: All 3 providers converged on this logic)_

**B. All sessions after constraint creation**
- Simple but produces inflated scores
- _(Rejected by all providers)_

**Synthesis recommendation:** ✅ **Option A — scope-intersection + temporal validity**
- Bidirectional prefix matching already implemented in Phase 5 scope validation
- Temporal validity requires Q4 solution (status_history)

**Sub-questions:**
- Minimum `sessions_active` count before showing score vs. "insufficient data"? Suggest: **3 sessions minimum**

---

### Q4: Temporal Versioning — Constraint State at Session Time

**Question:** When auditing a historical session, how do we know what the constraint's status was at the time that session ran (not its current status)?

**Why it matters:**
- A constraint currently `retired` may have been `active` when a session ran last month
- Without temporal history, retiring a constraint would clear all its historical amnesia flags
- New constraints would incorrectly generate retroactive amnesia events for sessions before the constraint existed

**Options identified:**

**A. `status_history` array in constraints.json (Recommended)**
- Add `status_history: [{status: str, changed_at: ISO8601}]` to each constraint
- Existing `status` field remains as current state
- When auditing session at time T: find last `status_history` entry with `changed_at <= session.start_time`
- `created_at` serves as activation timestamp
- _(Proposed by: OpenAI, Gemini)_

**B. Separate append-only event log (`data/constraint_events.jsonl`)**
- All mutations logged with CREATED/UPDATED/SUPERSEDED/RETIRED events
- Full audit trail for compliance purposes
- `constraints.json` remains a derived materialized view
- _(Proposed by: OpenAI as alternative, Perplexity variation)_

**Synthesis recommendation:** ✅ **Option A — status_history in constraints.json**
- Simpler than a separate event log
- Consistent with project pattern (keep JSON stores simple, DuckDB for complex queries)
- Append-only event log is over-engineered for a local development tool

**Sub-questions:**
- Should existing constraints get a backfilled `status_history` entry using current status + `created_at`? (Yes — migration script)

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Violation Detection Mechanism

**Question:** How does the system scan session events to detect constraint violations? Should it use regex on event payloads, or something more sophisticated?

**Why it matters:**
- Determines accuracy of HONORED/VIOLATED classification
- Must be deterministic (evidence grounding requirement)
- Must be fast enough for batch processing of all sessions

**Options identified:**

**A. hint_patterns regex scan on event payloads (Recommended)**
- Apply each constraint's `hint_patterns` against all event payload strings in session
- O(constraints × events) scan — manageable for 100s of constraints × 1000s of events
- Same pattern used in Phase 9 `EscalationDetector` for always-bypass patterns
- Evidence = the event(s) where pattern matched
- _(Proposed by: OpenAI, Gemini)_

**B. LLM-based semantic violation detection**
- Send session transcript to LLM with constraint description, ask "was this violated?"
- Higher accuracy for nuanced constraints
- Non-deterministic, expensive, not grounded
- _(Rejected by: all providers for Phase 10)_

**Synthesis recommendation:** ⚠️ **Option A — hint_patterns regex**
- Phase 10 MVP: regex only
- Can add semantic detection as optional layer in later phase

---

### Q6: Session Scope Derivation

**Question:** How does the audit engine determine what "scope" a session was working in, for matching against constraint scope_paths?

**Why it matters:**
- Determines which constraints are "relevant" and thus counted in denominators
- Bad scope detection = wrong denominators = meaningless durability scores

**Options identified:**

**A. Derive from file paths in event payloads (Recommended)**
- Extract file paths from tool call payloads: Read/Edit/Write tool `path` args, Bash commands with file patterns
- Union of all touched paths = session scope
- Consistent with how ConstraintExtractor infers scope from corrections (Phase 3)
- _(Proposed by: Gemini, Perplexity)_

**B. User-provided scope via CLI flag**
- `audit session --session-id X --scope src/pipeline/**`
- Flexible but requires manual input, defeats purpose of automated audit

**Synthesis recommendation:** ⚠️ **Option A — derive from event payloads**
- Automatic, no user input required
- Can be computed during session ingestion and stored on the episode record

---

## Tier 3: Implementation Details (Defer to Planning)

### Q7: DuckDB Evaluation Storage Schema

**Question:** Should per-session constraint evaluation results be stored in DuckDB tables, or recomputed on demand from the event stream?

**Why it matters:**
- Recomputation is idempotent but slow (scan all events for all sessions for all constraints)
- DuckDB storage enables fast aggregation queries for durability scores

**Options identified:**

**A. DuckDB tables (Recommended)**
- `session_constraint_eval(session_id, constraint_id, eval_state, evidence_events_json, eval_ts)`
- `amnesia_events(session_id, constraint_id, severity, evidence_events_json, detected_at)`
- Durability score computed via SQL: `COUNT(CASE WHEN eval_state='HONORED') / COUNT(*)`
- Consistent with existing episodes, escalation tables in DuckDB

**B. Recompute on demand**
- `audit session` scans events each time, no persistence
- Idempotent but O(n²) for full durability report across all sessions

**Synthesis recommendation:** 🔍 **Option A — DuckDB tables**, consistent with existing stack

---

## Next Steps (YOLO Mode — Proceeding to Auto-Answer)

Since `--yolo` flag was passed, CLARIFICATIONS-ANSWERED.md will be auto-generated with the synthesis recommendations above.

---

*Multi-provider synthesis: OpenAI gpt-5.2 + Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-20*
