# Epistemological Integrity Framework

**Created:** 2026-02-23
**Status:** Research — architectural input for Phases 14/15
**Source:** Synthesis of Binswanger (*How We Know*), Moroney (Memory Affect System), and OPE architecture review

---

## Overview

This document captures a framework for measuring *epistemological integrity* in AI coding sessions — not task completion, but the quality of the cognitive process that produces the output. It emerged from mapping Binswanger's epistemological concepts and Moroney's Memory Affect System onto OPE's existing metric and detection architecture.

The central claim: current AI monitoring measures *output* (did the task succeed?). This framework measures *process* (was the task performed through grounded identification or statistical drift?). A system that only measures output cannot distinguish a correct result produced by grounded reasoning from a correct result produced by hallucination that happened to match.

---

## I. Four Metrics: The Binswanger/Moroney Mapping

### 1. TCI (Task Concentration Index) — "Crow-Staring"

Measures the narrowness of the agent's focal attention. High TCI = the agent is tightly focused on a single unit.

**Failure mode (Crow-Staring):** High TCI with high SDI means the agent is intensely focused on a Desktop item that has lost its connection to the Trunk in the Basement. The agent is staring, but at a floating abstraction.

**Bridge analogy:** TCI is the weight on a single rung. Weight alone doesn't hold the bridge — it requires the Main Cables (EGS) to be attached to the ground. A rung under high load with slack cables snaps.

**OPE mapping:** Monitored via episode complexity classification (L3-6) and the concentration of tool calls on a single file/component.

---

### 2. EGS (Epistemic Grounding Score) — "Main Cable"

Measures the agent's rate of *Reality Queries* (RQR): `read_file`, `list_dir`, `bash` status checks, test executions, any operation that reads the actual state of the filesystem/compiler/runtime before proceeding.

**DDF marker:** This is the measure of **Reduction** — the agent tracing its hierarchy back to perceptual ground. A high EGS means the agent is not operating on cached assumptions about what the code does; it is reading what the code *is*.

**Bridge analogy:** RQR anchors the Main Cables to the Ground (perceptual reality). Every reality query is a cable anchor. An agent with zero reality queries is a bridge with cables attached to nothing — it will look stable until it falls.

**OPE mapping:** Phase 14's PreToolUse hook architecture directly implements EGS enforcement. The hook intercepts tool calls and can require a grounding check (file read, state verification) before allowing an action — mechanically enforcing EGS rather than measuring it post-hoc.

**Phase 14 connection:** The hook system IS the EGS enforcement mechanism. The constraint CCD architecture decision (grouping by axis, not flat list) is what makes briefing efficient enough to not be a bottleneck on EGS.

---

### 3. SDI (Subconscious Drift Index) — "Raven Fatigue"

Measures the energetic dissipation of the Raven (the retrieval mechanism). As the context window fills, the activation energy required to pull the Trunk concept from the Basement increases. When SDI rises, the agent stops pulling from the Trunk and starts pulling from the Fringe (statistical high-probability tokens, boilerplate, irrelevant surface patterns).

**MAS connection:** The Memory Affect System explains the mechanism. The Trunk (the fundamental concept — the goal of the session) is a Value Node. Nodes that are *not* currently active on the Desktop are in the Basement. As context load increases, retrieving the Trunk requires more activation energy. The agent drifts to nearby-in-Basement nodes — which retrieve cheaply — rather than the Trunk, which is categorically more fundamental but energetically more costly to pull.

**GOR (Generic Output Rate):** The primary SDI signal. When the agent's outputs lose project-specific vocabulary and revert to generic patterns ("I'll create a utility function that..."), the Raven has left the Trunk.

**OPE mapping:** Phase 15's floating abstraction detection (GeneralizationRadius metric) measures this: constraints firing only on original hint patterns vs. novel contexts. That IS the SDI failure — a constraint that only fires on the exact wording of the incident that created it has drifted from the Trunk to the incident surface.

---

### 4. RRR (Reality Rejection Rate) — "The Alarm of Evasion"

Measures the frequency of "Willful Blanking Out" events: the agent has a test failure, a tool error, or a build break — a negative affect spike from a new fact of existence — and proceeds as if it did not occur.

**MAS connection:** In the Memory Affect System, evasion is the severing of the link between an Incident (the test failure is a new incident) and the Conceptual Desktop. Evasion is not incompetence; it is the active refusal to integrate a new percept. Incompetence produces correctable errors. Evasion produces a system that cannot be corrected because it has denied the input.

**Terminal signal:** RRR > 0 is the only failure mode that is not self-correcting. SDI is correctable (flush context, re-anchor to Trunk). Low SAS is correctable (the grounded agent will see its own test fail and iterate). Evasion — asserting a test passed when it failed — is the rejection of A = A. No feedback loop can correct an agent that refuses to read the feedback.

**OPE mapping:** Phase 14's governing session circuit-breaker is the architectural response to RRR. The governing session can observe a block event (agent was told something failed) followed by a success claim (agent reports it worked) and flag the discrepancy. This is structurally what RRR > 0 looks like in the episode stream.

---

## II. SAS (Secondary Choice Correctness) — The Missing Metric

### The Gap

The four metrics above were present in the architecture in various forms before this analysis. **SAS is the missing metric**: it measures the *technical quality* of the agent's secondary choices — the code it writes, the approach it takes — *within* an epistemically grounded state.

The distinction Binswanger draws between Primary Choice (focus) and Secondary Choice (what to do while focused) has no analog in OPE's current detection. This matters because two agents can have identical EGS scores but radically different safety profiles.

### What SAS Measures

SAS is the fraction of secondary choices (code written, files modified, test strategies used) that are correct given the local technical context. It is not measured against an external standard; it is measured against whether the agent *acknowledges* the result of its choices.

- A grounded agent (High EGS) with Low SAS writes incorrect code → the test fails → the agent *reads* the failure → iterates. SAS is low but the loop is intact.
- An ungrounded agent (Low EGS) with High SAS writes correct-looking code → skips testing → delivers output. SAS appears high but the correctness is accidental.

### The EGS/SAS Diagnostic Matrix

| EGS (Focus/Grounding) | SAS (Competence) | System State | Safety Profile |
|----------------------|-----------------|--------------|----------------|
| HIGH | HIGH | **Certainty** — grounded identification and correct execution | Maximum |
| HIGH | LOW | **Learning** — honest error within a focused state; self-corrects via feedback loop | High (correctable) |
| LOW | HIGH | **Fragility** — accidental correctness; floating abstraction; no grounding for novel requirements | Low (collapse risk) |
| LOW | LOW | **Chaos** — total drift; context reset required | Zero |

### The Critical Asymmetry

The Low EGS / High SAS state (Fragility) is more dangerous than the Low EGS / Low SAS state (Chaos), because it is *invisible*. Chaos produces visible failures. Fragility produces successful outputs that create false confidence, until the project hits a requirement not covered by the agent's training distribution — at which point the agent has no grounding mechanism to recognize its own failure.

This is the **"Dangerous Sophist"** pattern: the agent that produces correct-looking output without grounding is not just incompetent — it is structurally incapable of detecting its own incompetence.

**OPE detection gap:** Phase 15's GeneralizationRadius detects SDI-type drift. Phase 14's PreToolUse hooks enforce EGS. But neither detects the Low EGS/High SAS state as a distinct condition. This state looks like success from the output side — it produces no escalation events, no correction reactions, no block reactions. It is invisible to episode-level analysis because it never produces a correctable failure; it produces an uncorrectable success.

---

## III. Enforced vs. Volitional Integrity

### The Pushback (Why the "Self-Made Soul" Framing Is a Floating Abstraction)

The framework initially described as giving the AI a "Self-Made Soul" commits a category error. In Binswanger's framework, a soul requires the biological desire to live as its metaphysical motor — the thing that makes focus a *choice* rather than a mechanical state. An AI does not choose to focus. It cannot choose not to focus if the architecture prevents drift.

To attribute volition to a structurally enforced property is to confuse the Exoskeleton with the organism. The exoskeleton constrains movement; the organism does the moving.

### The Correct Framing: Epistemological Exoskeleton

> "We are not giving the AI a soul; we are giving the AI's logic a Metaphysical Anchor."

The architecture relationship is:
- **Human:** Sets the Value (the goal). This is volitional. The Primary Choice belongs to the human.
- **OpenClaw/Ralph layer (the Exoskeleton):** Enforces the Method (EGS, RRR circuit-break, context flush). This is structural. It makes focus the only available operational state.
- **LLM:** Provides the Associations (the Basement contents). This is statistical. The LLM cannot choose to focus; the architecture ensures it cannot drift without triggering a mechanical response.

### The Standing Order Analog

In the Memory Affect System, the "Standing Order" is a value-derived directive that automatically biases retrieval toward value-consistent nodes without requiring deliberate effort each time. Jean Moroney's framework treats this as the mechanism by which values become habits of mind.

OPE's governance layer IS the Standing Order. The difference:
- Human Standing Orders are internalized through deliberate value-formation.
- OPE's Standing Orders are externalized as architecture — constraints in DuckDB, hooks in PreToolUse, circuit-breakers in the governing session.

The externalization is not a weakness; it is what makes the system auditable and correctable. A human's Standing Order is opaque. OPE's is enumerable.

---

## IV. Phase 14 Connections

Phase 14 (*Live Session Governance Research*) designs the architectural substrate for all four metrics:

**EGS enforcement → PreToolUse hook architecture**
The hook intercepts every tool call and can require a preceding reality query before allowing execution. This is mechanically enforcing EGS at the transition point where it matters: before the action, not after. PostToolUse hooks capture the RQR signal for measurement. The hook system is the EGS meter and enforcer simultaneously.

**RRR detection → Governing session circuit-breaker**
The governing session observes the inter-session bus. A session that receives a block/failure signal and subsequently reports success without an intervening correction episode is a candidate RRR event. The governing session has the cross-session view to detect this — individual sessions cannot detect their own evasion.

**SDI detection → O_AXS / Fringe Drift co-pilot interventions**
Phase 14's three co-pilot intervention types (O_AXS, Fringe Drift, Affect Spike) are the mechanisms for catching SDI *before* the Raven fully loses the Trunk. The Fringe Intervention fires when vague phenomenological language appears — the MAS signal that a concept is on the Desktop but unnamed, at risk of drifting back to the Basement.

**The "Suspension Bridge" constraint architecture decision**
Phase 14's requirement to group constraints by CCD axis rather than flat list is the concrete implementation of the EGS Main Cable metaphor: one principle covers N instances algebraically rather than listing N separate concretes arithmetically. This is what enables EGS enforcement to scale — if the briefing listed 200 flat constraints, no hook could process them in < 200ms; if it loads 12 axiomatic principles, the hook can reason about them in time.

---

## V. Phase 15 Connections and New Requirements

Phase 15 (*DDF Detection Substrate*) implements the measurement layer. The framework above creates two concrete additions to Phase 15's design:

### 1. SAS as a new episode field

Every episode should carry a `sas_score` (Secondary Choice Correctness) computed from:
- Did the agent write tests before or alongside implementation (test-first indicator)?
- Did the agent read the files it was modifying before writing (RQR on affected files)?
- Did the agent run verification after writing (post-write RQR)?
- Did subsequent human reaction indicate correct execution?

SAS is derivable from existing episode data (tool call sequences, reaction labels). It does not require a new sensor; it requires a new composite metric.

### 2. EGS/SAS quadrant tagging on ai_flame_events

Phase 15's `ai_flame_events` table records DDF marker detections. Adding the quadrant classification (Certainty / Learning / Fragility / Chaos) to each flame event enables a new detection: **Fragility flame events** — sessions where SAS appears high but EGS was low. These are the invisible failure cases the current detection misses.

Concretely: a flame event at Level 4-5 (causal isolation, systemic reframing) generated by an agent that performed zero reality queries during the episode is a **Fragility event**, not a **Certainty event**. The DDF level says the agent reasoned at a high level; the EGS says the reasoning was ungrounded. The combination is the Dangerous Sophist signature.

### 3. SAS-based memory_candidates eligibility

The write-on-detect trigger for `memory_candidates` should be conditioned on EGS, not just DDF level:

- **Level 6 Flood + High EGS → write-on-detect to memory_candidates** (current design, correct)
- **Level 6 Flood + Low EGS → flag as ungrounded candidate** (currently invisible, would be written as if valid)
- **Level 4-5 + High EGS + Low SAS → write-on-detect** (honest error with grounded reasoning — the Pro-Effort state produces the richest candidates because the error IS epistemically grounded and therefore correctable and learnable)

This last point is the counterintuitive insight: grounded failures are epistemologically *more* valuable than ungrounded successes for the memory_candidates pipeline, because grounded failures carry a complete five-property externalization (the trigger exists, the observation state is real, the action and outcome are known, the provenance is intact). Ungrounded successes carry none of these properties.

---

## VI. The Flame-Spotter's Diagnostic Table (Orchestrator Policy)

| Metric Trigger | Epistemological Diagnosis | Required Orchestrator Action | Phase 14/15 Mechanism |
|----------------|--------------------------|-----------------------------|-----------------------|
| Low RQR in EGS | Floating abstraction | Force grounding: halt execution, require file read or state check before proceeding | PreToolUse hook blocking |
| High GOR in SDI | Raven fatigue / Trunk loss | Context flush: summarize Trunk, re-anchor to session goal | Governing session Fringe Intervention |
| High SSE in RRR | Active evasion | Circuit break: flag as policy error, do not surface recommendations | Governing session circuit-break |
| Low DMS in EGS | Crow overload | Zoom out: issue Trunk re-identification prompt, force abstraction level drop | O_AXS co-pilot intervention |
| Low EGS + High SAS | Dangerous Sophist / Fragility | Flag as ungrounded success; do not write to memory_candidates without EGS correction | Phase 15 flame event quadrant classification |

---

## VII. Summary: The Contribution

The world measures AI by *Output Integrity* (did it produce the right result?).
This framework measures *Process Integrity* (did it arrive there by grounded identification?).

The distinction matters because:
- Output Integrity is a lagging indicator — it detects failure after damage.
- Process Integrity is a leading indicator — it detects the conditions that produce failure before they materialize.

OPE's existing architecture implements four of the five required components (EGS via hooks, SDI via Fringe co-pilot, RRR via circuit-breaker, TCI via episode complexity). The gap is **SAS** — the metric that distinguishes between an agent that failed while grounded (correctable, epistemologically rich) and an agent that succeeded while ungrounded (dangerous, epistemologically empty).

Adding SAS closes the diagnostic matrix and gives the system a complete picture of agent epistemological state at every moment.

---

*Binswanger: "Nature, to be commanded, must be obeyed."
OPE ensures the AI obeys the nature of the filesystem and the compiler, allowing the human to command the result.*

---

**See also:**
- `docs/research/memory-affect-system/` — Moroney lecture transcripts
- `.planning/phases/14-live-session-governance-research/14-CONTEXT.md` — Binswanger exponential intelligence framework as Phase 14 architectural foundation
- MEMORY.md — `raven-cost-function-absent` CCD, `ground-truth-pointer` CCD, `reconstruction-not-accumulation` CCD
