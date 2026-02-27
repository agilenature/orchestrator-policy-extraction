# CLARIFICATIONS-NEEDED.md

## Phase 11: Project-Level Wisdom Layer — Stakeholder Decisions Required

**Generated:** 2026-02-20
**Mode:** Multi-provider synthesis (Gemini Pro + Perplexity Sonar Deep Research)
**Source:** 2 AI providers analyzed Phase 11 requirements (OpenAI query returned empty)

---

## Decision Summary

**Total questions:** 8
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 2 questions — Should answer for quality
**Tier 3 (Polish):** 2 questions — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: project_wisdom Table Schema — Flat vs. Attribute Table

**Question:** Should type-specific fields for the 4 entity types be stored in a separate `wisdom_attributes` table (clean polymorphism) or in a `metadata` JSON column (consistent with existing project patterns)?

**Why it matters:** Determines the DuckDB schema, Pydantic models, and all queries. Changing this later requires migration. The wrong choice creates either excessive complexity (separate attribute table for a small dataset) or poor queryability (all-JSON makes filtering harder).

**Options identified by providers:**

**A. Separate `wisdom_attributes` table** (Perplexity recommendation)
- `wisdom_attributes(wisdom_id FK, attribute_key VARCHAR, attribute_value JSON)`
- Pros: Clean polymorphism, avoids sparse columns, enables attribute-level querying
- Cons: Joins on every read, inconsistent with project's existing pattern (all other tables use JSON columns)
- _(Proposed by: Perplexity)_

**B. `metadata` JSON column in `project_wisdom`** (Gemini recommendation)
- `project_wisdom.metadata JSON` for all type-specific fields
- Pros: Consistent with project patterns (episodes use STRUCT/JSON), simpler reads, no joins
- Cons: Less queryable at attribute level, type validation only at application layer
- _(Proposed by: Gemini)_

**Synthesis recommendation:** ⚠️ **Option B (metadata JSON)** — Consistent with project patterns (DuckDB episodes table uses JSON for nested data). The wisdom table will have < 1000 rows; attribute-level SQL querying is not a real need. Type validation via Pydantic models is sufficient.

**Sub-questions:**
- What are the required metadata fields per type? (See `content_for_embedding` templates)

---

### Q2: WisdomRetriever — Return Type and Recommender Integration

**Question:** Should `WisdomRetriever` return results merged into the existing `Recommendation` object, or should `Recommender.recommend()` return a new structured type with separate episode and wisdom fields?

**Why it matters:** The existing `Recommendation` and `SourceEpisodeRef` Pydantic models are frozen (immutable). Adding wisdom to them requires changing these models and all their consumers (shadow runner, reporter, CLI, tests). A separate return type avoids this but requires updating callers.

**Options identified by providers:**

**A. Extend existing `Recommendation` model** to include `wisdom_context: List[WisdomRef]`
- Pros: Single return type, wisdom is always alongside recommendations
- Cons: Breaks existing Pydantic frozen models, requires updating all callers and tests
- _(Approach compatible with both providers)_

**B. New `EnrichedRecommendation` wrapper** containing `recommendation: Recommendation` and `wisdom_context: List[WisdomRef]`
- Pros: Non-breaking, existing code works unchanged, wisdom is additive
- Cons: Callers must handle the wrapper; older code gets no wisdom context
- _(Approach compatible with both providers)_

**Synthesis recommendation:** ✅ **Option B (wrapper)** — Preserves 643 passing tests, avoids breaking the frozen Pydantic model invariant that's been critical throughout the project. Wisdom is additive context, not a core episode attribute.

**Sub-questions:**
- Should shadow mode evaluator receive `EnrichedRecommendation` or just `Recommendation`? (Proposal: Just `Recommendation` — wisdom is for humans, not shadow evaluation)

---

### Q3: Seed Wisdom Data — YAML or JSON, and Where Stored

**Question:** Should the seed wisdom file be `data/seed_wisdom.yaml` or `data/seed_wisdom.json`, and should it be committed to git alongside `data/constraints.json`?

**Why it matters:** The seed file establishes the canonical representation for all future wisdom ingestion. Its format determines the `wisdom ingest` CLI interface. Committing to git means it's version-controlled alongside constraints, creating a parallel durable store.

**Options identified by providers:**

**A. `data/seed_wisdom.yaml`** (Gemini recommendation)
- Pros: More human-writable, supports comments for provenance, familiar from `data/config.yaml`
- Cons: Requires PyYAML dependency (may not already be installed)
- _(Proposed by: Gemini)_

**B. `data/seed_wisdom.json`**
- Pros: No new dependency (json stdlib), consistent with `data/constraints.json`
- Cons: Less human-friendly for manual authoring
- _(Pattern consistent with existing project)_

**Synthesis recommendation:** ⚠️ **Option B (JSON)** — Consistent with `data/constraints.json` project pattern, no new dependency. The seed file will be authored once; JSON is sufficient. Use `wisdom_id`, `type`, `title`, `description`, `source_document`, `confidence_score`, `metadata` keys.

**Sub-questions:**
- Should DuckDB be the source of truth (write-through to JSON), or is JSON authoritative (write-through to DuckDB)? (Proposal: DuckDB is source of truth, `data/seed_wisdom.json` is the ingestion input only, not a persistent store like constraints.json)

---

### Q4: Dead End Warning Surfacing — In Recommendations or in Shadow Report

**Question:** Should dead end warnings be surfaced in the `EnrichedRecommendation` (returned to callers in real-time) or in the shadow report (batch analysis after the fact)?

**Why it matters:** Real-time surfacing changes the `recommend()` call path and needs to be fast (<100ms). Shadow report surfacing is simpler (batch query on wisdom table) but doesn't help a future policy agent making live decisions.

**Options identified by providers:**

**A. Real-time in `EnrichedRecommendation.dead_end_warnings: List[WisdomRef]`**
- Pros: Policy agent sees warnings at decision time, enables prevention
- Cons: Adds latency to every `recommend()` call (2 extra searches), complexity
- _(Proposed by: Gemini)_

**B. Batch in shadow report** (post-hoc analysis)
- Pros: No latency impact on recommendations, simpler pipeline
- Cons: Warnings come too late to prevent decisions; policy agent can't use them
- _(Compatible with Perplexity approach)_

**Synthesis recommendation:** ✅ **Option A (real-time)** — The purpose of dead end detection is prevention. Phase 11 adds a `WisdomRetriever` call alongside the episode retriever. Per WISDOM-02, wisdom entities are returned "alongside" episodes — they should be concurrent, not sequential with episodes.

**Sub-questions:**
- Should dead end warnings be filtered by confidence_score threshold? (Proposal: Only surface dead ends with confidence_score >= 0.7)

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Scope Decision Enforcement — ConstraintStore Linkage

**Question:** Should `ScopeDecision` wisdom entities optionally link to existing `ConstraintStore` entries via `constraint_ids: List[str]`, or should scope enforcement be entirely standalone text-based?

**Why it matters:** Linking to ConstraintStore reuses the existing amnesia detection and durability tracking infrastructure (Phase 10). Standalone text-only means building new enforcement from scratch.

**Options identified by providers:**

**A. Optional `constraint_ids` linkage in metadata** (Gemini)
- `ScopeDecision.metadata.constraint_ids: Optional[List[str]]` — links to existing constraints
- `wisdom check-scope` runs constraint validation for linked IDs; lists unlinked decisions as text
- Pros: Reuses Phase 10 durability/amnesia infrastructure, zero new enforcement logic
- Cons: Requires human to create and link constraints; some scope decisions may be hard to express as constraints

**B. Standalone scope enforcement** — new `enforcement_criteria` JSON structure
- `ScopeDecision.metadata.enforcement_criteria` — custom assertion format
- `wisdom check-scope` evaluates criteria directly against session data
- Pros: More expressive, doesn't require constraint creation for every scope decision
- Cons: New enforcement logic, duplicates constraint system's purpose

**Synthesis recommendation:** ⚠️ **Option A (constraint linkage)** — Consistent with project's "Wisdom explains WHY, Constraints enforce WHAT" principle. New enforcement logic is out of scope for Phase 11.

---

### Q6: content_for_embedding Templates Per Entity Type

**Question:** What should the `content_for_embedding` synthesis template be for each entity type?

**Why it matters:** This text drives both FTS and vector search quality. Poor templates mean poor retrieval.

**Options identified by providers:**

**Both providers:** Use natural sentence templates, not field dumps.

**Proposed templates (both providers agree on this pattern):**
- **Breakthrough:** `"Breakthrough: [title]. [description]. This insight was discovered because [metadata.discovery_path if present]."`
- **DeadEnd:** `"Dead end: [title]. [description]. The attempted approach [metadata.attempted_strategy if present] failed because [metadata.failure_reason if present]."`
- **ScopeDecision:** `"Scope decision: [title]. [description]."`
- **MethodDecision:** `"Method decision: [title]. [description]. Chosen over [metadata.rejected_alternatives if present]."`

**Synthesis recommendation:** ✅ Use templates above, with graceful fallback to `"[type]: [title]. [description]."` when metadata fields absent.

---

## Tier 3: Polish Decisions (🔍 Defer to Implementation)

### Q7: Wisdom Entry Provenance Fields

**Question:** Should `episode_ids` be required or optional? Should `source_document` be validated to exist on disk?

**Synthesis recommendation:** Optional `episode_ids` (wisdom may come from external documents, not episodes). `source_document` stored as relative path string, not validated on ingest (documents may move).

---

### Q8: `wisdom reindex` CLI and HNSW Index Timing

**Question:** Should the HNSW index on `project_wisdom.embedding` be built immediately after each ingest, or deferred to a `wisdom reindex` command?

**Synthesis recommendation:** Build HNSW index after bulk ingest via explicit `wisdom reindex` command (consistent with Phase 5 pattern: `rebuild_fts_index()` and HNSW deferred to after data load). Don't rebuild on every single insert.

---

## Next Steps (Non-YOLO Mode)

**✋ PAUSED — Awaiting Your Decisions**

1. **Review these 8 questions**
2. **Provide answers** (create CLARIFICATIONS-ANSWERED.md manually, or tell Claude your decisions)
3. **Then run:** `/gsd:plan-phase 11` to create execution plan

---

## Alternative: YOLO Mode

```bash
/meta-gsd:discuss-phase-ai 11 --yolo
```

---

*Multi-provider synthesis: Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-20*
*Non-YOLO mode: Human input required*
