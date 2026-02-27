# CLARIFICATIONS-NEEDED.md

## Phase 15: DDF Detection Substrate — Stakeholder Decisions Required

**Generated:** 2026-02-24
**Mode:** Multi-provider synthesis (Gemini Pro, Perplexity Sonar Deep Research)
**Source:** 2 AI providers analyzed Phase 15 requirements (OpenAI returned empty response)

---

## Decision Summary

**Total questions:** 8
**Tier 1 (Blocking):** 4 — Must decide before Wave 1 implementation
**Tier 2 (Important):** 4 — Should decide before Wave 2

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: Write-on-Detect Fidelity Boundary

**Question:** Does "immediate deposit to memory_candidates" (DDF-09) mean synchronous with Level 6 detection in the Tier 1 hook, or atomic with Level 6 confirmation in the Tier 2 OPE post-task pipeline?

**Why it matters:** Tier 1 hooks cannot produce valid `ccd_axis`, `scope_rule`, `flood_example` values (CHECK constraints) without LLM context. Forcing deposits at Tier 1 requires relaxing those constraints. Keeping deposits at Tier 2 means Level 6 fires are processed ~3.3s after session, not at detection time.

**Options identified by providers:**

**A. Tier 2 Only (OPE pipeline writes to memory_candidates post-task)**
- Tier 1 hooks write only to `flame_events` (staging)
- OPE pipeline processes flame_events, confirms Level 6, writes to memory_candidates atomically with confirmation
- No CHECK constraint relaxation needed
- Write authority stays in DuckDB single-writer bus process
- _(Proposed by: Gemini, Architecture precedent from Phase 14 spike)_

**B. Two-Tier Deposit (Tier 1 writes fidelity=1 stub, Tier 2 upgrades to fidelity=2)**
- Tier 1 immediately writes placeholder with provisional ccd_axis
- CHECK constraints relaxed to permit fidelity=1 entries
- Separate enrichment pipeline upgrades to fidelity=2
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A — Tier 2 Only**
- Rationale: CHECK constraints exist for a reason (CCD-quality enforcement). Relaxing them introduces a class of entries that look validated but aren't. The DuckDB single-writer constraint also makes Tier 1 writes problematic. "Immediate" in DDF-09 means atomic with confirmation, not synchronous with the user event.

**Sub-questions:**
- Should `flame_events` carry a `deposited_to_candidates BOOLEAN DEFAULT false` flag for retry tracking?
- Should `memory_candidates` add `source_flame_event_id` FK for lineage?

---

### Q2: DDF Marker Level Heuristics — Tier 1 Stub Scope

**Question:** Which DDF marker levels (0-7) should be detected by Tier 1 regex stubs (hook time), and which require Tier 2 OPE LLM scoring?

**Why it matters:** Tier 1 stubs run synchronously with every tool call; they must be fast (< 50ms). Tier 2 OPE scoring runs post-task. If too many levels are Tier 1, hooks become slow. If too few, real-time detection provides no value.

**Options identified by providers:**

**A. Tier 1 = L0-1 only; Tier 2 = L2-7**
- L0 (trunk identification): regex for categorization language ("is a [type] problem")
- L1 (guided causal discovery): regex for causal markers with prior instruction context
- L2-7: require LLM semantic analysis → Tier 2 only
- _(Proposed by: Gemini)_

**B. Tier 1 = L0-2, O_AXS; Tier 2 = L3-7**
- L2 (spontaneous CCD): detect assertive causal language without prior prompting → regex possible
- O_AXS: dual signal (token count + noun phrase) → fully computable at Tier 1
- _(Proposed by: Claude synthesis)_

**Synthesis recommendation:** ✅ **Option B — Tier 1 = L0-2, O_AXS; Tier 2 = L3-7**
- Rationale: O_AXS must fire in real-time to affect session behavior (co-pilot intervention). L2 detection (unprompted causal language) is pattern-matchable without LLM. L3+ (isolation, analogy, flood) require context comparison across messages → Tier 2.

**Sub-questions:**
- Should Tier 1 detections carry `detection_source='stub'` and Tier 2 carry `detection_source='opeml'` for recalibration tracking?
- What precision/recall tradeoff is acceptable for stub detection? (High recall / low precision preferred: emit candidates, OPE filters)

---

### Q3: O_AXS Signal Thresholds

**Question:** What specific thresholds operationalize the O_AXS dual signal (granularity drop + novel concept)?

**Why it matters:** O_AXS is the tagger extension required for DDF-06. It changes episode mode to `ESCALATE→O_AXS`. Thresholds determine false positive rate against real sessions.

**Options identified by providers:**

**A. Quantitative thresholds (current recommendation)**
- Granularity drop: current prompt token count < 0.5 × avg(prior 4 prompts)
- Novel concept: capitalized noun phrase not in session `known_concepts` set, appearing 2+ times in last 3 messages
- _(Proposed by: Claude synthesis combining Gemini + Perplexity)_

**B. LLM-scored specificity (Gemini approach)**
- Specificity score 1-10 for each prompt via LLM
- If N ≤ 3 AND N-1 ≥ 8 AND new capitalized noun phrase → O_AXS
- More accurate but adds LLM call to Tier 1 (too slow)

**C. 30% granularity drop + cosine distance threshold (Perplexity approach)**
- Embedding-based concept novelty
- Requires sentence-transformers at hook time (too heavy for Tier 1)

**Synthesis recommendation:** ✅ **Option A — Quantitative thresholds (Tier 1 computable)**
- Rationale: Options B and C require LLM or embeddings at Tier 1, violating latency requirement. Option A is O(1) computable from message JSON. Thresholds can be tuned via `config.yaml` after calibration against real sessions.

**Sub-questions:**
- Should O_AXS fire on both human and AI messages, or human only? (Architecture says "instruction granularity" → human; AI can have separate `ai_flame_events` path)
- Should the `known_concepts` set persist across sessions (project-level) or reset per session?

---

### Q4: False Integration Proxy Scope

**Question:** Since CCD axis tagging of code entities is not yet built, should DDF-07 be deferred entirely, or implemented as a PREMISE-scope-divergence proxy?

**Why it matters:** DDF-07 is a Phase 15 requirement. Without CCD axis metadata, a true Package Deal detector cannot be built. A proxy exists (PREMISE records with same claim applied to different module scopes) but has lower fidelity and may produce false positives.

**Options identified by providers:**

**A. Defer DDF-07 to Phase 16 when axis tagging exists**
- No false positives from missing axis data
- But Phase 15 delivers 0 of DDF-07
- _(Proposed by: implicit in Gemini's "hypothesize and check" — acknowledges no registry)_

**B. Implement heuristic proxy now (PREMISE scope divergence)**
- Use PremiseRegistry: when same `claim` text appears in PREMISEs with different `project_scope` fields → emit DDF-07 marker
- Mark as `fidelity=1`, `detection_source='heuristic_proxy'`
- _(Proposed by: Claude synthesis)_

**C. Single-pass LLM hypothesize-and-check (Gemini approach)**
- OPE prompt: "Identify two entities treated as unit. Hypothesize CCD axis for each. If different → Flag."
- Higher quality than B, doesn't require axis registry
- Adds LLM call per episode in Tier 2

**Synthesis recommendation:** ✅ **Option C — LLM hypothesize-and-check in Tier 2 OPE**
- Rationale: Option A misses Phase 15 requirement. Option B has too many false positives. Option C is within Tier 2 budget (post-task, not real-time). The hypothesized axes can also be written to `memory_candidates` as their own provisional entries, seeding the eventual axis registry.

**Sub-questions:**
- Should hypothesized axes (from Option C) be stored in `premise_registry` or a new `axis_candidates` table?
- What confidence threshold should the OPE LLM use to fire DDF-07 vs. log as "inconclusive"?

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Epistemological Origin — Hard Enum or Probability Distribution?

**Question:** Should `epistemological_origin` be a hard enum value (`reactive | principled | inductive`) or a probability distribution (`{reactive: 0.7, principled: 0.2, inductive: 0.1}`)?

**Why it matters:** Many decisions have mixed origins. Hard enum loses information. Probability distribution complicates downstream use (existing code expects enum).

**Options:**
**A. Hard enum** — pick highest-scoring category, accept information loss. Simpler downstream. _(Both providers implied this)_
**B. Probability distribution** — store as JSON column. Richer, but breaks existing ConstraintStore schema.
**C. Hard enum + confidence float** — primary assignment + confidence score (e.g., `reactive, confidence=0.7`).

**Synthesis recommendation:** ⚠️ **Option C — Hard enum + confidence float**
- Rationale: Minimal schema change (add `epistemological_confidence FLOAT`). Downstream can ignore confidence initially, use it later.

---

### Q6: GeneralizationRadius — Scope Level

**Question:** Should `generalization_radius` be computed at Phase 15 as a count-based proxy (distinct scope_path prefixes where constraint has fired), or deferred until embedding-based computation is feasible?

**Options:**
**A. Count-based proxy now** — `COUNT(DISTINCT scope_path_prefix) FROM session_constraint_eval`. Computable from existing DuckDB data. Simple.
**B. Defer to Phase 16** — embedding-based semantic distance when sentence-transformers are fully integrated.

**Synthesis recommendation:** ⚠️ **Option A — Count-based proxy for Phase 15**
- The proxy gives immediate signal (stagnation detection). Embedding refinement is Phase 16 scope.

---

### Q7: Causal Isolation Query — Active or Passive?

**Question:** Should DDF-08 only *record* that FoilInstantiator performed isolation (passive), or should it also *trigger* new FoilInstantiator queries for post-hoc claims that weren't previously foil-checked (active)?

**Options:**
**A. Passive recorder only** — listen for FoilInstantiator results, log in `ai_flame_events`. Zero duplication.
**B. Active trigger** — DDF-08 also detects claims that lack foil verification and triggers new foil queries.

**Synthesis recommendation:** ⚠️ **Option A — Passive recorder for Phase 15**
- Active trigger is Phase 16 scope. Phase 15 establishes the record; Phase 16 adds the trigger capability.

---

### Q8: memory_candidates Schema Extension

**Question:** Which new columns should be added to `memory_candidates` to support automated flame-event deposits?

**Proposed additions (need confirmation):**
- `source_flame_event_id VARCHAR` — FK back to `flame_events.id` for lineage (nullable for human entries)
- `fidelity INTEGER DEFAULT 2` — 2=OPE-confirmed, 1=reserved
- `detection_count INTEGER DEFAULT 1` — incremented on subsequent Level 6 floods for same concept
- Dedup key: `UNIQUE(ccd_axis, scope_rule)` — prevents duplicate entries for same concept

**Open questions:**
- Does the existing `memory_candidates` UNIQUE constraint need changing? (Currently: `UNIQUE(id)`, no content-level dedup)
- Should `detection_count` affect review priority in the existing review CLI?

---

## Next Steps (YOLO Mode)

Auto-generating CLARIFICATIONS-ANSWERED.md with recommended decisions.

---

*Multi-provider synthesis: Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-24*
*YOLO mode: Proceeding to auto-generate answers*
