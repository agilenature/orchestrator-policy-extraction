# Future Work and Potentialities
## DDF-Enabled Innovations: A Living Research Roadmap

*Started: 2026-02-21*
*Status: Living document — updated as discoveries are made and capabilities built*
*Companion to: DISCOVERY_DETECTION_FRAMEWORK.md*

---

## Design Principle: The AI Is a Subject, Not Only an Observer

*Stated explicitly: 2026-02-21*

**The ultimate goal of this system is not analysis — it is capability transfer.**

The human wants the AI to replace them as orchestrator of coding agents. Everything built in Phases 14-18 serves two purposes simultaneously:
1. **Observer mode** — analyze human (and third-party) cognition using DDF, TransportEfficiency, and structural integrity detection
2. **Self-improvement mode** — use the same framework to improve the AI's own epistemological capacity across sessions

The AI is a first-class subject of the system, not a tool of it. The `ai_flame_events` table, the AI's own TransportEfficiency score, the MEMORY.md auto-generation pipeline, and Bridge-Warden applied to AI-generated principles — all of these directly expand the AI's capacity to orchestrate without human intervention.

**The replacement arc:** As the AI's CCD store grows through the MEMORY.md pipeline, the human's role shifts:
- **Stage 1** (current): Human orchestrates; OPE records and analyzes
- **Stage 2** (Phase 15-16): AI co-orchestrates; human reviews FlameEvents and curates MEMORY.md candidates
- **Stage 3** (Phase 17-18): AI orchestrates; human reviews and approves AI decisions
- **Stage 4** (post-18): Human audits; AI orchestrates autonomously with high TransportEfficiency and structural integrity

The measurable condition for each stage transition: the AI's TransportEfficiency and StructuralIntegrityScore stabilize above thresholds that match the human's own IntelligenceProfile. Not vague "AGI" — a specific, project-scoped, measurable capability transfer.

**The MEMORY.md is the mechanism.** Each CCD-quality entry is one transferred epistemological capacity. The pipeline makes this transfer systematic, validated (flood test), and cumulative.

---

## How to Use This Document

This document tracks the frontier of what the DDF framework enables — organized by horizon. Each item has a status that evolves as work progresses. Add new items as discoveries occur. Promote items from one horizon to the next as prerequisites are built.

**Status vocabulary:**
- `IDEA` — identified, not yet researched
- `RESEARCHED` — theoretical foundation established
- `PLANNED` — in roadmap with phase assignment
- `SPIKE` — being validated experimentally
- `BUILDING` — active implementation
- `COMPLETE` — delivered and verified
- `OPEN` — active research question without clear answer yet

---

## Horizon 1: Immediate (Phase 14)

### H1-01 — O_AXS Episode Mode
*Status: PLANNED (Phase 14-01/02)*
Add `O_AXS` as a first-class episode mode in the tagger. Axis Shift episodes are the highest-value training data in the entire dataset — they capture the moment the human restructures the conceptual framework, not just directs the agent.

**What it enables:** All subsequent DDF capabilities depend on this. It's the detection substrate.

**Next action:** Include in Phase 14-01 hook contracts research — O_AXS as the trigger event for live DDF co-pilot interventions.

---

### H1-02 — Real-Time DDF Co-Pilot (Executive Spike)
*Status: SPIKE (Phase 14-03)*
When O_AXS fires in a live session, the system prompts the human to name the new axis, requests a Concretization Flood, and drafts a candidate wisdom entity for immediate save. Combats Prose Principle Lag before insights drift back into implicit knowledge.

**What it enables:** Insight capture at the moment of formation — before the spiral loop closes without recording the CCD.

**Open question:** What is the acceptable latency between UserPromptSubmit and intervention? If too slow, the human has already moved on. Target: < 3 seconds.

---

### H1-03 — Session File Architecture Understanding
*Status: COMPLETE (documented 2026-02-21)*
Claude Code writes full session transcripts to `~/.claude/projects/<encoded-path>/<session-id>.jsonl` in real time. Sub-agent transcripts at `agent-<agentId>.jsonl`. No special capture mechanism required — the OPE pipeline already consumes these files.

**What it enables:** The OpenClaw spike (H1-04) requires no new infrastructure for session capture.

---

### H1-04 — OpenClaw Bus Spike (Batch DDF + Local Bus)
*Status: SPIKE (Phase 14-04)*
Governing orchestrator assigns tasks via a lightweight local HTTP bus. Worker sessions complete and exit. Orchestrator reads the JSONL from the known path, runs `python -m src.pipeline.cli extract`, extracts FlameEvents from the full session context. Tests whether full-session batch detection produces richer DDF signal than per-prompt real-time detection.

**Bus candidates evaluated in spike:**
- A) Chat-with-API: Mattermost/Rocket.Chat — human-readable, REST API, good for monitoring
- B) Message broker: NATS or Redis Streams — pure machine-to-machine, `openclaw.tasks` / `openclaw.results`
- C) Tiny local HTTP bus: FastAPI + SQLite — zero new dependencies, full schema control, swappable internals

**Recommendation:** Start with C for zero-dependency validation. Abstract the bus interface so A or B can be swapped without changing Claude Code session scripts.

**Open question:** Real-time (H1-02) vs. batch (H1-04) — which produces higher quality DDF detections? Real-time has lower latency for intervention. Batch has full session context for richer analysis. May need both: real-time for co-pilot intervention, batch for IntelligenceProfile scoring.

---

### H1-05 — Logical Integrity Gate (Fallacy Detection System)
*Status: PLANNED (Phase 14.1 + Phase 15)*

The Premise Registry and PAG together implement a **Fallacy Checker** — not just a memory aid. Each major fallacy category has a structural signature detectable without AI session state:

| Fallacy | Structural Signature | Detection Mechanism | Phase |
|---|---|---|---|
| **Equivocation** | Same term, different CCD axes across two PREMISE blocks | FOIL field: semantic drift without re-definition | 14.1 |
| **Context Dropping** | Active constraint absent from PREMISE declaration | Amnesia (Phase 10) + PAG write-boundary gap | 14.1 |
| **Stolen Concept** | Child node active, parent node stained/invalid | Staining pipeline + `parent_episode_id` causal chain | 14.1 |
| **Self-Exclusion** | SCOPE contradicts write-class action issued | CLAUDE.md SCOPE field vs. mutation type mismatch | 14.1 (CLAUDE.md live) |
| **Begging the Question** | `derivation_depth=0` — no upward movement | Premise ID reappears in derivation_chain (loop) | 14.1 |
| **Ad Ignorantiam** | `validation_calls_before_claim=0` | RQR=0 on positive factual PREMISE | 14.1 |
| **Package Deal** | One PREMISE SCOPE covers two non-overlapping CCD axes | False Integration marker in `ai_flame_events` | 15 |
| **Post Hoc** | Causal claim from temporal sequence alone | Causal Isolation Query (Method of Difference) | 15 |

**The core insight:** Hallucinations are a subset of fallacies.
- Confident wrong assertion = Equivocation (semantic drift without re-definition)
- Missing constraint = Context Dropping (High-Activation Node not on Desktop)
- Uses deleted dependency = Stolen Concept (parent stained, child active)
- "No errors seen → code correct" = Ad Ignorantiam (RQR=0)

**Architectural implication:** Token probability is what the model maximizes; logical process integrity is what OPE enforces. These are orthogonal dimensions. A high-probability output can be a fallacy; a low-probability output can be valid. The PAG is not a memory aid — it is a **logical integrity gate**. Training data addresses the probability of fallacies; logical process enforcement addresses the structural conditions that make them possible.

**Classification into two categories:**
- **In-derivation fallacies** (Equivocation, Context Dropping, Stolen Concept, Self-Exclusion, Begging the Question, Ad Ignorantiam): caught at the write boundary by structural observation of the current derivation chain.
- **Process fallacies** (Package Deal, Post Hoc): require observing the derivation process across entities (Package Deal) or across historical episodes (Post Hoc). Phase 15 territory.

**Reference:** Binswanger, *How We Know*, Chapter 7 (fallacies as illogical processing). The Suspension Bridge analogy (Chapter 6) grounds Phase 18's structural integrity detection. The Fallacy Checker closes the loop at Phase 14.1: it is the Layer 4 (Control) complement to Phase 18's Layer 5 (Verification) structural integrity signals.

**What it enables:** The first system that recognizes Logical Integrity as more important than Token Probability. Detection of cognitive dead-ends before the AI drives into them.

---

## Horizon 2: Near-Term (Phase 15-16)

### H2-01 — FlameEvent Store (Core DDF Infrastructure)
*Status: PLANNED (Phase 15)*
`flame_events` DuckDB table: session_id, human_id, prompt_number, marker_level (1-7), marker_type, evidence excerpt, quality_score, axis_identified, flood_confirmed (bool), ccd_scope.

**What it enables:** Everything in Horizon 2 and beyond. This is the concept store that replaces magnitude-level session memory.

**Design principle:** The FlameEvent store is not a memory bank — it is a concept store. It stores CCDs with scope rules and validation evidence, not operational details. This is the agent implementation of Rand's measurement omission.

---

### H2-02 — IntelligenceProfile per Human
*Status: PLANNED (Phase 15) — updated 2026-02-21 with three-tier architecture metrics*
Per-human aggregate computed from FlameEvents over time:
- `flame_frequency` — FlameEvents per hour of session
- `avg_marker_level` — weighted average of marker levels (frequency × level)
- `spiral_depth` — concept scope expansion across sessions (Generalization Radius)
- `flood_rate` — proportion of abstractions that generate confirmed floods
- `ccd_domains` — map of domains where CCD-level depth is held vs. magnitude-level

**New metrics (from Crow/Raven architecture discovery, 2026-02-21):**
- `raven_depth` — average conceptual distance of Basement retrievals: how far does this human reach when pulling fundamentals? Distinguishes deep retrievers (cross-domain fundamentals applied to local problems) from local retrievers (previous-project patterns repeated)
- `crow_efficiency` — average unit reduction ratio per session: how many magnitudes compressed into each CCD? High efficiency = broad CCDs. Low efficiency = many narrow rules. Measures compressive power of concept formation.
- `transport_speed` — Fringe→Focus transition time in prompts: how quickly does "something feels off" become a named concept? Faster transport = responsive conceptual metabolism. Long lags = ideas drifting back to Basement without capture (Drift risk)
- `trunk_quality` — proportion of Level 0 Trunk Identifications that survive downstream validation: the fundamental named actually explains the most derivative facts. High quality = genuine insight. Low = premature generalization (galaxy-brain risk at Level 0)

**Composite metric — `TransportEfficiency` (the Sacred Fire Index):**
A single-number summary of how well the human navigates the Crow/Raven constraints when collaborating with AI:

> TransportEfficiency = raven_depth × crow_efficiency × (1/transport_speed) × trunk_quality

- High score: deep Basement retrieval, high compression, fast Fringe→Focus, genuine fundamentals
- Low score: local retrieval only, narrow rules, slow or frequent Drift, premature generalizations

This is the metric Binswanger names when he defines the "Sacred Fire" — the efficiency and precision of the transport system. Prior to DDF, this was observable only subjectively ("that was a productive session"). TransportEfficiency makes it measurable, comparable across sessions and humans, and trackable over time as deliberate cognitive practice.

**What it enables:** The conceptual topology map of a specific mind. Hiring signal (Phase 16). Calibration of AI operating mode to match human's habitual level. Team assembly by topological coverage. TransportEfficiency as a trainable metric — coaching for specific weak sub-scores.

**Update cadence:** Recomputed after each session. Historical trend available for growth tracking.

---

### H2-03 — Constraint Epistemological Origin
*Status: PLANNED (Phase 15)*
Add `epistemological_origin` field to every constraint: `reactive` | `principled` | `inductive`.

- `reactive`: generated from post-hoc correction (magnitude stored)
- `principled`: generated from O_AXS event with named CCD (concept stored)
- `inductive`: generated from Concretization Flood pattern across multiple sessions (concept validated)

**What it enables:** Amnesia detection at the right level. A `principled` constraint should be checked for CCD-level honoring (does the principle apply to this new situation?), not just text-match honoring. A `reactive` constraint is checked at magnitude level until enough instances promote it.

**Connection to Phase 10:** This is the formal solution to "constraint honored in text but violated in principle" — the category of amnesia that Phase 10 can detect the outcome of but not the cause.

---

### H2-04 — Generalization Radius Metric
*Status: PLANNED (Phase 15)*
Track whether each constraint fires on an expanding set of contexts (genuine CCD-level understanding) or a fixed set (magnitude-level rule memorization). Stagnation after sufficient sessions = floating abstraction risk flag.

**Formula:** scope_paths set at session N vs. session N+10. Growing set = ascending spiral. Fixed set = plateau warning.

**What it enables:** Leading indicator for future amnesia. A constraint with stagnating Generalization Radius will fail in novel contexts before it actually does.

---

### H2-05 — Spiral Tracking (Auto-Seeding Wisdom)
*Status: PLANNED (Phase 15)*
Constraints with ascending scope_paths across sessions are automatically identified as high-value wisdom seed candidates and promoted to `project_wisdom` for review. Replaces manual curation of `seed_wisdom.json` with evidence-based auto-promotion.

**Ascending spiral signature:** scope_paths grows across sessions AND the constraint continues to be honored in the expanded scope (not just applied and then violated).

---

### H2-06 — Candidate Assessment System
*Status: PLANNED (Phase 16)*
Scenario generator pulls from the OPE project's own historical dead ends and breakthroughs (41 plans, 13 phases) to produce calibrated pile problems:
- Level 1-2 scenarios: one abstraction unlocks the solution
- Level 3-4 scenarios: fundamental identification required across 5+ symptoms
- Level 5-7 scenarios: AI's framing must be rejected and reoriented from a contradiction the candidate must notice themselves

Live DDF detection during candidate session. Assessment Report at end: FlameEvent timeline, level distribution, axis quality scores, flood rate, spiral evidence within session, comparison to population baseline.

**Critical design constraint:** Candidate knows they are being assessed for epistemological quality — how they think with AI, not just what they produce. The assessment rewards intellectual independence from AI suggestions (Level 5 Premise Check requires rejecting the AI's framing). Candidates who simply adopt AI vocabulary will score at Level 1-2 regardless of output quality.

---

### H2-08 — Fringe Intervention (Real-Time Pre-Level-4 Co-Pilot)
*Status: PLANNED (Phase 14/15)*
A new real-time intervention type distinct from the O_AXS intervention. The Fringe Intervention fires *before* naming occurs — when the system detects hedged, phenomenological language indicating the human has a Fringe awareness that has not yet ascended to the Desktop.

**Signal patterns:**
- "Something feels off about..."
- "This doesn't sit right..."
- "There's something here I haven't named yet..."
- "I don't know why but I keep coming back to..."
- Vague quality-of-code language (texture complaints, not specific errors)

**Intervention:** Immediately prompt naming — "What specifically feels wrong? Try to name the axis." This converts Fringe awareness into Level 4 articulation before the awareness drifts back to the Basement (Drift = insight loss in real time).

**Why this matters:** Current Phase 14 co-pilot design detects O_AXS *after* the axis is named (Level 4 completion). Fringe Intervention adds a new trigger: detecting the *onset* of Level 4 and accelerating the Fringe→Focus transition. This recovers insights that would otherwise be lost between sessions.

**New concept: Fringe Drift** — the failure mode where the human's Fringe awareness fades back to Basement before it can be named. Drift leaves no JSONL trace (there was nothing explicit to record). It is invisible to post-hoc analysis. Only real-time detection can catch it.

**What it enables:** Recovery of insights at the moment of formation, before Drift. Estimated yield: significant — Fringe Drift is common in long sessions where cognitive load accumulates and the human's "this bugs me" awarenesses are overwritten by new tool call output.

**Open question:** How to distinguish genuine Fringe awareness from conversational hedging or politeness? Requires further calibration of signal patterns against session data.

---

### H2-09 — CCD-Quality MEMORY.md Auto-Generation Pipeline
*Status: PLANNED (Phase 15)*

The discovery that CCD-level MEMORY.md entries function as a **substitute Raven cost function** for the AI creates a concrete engineering requirement: automate the generation of CCD-quality entries from validated FlameEvents.

**The mechanism:**
When a Level 6 Concretization Flood is confirmed (3+ spontaneous instances in novel domains), the pipeline has the full CCD structure in hand:
- The axis (from `axis_identified` in the FlameEvent)
- The scope rule (inferred from the domains the flood covered)
- A validated flood example (the first spontaneous instance cited)

These three elements are exactly what a CCD-quality MEMORY.md entry requires. The pipeline auto-drafts the entry in structured format:

```
## [axis_name]
**CCD axis:** [what all instances share]
**Scope rule:** [what counts as an instance; what does not]
**Flood example:** [one validated novel instance from the Concretization Flood]
**Origin:** FlameEvent [session_id], Level 6, confirmed [flood_confirmed date]
```

**`memory_candidates` DuckDB table:** Stores auto-drafted entries awaiting human review. Human reviews and accepts/rejects/edits each candidate. Accepted entries are output to MEMORY.md in the structured format. Rejected entries are logged with rejection reason for model improvement.

**The quality gate:** Only entries with marker_level >= 6 AND flood_confirmed = true are drafted. Entries from reactive corrections (epistemological_origin = 'reactive') are never drafted regardless of level — they are magnitude storage masquerading as concept storage. Only `principled` and `inductive` origin entries qualify.

**What it enables:** The closed loop between the DDF (detecting CCD formation) and the AI's operating intelligence (CCD-guided retrieval). The human no longer needs to manually curate MEMORY.md to maintain the AI's intelligence across sessions. The DDF does it automatically, with human review as the final gate.

**The key insight it implements:** CCD-level MEMORY.md entries are the external Raven cost function the AI lacks internally. By automating their generation from validated FlameEvents, the pipeline makes the AI's intelligence self-sustaining: each session that produces genuine CCD insights automatically upgrades the AI's retrieval system for the next session.

**Prerequisites:** H2-01 (FlameEvent store), H2-03 (epistemological origin), Level 6 detection active

---

### H2-07 — Bridge-Warden Structural Integrity Detection
*Status: PLANNED (Phase 17)*
Four new detection signals derived from Binswanger's Suspension Bridge analogy (Chapter 6) — the downward path and structural integrity dimension that completes the DDF:

- **Signal A: Gravity Check (Reduction)** — human traces a high-level abstraction back to perceptual ground; anchors AI hallucinations to observable facts
- **Signal B: Main Cable (Top-Down Integration)** — human strings a load-bearing principle that stabilizes many existing concretes simultaneously; triggers CTT Op-8 validation
- **Signal C: Dependency Sequencing** — human refuses to build higher levels before lower levels are logically grounded; enforces epistemological hierarchy in real time
- **Signal D: Spiral Reinforcement** — human uses higher-level understanding to simplify and strengthen earlier code; the roof strengthening the walls

**`StructuralEvent` table:** Records all four signals per session with evidence and structural_role.
**`StructuralIntegrityScore`:** Health metric for the knowledge structure built in a session.
**CTT Op-8 (Top-Down Tension):** Validates principles are load-bearing — eliminates instances, integrates elements, independently detectable. Floating cables (principles that fail Op-8) flagged as amnesia precursors.
**Two-dimensional profile:** Ignition axis (Phase 15 FlameEvents) × Integrity axis (Phase 17 StructuralEvents) = complete characterization of how a human thinks with AI.

**What it enables:** Detecting not just whether the human is generating insights but whether those insights are integrating into a structurally sound edifice. A session with high Ignition and poor Integrity produces brilliant ideas that float and collapse.

---

## Horizon 3: Medium-Term Innovations

### H3-01 — CCD-Level RAG Retrieval
*Status: RESEARCHED*
Current RAG retrieval matches surface similarity — magnitude against magnitude. It finds episodes where the same words appeared. What it should find is episodes where the same *axis* was at play.

**The innovation:** Retrieve by CCD identity, not surface proximity. Two episodes can be surface-dissimilar (different domain, different technology, different error) while sharing the same axis (e.g., "irreversible actions require human confirmation"). Semantic embedding helps but doesn't fully solve this — embeddings are still magnitude-proximity.

**Approach:** Index episodes by their FlameEvent CCDs. When a new situation arrives, extract the candidate CCD from the current context, then retrieve by CCD-match rather than text-similarity. Fall back to embedding similarity only when no CCD match exists.

**Prerequisites:** H2-01 (FlameEvent store), H2-03 (epistemological origin on constraints)

---

### H3-02 — Organizational Dysfunction Diagnostics
*Status: RESEARCHED*
Apply DDF across an entire team's sessions to detect structural conceptual pathologies:

**Level 1 lock-in:** No sessions produce FlameEvents above Level 2. The organization is accumulating operational experience without conceptual advance. Will repeat the same classes of mistakes indefinitely because it never identified the CCDs.

**Single-CCD-holder bottleneck:** One person (usually founder/lead) produces 90% of Level 5+ FlameEvents. Everyone else operates at Level 1-2. This is a conceptual dependency, not a skill dependency. When that person leaves, the organization loses its concept store — this is what actually happens when a company "loses its soul."

**Floating abstraction inflation:** High Level 2 vocabulary (everyone uses "scalability," "technical debt," "data-driven") but zero Level 6 Floods on those terms. The words circulate; the concepts are absent. This organization makes systematically wrong decisions that feel principled.

**Prerequisites:** H2-01 (FlameEvent store), H2-02 (IntelligenceProfile), multi-user deployment

---

### H3-03 — Team Assembly by Topological Coverage
*Status: IDEA*
Given a project's CCD landscape (which axes are critical), and a pool of candidates with mapped conceptual topologies (IntelligenceProfiles), compute the optimal team as the minimal set whose topologies cover the project's CCD landscape — each critical axis having at least one Level 5+ CCD-holder.

This is fundamentally different from skill-matrix team assembly. It predicts which combinations will produce genuine innovation (complementary topologies) vs. competent execution (similar topologies reinforcing each other at the magnitude level).

**Prerequisites:** H2-02 (IntelligenceProfile), H2-06 (Candidate Assessment), multi-project CCD dataset

---

### H3-04 — CCD-Level Alignment (The DDF Answer to RLHF)
*Status: RESEARCHED*
Current RLHF: trains on human preference judgments (magnitudes). Generalizes poorly to novel situations with different surface features but the same underlying axis.

DDF alignment: extract the CCD that generated the preference, not the preference itself. When a human blocks an AI action, capture not just "they blocked this" but "the axis this violated was: [CCD]." The constraint now generalizes to any instance of the axis regardless of surface form.

**What this means:** An AI trained on CCD-level constraints would correctly block genuinely novel situations that share the axis with a training constraint — even if the surface features have never appeared in training. This is the difference between alignment that interpolates and alignment that generalizes.

**Prerequisites:** H2-01 (FlameEvent store), H2-03 (epistemological origin), large-scale CCD dataset

---

### H3-05 — The Expertise Reclassification
*Status: RESEARCHED*
Current expertise model: years of experience + depth of specialization.
DDF expertise model: CCD depth in the relevant domain, validated by Flood.

A practitioner is expert in a domain if and only if they can:
1. Name the CCDs of the domain (not just the terminology)
2. Generate Concretization Floods on demand for those CCDs
3. Perform valid Contextual Transfusions from the domain to novel situations

This makes expertise falsifiable. You cannot fake a Flood. The DDF makes the distinction between CCD-holders and magnitude-possessors measurable — regardless of years of experience, credentials, or title.

**Application:** Performance reviews, promotion decisions, hiring signals — all transformed by having a direct measure of conceptual depth rather than proxies.

---

## Horizon 4: Long-Term Potentialities

### H4-01 — The Joule for Intellectual Progress
*Status: RESEARCHED*
The FlameEvent is the first unit of measure for conceptual advance. This enables engineering intellectual progress — designing sessions, environments, and challenges that target specific DDF levels — because the target is now measurable.

Prior state: "that was a productive session." Post-DDF: "this session produced 3 Level 5 events with CCD of State Management, validated by 7-instance Flood." The difference is the same as pre- and post-measurement in any physical science.

---

### H4-02 — Paradigm Shift Detection in Any Field
*Status: IDEA*
Apply DDF to the literature of any field. A paradigm shift has a DDF signature:
- Pre-shift: burst of Level 7 events across multiple researchers ("I don't have a name for this yet") — the Spiral Phase Consciousness cloud
- Convergence: different researchers independently identifying the same CCD
- The shift: one Level 5 Premise Check Pivot at field scale (existing framework identified as containing logical contradiction) followed by Level 6 Flood from the new paradigm

Darwin's era would have shown this pattern in biological literature 1840-1859. The DDF, applied to current scientific literature streams, would identify which fields are currently in the Level 7 pre-convergence phase — the intellectual tipping points that haven't happened yet.

**Prerequisites:** DDF applied to text corpora, not just session transcripts. Requires NLP-level CCD extraction without human-in-the-loop.

---

### H4-03 — The Concept Genome of Human Knowledge
*Status: IDEA*
Accumulated FlameEvents across millions of sessions, people, and projects constitute an empirical map of the conceptual structure of human knowledge. Not Wikipedia (magnitude map). Not a knowledge graph (relation map). A **concept topology**: which CCDs are fundamental (appear across many unrelated domains), which are local (domain-specific), which are bridges (connecting previously separate domains — sources of the largest paradigm shifts).

This would identify the load-bearing CCDs of human knowledge — the intellectual equivalent of keystone species. Their loss through cultural forgetting or educational failure would be catastrophically consequential in ways currently invisible.

**Prerequisites:** Global-scale FlameEvent collection, cross-domain CCD clustering, decade-scale data

---

### H4-04 — DDF-Trained AI: CCD Learning vs. Magnitude Learning
*Status: RESEARCHED*
Current AI training objective: predict the next token across magnitude-rich datasets.
DDF training objective: learn to perform measurement omission — identify the axis, drop the magnitudes, validate with flood generation.

A dataset of FlameEvent episodes at Level 5-6 (named CCDs, validated scope rules, Concretization Floods) would teach a model to form concepts rather than match patterns. This model would generalize to genuinely novel situations because it holds the axis, not just instances of the axis.

This is a new training objective, not just better data. The path to an AI that can genuinely generalize rather than interpolate.

**Prerequisites:** Large-scale FlameEvent dataset, new training objective formulation, experimental validation

---

### H4-05 — Intellectual Honesty as a Measurable Property
*Status: RESEARCHED*
Shuttling gives a precise test for intellectual honesty: a person is intellectually honest if their principles generate Floods on demand.

A person who can state "irreversible actions require human confirmation" and immediately generate 10 novel instances of irreversible actions across diverse domains holds the concept. A person who can state the same principle but cannot generate instances without AI prompting holds the words. The DDF distinguishes these with the Flood test.

This means intellectual honesty — previously a character assessment — becomes measurable in coding sessions. Floating abstraction inflation is not just an organizational pathology; it is individual intellectual dishonesty made visible.

---

## Open Research Questions

These are the questions the current framework raises but does not answer. They are active frontiers.

### OQ-01 — Real-Time vs. Batch DDF Detection Trade-offs
*To be answered by Phase 14 spikes*
Real-time (per UserPromptSubmit) enables live intervention but has limited context. Batch (full session post-completion) has rich context but misses the intervention window. Can both modes be combined — real-time for intervention, batch for scoring — without double-counting?

### OQ-02 — CCD Extraction Without Human-in-the-Loop
The DDF currently requires a human to name the axis (the axis_identified field). Can the system detect that an Axis Shift occurred, and propose candidate CCDs, without requiring the human to explicitly name it? This is required for H4-02 (paradigm shift detection in literature).

### OQ-03 — The Minimum Viable Flood
How many spontaneous instances constitute a validated Concretization Flood? The current framework says "a flood" without specifying minimum. For automated detection, a threshold is required. Preliminary estimate: 3+ instances in domains not previously discussed. Needs empirical validation from spike data.

### OQ-04 — Cross-Session CCD Identity
When the same CCD appears across different sessions (possibly with different words), how do you recognize it as the same concept rather than two separate concepts? This is the deduplication problem at the CCD level — harder than text deduplication because two textually different descriptions may refer to the same axis.

### OQ-05 — The Level 7 Resolution Mechanism
Spiral Phase Consciousness (Level 7) marks a concept-in-formation. What is the mechanism by which it resolves to a named concept? How do you detect when a Level 7 event from session N has resolved in session N+k? What triggers the transition from "open question" to "CCD with scope rule"?

### OQ-06 — DDF Applied to AI-Generated Content
The DDF markers were designed for detecting human conceptual integration. Can they be applied to AI output to detect when the AI is operating at CCD-level vs. magnitude-level? This would be a new kind of AI evaluation — not "is the answer correct" but "at what depth of abstraction is the AI reasoning"?

### OQ-07 — The Population Baseline Problem
The IntelligenceProfile is meaningful only relative to a baseline. What is the population distribution of DDF marker levels in professional software developers? Without this, the profile has no normative interpretation. Requires large-scale data collection to establish.

### OQ-08 — The Fringe Drift Rate
*Opened 2026-02-21*
What proportion of Fringe awarenesses drift back to Basement without ever becoming named concepts? This is currently unobservable in post-hoc analysis (Drift leaves no JSONL trace). Real-time Fringe Intervention (H2-08) is the only tool for measuring it. Requires the co-pilot to log every Fringe signal detected, then compare against named concepts that follow. The gap = Drift rate. Hypothesis: significant — long sessions accumulate Drift as cognitive load rises and new tool call output overwrites awareness. If confirmed, Fringe Intervention is one of the highest-value co-pilot functions.

### OQ-09 — The Optimal MEMORY.md Representation
*Opened 2026-02-21*
Given the discovery that CCD-level MEMORY.md entries function as a substitute Raven cost function for the AI — imposing the benefits of concept-formation onto AI retrieval without requiring the AI to develop it internally — what is the optimal structure for a MEMORY.md entry? A CCD-quality entry should: (1) identify the CCD axis, (2) state the scope rule (what counts as an instance), (3) include one validated flood example, (4) flag whether the entry is CCD-level or magnitude-level. Without this discipline, MEMORY.md reverts to magnitude storage and loses its Raven-simulation benefit. The DDF provides the vocabulary for this quality standard — but the format specification and auto-generation pipeline need development.

---

### H4-06 — Conceptual Type Theory (CTT): Formalizing the Algebra of Cognition
*Status: RESEARCHED — full research specification in CONCEPTUAL_TYPE_THEORY_RESEARCH_SPEC.md*

A formal mathematical system encoding Rand's claim that "conceptual awareness is the algebra of cognition." A concept is formalized as a triple (C, M, ∅) — CCD retained, measurement space preserved, specific measurements omitted. Seven CTT operations are specified (concept formation, genus computation, category error detection, Contextual Transfusion validation, CCD-level constraint matching, floating abstraction detection, concept deepening).

**Formal connections:** Type theory (concepts as types), category theory (concept formation as functor), measurement theory (CCDs as measurable axes). CTT adds what none of these have: the Flood Criterion, the Spiral structure, and the Floating Abstraction grounding requirement.

**The architectural implication:** A CTT-based AI would hold explicit concept objects in a concept store rather than implicit patterns in weights — generalizing by axis identity, not surface-pattern matching. This is the formal path to AI that genuinely generalizes rather than interpolates.

**Why now:** The formal tools are mature. Objectivist epistemology is fully developed. The OPE project is building the empirical validation apparatus (FlameEvent store) for the first time. Three conditions exist simultaneously that have never coexisted before.

**Research phases:** (1) Core formalism + theorems, (2) Computational implementation + OPE integration, (3) Empirical grounding from FlameEvent data, (4) CTT-based AI architecture prototype.

**Prerequisites:** H2-01 (FlameEvent store), H2-03 (epistemological origin), large-scale CCD dataset

---

## Update Log

| Date | Discovery | Added To |
|------|-----------|----------|
| 2026-02-21 | DDF framework developed (7 markers, Shuttling, Genus Method, Spiral Theory) | DISCOVERY_DETECTION_FRAMEWORK.md |
| 2026-02-21 | DDF as solution to agent memory problem via measurement omission | DDF doc, H2-01, H2-03, H3-01 |
| 2026-02-21 | Human-AI mirror effect: human operating level determines AI apparent intelligence | DDF doc, H2-02 |
| 2026-02-21 | FlameEvent store as concept store (not memory bank) — the core architecture | H2-01 |
| 2026-02-21 | Executive spike identified as hook substrate for real-time DDF | H1-02, Phase 14-03 |
| 2026-02-21 | OpenClaw bus spike with Claude Code JSONL path knowledge | H1-03, H1-04, Phase 14-04 |
| 2026-02-21 | Long-term potentialities: joule metaphor, concept genome, paradigm shift detection, CCD alignment, DDF training objective | H4-01 through H4-05 |
| 2026-02-21 | Conceptual Type Theory (CTT) research specification — formalization of Algebra of Cognition | H4-06, CONCEPTUAL_TYPE_THEORY_RESEARCH_SPEC.md |
| 2026-02-21 | Suspension Bridge analogy (Binswanger Ch.6) — vertical dimension of DDF, four structural integrity signals, CTT Op-8 (Top-Down Tension), Phase 17 scoped | DDF doc Section 8, CTT spec Op-8, H2-07, ROADMAP Phase 17 |
| 2026-02-21 | Crow/Raven/Fringe three-tier memory architecture — every DDF marker is a tier-shift event; Level 0 (Trunk Identification) added; AI cognitive profile formalized (infinite Basement, no Crow, no Raven); Fringe Drift as real-time insight loss; new IntelligenceProfile metrics | DDF doc Section 9, H2-02 (updated), H2-08 |
| 2026-02-21 | Root cause of agent amnesia: cost-function failure (no Raven limit = no selection pressure for concept formation); DDF as external imposition of Raven cost function on AI Basement; CCD-level MEMORY.md as substitute for Raven-guided filing; unified definition of memory synthesizing both sessions | DDF doc Section 9 (Unified Definition subsection) |
| 2026-02-21 | TransportEfficiency composite metric defined (Sacred Fire Index = raven_depth × crow_efficiency × (1/transport_speed) × trunk_quality); CCD-quality MEMORY.md auto-generation pipeline scoped; both placed in Phase 15 success criteria; TransportEfficiency added to Phase 16 Assessment Report | ROADMAP Phase 14 SC-5, Phase 15 SC-3/7/8, Phase 16 SC-3; H2-02 (updated); H2-09 (new) |
| 2026-02-21 | AI self-application directive: the entire Phase 14-18 stack applies to the AI as a first-class subject, not only as observer. ai_flame_events table, AI TransportEfficiency, Bridge-Warden on AI principles. Capability transfer arc defined: Stage 1 (human orchestrates) → Stage 4 (AI orchestrates autonomously). Phase renumbering: 16=Sacred Fire Intelligence, 17=Candidate Assessment, 18=Bridge-Warden | ROADMAP Phases 15-18 restructured; FUTURE_WORK Design Principle section added |
| 2026-02-21 | First CCD-quality MEMORY.md entries written manually from this session's validated discoveries — beginning the capability transfer: amnesia CCD, CCD-quality entry format, three-tier architecture, human-AI system, TransportEfficiency, DuckDB upsert, episode unit, OPE goal | MEMORY.md (AI concept store for this project) |
| 2026-02-23 | Premise-Assertion Architecture designed: three temporal modes (retrospective/introspective/projective), Premise Registry schema, PAG hook, foil instantiation, episode causal links. CLAUDE.md Premise Declaration Protocol created (~/.claude/CLAUDE.md). Phase 14.1 added to ROADMAP.md. | ROADMAP Phase 14.1, STATE.md Pending Todos |
| 2026-02-23 | Fallacy Detection System derived from Premise Registry + PAG: 8 fallacy categories mapped to OPE components, hallucinations identified as fallacy subset, logical integrity vs. token probability distinction formalized, in-derivation vs. process fallacy classification. Three new schema fields added to premise_registry (derivation_depth, validation_calls_before_claim, derivation_chain). False Integration marker + Causal Isolation Query added to Phase 15. | H1-05 (new), ROADMAP Phase 14.1 + Phase 15, MEMORY.md (fallacy-as-process-failure CCD) |
