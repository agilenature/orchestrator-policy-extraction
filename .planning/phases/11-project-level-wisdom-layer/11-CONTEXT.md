# CONTEXT.md — Phase 11: Project-Level Wisdom Layer

**Generated:** 2026-02-20
**Phase Goal:** The pipeline captures and retrieves project-level knowledge (breakthroughs, dead ends, scope decisions) as structured entities in a `project_wisdom` DuckDB table. The RAG retriever uses these alongside episode context.
**Synthesis Source:** Multi-provider AI analysis (Gemini Pro with high thinking, Perplexity Sonar Deep Research)
**Note:** OpenAI Phase 11 query returned empty (no content); 2-provider synthesis (Gemini + Perplexity) satisfies minimum threshold.

---

## Overview

Phase 11 extends the existing RAG pipeline with a new knowledge layer: project-level wisdom entities extracted from analysis documents and stored alongside episodes. The core challenge is that wisdom entities (Breakthrough, DeadEnd, ScopeDecision, MethodDecision) are semantically different from episodes—they are meta-level, abstract, and heterogeneous—yet must integrate seamlessly with the existing HybridRetriever (BM25 + VSS) that currently returns only Episode objects.

Six interconnected gray areas require architectural decisions before implementation can proceed. The decisions are ordered by dependency: schema first, then embedding, then retrieval fusion, then ingestion, then detection, then CLI.

**Confidence markers:**
- ✅ **Consensus** — Both providers independently identified this as critical
- ⚠️ **Recommended** — 1 provider identified; high-confidence single-provider insight
- 🔍 **Needs Clarification** — 1 provider identified, lower certainty

---

## Gray Areas Identified

### ✅ 1. Wisdom Entity Schema: Fields, Polymorphism, and Embedding Content (Consensus)

**What needs to be decided:**
The DuckDB `project_wisdom` table schema: which fields are common to all entity types, which are type-specific, and critically what text content is stored for FTS and embedding (the `content_for_embedding` column).

**Why it's ambiguous:**
Four entity types (Breakthrough, DeadEnd, ScopeDecision, MethodDecision) have fundamentally different semantic fields. A naive approach (single flat table with nulls) creates sparse data and poor FTS/embedding quality. A Breakthrough needs `problem` + `solution`; a DeadEnd needs `attempted_strategy` + `failure_reason`. Without a `content_for_embedding` standard, the retriever can't generate meaningful vectors.

**Provider synthesis:**
- **Gemini:** Use Pydantic Discriminated Unions at the Python layer, maintain a `content_for_embedding` text column in DuckDB synthesizing the key semantics for each type. Example: `"Dead End: [strategy] failed because [reason]."` and `"Breakthrough: [solution] solved [problem]."`
- **Perplexity:** Core table stores common fields (id, type, title, description, created_at, episode_ids, confidence_score, embedding_vector, source_document); type-specific attributes go in a separate `wisdom_attributes` table (attribute_key, attribute_value JSON) or in metadata_json. Enforces type constraints via CHECK and Pydantic Field validators.

**Proposed implementation decision:**
Hybrid flat + JSON approach (consistent with existing episodes table pattern):
- Core `project_wisdom` columns: `wisdom_id` (UUID PK), `type` (CHECK: breakthrough|dead_end|scope_decision|method_decision), `title`, `description` (FTS-indexed), `content_for_embedding` (synthesized text), `embedding` (FLOAT array), `confidence_score` (FLOAT 0–1), `episode_ids` (JSON array), `source_document` (VARCHAR), `created_at`, `metadata` (JSON for type-specific attributes)
- Type-specific metadata stored in `metadata` JSON column (no separate table, consistent with project patterns)
- `content_for_embedding` synthesized per type: `"[type_label]: [title]. [description]."` as minimum, richer when metadata fields populated.
- Pydantic discriminated union models with `type` as discriminator field

**Open questions:**
- Should `episode_ids` be mandatory (every wisdom must link to episodes) or optional (allows ingesting wisdom from external docs)?
- Should we use a `wisdom_text` column for FTS or reuse `content_for_embedding`?

**Confidence:** ✅ Both providers agreed this is blocking (can't build anything else without schema)

---

### ✅ 2. Retrieval Integration: How Wisdom Merges with Episodes (Consensus)

**What needs to be decided:**
Whether to extend `HybridRetriever` to query wisdom alongside episodes (single merged result), or create a separate `WisdomRetriever` that runs in parallel and delivers results as a distinct category.

**Why it's ambiguous:**
The existing `HybridRetriever` returns `List[Episode]`. Adding wisdom changes the return type to `Union[Episode, WisdomEntity]`, breaking the `Recommender` and all downstream consumers. But separate retrieval requires changing how context assembly works. The scoring scales are also incompatible: wisdom similarity ≥ 0.8 might be meaningless compared to episode similarity ≥ 0.7.

**Provider synthesis:**
- **Gemini:** Separate `WisdomRetriever` running parallel to `HybridRetriever`. Context assembly creates distinct sections: "Project Wisdom" (high priority) vs. "Relevant Past Episodes" (contextual evidence). Do NOT dilute the episode retriever's focus.
- **Perplexity:** Two-stage retrieval with optional RRF (Reciprocal Rank Fusion) for merging: Stage 1 retrieves top-N wisdom and top-k episodes separately; Stage 2 applies RRF if a single merged list is needed. RRF score = Σ (1 / (k + rank)) with k=60 default. Maintains option for either separate or merged presentation.

**Proposed implementation decision:**
**Separate `WisdomRetriever` + optional RRF fusion in Recommender:**
1. Create `WisdomRetriever` class (BM25 on `description`/`content_for_embedding` + VSS on `embedding`) returning `List[WisdomEntity]` top-3 results
2. `Recommender.recommend()` calls both `HybridRetriever` (episodes) and `WisdomRetriever` (wisdom) independently
3. Return structured `RecommendationResult` with separate `episodes: List[SourceEpisodeRef]` and `wisdom_context: List[WisdomRef]` fields
4. Add wisdom as preamble block in the recommendation context: "Relevant Project Wisdom: [entries]"
5. RRF fusion is optional (for future single-list use cases) but not required for Phase 11

**Open questions:**
- How many wisdom results per recommendation? (Proposal: top-3, hard cap)
- Should wisdom results ever suppress episode results? (Proposal: No, additive only)

**Confidence:** ✅ Both providers agreed a separate retriever path is cleaner

---

### ✅ 3. Document Ingestion: Converting Objectivism Analysis Docs to Wisdom Entries (Consensus)

**What needs to be decided:**
How to extract 15+ structured wisdom entries from the four objectivism analysis documents in `docs/analysis/objectivism-knowledge-extraction/`. These are already-written markdown files; the question is the ingestion mechanism.

**Why it's ambiguous:**
The docs are analyst-written narrative, not machine-readable structured data. A custom NLP parser for 4 one-off files is over-engineering. Full automated LLM extraction without human review risks incorrect entities corrupting the wisdom base. Manual entry is slow and doesn't exercise the "pipeline captures" requirement.

**Provider synthesis:**
- **Gemini:** Create a `seed_wisdom.yaml` (or JSON) file manually structured from the analysis docs, then implement `wisdom ingest <file>` CLI command to load it into DuckDB. This builds the tool for future use while handling the one-off migration cleanly.
- **Perplexity:** Three-stage pipeline: (1) document structure recognition (section detection), (2) prompt-based LLM extraction (per section, per type), (3) human curation via `wisdom validate` interactive CLI. Preserves provenance (source_document field links back to origin file).

**Proposed implementation decision:**
**YAML seed file + `wisdom ingest` CLI command (Gemini approach, with Perplexity provenance):**
1. Manually extract 15+ entries from the 4 analysis docs into `data/seed_wisdom.yaml` with explicit type labels and fields
2. Include `source_document` field linking each entry to its origin file
3. Implement `python -m src.pipeline.cli wisdom ingest <yaml_file>` that validates against Pydantic models and writes to DuckDB
4. Embed each entry during ingest using the existing sentence-transformer embedder
5. Full LLM-assisted parsing (Perplexity approach) is deferred: the 4 docs are small enough for manual extraction and the seed YAML establishes the schema

**Open questions:**
- Should `confidence_score` be required during manual ingestion (0.0-1.0)? (Proposal: Default to 0.9 for human-curated entries)
- Should existing objectivism analysis docs be read-only sources, or will they be updated over time?

**Confidence:** ✅ Both providers agreed seed file + ingest CLI is the right pattern

---

### ✅ 4. Dead End Detection Logic: Threshold and Context Definition (Consensus)

**What needs to be decided:**
The specific mechanism for detecting when a current recommendation context matches a known dead end — specifically: (A) what "context" is compared against the dead end (current query, recent episode, task description), and (B) what similarity threshold triggers a warning.

**Why it's ambiguous:**
"Context matches known failures" is under-defined. Comparing against code changes (option B) requires a code-understanding embedding model. Comparing against the task prompt (option A) is simpler but misses cases where the user doesn't articulate they're attempting a known dead end approach. A high threshold (0.85+) misses relevant warnings; a low threshold (0.5) generates annoying false positives.

**Provider synthesis:**
- **Gemini:** Intent-based matching: embed the current task/prompt, vector search against DeadEnd entities, inject warning block in context if similarity > threshold (e.g., 0.85). Warns on approach before execution.
- **Perplexity:** Hybrid detection: require agreement between BM25 (vocabulary match) AND vector similarity (semantic match). A dead end is surfaced only if it appears in top-10 of BOTH searches and combined RRF score exceeds threshold. Reduces false positives significantly.

**Proposed implementation decision:**
**Hybrid BM25 + vector with two-signal agreement (Perplexity approach):**
1. `DeadEndDetector.detect(query_text: str) -> List[WisdomEntity]` — searches `project_wisdom` WHERE type='dead_end'
2. Returns entries that rank in top-10 of BOTH BM25 and vector searches (dual-signal filter)
3. Default threshold: dual top-10 agreement (no separate score threshold needed initially)
4. `WisdomRetriever` incorporates this as a special path: dead end results flagged with `is_warning=True`
5. Conservative start: calibrate later with empirical data from real usage

**Open questions:**
- Should dead end warnings suppress the recommendation or merely annotate it? (Proposal: Annotate only, don't suppress)
- Should there be a dead end severity field (severity: warning/error)? (Proposal: Yes, with 'warning' default)

**Confidence:** ✅ Both providers agreed hybrid detection reduces false positives

---

### ⚠️ 5. Scope Decision Enforcement: ConstraintStore Linkage vs. Standalone (Recommended)

**What needs to be decided:**
How `wisdom check-scope` "enforces" scope decisions. Can it mechanically check code/state, or is it a read-only summary for human review? Should ScopeDecision entities link to constraint IDs in the existing ConstraintStore?

**Why it's ambiguous:**
Text-based scope decisions (e.g., "don't use Auth0, use dummy auth") can't be mechanically enforced without code analysis. The existing ConstraintStore already handles enforcement. Risk of duplicating logic if Wisdom tries to do enforcement independently.

**Provider synthesis:**
- **Gemini:** ScopeDecision entities have optional `related_constraint_ids: List[str]` field linking to ConstraintStore entries. `check-scope` runs existing constraint validation for linked constraints. If no constraints linked, outputs scope decisions as human-readable list. Wisdom explains WHY; Constraints enforce WHAT.
- **Perplexity:** `check-scope` accepts `project_id`, exits with code 0 (pass), 1 (violation), 2 (error). Enforcement criteria stored as structured JSON in `metadata.enforcement_criteria`. CLI checks these criteria against project state.

**Proposed implementation decision:**
**ConstraintStore linkage (Gemini approach) with structured exit codes (Perplexity approach):**
1. `ScopeDecision` metadata includes optional `constraint_ids: List[str]` linking to ConstraintStore
2. `wisdom check-scope [--session <session_id>]` command:
   - Lists active ScopeDecision entities
   - For each with `constraint_ids`, runs existing constraint compliance check for that session
   - Reports: decisions linked to constraints (checked mechanically) vs. text-only decisions (reported for human review)
   - Exit codes: 0=all pass, 1=violation found, 2=error
3. This avoids duplicating constraint enforcement logic already built in Phases 3/10

**Open questions:**
- Should Phase 11 create new ConstraintStore entries for scope decisions that don't yet have linked constraints?

**Confidence:** ⚠️ Gemini identified this; Perplexity addressed CLI interface separately

---

### ⚠️ 6. Embedding Strategy: Same Model as Episodes vs. Separate (Recommended)

**What needs to be decided:**
Whether wisdom entities use the same sentence-transformer model as episodes, or require a separate/different embedding approach.

**Why it's ambiguous:**
Wisdom entities are abstract/analytical text; episodes are concrete session logs. The existing model may not capture "Breakthrough: X solved Y" as meaningfully as concrete code-related text. However, using different models makes RRF fusion mathematically problematic (vector spaces incompatible for direct similarity comparison).

**Provider synthesis:**
- **Gemini:** Asked whether the existing embedding model works well for abstract concepts vs. code logs — noted this as an open question, suggested using a prefix ("Instruction: ...") if needed.
- **Perplexity:** Use the same embedding model for both. Benefits: comparable similarity scores enable meaningful retrieval, simpler model management, avoids fine-tuning costs. Expose `embedding_model` as a configurable parameter for future A/B testing. 768-dim vectors acceptable for sub-100K wisdom table size.

**Proposed implementation decision:**
**Same model as episodes (Perplexity approach):**
1. Reuse `EpisodeEmbedder` model for wisdom entity embeddings
2. Store embeddings in `project_wisdom.embedding` column (same dimensions as episodes.embedding)
3. Ensure `content_for_embedding` text is well-formed to maximize embedding quality (natural sentences, not field dumps)
4. Mark embedding model in DuckDB schema as a configurable constant (no hardcoded model names in SQL)
5. Provide `wisdom reindex` CLI command for regenerating embeddings when model changes

**Open questions:**
- Should wisdom embeddings use a prefix prompt (e.g., "Project wisdom: ") to help the model distinguish wisdom from regular text? (Proposal: Experiment after initial implementation)

**Confidence:** ⚠️ Perplexity strongly recommended unified model; Gemini raised the question without resolution

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking):**
- [ ] `project_wisdom` table schema finalized (columns, types, CHECK constraints, content_for_embedding pattern per type)
- [ ] Retrieval integration architecture decided (separate WisdomRetriever + optional RRF confirmed)
- [ ] Document ingestion approach decided (seed YAML + `wisdom ingest` CLI confirmed)
- [ ] Dead end detection mechanism confirmed (dual BM25+vector top-10 agreement)

**Tier 2 (Important):**
- [ ] Scope decision enforcement linkage confirmed (ConstraintStore `constraint_ids` optional field)
- [ ] Embedding model strategy confirmed (reuse EpisodeEmbedder)

**Tier 3 (Polish):**
- [ ] `content_for_embedding` synthesis templates per entity type
- [ ] CLI exit code conventions for `wisdom check-scope`
- [ ] Wisdom provenance fields (source_document, episode_ids optionality)

---

*Multi-provider synthesis by: Gemini Pro (high thinking), Perplexity Sonar Deep Research*
*Note: OpenAI Phase 11 query returned no content — 2-provider synthesis used*
*Generated: 2026-02-20*
