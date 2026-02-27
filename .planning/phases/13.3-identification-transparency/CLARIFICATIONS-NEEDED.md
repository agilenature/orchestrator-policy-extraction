# CLARIFICATIONS-NEEDED.md

## Phase 13.3: Identification Transparency Layer — Stakeholder Decisions Required

**Generated:** 2026-02-23
**Mode:** Multi-provider synthesis (Gemini Pro, Perplexity Sonar)
**Source:** 2 AI providers analyzed Phase 13.3 requirements (OpenAI response truncated)

---

## Decision Summary

**Total questions:** 8
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 3 questions — Should answer for quality
**Tier 3 (Polish):** 1 question — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: PoolBuilder ID Generation — How are identification_instance_ids generated?

**Question:** When the PoolBuilder sources identification instances from existing DuckDB tables (events, episodes, constraints, etc.), the underlying rows have their own primary keys (event_id, episode_id, constraint_id, etc.) but no `identification_instance_id`. How should stable, durable IDs be generated for these instances?

**Why it matters:** The UNIQUE constraint on `identification_instance_id` in `identification_reviews` requires stable IDs — if IDs change across runs, the at-most-once-verdict invariant cannot be enforced. Additionally, ID instability would break the Harness's specification-closure SQL join.

**Options:**

**A. Hash-based synthetic IDs**
- `SHA256(source_table + primary_key + point_type)[:16]` as hex string
- Deterministic across re-runs regardless of data insertion order
- Stable until source row is modified
- _(Proposed by: Gemini Pro)_

**B. Composite natural keys**
- `{source_table}:{primary_key}:{point_type}` as VARCHAR
- No hashing, human-readable, directly traceable
- Longer strings, but DuckDB VARCHAR handles this
- _(Proposed by: Perplexity)_

**C. Sequential UUIDs per PoolBuilder run**
- UUID4 generated fresh each time
- ❌ NOT viable — breaks at-most-once across runs
- _(Rejected by both providers)_

**Synthesis recommendation:** ✅ **Option B — Composite natural key** (`{source_table}:{primary_key}:{point_type}`)
- Rationale: Human-readable, directly traceable to source artifact (ground-truth-pointer CCD), no hashing loss, DuckDB stores VARCHAR efficiently. Directly satisfies provenance_pointer requirement.

**Sub-questions:**
- Should the composite include a version field to support re-reviewing after pipeline code changes?
- What is `point_type` for each of the 35 points — enumerated constant or derived?

---

### Q2: Append-Only Enforcement — Code-only or DuckDB triggers?

**Question:** The `identification_reviews` table must be append-only (no UPDATE or DELETE). DuckDB's trigger support differs from traditional RDBMS. What enforcement mechanism should be used?

**Why it matters:** The Harness depends on append-only semantics as a structural invariant. If the table can be modified outside the writer, the harness's delta-retrieval baseline is corrupted and the bootstrap-circularity resolution breaks.

**Options:**

**A. Code convention only**
- `writer.py` is the only entry point; only INSERT operations permitted
- Simple, no DuckDB-level enforcement
- Can be bypassed by direct SQL access
- _(Lower confidence approach)_

**B. Code convention + UNIQUE constraint**
- UNIQUE(identification_instance_id) prevents duplicate inserts but doesn't prevent deletes
- Application code forbids DELETE/UPDATE
- _(Proposed by: Perplexity — "defense in depth")_

**C. Gemini's "soft-state" relaxation**
- UNIQUE(identification_instance_id, review_timestamp) to allow re-reviewing
- Logical uniqueness enforced by window function
- ❌ Conflicts with the at-most-once-verdict invariant which is a core design decision
- _(Proposed by: Gemini — but conflicts with established design)_

**Synthesis recommendation:** ✅ **Option B — Code convention + UNIQUE(identification_instance_id)**
- Rationale: Option C relaxes the invariant that resolves bootstrap-circularity — reject. The at-most-once-verdict design decision is fixed. Code-level enforcement via writer class with UNIQUE as DB backstop is the correct pattern (matches existing OPE patterns for append-only logging).

---

### Q3: Does `memory_candidates` exist as a DuckDB table yet, or must Plan 13.3-01 create it?

**Question:** Phase 13.3 routes rejected verdicts with opinions to `memory_candidates`. The ROADMAP references memory_candidates as a Phase 15/16 concept (the deposit store for DDF candidates). Does Plan 13.3-01 need to create this table, or does it already exist?

**Why it matters:** If the table doesn't exist, Plan 13.3-01 scope expands to include schema creation. If it does exist (partially created), the CCD format constraint may conflict with existing structure.

**Options:**

**A. Create memory_candidates in Plan 13.3-01 (minimal schema)**
- Fields: id, source_instance_id, ccd_axis, scope_rule, flood_example, pipeline_component, heuristic_description, status, created_at
- CCD format constraint enforced: all three CCD fields must be non-empty (is_valid_ccd())
- Phase 15/16 can extend the table with additional fields
- _(Consensus recommendation)_

**B. Leave memory_candidates as a concept, write to a separate spec_correction_candidates table**
- Avoids coupling Phase 13.3 to Phase 15/16 schema
- But splits the deposit pipeline — memory_candidates and spec_correction_candidates are different tables with same purpose
- _(Not recommended — creates schema fragmentation)_

**Synthesis recommendation:** ✅ **Option A — Create memory_candidates in Plan 13.3-01**
- Rationale: snippet-not-chunk CCD requires the schema to enforce CCD format structurally (not by convention). Creating the table now with the CCD constraint is the correct investment. Phase 15/16 extends, does not replace.

---

### Q4: Delta-retrieval — What exactly is `axis_retrieval_rate` and how is it measured?

**Question:** The Harness's delta-retrieval invariant stores an `axis_retrieval_baseline` per session and asserts it is non-decreasing. But "axis retrieval rate" requires a definition: what is being measured?

**Why it matters:** This is the empirical measure of whether MEMORY.md improvements are changing AI retrieval quality. Without a concrete definition, the invariant is unimplementable.

**Options:**

**A. Accept rate as proxy**
- axis_retrieval_rate = accepted_verdicts / total_verdicts in this session
- Increasing accept rate = fewer classification errors = better axis retrieval
- Simple, measurable without ground truth
- _(Proposed by: Perplexity)_

**B. Layer coverage as proxy**
- axis_retrieval_rate = layers_with_at_least_1_accepted / 8
- Breadth-first measure of correct classification across layers
- Less sensitive to density effects
- _(Proposed by: Gemini — checksumming approach, adapted)_

**C. Both, as a composite**
- Store both metrics in axis_retrieval_baseline
- Delta-retrieval invariant checks both are non-decreasing
- More complete, more complex

**Synthesis recommendation:** ✅ **Option A — Accept rate as proxy** (simpler, Phase 15 can extend)
- Rationale: Accept rate is the most direct proxy for "the AI's classifications are correct." The delta-retrieval invariant is already structural complexity — keep the metric simple in Phase 13.3 and let Phase 15/16 extend with richer measures.

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Balanced Sampler — How to handle layers with 0 unreviewed instances?

**Question:** Early in the review process, Layer 7 (escalation detection) and Layer 8 (policy feedback) may have very few or zero unreviewed instances. The sampler target is uniform distribution across all 8 layers with no layer >20% when N≥40.

**Options:**

**A. Skip empty layers, redistribute quota proportionally**
- When Layer 8 has 0 instances, remove it from the distribution
- Redistribute its quota equally across remaining active layers
- Log warning "Layer 8 fully reviewed or not yet populated"
- _(Proposed by: Perplexity)_

**B. Block on empty layers (force population first)**
- If any required layer has 0 instances, `review next` returns an error
- Forces pipeline to run first to populate all layers
- _(Proposed by: Gemini — inverse frequency weighting handles this naturally)_

**C. Weighted inverse frequency (never blocks)**
- P(select_layer_N) = 1 / (Count_unreviewed(N) × Σ(1/Count_all))
- When count is 0, layer is excluded automatically from probability mass
- _(Perplexity + Gemini — mathematically equivalent to Option A)_

**Synthesis recommendation:** ⚠️ **Option A / C (equivalent) — Skip empty layers with graceful degradation**
- Rationale: Blocking on empty layers prevents the review system from being useful while the pipeline is still being run. Graceful degradation enables incremental review as pipeline runs accumulate data.

---

### Q6: Trust Level Reset — How does a classification rule recover from a reject?

**Question:** IDTRANS-04 defines established = 10+ accepts + 0 rejects (strict). If a component accumulates 15 accepts, then receives 1 reject (because the human identified a heuristic error), the component drops from established. How does it recover?

**Options:**

**A. Resolve mechanism — mark reject as superseded after code fix**
- Add `resolved_at` timestamp to identification_reviews rows with verdict='reject'
- Resolved rejects don't count toward reject_count
- When pipeline component is fixed and new verdicts come in, the old reject is marked resolved
- _(Both providers implied this is needed)_

**B. Versioned components — reset count on version bump**
- Add `pipeline_component_version` to identification_rule_trust
- When component version increments (git hash or manual), previous reject counts are archived
- Clean slate for the new version
- _(Gemini's proposed approach)_

**C. Never recover — reject is permanent until MEMORY.md fix**
- "One strike" is intentional friction forcing root-cause fix
- Trust level can never exceed "provisional" after a reject until the memory_candidates entry is resolved
- Simplest schema, strongest incentive for quality
- _(Strict reading of IDTRANS-04)_

**Synthesis recommendation:** ⚠️ **Option C with observation** — Start strict (never recover), add `resolved_at` in Phase 15/16 if needed.
- Rationale: The "0 rejects" threshold is intentional — it's the signal that forces a spec-correction candidate into memory_candidates. The recovery mechanism should be: write to memory_candidates, review, update MEMORY.md, re-run the pipeline with the fix, and new verdicts will naturally rebuild trust. No schema complexity needed in Phase 13.3.

---

### Q7: N-version consistency check algorithm — How to parse MEMORY.md?

**Question:** The Harness checks that every accepted memory_candidates entry has a corresponding entry in MEMORY.md. MEMORY.md is a markdown file, not structured data. What parsing strategy should the Harness use?

**Options:**

**A. CCD axis as natural key — check ccd_axis field in MEMORY.md**
- MEMORY.md already structures entries with `**CCD axis:** [axis-name]` headers
- Parse with regex: `\*\*CCD axis:\*\* (.+)` → set of known axes
- Check: every memory_candidates row with status='accepted' has its ccd_axis in the MEMORY.md axis set
- _(Simplest — uses existing MEMORY.md format as-is)_

**B. Anchor tags in MEMORY.md — HTML comments with IDs**
- Add `<!-- CCD_ID: {candidate_id} -->` before each entry
- Harness parses these tags
- More precise but requires modifying MEMORY.md format
- _(Proposed by Gemini)_

**C. Structured headers with parseable format**
- `## SPEC_ERROR: {id} | {spec}` format enforced in MEMORY.md
- _(Proposed by Perplexity — changes MEMORY.md format significantly)_

**Synthesis recommendation:** ⚠️ **Option A — ccd_axis as natural key**
- Rationale: MEMORY.md already uses `**CCD axis:** axis-name` format consistently. Changing this format for Harness parsing would require migrating all existing entries. The ccd_axis string is the natural key — unique by design (each axis should appear once). No format change needed.

---

## Tier 3: Polish Decisions (🔍 Single Provider)

### Q8: PoolBuilder — Create a unified SQL VIEW or 35 separate extractor functions?

**Question:** Gemini proposed a single unified DuckDB VIEW (`view_identification_pool`) that unions all 35 identification point types. Perplexity used individual queries per layer. Which approach is more maintainable?

**Options:**

**A. Single unified VIEW**
- Pros: one query to source all instances, clean abstraction
- Cons: complex UNION of heterogeneous schemas, hard to maintain as pipeline evolves

**B. PoolBuilder class with per-layer query methods**
- `_query_layer1()`, `_query_layer2()`, etc.
- More verbose but each query is readable and independently testable
- Aligns with OPE's existing pattern (isolated components, TDD)

**Synthesis recommendation:** 🔍 **Option B — PoolBuilder class with per-layer methods**
- Rationale: The 35 points have fundamentally different schemas — forcing them into a single VIEW creates artificial coupling. Per-layer methods are independently testable and match the project's TDD pattern.

---

## Next Steps

**YOLO Mode — Auto-answering and proceeding to /gsd:plan-phase 13.3**

The CLARIFICATIONS-ANSWERED.md file will be generated automatically with synthesis recommendations selected above.

---

*Multi-provider synthesis: Gemini Pro (high thinking), Perplexity Sonar Reason*
*Generated: 2026-02-23*
*YOLO mode: Auto-answers will be generated*
