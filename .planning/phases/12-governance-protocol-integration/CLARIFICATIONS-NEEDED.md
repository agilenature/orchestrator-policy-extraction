# CLARIFICATIONS-NEEDED.md

## Phase 12: Governance Protocol Integration — Stakeholder Decisions Required

**Generated:** 2026-02-20
**Mode:** Multi-provider synthesis (OpenAI gpt-4.1, Gemini Pro, Perplexity Sonar Deep Research)

---

## Decision Summary

**Total questions:** 11
**Tier 1 (Blocking):** 5 — Must answer before planning
**Tier 2 (Important):** 4 — Should answer for quality
**Tier 3 (Polish):** 2 — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: What Markdown structure does the objectivism pre-mortem use?

**Question:** The parser must identify section boundaries. Does the objectivism pre-mortem use H2 (`##`) or H3 (`###`) for "Failure Stories" and "Assumptions" sections? Are stories organized as a numbered list, bulleted list, or H3 sub-headings? Are assumptions a flat bulleted list or multi-paragraph?

**Why it matters:** The extraction granularity (one entity per list item vs. one entity per sub-heading block) directly determines whether we get 11 stories and 15 assumptions or some other count.

**Options:**
**A. H2 sections with numbered list items (one story per list item)**
- Simple parser, one list item = one entity
- _(Most likely based on standard pre-mortem templates)_

**B. H2 sections with H3 sub-headings (one story per sub-heading block)**
- Parser must aggregate multi-paragraph blocks per sub-heading
- _(More detailed format, seen in in-depth post-mortems)_

**C. Mix of both (numbered list for stories, H3 for assumptions)**
- Parser must handle asymmetric structure
- _(Less likely but possible)_

**Synthesis recommendation:** ✅ **Option A** (list-item granularity) — the most common pre-mortem format. Parser should try list-item first, fall back to sub-heading blocks.

---

### Q2: Are there multiple pre-mortem files or one canonical file?

**Question:** The objectivism analysis produced 4 documents in `docs/analysis/objectivism-knowledge-extraction/`. Which file(s) contain the 11 failure stories and 15 assumptions? Is there one canonical pre-mortem file, or are stories/assumptions distributed across multiple documents?

**Why it matters:** The ingest command takes `<file>` as argument. If the reference data is spread across multiple files, the integration test needs to run multiple ingests.

**Options:**
**A. One canonical pre-mortem file** — `govern ingest single_file.md` gets all 11+15
**B. Multiple files requiring batch ingest** — `govern ingest dir/` or multiple calls

**Synthesis recommendation:** ✅ **Option A** — Plan 07 phase description suggests REUSABLE_KNOWLEDGE_GUIDE.md and DECISION_AMNESIA_REPORT.md as distinct documents, with DECISION_AMNESIA_REPORT.md being the closest match to a pre-mortem. Single file assumed.

---

### Q3: What counts as "bulk operation" for session-level detection?

**Question:** Providers proposed three different bulk signals: (1) git commits touching ≥10 files, (2) Write/Edit tool calls ≥3 per episode, (3) ≥5 entities modified in one ingest call. Which primary signal should drive the missing_validation flag for sessions?

**Why it matters:** Too loose = noisy false positives, users ignore flags. Too tight = misses real bulk changes.

**Options:**
**A. Ingest-triggered only** — only `govern ingest` calls that modify ≥5 entities trigger bulk flag
- Simple, predictable, directly tied to governance operations
- _(Synthesis recommendation)_

**B. Session file-edit volume** — sessions where ≥10 distinct files were modified via Write/Edit trigger flag
- Broader scope, catches all bulk coding sessions
- Requires querying episode event stream

**C. Both signals** — ingest bulk OR session bulk triggers the flag
- Maximum coverage, more complex implementation

**Synthesis recommendation:** ⚠️ **Option A** for Phase 12 (simpler, directly relevant to governance) — Session-level signal can be added in Phase 13 or as a follow-up.

---

### Q4: What stability check command should be registered by default?

**Question:** `govern check-stability` runs registered commands from config. What is the default command for this project? Running all 712 tests would be correct but slow; a targeted subset would be faster but requires defining it.

**Options:**
**A. Run full test suite** (`pytest tests/`) — comprehensive, no new test organization needed
**B. Run a stability tag/subset** (`pytest tests/ -m stability`) — fast, requires tagging tests
**C. No default; require explicit config** — safest, no assumptions

**Synthesis recommendation:** ⚠️ **Option A** for now — the project is small enough (712 tests), and running all tests is the correct stability signal. Can be narrowed later.

---

### Q5: Should a failed stability check mark episodes as "validated" or leave them "pending"?

**Question:** If a stability check runs but fails (tests fail), does that satisfy "has been validated" (check was performed) or not (validation wasn't clean)?

**Options:**
**A. Any completed check = validated** — `stability_check_status='validated'` regardless of pass/fail; status separately tracked
**B. Only passing checks = validated** — `stability_check_status='validated'` only on exit 0; failing keeps `'pending'`

**Synthesis recommendation:** ✅ **Option A** — "validation performed" is distinct from "validation passed". Both the flag and the outcome should be persisted. The ShadowReporter metric tracks pass rate separately.

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q6: Constraint severity assignment — should DECISIONS.md entries produce constraints?

**Question:** GOVERN-01 says `govern ingest` handles both pre-mortem files AND DECISIONS.md. Pre-mortem assumptions clearly produce constraints. But should DECISIONS.md entries also produce constraints, or only wisdom entities (scope_decision/method_decision)?

**Options:**
**A. DECISIONS.md → wisdom entities only** (scope_decision/method_decision; no constraints extracted)
**B. DECISIONS.md → wisdom entities + constraints** (ACTIVE decisions with "shall/must not" language → constraints too)

**Synthesis recommendation:** ⚠️ **Option A** — cleaner separation; DECISIONS.md encodes scope/method choices (wisdom), not behavioral guardrails (constraints). Only pre-mortem assumptions → constraints.

---

### Q7: Where is the objectivism pre-mortem content? What are the actual section headers?

**Question:** The reference integration test needs to find the source file. The 4 documents are: REUSABLE_KNOWLEDGE_GUIDE.md, PROBLEM_FORMULATION_RETROSPECTIVE.md, VALIDATION_GATE_AUDIT.md, DECISION_AMNESIA_REPORT.md. Which file contains the 11 failure stories and 15 assumptions?

**Options:**
**A. DECISION_AMNESIA_REPORT.md** — most likely, amnesia report lists failure instances as stories
**B. REUSABLE_KNOWLEDGE_GUIDE.md** — contains dead ends and breakthroughs
**C. A combined/synthesized file to be created** — governance ingestion creates its own pre-mortem fixture

**Synthesis recommendation:** ⚠️ Need to read the actual files to confirm (executor task, not planning question). Assume Option C if the files don't match the expected structure — create a `data/objectivism_premortem.md` governance fixture from the analysis documents as part of the phase.

---

### Q8: Should `govern ingest` support directory ingestion?

**Question:** If governance documents expand to a directory of pre-mortem files, should `govern ingest <dir>` process all `.md` files in the directory?

**Options:**
**A. File-only for Phase 12** — `govern ingest <file.md>` only; directory support deferred
**B. Directory support from start** — `govern ingest <path>` handles both files and directories

**Synthesis recommendation:** ⚠️ **Option A** — YAGNI; start with file-only, add directory support if needed.

---

### Q9: Missing validation grace window — should it be time-based or session-based?

**Question:** When should a bulk-flagged episode be marked `missing_validation`? OpenAI proposed 2 hours from session end; Gemini implied it's checked at next `check-stability` run.

**Options:**
**A. Time-based** — 2-hour grace window after episode end
**B. Session-boundary-based** — flagged when a new session starts without prior check
**C. On-demand only** — only flagged when `govern check-stability` is explicitly run

**Synthesis recommendation:** ⚠️ **Option C** — simplest implementation; `govern check-stability` is the active actor that queries and updates status. No background timers or session hooks needed.

---

## Tier 3: Polish Decisions

### Q10: Should `govern ingest` print a summary table or simple counts?

**Question:** What does the CLI output look like after successful ingestion?

**Options:**
**A. Simple counts** — "Ingested: 11 wisdom entities, 15 constraints"
**B. Summary table** — table showing each entity with type and title
**C. Both** — counts by default, `--verbose` shows full table

**Synthesis recommendation:** ✅ **Option C** — matches existing CLI patterns (e.g., audit commands).

---

### Q11: Should `govern` group use exit code 2 for validation failures (matching wisdom CLI pattern)?

**Question:** Phase 11's `wisdom check-scope` uses exit code 2 for violations, 0 for clean, 1 for errors. Should `govern check-stability` use the same convention?

**Options:**
**A. Same convention** — 0=clean, 1=runtime error, 2=validation failure
**B. Simpler** — 0=pass, 1=any failure

**Synthesis recommendation:** ✅ **Option A** — consistency with existing CLI conventions.

---

## Next Steps (Non-YOLO Mode)

**✋ PAUSED — Awaiting Your Decisions**

1. **Review these 11 questions**
2. **Provide answers** (create CLARIFICATIONS-ANSWERED.md or tell Claude your decisions)
3. **Then run:** `/gsd:plan-phase 12` to create execution plan

---

*Multi-provider synthesis: OpenAI gpt-4.1 + Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-20*
