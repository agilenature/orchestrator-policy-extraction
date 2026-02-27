# CLARIFICATIONS-NEEDED.md

## Phase 17: Candidate Assessment System — Stakeholder Decisions Required

**Generated:** 2026-02-24
**Mode:** Multi-provider synthesis (OpenAI gpt-5.2, Gemini Pro, Perplexity Sonar Deep Research)

---

## Decision Summary

**Total questions:** 7
**Tier 1 (Blocking):** 4 questions — Must answer before planning
**Tier 2 (Important):** 2 questions — Impact scoring quality
**Tier 3 (Polish):** 1 question — Can decide during implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: Scenario Materialization Format

**Question:** What does a "pile problem" scenario consist of concretely — full repository, text-only description, or minimal broken artifact?

**Why it matters:** The scenario generator can't be built without knowing what it produces. Full repos are expensive/fragile to generate from wisdom entries. Text-only is too abstract. The answer determines the schema of the scenarios table, the generator algorithm, and the assessment session setup procedure.

**Options:**

**A. Seed-Based Synthesis (Recommended — Gemini + OPE-aligned)**
- Produce two files: `scenario_context.md` (problem briefing, no solution hints) + a minimal broken implementation file that demonstrates the failure symptom but hides the root cause behind an abstraction layer
- For L5-L7: actor's CLAUDE.md pre-seeded with a plausible-but-wrong framing the candidate must reject
- _(Proposed by: Gemini, confirmed as OPE-appropriate by synthesis)_

**B. Text-Only Problem Description**
- Scenario is a pure text prompt; candidate interacts with the AI to explore it
- No code file; the pile problem is entirely conceptual
- _(Faster to generate; loses the realistic coding session dynamic)_

**C. Full Mock Repository**
- Scenario generator creates a full repository with multiple files reproducing the failure
- Maximum realism; extremely expensive and fragile to generate automatically
- _(Proposed by: Perplexity L5-L7; likely too complex for MVP)_

**Synthesis recommendation:** ✅ **Option A — Seed-Based Synthesis**
- Aligns with existing project_wisdom structure (wisdom entries describe specific failure modes that translate naturally to broken-snippet seeds)
- Deposit-not-detect: the generator is scaffolding; the candidate's flame_events from working with a real artifact are the deposit

**Sub-questions:**
- Should generated files be validated (run + confirm failure) before deployment?
- Which wisdom entity types (dead_end, breakthrough, scope_decision) seed which DDF levels?

---

### Q2: Actor-Observer Process Separation

**Question:** How is the AI's dual role (calibrated collaborator + assessed-by-OPE-pipeline) implemented without contaminating either role?

**Why it matters:** If the Actor AI both participates in the session AND generates ai_flame_events from its own live state, assessment sessions will contain deliberately-degraded AI reasoning (per handicap) polluting the main IntelligenceProfile. If the Observer runs in-process with the Actor, it can break the Actor's calibrated persona.

**Options:**

**A. Strict Process Isolation (Recommended — Gemini)**
- Actor: Claude Code instance with custom assessment CLAUDE.md (sets persona/handicap level)
- Observer: OPE extract pipeline running post-session (or tail mode) against the Actor's JSONL transcript
- ai_flame_events generated from transcript analysis by Observer, NOT from Actor's live internal state
- Actor does not know it is scoring the candidate; no self-monitoring code in Actor context
- _(Proposed by: Gemini)_

**B. Shared-Process with Event Segregation**
- Single Claude Code process; assessment events tagged with `assessment=True` flag
- OPE pipeline filters on the flag; production IntelligenceProfile excludes `assessment=True` events
- Simpler infrastructure; higher risk of persona contamination

**Synthesis recommendation:** ✅ **Option A — Strict Process Isolation**
- Deposit-not-detect: Observer is the deposit mechanism; Actor's transcript is its input. Clean separation.
- Actor's genuine reasoning (even when handicapped) produces genuine ai_flame_events at the target level

**Sub-questions:**
- How is the Actor's handicap encoded? Custom CLAUDE.md per scenario? Or SessionStart hook injection?
- Should the Actor know it's in an assessment scenario, or should that context be invisible to it?
- How do we prevent a L5-L7 Actor (holding a wrong framing) from self-correcting before the candidate reaches the contradiction?

---

### Q3: Session Isolation Level

**Question:** How isolated must candidate assessment environments be — Docker/Firecracker containers, or filesystem-level isolation only?

**Why it matters:** Docker adds provisioning latency and operational complexity. Filesystem isolation is simpler but shares OS resources. The answer affects provisioning time, infrastructure requirements, and how the CLI is built.

**Options:**

**A. Filesystem-Level Isolation (Recommended — Gemini, OPE-appropriate)**
- Create `/tmp/ope_assess_{session_id}/` as isolated working directory
- Launch Claude Code with project dir override to this path
- PAG hook (Phase 14, already built) blocks dangerous mutating commands outside assessment dir
- Zip final state → store in transport_efficiency_sessions before cleanup
- _(Proposed by: Gemini; deposit-aligned: final artifact zipped and stored)_

**B. Docker Container Isolation**
- Each assessment session runs in a Docker container with 4GB RAM, 2 CPU, 50GB disk quotas
- True OS-level isolation; prevents disk-fill and process-escape scenarios
- Provisioning latency: 10-30 seconds per session
- _(Proposed by: Perplexity; appropriate for production deployment)_

**Synthesis recommendation:** ✅ **Option A for MVP, upgrade path to B**
- Simpler infrastructure matches current OPE single-machine architecture
- Docker is the upgrade path for when multiple concurrent assessments are needed

**Sub-questions:**
- Does Claude Code support a `--project-dir` or equivalent CLI argument to override working directory?
- Should the assessment session's `.claude/MEMORY.md` be blank (fresh start) or pre-seeded with the AI's current IntelligenceProfile?

---

### Q4: Memory Deposit Contamination Control

**Question:** How do we prevent deliberately-degraded AI reasoning (from handicapped Actor sessions) from polluting the production `memory_candidates` and `IntelligenceProfile`?

**Why it matters:** Phase 17's secondary goal is depositing the richest ai_flame_events ever generated. But the Actor is intentionally reasoning at sub-optimal levels. If assessment flame_events feed the same IntelligenceProfile as production work, the AI appears to be getting worse, not better.

**Options:**

**A. source_type Column + Exclusion by Default (Recommended — Gemini + Perplexity)**
- Add `source_type VARCHAR CHECK IN ('production', 'assessment', 'simulation_review')` to `memory_candidates` and `ai_flame_events` (tagged at write time)
- `IntelligenceProfile` CLI excludes `assessment` source_type by default; `--include-assessments` flag for research
- **The Assessment Report** (not the raw transcript) is the terminal deposit to `memory_candidates` with `source_type='simulation_review'` and `fidelity=3`
- `simulation_review` entries capture the *dynamics* (what framing did AI hold? at what level did candidate operate? TE delta?) — not the specific tokens of handicapped reasoning
- _(Proposed by: Gemini + Perplexity synthesis)_

**B. Separate Assessment DuckDB Database**
- All assessment flame_events written to a separate `assessment.db`; never merged with `ope.db`
- Assessment Report manually exported to `memory_candidates` in `ope.db` by human reviewer
- Maximum separation; manual friction on every deposit

**Synthesis recommendation:** ✅ **Option A — source_type column + exclusion by default**
- Deposit-not-detect: the Report is the deposit; the transcript analysis is the detection
- Simpler than separate DB; aligns with existing memory_candidates schema extensions (Plans 15-16 already added columns)

**Sub-questions:**
- Should `simulation_review` deposits bypass the MEMORY.md review CLI (Phase 16) or go through it?
- At what initial trust level / confidence do `simulation_review` entries start?

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q5: Level 5-7 Rejection Detection Mechanism

**Question:** How do we detect a meaningful semantic rejection (Level 5: candidate rejects AI's causal model and proposes a better alternative) vs. a stylistic preference rejection (candidate says "I prefer X style" — not epistemologically significant)?

**Why it matters:** ASSESS-03 requires a DDF level distribution including L5-L7 events. If rejection detection fires on false positives (style disagreements, typo corrections), the Assessment Report overstates candidate epistemological quality. If it misses true semantic rejections, it understates it.

**Options:**

**A. Outcome-Gated Epistemology (Recommended — Gemini)**
- Rejection counts as Level 5 ONLY IF `candidate_te > baseline_te × 0.9` (candidate's solution outperforms AI's proposed path)
- If Rejection AND candidate_te < threshold → `stubbornness_indicator=True` (not a Level 5)
- Requires pre-computed `baseline_te` (AI clean-run TE for each scenario)
- _(Proposed by: Gemini)_

**B. Linguistic Marker Detection**
- Detect semantic rejection via NLP: candidate output contains "actually, the root issue is...", "the AI's framing assumes X but...", axis-identification language
- No outcome gate; fires on explicit language patterns
- High recall, medium precision; risk of false positives on candidates who verbalize without insight

**Synthesis recommendation:** ⚠️ **Option A — Outcome-Gated**
- Most robust to gaming; grounds epistemological claims in observable outcomes
- Requires pre-computation of baseline_te per scenario (one-time calibration run)

**Sub-questions:**
- What threshold ratio is appropriate? (0.9 = candidate must reach 90% of AI's clean-run TE?)
- Should Fringe-signal rejections ("something feels off") bypass the outcome gate and count as L5-pre-naming?

---

### Q6: TE Score Normalization for Assessment Context

**Question:** How are assessment TE scores made comparable across: (a) different scenarios of different difficulty, and (b) the existing production TE population baseline from Phase 16?

**Why it matters:** Assessment TE and production TE are not dimensionally compatible (different time scales, problem sizes, event counts). ASSESS-03 requires population baseline comparison — but comparing raw assessment TE to raw production TE is meaningless.

**Options:**

**A. Within-Scenario Ratio Normalization (Recommended — Gemini + synthesis)**
- `candidate_ratio = candidate_te / scenario_baseline_te` (AI clean-run)
- Candidate ratio > 1.0: outperformed AI baseline; < 1.0: underperformed
- Cross-scenario population: maintain `assessment_baselines` table; after N>=10 assessments per scenario, compute mean/stddev of ratio → percentile rank
- Write to `assessment_te_sessions` table (NOT `transport_efficiency_sessions`) to keep production baseline clean
- _(Proposed by: Gemini + Perplexity synthesis)_

**B. Z-Score Normalization Against Assessment Population**
- `TE_normalized = (score - mean_assessment_historical) / stddev_assessment_historical`
- Requires building up assessment history before normalization is meaningful
- Population is assessment-only (not production-contaminated)
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ⚠️ **Option A — Within-Scenario Ratio**
- Immediately actionable even for first assessment (ratio against AI baseline is always available)
- Deposit-not-detect: `assessment_te_sessions` is scaffolding (measurement); the Assessment Report deposit is terminal

**Sub-questions:**
- Should `transport_speed` sub-metric be excluded from assessment TE? (Assessment problem contexts too small for meaningful speed measurement)
- What if the scenario has never been run (no baseline_te)? Flag as `baseline_pending` and skip normalization?

---

## Tier 3: Polish Decisions (🔍 Can Decide During Implementation)

### Q7: Scenario DDF-Level Annotation Mechanism

**Question:** How are `project_wisdom` entries annotated with their target DDF level before the first assessment, given that entries currently have no DDF-level metadata?

**Why it matters:** The scenario generator needs `ddf_target_level` to calibrate pile problems. Without it, all scenarios are treated as equally calibrated (they're not). This is a data quality issue, not an architecture issue.

**Options:**

**A. CLI Annotation Tool + Auto-Calibration (Recommended)**
- Add `scenario_seed TEXT` and `ddf_target_level INTEGER` columns to `project_wisdom`
- CLI command: `python -m src.pipeline.cli intelligence assess annotate-scenarios` — presents each wisdom entry interactively, prompts for level + optional seed
- Auto-calibration: after 10 assessments per scenario, adjust `ddf_target_level` if median candidate performance consistently hits the target (too easy → lower) or misses it (too hard → raise)
- _(Proposed by: synthesis)_

**B. Manual JSON Configuration**
- Maintain a separate `data/assessment_scenarios.json` with scenario definitions and DDF levels
- No DB schema changes; scenarios are a configuration artifact, not derived from wisdom table
- Simpler but decoupled from wisdom table updates

**Synthesis recommendation:** 🔍 **Option A — CLI Annotation**
- Keeps scenario metadata co-located with wisdom entries
- Auto-calibration closes the loop from assessment outcomes back to scenario difficulty spec (closed-loop-to-specification CCD axis)

**Sub-questions:**
- Should `ddf_target_level` be an integer (single level) or a range `[min_level, max_level]`?

---

## Next Steps (YOLO Mode)

**This file was generated in YOLO mode.**

CLARIFICATIONS-ANSWERED.md has been auto-generated with recommended answers.
Proceed to `/gsd:plan-phase 17` to create the execution plan.

---

*Multi-provider synthesis: OpenAI gpt-5.2 + Gemini Pro + Perplexity Sonar Deep Research*
*Generated: 2026-02-24 | YOLO mode*
