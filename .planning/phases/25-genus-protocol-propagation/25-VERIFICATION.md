---
phase: 25-genus-protocol-propagation
verified: 2026-02-28T14:01:56Z
status: passed
score: 8/8 must-haves verified
---

# Phase 25: Genus Protocol Propagation — Verification Report

**Phase Goal:** Genus-first behavior propagates beyond OPE to every Claude Code session in the ecosystem. Three deliverables: (1) ~/.claude/CLAUDE.md gains the official GENUS field format in the Premise Declaration Protocol; (2) session_start.py surfaces a genus hint in the [OPE] briefing when prior genera exist in axis_edges for the current repo scope; (3) the OPE governance bus gains a /api/genus-consult endpoint. The /genus-first skill is updated to use the bus oracle as Mode A when OPE_BUS_SOCKET is set but data/ope.db is absent. PLUS: a new global /reframe skill with 3 capability tiers.
**Verified:** 2026-02-28T14:01:56Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                       | Status     | Evidence                                                                                                      |
|----|----------------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------------------------|
| 1  | ~/.claude/CLAUDE.md has GENUS field as optional 5th line in Declaration Format              | VERIFIED   | Line 29: `GENUS: [mechanism name] | INSTANCES: [instance A, instance B]` present in declaration block         |
| 2  | CLAUDE.md has Genus Declaration section with fundamentality criterion and mechanism-vs-symptom | VERIFIED | Lines 58-77: full "Genus Declaration" subsection including two-instances criterion, causal explanation, and mechanism vs. symptom table |
| 3  | session_start.py emits [OPE] GENUS hint when genus_count > 0                               | VERIFIED   | Lines 132-140: `genus_count = check.get("genus_count", 0)` + print `[OPE] GENUS: N prior genera available -- /genus-first before writing` |
| 4  | /api/genus-consult endpoint registered in server.py                                         | VERIFIED   | Line 240: `Route("/api/genus-consult", genus_consult, methods=["POST"])` present; handler at lines 214-233   |
| 5  | GenusOracleHandler implements tokenization-based search with confidence scoring              | VERIFIED   | `src/pipeline/live/genus_oracle.py` (189 lines): `_tokenize()`, `query_genus()`, instance boost, confidence capping, repo-scoped JOIN |
| 6  | /genus-first SKILL.md includes OPE-via-bus Mode A sub-mode using /api/genus-consult        | VERIFIED   | Lines 49, 79-87, 193: OPE-via-bus mode detected via `OPE_BUS_SOCKET`, POSTs to `/api/genus-consult`, documented as Mode A sub-mode |
| 7  | ~/.claude/skills/reframe/SKILL.md exists with 3-tier capability detection and 3 protocols  | VERIFIED   | 163-line SKILL.md: TIER_1_OPE_LOCAL / TIER_2_OPE_BUS / TIER_3_LIGHTWEIGHT detection; Premise-Declare-First / Axis-Before-Fix / Pattern-Not-Symptom protocols; fail-open + never-block fallback |
| 8  | All 15 genus oracle tests pass + integration test verifies non-OPE session round-trip       | VERIFIED   | `pytest tests/pipeline/live/test_genus_oracle.py` → 15 passed; `pytest tests/pipeline/live/test_genus_consult_integration.py` → 5 passed (all integration scenarios) |

**Score:** 8/8 truths verified

---

### Required Artifacts

| Artifact                                                                          | Expected                                             | Status     | Details                                                                                   |
|-----------------------------------------------------------------------------------|------------------------------------------------------|------------|-------------------------------------------------------------------------------------------|
| `~/.claude/CLAUDE.md`                                                             | GENUS field + Genus Declaration section              | VERIFIED   | GENUS line 29 in declaration block; full Genus Declaration subsection lines 58-77          |
| `src/pipeline/live/hooks/session_start.py`                                        | Emits [OPE] GENUS hint when genus_count > 0          | VERIFIED   | Lines 132-140: reads genus_count from check response, prints hint when > 0                |
| `src/pipeline/live/bus/server.py`                                                 | POST /api/genus-consult endpoint                     | VERIFIED   | 241-line file; genus_consult handler lines 214-233; registered in routes line 240         |
| `src/pipeline/live/genus_oracle.py`                                               | GenusOracleHandler with tokenization + confidence    | VERIFIED   | 189-line file; `_tokenize()`, `query_genus()`, `_fetch_genus_edges()`, instance boost scoring |
| `~/.claude/skills/genus-first/SKILL.md`                                           | OPE-via-bus tier (Mode A sub-mode)                   | VERIFIED   | 195-line file; OPE-via-bus detected at line 49; bus POST at lines 82-86; Mode A documented at line 193 |
| `~/.claude/skills/reframe/SKILL.md`                                               | 3-tier capability, 3 protocols, unconditional fallback | VERIFIED | 163-line file; three tiers lines 40-51; three protocols lines 99-101; fail-open line 159; never-block line 160 |
| `tests/pipeline/live/test_genus_oracle.py`                                        | 15 genus oracle tests                                | VERIFIED   | Exactly 15 tests collected and passed; covers empty input, missing table, partial match, top-1, instances, valid flag, repo scoping, instance boost, confidence capping, _tokenize |
| `tests/pipeline/live/test_genus_consult_integration.py`                           | Integration test: non-OPE session receives genus response | VERIFIED | 5 tests: CRAD match, unrelated problem null, empty body fail-open, repo scoping, instance boost |

---

### Key Link Verification

| From                               | To                                        | Via                                              | Status   | Details                                                                                          |
|------------------------------------|-------------------------------------------|--------------------------------------------------|----------|--------------------------------------------------------------------------------------------------|
| `session_start.py`                 | `/api/check`                              | `_post_json("/api/check", ...)` → `genus_count`  | WIRED    | Line 95: posts to /api/check; line 133: reads `genus_count` from response                        |
| `server.py` `/api/check`           | `GovernorDaemon.get_briefing()`           | `briefing.genus_count`                           | WIRED    | Line 119: `_daemon.get_briefing()`; line 129: `briefing.genus_count` in response                |
| `GovernorDaemon`                   | `axis_edges`                              | `_query_genus_count()` DuckDB query              | WIRED    | `daemon.py` line 69-70: `_query_genus_count(repo=repo)` called; result assigned to genus_count  |
| `server.py` `/api/genus-consult`   | `GenusOracleHandler.query_genus()`        | `_genus_oracle.query_genus(problem, repo)`       | WIRED    | Line 225: `result = _genus_oracle.query_genus(problem, repo)`; returned as JSONResponse          |
| `GenusOracleHandler`               | `axis_edges` (genus_of rows)              | `_fetch_genus_edges()` + token overlap scoring  | WIRED    | Lines 97-98: `rows = self._fetch_genus_edges(repo)`; lines 110-146: scoring loop returning top-1 |
| `genus-first SKILL.md`             | `/api/genus-consult`                      | `curl --unix-socket $OPE_BUS_SOCKET`             | WIRED    | Lines 82-86: curl command POSTs to `/api/genus-consult` when OPE-via-bus mode active            |
| `reframe SKILL.md`                 | `/api/genus-consult`                      | `curl --unix-socket $OPE_BUS_SOCKET` (Tier 2)   | WIRED    | Lines 83-87: Tier 2 curl to `/api/genus-consult`; result used in protocol selection lines 103-106 |

---

### Requirements Coverage

All 8 must-haves from the phase specification are satisfied. No REQUIREMENTS.md scan performed (requirements embedded in must-haves list above).

---

### Anti-Patterns Found

None detected. Scanned `session_start.py`, `genus_oracle.py`, `server.py`, both SKILL.md files:

- No TODO/FIXME/placeholder comments in any file
- No `return null` stubs — all handlers return substantive responses
- No empty handlers — `genus_consult` calls oracle, `query_genus` implements full scoring
- Fail-open pattern is intentional and correctly implemented (not a stub)

---

### Human Verification Required

None. All observable behaviors are verifiable programmatically:

- Test suite coverage is comprehensive (15 unit + 5 integration tests, all passing)
- SKILL.md logic is declarative and can be read for protocol correctness
- No UI rendering, real-time behavior, or external service integration required

---

### Gaps Summary

No gaps. All 8 must-haves pass all three levels (exists, substantive, wired).

**Key validation evidence:**

1. `~/.claude/CLAUDE.md` GENUS field is on line 29 of the declaration block as the optional 5th field, and the Genus Declaration subsection (lines 58-77) provides the fundamentality criterion with the mechanism-vs-symptom distinction table.

2. `session_start.py` correctly reads `genus_count` from the `/api/check` response (which the GovernorDaemon computes by querying axis_edges), and conditionally prints the `[OPE] GENUS:` hint line only when `genus_count > 0`.

3. The `/api/genus-consult` endpoint is fully wired: registered in the Starlette routes, backed by `GenusOracleHandler` (imported at line 26, instantiated at line 51, called at line 225), which implements tokenization-based scoring with instance boost and repo-scoped JOIN.

4. Both SKILL.md files are substantive (163 and 195 lines respectively) with no stubs. The genus-first skill correctly detects OPE-via-bus mode and POSTs to `/api/genus-consult`. The reframe skill has all three capability tiers, all three reasoning protocols, and the unconditional fail-open fallback.

5. All 20 tests (15 oracle unit + 5 integration) pass with no failures.

---

_Verified: 2026-02-28T14:01:56Z_
_Verifier: Claude (gsd-verifier)_
