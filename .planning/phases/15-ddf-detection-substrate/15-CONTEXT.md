# CONTEXT.md — Phase 15: DDF Detection Substrate

**Generated:** 2026-02-24
**Phase Goal:** Implement the DDF as a deposit substrate for the AI's concept store. Detection machinery (flame_events, ai_flame_events, co-pilot interventions) is instrumental — it exists to trigger write-on-detect deposits to `memory_candidates`. The AI's missing cost function means it cannot form genuine concepts; this phase borrows the human's selection pressure to build the AI's filing system.
**Synthesis Source:** Multi-provider AI analysis (Gemini Pro, Perplexity Sonar Deep Research)
**Note:** OpenAI returned empty response; synthesis based on 2 providers (minimum threshold met).

---

## Overview

Phase 15 is the first implementation phase of the DDF system. It builds the deposit substrate: `flame_events`, `ai_flame_events`, `O_AXS` episode mode, `IntelligenceProfile` aggregates, and write-on-detect to `memory_candidates`. The governing axis from MEMORY.md applies directly: **deposit-not-detect** — every component is evaluated by whether it deposits to `memory_candidates`. Detection that never produces a candidate is instrumentation noise.

Eight implementation gray areas were identified. Four are consensus blockers (both providers), four are important architectural decisions.

**Confidence markers:**
- ✅ **Consensus** — Both providers identified this as critical/blocking
- ⚠️ **Recommended** — 1 provider identified with strong rationale; other touched tangentially
- 🔍 **Needs Clarification** — 1 provider identified; potentially important

---

## Gray Areas Identified

### ✅ 1. Write-on-Detect Fidelity: When Does "Immediate" Mean?

**What needs to be decided:**
The write-on-detect requirement (DDF-09) says every Level 6 FlameEvent triggers "immediate deposit" to `memory_candidates`. But `memory_candidates` has CHECK constraints requiring non-empty `ccd_axis`, `scope_rule`, and `flood_example`. Real-time hooks (Tier 1) cannot compute these reliably — they lack LLM context. Post-task OPE pipeline (Tier 2) can compute them but runs 3.3s after the session.

**Why it's ambiguous:**
"Immediate" could mean:
- Synchronous with detection event (blocks session flow if Tier 1)
- Atomic with confirmation (Tier 2 runs immediately after Level 6 is confirmed by OPE pipeline)
- Batched post-task (OPE pipeline processes all at once after session)

The current architecture already has a two-tier fidelity model (from Phase 14 spike). The question is whether `memory_candidates` CHECK constraints need to be relaxed to permit `fidelity=1` stubs, or whether Tier 1 only writes to `flame_events` and Tier 2 does the `memory_candidates` write.

**Provider synthesis:**
- **Gemini:** "Write-on-detect occurs in Tier 2 (OPE Pipeline). Tier 1 (Hooks) only logs candidate flame_events (Level 0-1). OPE pipeline reads these, upgrades them, and writes to memory_candidates atomic with detection."
- **Perplexity:** "Two-tier deposit: Tier 1 writes `fidelity=1` entries immediately with provisional ccd_axis. CHECK constraints should be relaxed to permit provisional entries. Separate enrichment pipeline upgrades to `fidelity=2`."

**Proposed implementation decision:**
Write to `memory_candidates` happens in **Tier 2 (OPE Pipeline)**, triggered atomically when Level 6 is confirmed during post-task OPE processing. Tier 1 hooks write only to `flame_events` (staging). This avoids CHECK constraint relaxation and keeps write authority in the DuckDB single-writer bus process.

However: add a `fidelity` column to `memory_candidates` now (fidelity=2 = OPE-confirmed, fidelity=1 = future stub path). The CHECK constraint on `ccd_axis`/`scope_rule`/`flood_example` remains — Tier 2 must provide these. A provisional/stub path (fidelity=1 with relaxed CHECK) can be added in Phase 16 if needed.

**Open questions:**
- If an OPE run fails mid-session, are Level 6 detections lost? (Need retry mechanism in `flame_events` with `deposited_to_candidates=false` flag)
- Should `memory_candidates` carry a `source_flame_event_id` FK for lineage?

**Confidence:** ✅ Both providers agreed this is the critical blocking decision for Phase 15.

---

### ✅ 2. DDF Marker Level Detection Heuristics (What Text Patterns Indicate Each Level?)

**What needs to be decided:**
The OPE pipeline must classify events into DDF marker levels 0-7 from JSONL session content. No explicit annotation system exists. The heuristics are the entire detection mechanism.

**Why it's ambiguous:**
Each level is a distinct epistemic state:
- Level 0: Trunk Identification (fundamental problem category recognition)
- Level 1: CCD introduction (guided causal discovery)
- Level 2: Spontaneous CCD (unprompted causal discovery by AI)
- Level 3: Causal Isolation (Method of Difference applied)
- Level 4: Analogy Recognition (structural transfer across domains)
- Level 5: Flood Initiation (pattern recognized as ubiquitous)
- Level 6: Flood Confirmed (principle enumerated across multiple domains)
- Level 7: Spiral (principle generates its own discovery)

The text signals for each level are not specified, and different users express reasoning differently.

**Provider synthesis:**
- **Perplexity:** Detailed linguistic markers per level. L0: problem decomposition language, categorization ("this is a [type] problem"). L1: counterfactuals, mechanism descriptions ("works by means of"). L2: shift from "I should investigate" to assertive "the cause is...". L3: "all other factors equal", isolation methodology. L4: explicit comparison ("similar to", "follows the same pattern"). L5: surprise at ubiquity ("I didn't realize this was so common"), scope expansion. L6: enumeration of multiple instances across domains + confidence. L7: meta-reasoning about the reasoning process.
- **Gemini:** Proposed scoring prompt per level. L0-1 via Tier 1 stub; L2-7 require OPE pipeline LLM analysis.

**Proposed implementation decision:**
Implement a **multi-signal scoring system** per level with Tier 1 stubs for L0-1 (regex-based) and Tier 2 OPE LLM scoring for L2-7. Each level fires when a confidence threshold is crossed (sum of weighted signals > threshold). Signals: lexical (keyword patterns), structural (message length change, hedging decrease), sequential (position in session arc).

Tier 1 stub heuristics (in `flame_detector.py`):
- L0: `re.search(r'\b(is a|represents a|this is the)\b.*\b(problem|pattern|constraint)\b', text)`
- L1: `re.search(r'\b(because|caused by|results in|since)\b', text)` with prior instruction in context

Tier 2 OPE scoring: `FlameEventExtractor` class runs after episode population, uses a structured prompt to score levels 2-7.

**Open questions:**
- Should flame_events carry a `confidence_score` per level, or just the final `marker_level` int?
- False positive tolerance: what is acceptable? (Suggest: track `detection_source: 'stub' | 'opeml'` to allow later recalibration)

**Confidence:** ✅ Both providers identified this as foundational — without it, nothing downstream can be implemented.

---

### ✅ 3. O_AXS Detection Algorithm: What Measurable Signals Distinguish It?

**What needs to be decided:**
The O_AXS episode mode fires when "instruction granularity drops sharply AND a new unifying concept is introduced." Both conditions are subjective without concrete operationalizations.

**Why it's ambiguous:**
"Instruction granularity" is not defined numerically. "New unifying concept" requires knowing what concepts were present before. Neither is directly observable from JSONL fields.

**Provider synthesis:**
- **Gemini:** Sliding window comparator. Specificity score for previous 3 prompts (1-10 scale via LLM). If Prompt N ≤ 3 (abstract) and Prompt N-1 ≥ 8 (specific), AND Prompt N contains capitalized noun phrase not previously seen → O_AXS fires.
- **Perplexity:** Rolling window analysis: granularity measured as average tokens per instruction + action description complexity. When granularity drops ≥ 30% from prior window, AND semantic analysis detects novel concept cluster (cosine distance from prior concepts above threshold) co-occurring with low-granularity instructions → O_AXS fires.

**Proposed implementation decision:**
Two-signal detection (both must fire):

Signal A — Granularity drop: Compute `instruction_token_count` for last 5 human prompts. If current prompt token count < 0.5 × avg(prior 4 prompts), granularity drop = True. (Tier 1 stub: token count from message JSON is available immediately)

Signal B — Novel concept introduction: Track a per-session `known_concepts` set. Extract capitalized noun phrases from current message. If any noun phrase is not in `known_concepts` AND appears more than once in last 3 messages → novel concept = True.

When both signals fire, emit O_AXS tag on the current episode. This is computable at Tier 1 (stub fidelity) from message content alone, making O_AXS the one DDF marker that can fire at hook time.

**Open questions:**
- Should O_AXS apply to human messages, AI messages, or both? (Phase 14.1 says "instruction granularity" → human, but AI can also introduce unifying concepts)
- Threshold tuning: the 50% and 0.5x thresholds are initial guesses; real session calibration required

**Confidence:** ✅ Both providers flagged this as blocking; specific thresholds need calibration against real sessions.

---

### ✅ 4. False Integration Detection: Blocked by Missing CCD Axis Tagging

**What needs to be decided:**
DDF-07 (False Integration / Package Deal fallacy) requires comparing the CCD axis of two code entities. But CCD axis tagging of code entities is not yet built. How to implement DDF-07 without it?

**Why it's ambiguous:**
Full False Integration detection is fundamentally blocked until code entities carry CCD axis metadata. Yet DDF-07 is a Phase 15 requirement. Two choices: (a) defer DDF-07 to Phase 16 when axis tagging exists; (b) implement a heuristic proxy now.

**Provider synthesis:**
- **Gemini:** "Single-pass Hypothesize and Check prompt — OPE asks: 'Identify two entities treated as a unit. Hypothesize CCD axis for each. If axes differ but same rule applied → Flag DDF-07.' Cannot rely on database lookups; must be contained in extraction context window."
- **Perplexity:** "Maintain reasoning rule registry. When rule is applied to new entity, check if new entity differs significantly (semantic distance + structural features) from original context. If significantly different without explicit justification → False Integration fires."

**Proposed implementation decision:**
Implement DDF-07 as a **heuristic proxy** in Tier 2 OPE (not Tier 1), clearly marked as `detection_source='heuristic_proxy'` with `fidelity=1`. The heuristic: when the OPE pipeline observes the same PREMISE or reasoning rule applied in the same session to two entities with different structural characteristics (file type, module scope, data type), emit a False Integration marker.

Concrete operationalization:
1. Extract entities from PREMISE blocks (already being processed by Phase 14.1 PremiseRegistry)
2. Compare `project_scope` field across PREMISE records that share identical or near-identical `claim` text
3. If same claim is applied to entities in different modules → emit `ai_flame_events` record at `marker_type='false_integration'`, `marker_level=2` (spontaneous CCD detection class)

This defers full DDF-07 (axis-aware) to when CCD axis tagging exists, but deposits a detectable proxy now.

**Open questions:**
- Should hypothesized axes from the OPE prompt be written to `memory_candidates` as their own entries (separate from the false integration marker)?
- How does CCD axis tagging get built — is that Phase 16 scope?

**Confidence:** ✅ Both providers identified this as a blocking architectural decision; proxy approach is consensus direction.

---

### ⚠️ 5. Epistemological Origin Inference: Heuristics for Reactive/Principled/Inductive

**What needs to be decided:**
DDF-05 requires an `epistemological_origin` field on every constraint: `reactive | principled | inductive`. The categorization algorithm is not defined.

**Why it's ambiguous:**
The categories are conceptually clear but operationally blurry. A "principled" decision may look identical to a "reactive" decision in text if the principles are implicit. An "inductive" decision requires observing multiple examples before generalization.

**Provider synthesis:**
- **Gemini:** Pattern-based classifier. Reactive: prior turn has user_correction + negative sentiment → constraint generated immediately. Inductive: prior AI reasoning contains evidence_list or example_citation. Principled: citations of existing premise_registry items + deontic modal verbs (must, inherently) without immediate examples.
- **Perplexity:** Weighted feature scoring. Reactive: low constraint-justification depth, no alternatives mentioned, pattern-match → apply language. Principled: constraint enumeration, trade-off discussion, causal grounding. Inductive: multiple examples before generalization, progressive language (tentative → confident). Confidence score accompanies each assignment.

**Proposed implementation decision:**
Implement as a **weighted scoring classifier** in `ConstraintExtractor` (Phase 3 component, already exists). Add `epistemological_origin` as a new field computed at extraction time using three signal groups:

Reactive signals (high weight): episode contains `reaction_label IN ('block', 'correct')` + constraint extracted within same episode + no prior examples of same constraint text.
Principled signals: constraint text contains modal language (`must`, `never`, `always`, `inherently`) + PREMISE blocks present in episode + no correction trigger.
Inductive signals: constraint has `examples` array in ConstraintStore with 3+ entries from different sessions before this episode + constraint text describes pattern ("when X, always Y").

Default fallback: `principled` (safest assumption for policy).

**Open questions:**
- Should `epistemological_origin` be a hard enum or a probability distribution? Probability gives more information but complicates downstream use.
- Does the existing ConstraintExtractor need to be refactored, or can `epistemological_origin` be added as a post-processing step?

**Confidence:** ⚠️ Both providers agreed on pattern-based approach; specific threshold tuning needed.

---

### ⚠️ 6. GeneralizationRadius: Definition and Calculation

**What needs to be decided:**
DDF-04 requires a `GeneralizationRadius` metric for detecting floating abstractions (constraints that fire only on original hint patterns vs. novel contexts). The metric is named but not defined.

**Why it's ambiguous:**
Generalization radius could be:
- Embedding distance between original and applied contexts
- Count of distinct scopes where constraint has fired
- Ratio of novel-context firings to original-context firings
- LLM-scored 0-1 float

**Provider synthesis:**
- **Gemini:** LLM-derived float (0.0–1.0) "Concept-Instance Gap." OPE prompt asks: "Rate the gap between the concrete observation and the abstract label applied." Simple, no embedding dependency.
- **Perplexity:** Embedding-based semantic distance between problem-space of original constraint context and furthest applied context. Multiple domains = high radius. SQL aggregation over session constraint_eval records.

**Proposed implementation decision:**
Phase 15 implements `generalization_radius` as a **simple count-based proxy**: number of distinct `scope_paths` prefixes where the constraint has fired (from `session_constraint_eval` table, Phase 10). This is computable from existing DuckDB data without embeddings.

Formula: `generalization_radius = COUNT(DISTINCT scope_path_prefix) FROM session_constraint_eval WHERE constraint_id = X`

A radius of 1 = only ever fired in original scope (stagnant / potential floating abstraction). Radius ≥ 3 with varied prefixes = genuinely generalizing constraint.

Embedding-based radius is deferred to Phase 16 when sentence-transformers are more integrated.

**Open questions:**
- What threshold triggers a "stagnation" flag? (Proposed: radius = 1 after 10+ firings)
- Should the metric be stored in `constraints.json`, DuckDB `session_constraint_eval`, or a new `constraint_metrics` table?

**Confidence:** ⚠️ Gemini addressed directly; Perplexity gave detailed formula but embedding-dependent.

---

### ⚠️ 7. Causal Isolation Query Integration: Record or Trigger?

**What needs to be decided:**
DDF-08 (Causal Isolation Query) must detect Post Hoc Ergo Propter Hoc fallacy using foil instantiation (from Phase 14.1 FoilInstantiator). The architectural question: does DDF-08 *trigger* the FoilInstantiator or *record* that it was used?

**Why it's ambiguous:**
DDF-08 is called a "query" suggesting it is an action. But flame_events is a log. The FoilInstantiator already exists (Phase 14.1) and runs as part of the OPE pipeline. If DDF-08 re-triggers it, there's duplication. If DDF-08 only records, the detection is passive.

**Provider synthesis:**
- **Gemini:** DDF-08 is the *record*, not the *trigger*. FoilInstantiator acts; Phase 15 listens for its result and logs it as Level 3 (Causal Isolation) or Level 6 (Flood Confirmed if foil holds) flame event.
- **Perplexity:** Provided DuckDB query structure for detecting post-hoc claims against `foil_path_outcomes`. Framed as an active query component.

**Proposed implementation decision:**
DDF-08 is a **listener/recorder** (Gemini's approach). The FoilInstantiator already runs during episode population (Phase 14.1 integration). Phase 15 adds a post-hoc detection step in the OPE pipeline (Step ~15) that:
1. Reads completed FoilInstantiator results from `premise_registry.foil_path_outcomes`
2. Runs Perplexity's SQL to identify episodes with post-hoc claims (temporal sequence without foil validation)
3. Emits `ai_flame_events` records at `marker_level=3` when causal isolation was performed, or flags missing isolation as a negative marker

Separation of concerns: FoilInstantiator = actor; DDF-08 pipeline step = recorder + analyzer.

**Open questions:**
- Do we record *failed* foil attempts (where foil showed no difference)? (Proposed: yes, at marker_level=2 with `flood_confirmed=false`)
- Should DDF-08 trigger new FoilInstantiator queries for claims that weren't previously foil-checked? (Proposed: Phase 16 scope — adds active query capability)

**Confidence:** ⚠️ Gemini addressed directly; Perplexity provided query structure. Consensus: record first, active trigger later.

---

### ⚠️ 8. memory_candidates Schema: FK Lineage and Dedup Strategy

**What needs to be decided:**
When Level 6 fires multiple times for the same concept in one session (a Flood), should 5 `flame_events` → 5 `memory_candidates` entries, or 1 with an updated frequency counter? Also: should `memory_candidates` carry `source_flame_event_id` for lineage?

**Why it's ambiguous:**
Current `memory_candidates` schema (from Phase 13.3) has no FK back to detection events. The CCD format CHECK constraint (`ccd_axis`, `scope_rule`, `flood_example` must be non-empty) was designed for human-reviewed entries. Automated writes may collide on dedup.

**Provider synthesis:**
- **Gemini:** 1 candidate per concept (dedup), increment frequency counter. Mapping: `memory_candidates.source_event_id = flame_events.id`, `content = evidence_excerpt`, `ccd_axis = axis_identified`, `status = 'pending'`.
- **Perplexity:** Explicit deposit structure with `source_flame_event_id` FK + `fidelity` field. Level 6 flood → first deposit creates entry, subsequent instances update `flood_examples` list.

**Proposed implementation decision:**
Extend `memory_candidates` schema with:
- `source_flame_event_id VARCHAR` (FK to `flame_events.id`, nullable for human-written entries)
- `fidelity INTEGER DEFAULT 2` (2 = OPE-confirmed, 1 = reserved for future stub path)
- `detection_count INTEGER DEFAULT 1` (incremented on subsequent Level 6 firings for same concept)

Dedup logic: `UPSERT ON CONFLICT(ccd_axis, scope_rule) DO UPDATE SET detection_count = detection_count + 1, flood_example = [append new example if different]`. This prevents flooding `memory_candidates` with duplicate entries.

The `id` primary key (existing) remains UUID; the `(ccd_axis, scope_rule)` pair serves as the natural dedup key for automated deposits.

**Open questions:**
- Is `(ccd_axis, scope_rule)` sufficient for dedup, or can two distinct concepts share the same axis + scope rule text? (Likely yes — scope_rule text must be CCD-format unique)
- Should `detection_count` influence the review priority? (Higher count → higher priority for human review)

**Confidence:** ⚠️ Both providers touched this; Gemini was more explicit about the mapping.

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking — must decide before coding):**
- [ ] Write-on-detect fidelity: Tier 2 only (OPE pipeline writes to memory_candidates after session)
- [ ] DDF marker level heuristics: multi-signal scoring with Tier 1 stub (L0-1) and Tier 2 OPE LLM (L2-7)
- [ ] O_AXS algorithm: dual signal (token count drop + novel noun phrase), computable at Tier 1
- [ ] False Integration proxy: use PREMISE block scope divergence as proxy for DDF-07 (mark fidelity=1/heuristic)

**Tier 2 (Important — should decide before Wave 1 implementation):**
- [ ] Epistemological origin: weighted scoring classifier in ConstraintExtractor
- [ ] GeneralizationRadius: count-based proxy (distinct scope_path prefixes) for Phase 15
- [ ] Causal Isolation Query: DDF-08 = recorder only (FoilInstantiator is the actor)
- [ ] memory_candidates schema extension: source_flame_event_id FK + detection_count + fidelity column

---

## Implementation Order (from Perplexity synthesis)

**Wave 1 (Foundations — unblocks all others):**
- `flame_events` and `ai_flame_events` DuckDB table schema
- Tier 1 stub heuristics for L0-1 (regex patterns in hooks)
- O_AXS tagger extension (dual-signal: token count + noun phrase)
- write-on-detect deposit to `memory_candidates` in Tier 2 OPE pipeline

**Wave 2 (Depends on Wave 1):**
- Tier 2 OPE FlameEventExtractor (L2-7 LLM scoring)
- Causal Isolation Query recorder (DDF-08 pipeline step)
- False Integration heuristic proxy (PREMISE scope divergence)

**Wave 3 (Depends on Wave 2):**
- Epistemological origin classifier in ConstraintExtractor
- GeneralizationRadius computation (count-based)
- IntelligenceProfile DuckDB aggregation

**Wave 4 (Integration + CLI):**
- `intelligence profile` CLI command
- Pipeline integration (new steps after existing Step 14)
- Tests + validation against real sessions

---

*Multi-provider synthesis by: Gemini Pro (high thinking), Perplexity Sonar Deep Research*
*Generated: 2026-02-24*
*YOLO mode: Auto-answers generated*
