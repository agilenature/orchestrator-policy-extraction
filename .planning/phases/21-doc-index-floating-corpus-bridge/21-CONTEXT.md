# CONTEXT.md — Phase 21: Doc Index Floating Corpus Bridge

**Generated:** 2026-02-27
**Phase Goal:** Bring the docs/ folder into the axis-indexed graph so sessions can retrieve relevant documentation by ccd_axis at session start without being told to look at specific files.
**Synthesis Source:** Multi-provider AI analysis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)
**Mode:** YOLO (auto-answered)

---

## Overview

Phase 21 closes the raven-cost-function-absent failure for the docs/ corpus. The docs/ folder (~27 markdown files across analysis/, architecture/, design/, guides/, research/) currently has file-provenance but no session-provenance — every time a session needs architectural decisions or design rationale, the human must explicitly prompt "look at the docs folder." This phase adds three components: (1) `doc_index` DuckDB table, (2) `doc_indexer.py` one-time indexing step, (3) session-start briefing extension delivering `relevant_docs` alongside constraints.

All three providers converged on the same core architecture. The primary tensions are: (a) the DuckDB single-writer constraint vs. the need for doc_indexer to write, (b) axis extraction without ML, (c) briefing format without flooding stdout.

**Confidence markers:**
- ✅ **Consensus** — Both active providers identified this as critical (OpenAI model detection confirmed, Gemini + Perplexity full responses received)
- ⚠️ **Recommended** — Strong rationale from 1 provider with no counterargument
- 🔍 **Needs Clarification** — Design choice with multiple valid approaches

---

## Gray Areas Identified

### ✅ 1. Axis Extraction Strategy — How to map docs to ccd_axis without ML

**What needs to be decided:**
How `doc_indexer.py` associates each markdown file (or section) with one or more `ccd_axis` values from the `memory_candidates` vocabulary.

**Why it's ambiguous:**
Pure regex fails on synonymy (a doc discussing "the missing cost function" won't match `raven-cost-function-absent`). Pure keyword matching is brittle. Embeddings require ML dependencies. YAML frontmatter requires human curation of all 27 docs upfront. The best approach is hybrid, but the ordering and confidence thresholds need to be decided.

**Provider synthesis:**
- **Gemini:** YAML frontmatter (primary, conf=1.0) → regex header/comment patterns → TF-IDF keyword fallback flagged as `association_type='heuristic'`
- **Perplexity:** Identical cascade: frontmatter → regex → keyword matching with explicit code; confidence 1.0/0.7/0.5 thresholds per tier; `extraction_method` column captures which tier fired

**Proposed implementation decision:**
**Three-tier hybrid cascade: frontmatter → regex → keyword matching**
- Tier 1 (conf=1.0): YAML frontmatter `axes:` list; most reliable, highest precision
- Tier 2 (conf=0.7): Regex matching of axis names in H1/H2 headers or inline `<!-- ccd: axis-name -->` comments
- Tier 3 (conf=0.4): Keyword set matching against axis token expansions (e.g., `raven-cost-function-absent` → tokens ['raven', 'cost', 'function', 'absent'])
- Docs with no match → `ccd_axis='unclassified'`, `extracted_confidence=0.0`
- The 27 existing docs should be manually inspected to add YAML frontmatter where obvious; doc_indexer fills gaps via Tier 2/3

**Open questions:**
- At what confidence threshold should a Tier 3 match be accepted vs. dropped to 'unclassified'?
- Should the indexer produce a warning/report of unclassified docs?

---

### ✅ 2. doc_index Schema Design — Columns, primary key, granularity

**What needs to be decided:**
The exact schema for `doc_index`, including whether to index at file-level or section-level, and how to represent multi-axis documents.

**Why it's ambiguous:**
- File-level vs. section-level: section-level gives finer-grained retrieval but requires heading extraction and anchors
- One row per file vs. one row per (file, axis): multi-axis docs need one of these approaches
- Whether to cache content (staleness risk) or store only pointers (requires file read at runtime)

**Provider synthesis:**
- **Gemini:** One row per (doc_path, ccd_axis), metadata + pointers only (no full text), `description_cache` for briefing without file read, section-level optional via `section_anchor`
- **Perplexity:** Identical one-row-per-axis design; `doc_content_hash` for change detection; `extraction_method` for auditability; `is_multi_axis` boolean flag

**Proposed implementation decision:**
```sql
CREATE TABLE doc_index (
    doc_path          VARCHAR NOT NULL,  -- relative path from repo root
    ccd_axis          VARCHAR NOT NULL,
    association_type  VARCHAR NOT NULL DEFAULT 'frontmatter'
        CHECK (association_type IN ('frontmatter', 'regex', 'keyword', 'manual', 'unclassified')),
    extracted_confidence FLOAT NOT NULL DEFAULT 1.0,
    description_cache VARCHAR,           -- first paragraph or frontmatter description
    section_anchor    VARCHAR,           -- optional '#heading-anchor' for deep links
    content_hash      VARCHAR NOT NULL,  -- SHA-256[:16] for change detection
    indexed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (doc_path, ccd_axis)
)
```
- File-level indexing for Phase 21 (section-level deferred)
- One row per (doc_path, ccd_axis) for clean multi-axis representation
- `description_cache` populated from first non-empty paragraph after frontmatter
- Deduplication in query layer when presenting to session

**Open questions:**
- Does `doc_index` live in `data/ope.db` (main DB) or a separate `data/doc_index.db`?
  (Recommendation: main ope.db for unified queries, but this requires the write-lock solution below)

---

### ✅ 3. Write Architecture — DuckDB single-writer constraint vs. doc_indexer writes

**What needs to be decided:**
How `doc_indexer.py` writes to `doc_index` given that the bus process (GovernorDaemon) is the single writer for `data/ope.db`.

**Why it's ambiguous:**
- If doc_indexer.py opens ope.db directly while bus is running → DuckDB write-write conflict (crash/lock error)
- If doc_indexer.py calls a new bus API endpoint → new endpoint needed, widens Phase 21 scope
- If doc_indexer.py runs only when bus is stopped → acceptable for one-time indexing but awkward for updates

**Provider synthesis:**
- **Gemini:** Offline-first: doc_indexer.py checks for active daemon (WAL file or process lock); aborts with clear message if running; "acceptable for one-time/infrequent indexing"
- **Perplexity:** Content-hash scheduled refresh owned by bus process (bus runs the indexer internally); direct DuckDB reads for hooks (MVCC means reads never block)

**Proposed implementation decision:**
**Two-mode design:**
1. **Initial index build** (one-time): `doc_indexer.py` runs as a standalone CLI tool. It checks if the bus is running by pinging `/tmp/ope-governance-bus.sock`; if reachable, it aborts with "Stop the bus daemon before re-indexing (`python -m src.pipeline.cli bus stop`)". If not running, opens ope.db directly and populates doc_index.
2. **Incremental refresh** (future): Bus daemon's startup sequence checks content hashes and refreshes stale entries via its own connection. For Phase 21, defer to post-initial-index.

**Open questions:**
- Is the stop-bus-to-reindex workflow acceptable for the developer experience?
- Should there be a `python -m src.pipeline.cli docs reindex` CLI command as the canonical way to trigger indexing?

---

### ✅ 4. Relevance Query Mechanism — How session_start determines which docs to deliver

**What needs to be decided:**
At session start, what query delivers relevant docs to the hook? Does this go through `/api/check` or does session_start.py query ope.db directly?

**Why it's ambiguous:**
- The bus currently owns all writes; reads are free via MVCC
- session_start.py already calls `/api/check` to get constraints — does doc delivery piggyback on this?
- Or does session_start.py open ope.db read-only independently?
- What axes are used as the filter? The session's active constraints carry ccd_axis values

**Provider synthesis:**
- **Gemini:** GovernorDaemon.get_briefing() extended: JOIN doc_index ON ccd_axis from active constraints; doc metadata returned in /api/check response
- **Perplexity:** Direct DuckDB read-only connection in SessionStart hook; extract ccd_axes from constraint briefing text; query doc_index for those axes

**Proposed implementation decision:**
**Extend /api/check response to include `relevant_docs` list:**
1. GovernorDaemon.get_briefing() queries doc_index: SELECT doc_path, ccd_axis, description_cache FROM doc_index WHERE ccd_axis IN (axes of active constraints) ORDER BY extracted_confidence DESC LIMIT 5
2. CheckResponse model extended with `relevant_docs: list[dict]` field (same pattern as existing `epistemological_signals: list`)
3. session_start.py prints relevant_docs to stdout under a `[OPE] Relevant documentation:` block
4. No direct ope.db connection in session_start.py (consistent with current pattern)

**Open questions:**
- What axes to use for filtering? Active constraint axes, or ALL known axes regardless of current constraints?
- Recommended: filter by axes of active constraints for the session's repo scope (most targeted)

---

### ✅ 5. Briefing Format & Context Window Budget — How docs are presented in stdout

**What needs to be decided:**
What exactly gets printed to stdout for relevant docs, and how many, to avoid flooding the session context.

**Why it's ambiguous:**
Printing full doc content to stdout at session start would saturate the context window. Printing only file paths may not be enough for the AI to know why the doc is relevant. The optimal format balances informativeness against context budget.

**Provider synthesis:**
- **Gemini:** Print file paths + description_cache (one-liner) only; do NOT print content; inject instruction "Read [path] for [axis]"
- **Perplexity:** Dynamic limit (1-5 docs based on constraint briefing length); composite ranking (confidence 50%, freshness 30%, constraint overlap 20%)

**Proposed implementation decision:**
**Fixed limit of 3 docs, path + axis + description_cache only:**
```
[OPE] 3 relevant doc(s) for current session:
[OPE]   - docs/guides/GOVERNING-ORCHESTRATOR-METHODOLOGY.md (axis: deposit-not-detect)
[OPE]     Describes the deposit-not-detect CCD axis with Phase 0-5 milestone context.
[OPE]   - docs/architecture/BOUNDED-SUPERVISORY-ARCHITECTURE.md (axis: identity-firewall)
[OPE]     Builder-operator separation design, SEMF three-plane architecture.
```
- Max 3 docs (consistent with existing constraint display of max 3 forbidden constraints)
- description_cache truncated to 80 chars
- Full content never printed to stdout; AI can Read() on demand
- If 0 docs match: silent (same as 0 constraints behavior)

---

### ⚠️ 6. Docs Without Axis Match — What to do with general/unclassified docs

**What needs to be decided:**
How to handle docs that don't map to any known ccd_axis (e.g., docs/guides/GLOBAL_GIT_HOOKS.md may be procedural, not axiomatic).

**Why it's ambiguous:**
Pure axis-join query excludes procedural docs that are nonetheless important. A fallback to "always show these docs" needs a mechanism.

**Proposed implementation decision:**
**Reserved `always-show` axis for high-value general docs:**
- Add `always-show` as a valid axis value (not in memory_candidates — it's a doc_index concept only)
- Docs manually tagged `always-show` are delivered in every session regardless of constraint axis match
- For Phase 21: 0-2 docs max in this category (e.g., GOVERNING-ORCHESTRATOR-METHODOLOGY.md)
- Unclassified docs (no reliable axis found by any tier) stored with `ccd_axis='unclassified'`, excluded from session delivery, logged for human review

---

### 🔍 7. Section-Level vs. File-Level Indexing

**What needs to be decided:**
Whether to index individual sections within docs (allowing delivery of just the relevant heading) or whole files.

**Why it's relevant:**
Section-level indexing would let the briefing say "Section 'DDF co-pilot architecture' in docs/design/AUTHORITATIVE_DESIGN.md" rather than the entire 50KB file.

**Proposed implementation decision:**
**File-level for Phase 21; section-level deferred.**
- 27 files is small enough that file-level pointers + AI Read() on demand is sufficient
- Section-level adds heading extraction complexity without proportional payoff at this corpus size
- If corpus grows to 100+ files, section-level becomes valuable — add as Phase 22

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking — must decide before planning):**
- [x] Axis extraction strategy → Hybrid 3-tier: frontmatter → regex → keyword
- [x] Schema → One row per (doc_path, ccd_axis), metadata+pointers, no full content
- [x] Write architecture → Offline-first: doc_indexer.py requires bus stopped; future incremental in bus startup
- [x] Query mechanism → Extend /api/check response with `relevant_docs`; GovernorDaemon queries doc_index

**Tier 2 (Important — drives implementation quality):**
- [x] Briefing format → Max 3 docs, path + axis + description_cache (80 chars)
- [x] Unclassified docs → `ccd_axis='unclassified'` excluded from delivery; `always-show` for general docs

**Tier 3 (Deferred):**
- [ ] Section-level indexing — Phase 22
- [ ] Incremental bus-owned refresh — post Phase 21

---

*Multi-provider synthesis: Gemini Pro (high thinking) + Perplexity Sonar Deep Research*
*OpenAI gpt-5.2-2025-12-11 confirmed reachable; model detection complete*
*Generated: 2026-02-27 (YOLO mode)*
