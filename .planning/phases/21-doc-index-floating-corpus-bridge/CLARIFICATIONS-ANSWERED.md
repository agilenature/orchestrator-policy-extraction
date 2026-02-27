# CLARIFICATIONS-ANSWERED.md

## Phase 21: Doc Index Floating Corpus Bridge — Decisions

**Generated:** 2026-02-27
**Mode:** YOLO (balanced strategy — auto-generated from provider synthesis)
**Source:** Gemini Pro + Perplexity Sonar Deep Research consensus

---

## Decision Summary

**Total questions:** 7
**Tier 1 (Blocking):** 4 answered
**Tier 2 (Important):** 2 answered
**Tier 3 (Polish):** 1 answered

---

## Tier 1: Blocking Decisions

### Q1: Axis Extraction Strategy

**YOLO DECISION:** **Option A — Hybrid 3-tier cascade (frontmatter → regex → keyword)**

**Implementation spec:**
- **Tier 1 (conf=1.0):** YAML frontmatter `axes:` list. Format: `axes: [deposit-not-detect, raven-cost-function-absent]`. Parsed via `python-frontmatter` (already available or use PyYAML header split).
- **Tier 2 (conf=0.7):** Regex match of known axis names in H1/H2 headers or inline comments (`<!-- ccd: axis-name -->`). Axis vocabulary loaded from `memory_candidates` table at index time.
- **Tier 3 (conf=0.4):** Token overlap: split axis name on `-`, count occurrences in document text. Accept if score ≥ threshold (default: 2+ tokens found with 3+ occurrences total).
- **Unclassified:** If no tier fires, `ccd_axis='unclassified'`, `extracted_confidence=0.0`, `association_type='unclassified'`.
- **Human pre-work:** Add YAML frontmatter to the ~10 most important docs (design/, guides/, architecture/). Indexer handles the rest via Tier 2/3.
- **Indexer output:** Print unclassified doc list to stderr for human review.

**Confidence:** ✅ Consensus (both providers)

---

### Q2: Write Architecture

**YOLO DECISION:** **Option A — Offline-first; doc_indexer.py requires bus stopped**

**Implementation spec:**
- `doc_indexer.py` (or `python -m src.pipeline.cli docs reindex`) checks for running bus by attempting socket connection to `/tmp/ope-governance-bus.sock`.
- If bus reachable: print `[ERROR] Bus daemon is running. Stop it first: python -m src.pipeline.cli bus stop` and exit with code 1.
- If bus not running: open `data/ope.db` directly, populate `doc_index` table via `DELETE FROM doc_index; INSERT ...` (full refresh).
- Idempotent: always full refresh (27 docs is fast, < 1 second).
- **Post-Phase-21:** Bus startup sequence can trigger incremental refresh via content hash comparison (log "doc_index already current" if no changes).

**Confidence:** ✅ Consensus

---

### Q3: Query Mechanism

**YOLO DECISION:** **Option A — Extend /api/check response with `relevant_docs`**

**Implementation spec:**
- `CheckResponse` model extended: `relevant_docs: list[dict[str, str]] = []`
  - Each entry: `{doc_path, ccd_axis, description_cache}` (3 fields max for wire efficiency)
- `GovernorDaemon.get_briefing(session_id, run_id, repo=None)` extended:
  - After filtering constraints, extract unique `ccd_axis` values from active constraints
  - Query: `SELECT DISTINCT doc_path, ccd_axis, description_cache FROM doc_index WHERE ccd_axis IN (?...) AND association_type != 'unclassified' ORDER BY extracted_confidence DESC LIMIT 5`
  - Deduplicate by doc_path (keep highest-confidence axis per doc)
  - Return max 3 docs (deduped) in briefing
- `session_start.py` reads `check.get('relevant_docs', [])` and prints (see Q5 for format)
- If doc_index table doesn't exist (pre-Phase-21 DB): graceful fallback, empty list

**Confidence:** ✅ Consensus

---

### Q4: doc_index Database Location

**YOLO DECISION:** **Option A — Main data/ope.db**

**Implementation spec:**
- `doc_index` table added to `data/ope.db` via `create_doc_schema()` function
- Called from the top-level `create_schema()` chain (same pattern as DDF, assessment, structural schemas)
- Idempotent `CREATE TABLE IF NOT EXISTS`
- GovernorDaemon opens existing `ope.db` connection — no new connection needed
- Bus schema DDL file: `src/pipeline/live/bus/doc_schema.py` (new file, same pattern as `schema.py`)

**Confidence:** ✅ Consensus (convenience + unified query access outweighs write-lock cost)

---

## Tier 2: Important Decisions

### Q5: Briefing Format

**YOLO DECISION:** **Paths + axis + description_cache truncated to 80 chars; max 3 docs**

**Implementation spec:**
```python
# In session_start.py, after constraints block:
relevant_docs = check.get("relevant_docs", [])
if relevant_docs:
    print(f"\n[OPE] {len(relevant_docs)} relevant doc(s) for this session:", flush=True)
    for doc in relevant_docs[:3]:
        path = doc.get("doc_path", "")
        axis = doc.get("ccd_axis", "")
        desc = doc.get("description_cache", "")[:80]
        print(f"[OPE]   - {path} (axis: {axis})", flush=True)
        if desc:
            print(f"[OPE]     {desc}", flush=True)
```
- Consistent with existing `[OPE]` prefix pattern
- Silent if 0 docs (same as 0 constraints behavior)
- Never prints full document content

**Confidence:** ⚠️ Recommended

---

### Q6: General Docs Without Axis Match

**YOLO DECISION:** **Option A — Reserved `always-show` axis for GOVERNING-ORCHESTRATOR-METHODOLOGY.md only**

**Implementation spec:**
- `always-show` is a valid `ccd_axis` value in `doc_index` only (NOT in `memory_candidates`)
- In GovernorDaemon query: `WHERE ccd_axis IN (?...) OR ccd_axis = 'always-show'`
- Manually set `always-show` in frontmatter for `docs/guides/GOVERNING-ORCHESTRATOR-METHODOLOGY.md`
- Rationale: This is the single most important reference doc for any OPE session

**Confidence:** ⚠️ Recommended

---

## Tier 3: Polish Decisions

### Q7: Section-Level vs. File-Level Indexing

**YOLO DECISION:** **File-level for Phase 21; section-level deferred**

**Rationale:** 27 files is small. File paths + description_cache is sufficient for the AI to locate relevant content via Read() on demand. Section-level adds heading extraction complexity without proportional benefit at this corpus size.

**Note as Phase 22 candidate** when corpus grows.

**Confidence:** 🔍 Conservative choice

---

## Implementation Blueprint (for /gsd:plan-phase)

### New files to create:
1. `src/pipeline/live/bus/doc_schema.py` — `DOC_INDEX_DDL`, `create_doc_schema()`, `create_doc_index_schema()` function
2. `src/pipeline/doc_indexer.py` — 3-tier hybrid extractor, bus-stop check, CLI entry point
3. `src/pipeline/cli/docs.py` — `docs` CLI group with `reindex` subcommand

### Files to modify:
1. `src/pipeline/live/bus/schema.py` — call `create_doc_schema()` in `create_bus_schema()`
2. `src/pipeline/live/bus/models.py` — add `relevant_docs: list[dict] = []` to `CheckResponse`
3. `src/pipeline/live/governor/daemon.py` — extend `get_briefing()` to query `doc_index`
4. `src/pipeline/live/hooks/session_start.py` — print `relevant_docs` block
5. `src/pipeline/cli/__main__.py` — register `docs` CLI group

### Suggested wave structure:
- **Wave 1**: doc_schema.py + DOC_INDEX_DDL + create_doc_schema() wired into schema chain (foundation)
- **Wave 2**: doc_indexer.py — 3-tier extraction + bus-stop check + full reindex (core deliverable)
- **Wave 3**: GovernorDaemon + CheckResponse + session_start.py extension (briefing delivery)
- **Wave 4**: CLI docs group + integration tests

### Estimated plans: 4 plans

---

*Auto-generated by discuss-phase-ai --yolo (balanced strategy)*
*Human review recommended before final planning*
*Generated: 2026-02-27*
