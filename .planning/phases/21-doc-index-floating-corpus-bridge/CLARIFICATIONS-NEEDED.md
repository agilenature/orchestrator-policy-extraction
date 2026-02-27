# CLARIFICATIONS-NEEDED.md

## Phase 21: Doc Index Floating Corpus Bridge — Stakeholder Decisions Required

**Generated:** 2026-02-27
**Mode:** Multi-provider synthesis (Gemini Pro, Perplexity Sonar Deep Research)
**Source:** 2 AI providers analyzed Phase 21 requirements

---

## Decision Summary

**Total questions:** 7
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 2 questions — Should answer for quality
**Tier 3 (Polish):** 1 question — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: Axis Extraction Strategy — How to map docs to ccd_axis

**Question:** What mechanism does `doc_indexer.py` use to associate each markdown file with one or more `ccd_axis` values from `memory_candidates`?

**Why it matters:** This determines whether the doc_index is accurate or noisy. Wrong axis associations mean irrelevant docs delivered at session start, degrading signal quality.

**Options identified:**

**A. YAML Frontmatter + Regex + Keyword cascade (Recommended)**
- Parse YAML frontmatter `axes:` field (conf=1.0), fall back to regex axis-name matching in headers (conf=0.7), fall back to keyword token matching (conf=0.4)
- Requires manually adding frontmatter to the 27 existing docs (one-time human task, ~30 mins)
- _(Proposed by: Gemini, Perplexity)_

**B. Keyword-only matching (No frontmatter required)**
- Search all doc text for axis name tokens; highest-count axis wins
- No human upfront work; lower precision
- _(Alternative for faster bootstrap)_

**C. Manual curation only**
- Human assigns ccd_axis to every doc in a YAML file; indexer reads that file
- Highest precision; most upfront work; fragile if docs change

**Synthesis recommendation:** ✅ **Option A — Hybrid cascade with frontmatter as Tier 1**
- Invest ~30 minutes adding frontmatter to the 27 docs
- doc_indexer.py handles the rest via regex/keyword fallback

---

### Q2: Write Architecture — How does doc_indexer.py write to ope.db?

**Question:** Given the DuckDB single-writer constraint (bus daemon owns all writes to ope.db), how should `doc_indexer.py` perform its index population?

**Why it matters:** If doc_indexer.py opens ope.db while the bus daemon is running, it will throw a write conflict or lock error. The design must prevent this.

**Options identified:**

**A. Offline-first: require bus stopped (Recommended)**
- doc_indexer.py pings the bus socket; if reachable, aborts with clear message
- Run as `python -m src.pipeline.cli docs reindex` after `python -m src.pipeline.cli bus stop`
- Simple; consistent with "one-time indexing" framing
- _(Proposed by: Gemini)_

**B. Bus-owned refresh: new `/api/docs/reindex` endpoint**
- doc_indexer logic moved inside the GovernorDaemon; triggered via POST
- Bus writes doc_index at startup automatically (reads all .md files, updates stale hashes)
- More complex; wider Phase 21 scope
- _(Proposed by: Perplexity for incremental refresh)_

**Synthesis recommendation:** ✅ **Option A for Phase 21; Option B deferred to post-21**
- Offline-first is simpler and fits the "one-time indexing step" framing
- Bus startup refresh is a natural Phase 22 addition

---

### Q3: Query Mechanism — Does /api/check deliver relevant_docs?

**Question:** Does the session-start hook query doc_index directly (read-only DuckDB), or does it receive relevant docs via the existing `/api/check` bus endpoint?

**Why it matters:** Determines whether GovernorDaemon needs to be extended vs. whether session_start.py needs a new DuckDB connection.

**Options identified:**

**A. Extend /api/check response with `relevant_docs` (Recommended)**
- CheckResponse model gets `relevant_docs: list[dict]` field (same pattern as `epistemological_signals`)
- GovernorDaemon.get_briefing() queries doc_index and includes results
- session_start.py prints relevant_docs from the check response — no new DB connection
- _(Proposed by: Gemini)_

**B. Direct ope.db read in session_start.py**
- session_start.py opens ope.db read-only after getting constraint briefing
- Extracts ccd_axes from active constraints; queries doc_index
- Bypasses bus; one more DB connection point
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A — Extend /api/check**
- Consistent with existing architecture (session_start.py already gets everything from the bus)
- GovernorDaemon owns the query; session_start.py stays thin

---

### Q4: doc_index Database Location — Main ope.db or separate file?

**Question:** Should the `doc_index` table live in `data/ope.db` (main database) or in a separate `data/doc_index.db`?

**Why it matters:** Determines whether doc_indexer.py requires bus to be stopped (ope.db) or can run independently (separate file).

**Options identified:**

**A. Main ope.db (Recommended)**
- Unified queries: GovernorDaemon can JOIN doc_index with constraints in one query
- Write-lock required (bus must stop before doc_indexer runs)
- _(Consistent with existing architecture)_

**B. Separate data/doc_index.db**
- doc_indexer.py can write at any time (no conflict with bus)
- GovernorDaemon opens doc_index.db with ATTACH or second connection
- Adds complexity; split storage; two DB files to maintain

**Synthesis recommendation:** ✅ **Option A — Main ope.db**
- JOIN capability is worth the stop-bus constraint
- "One-time indexing" means stopping the bus is acceptable

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Briefing Format — What gets printed to stdout?

**Question:** What format does session_start.py use when printing relevant docs to stdout?

**Options identified:**

**A. Paths + axis + description_cache (Recommended)**
```
[OPE] 3 relevant doc(s):
[OPE]   - docs/guides/GOVERNING-ORCHESTRATOR-METHODOLOGY.md (axis: deposit-not-detect)
[OPE]     Describes Phase 0-5 construction with GO methodology context.
```
- Max 3 docs (consistent with max 3 forbidden constraint display)
- description_cache truncated to 80 chars
- Full content never printed; AI reads on demand

**B. Paths only**
- Minimal stdout noise; AI must infer relevance from filename
- Less informative

**Synthesis recommendation:** ⚠️ **Option A — Paths + axis + description**

---

### Q6: General Docs Without Axis Match — How to handle

**Question:** Docs like `docs/guides/GLOBAL_GIT_HOOKS.md` may not map to any CCD axis. Should they ever appear in session briefings?

**Options identified:**

**A. Reserved `always-show` axis (Recommended)**
- Manually tag 0-2 "always show" docs in frontmatter with `axes: [always-show]`
- Delivered in every session regardless of constraint filter
- Separate from memory_candidates axis vocabulary (doc_index concept only)

**B. Never surface (only deliver axis-matched docs)**
- Simpler; less noise; human can always ask AI to read specific docs

**Synthesis recommendation:** ⚠️ **Option A — Reserved `always-show` for GOVERNING-ORCHESTRATOR-METHODOLOGY.md only**
- That doc is the single most important reference for any session

---

## Tier 3: Polish Decisions (🔍 Can defer)

### Q7: Section-Level vs. File-Level Indexing

**Question:** Should doc_indexer.py index individual H2 sections (with heading anchors) or whole files?

**Options identified:**

**A. File-level (Recommended for Phase 21)**
- Simpler; 27 files is small enough; AI reads full file on demand
- Defer section-level to Phase 22 if corpus grows

**B. Section-level**
- More precise delivery; links to exact heading
- Requires heading extraction, anchor generation in indexer

**Synthesis recommendation:** 🔍 **Option A for Phase 21; Note as Phase 22 candidate**

---

## Next Steps (YOLO Mode — Auto-answering)

All recommendations above are being auto-accepted. See CLARIFICATIONS-ANSWERED.md.

---

*Multi-provider synthesis: Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-27*
