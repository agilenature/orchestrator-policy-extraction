# CONTEXT.md — Phase 1: Event Stream Foundation

**Generated:** 2026-02-10
**Phase Goal:** Raw session logs (JSONL + git history) are transformed into tagged, segmented decision-point boundaries ready for episode population
**Synthesis Source:** Multi-provider AI analysis (Gemini Pro, Perplexity Sonar Deep Research)
**Note:** OpenAI provider did not return content (model detection succeeded but response empty)

---

## Overview

This phase establishes the foundation for extracting orchestrator policy learning episodes by normalizing heterogeneous session logs (Claude Code JSONL + git history) into a unified, tagged event stream, then segmenting that stream into decision-point episode boundaries. Three AI providers analyzed Phase 1 requirements and identified critical implementation decisions that must be resolved before development can proceed effectively.

**Confidence markers:**
- ✅ **Consensus** — Both Gemini and Perplexity identified this as critical
- ⚠️ **Recommended** — Perplexity emphasized, Gemini touched on
- 🔍 **Needs Clarification** — Gemini unique insight, potentially important

---

## Gray Areas Identified

### ✅ 1. Temporal Alignment of Git and JSONL Streams (Consensus)

**What needs to be decided:**
How to reliably merge the Git history stream with the JSONL conversation log stream into a single canonical sequence (`ts_utc`), given that they originate from different systems with potentially drifting clocks or asynchronous writing times.

**Why it's ambiguous:**
Git commits are timestamped by the local system clock. JSONL logs are timestamped by the API response time or the logger's clock. A tool call in JSONL at `12:00:01` might produce a git commit at `12:00:00` (clock drift) or `12:00:02`. If strictly sorted by timestamp, the "Commit Effect" might appear before the "Commit Cause" in the event stream, breaking causal analysis.

**Provider synthesis:**
- **Gemini:** Implement "Causal Windowing" merge strategy — JSONL is primary time source (orchestrator's brain), Git events are "Effects". When JSONL suggests a git operation, search for nearest Git commit within ±2 seconds and force Git event to occur immediately after JSONL tool execution event, overriding raw timestamp if necessary for logical ordering.
- **Perplexity:** Normalize all timestamps to ISO 8601 UTC format, but create explicit link structure between causally-related events (Claude Code action references git commit ID) rather than inferring temporal ordering from latency. Explicit, verifiable information (commit ID) is superior to inferred information (latency).

**Proposed implementation decision:**
**Hybrid approach:** Normalize timestamps to ISO 8601 UTC as canonical format, but use Gemini's causal windowing when explicit links are unavailable. For events with explicit causal links (JSONL includes commit hash in tool output), use Perplexity's link-based approach. For events without explicit links, use Gemini's ±2 second windowing with forced logical ordering. Mark link confidence (explicit=1.0, windowing=0.8, no-link=0.0).

**Open questions:**
- Does Claude Code JSONL output explicitly contain the resulting Git Commit Hash in tool output? (If yes → use link-based; if no → use windowing)
- What latency threshold should trigger "causal windowing" vs trusting timestamp order? (Proposal: ±2 seconds)
- How to handle ambiguous cases where multiple git commits occur within the window? (Proposal: pick closest by content similarity if ambiguous)

**Confidence:** ✅ Both providers agreed this is blocking

---

### ✅ 2. Episode Boundary Definition and Termination Criteria (Consensus)

**What needs to be decided:**
What patterns should trigger episode creation, and what constitutes a valid episode? Should episodes be minimal (single decision), maximal (complete problem-solving sequence), fixed-duration, session-based, or hybrid?

**Why it's ambiguous:**
The requirement mentions "start/end triggers" but doesn't specify episode scope. Does a `T_TEST` event end an episode regardless of result, or only upon specific outcome? Should test failure create a negative example episode (bad decision), or should the episode include both failure and self-correction?

**Provider synthesis:**
- **Gemini:** **Fail-Fast Segmentation** — Episode ends on ANY `T_TEST` execution or `T_RISKY` command. If test fails, episode is tagged `outcome: failure`. Next episode starts immediately with context "I just failed a test". This provides granular training data — we want to train the model to avoid the decision that led to failure, not obscure failure inside a long "eventually succeeded" episode.
- **Perplexity:** Implement configurable boundary detection with start triggers (O_GATE, O_CORR) and end triggers (next O_GATE, O_CORR, O_DIR, or 30s timeout). Begin with simple rule set but provide configuration options for alternative strategies (fixed windows, session-based, minimal vs maximal). Mark boundaries with confidence scores.

**Proposed implementation decision:**
**Configurable fail-fast with confidence scoring:**
- Episodes start on O_GATE or O_CORR events (orchestrator decision/interpretation)
- Episodes end on: (1) ANY `T_TEST` execution (Gemini's fail-fast), (2) `T_RISKY` command, (3) next O_GATE/O_CORR/O_DIR event, OR (4) 30-second timeout
- Tag episodes with `outcome: success/failure/timeout` based on end trigger
- Mark boundaries with confidence: explicit trigger (1.0), timeout (0.6)
- Provide alternative strategies in config.yaml for experimentation

**Open questions:**
- How to handle `T_LINT` (Linting)? Is lint error equivalent to test failure, or is it noise? (Proposal: Treat as observation, not end trigger, unless it prevents execution)
- Should nested decision points (user asks clarifying question mid-episode) create sub-episodes or interruptions? (Proposal: Tag as "complex" episode with metadata, but keep flat structure for Phase 1)
- What timeout value balances capturing intent vs cutting off slow operations? (Proposal: 30 seconds default, configurable)

**Confidence:** ✅ Both providers agreed this is blocking

---

### ✅ 3. Event Classification Label Definitions and Rules (Consensus)

**What needs to be decided:**
What does each classification label mean (O_DIR, O_GATE, O_CORR, X_PROPOSE, X_ASK, T_TEST, T_LINT, T_GIT_COMMIT, T_RISKY)? What are decision rules for assigning labels? How to handle multi-label assignments?

**Why it's ambiguous:**
Requirements provide label names but no definitions. Without semantic definitions and concrete rules, different developers will classify events inconsistently. This affects downstream boundary detection and policy learning.

**Provider synthesis:**
- **Gemini:** Implement keyword + distance heuristic for O_CORR vs O_DIR. If user message starts with "No", "Wrong", "Stop", "Fix", "Error" (reaction keywords from config.yaml), tag as O_CORR. If previous system event was T_TEST failure or T_RISKY alert and user responds immediately, default to O_CORR. All other user inputs are O_DIR.
- **Perplexity:** Create classification rule specification in config.yaml with: (1) semantic definition, (2) decision rules (conditions on event attributes, payload, temporal context), (3) exclusivity rules (can label co-occur?), (4) confidence scoring. Use hybrid approach with primary labels (one per event) and secondary labels (zero or more).

**Proposed implementation decision:**
**Config-driven classification with confidence scoring:**
- Define each label in config.yaml with semantic definition, decision rules, exclusivity, and confidence calculation
- Use Perplexity's hybrid approach: primary label (one per event, mutually exclusive) + secondary labels (additive)
- Implement Gemini's keyword heuristic for O_CORR detection as one decision rule
- Stratify rules into three tiers: (1) Direct from log evidence (high confidence), (2) Inferred from patterns (medium), (3) Risk model-based (lower but contextually relevant)
- Store confidence scores and source (direct, inferred, risk-model) with each classification

**Open questions:**
- Should sentiment analysis be used for O_CORR detection, or is keyword matching sufficient? (Proposal: Keyword matching for Phase 1, sentiment as future enhancement)
- What should "X_PROPOSE" and "X_ASK" specifically mean? (Need stakeholder clarification)
- How to handle events that could receive multiple primary labels? (Proposal: Use confidence scoring to pick one, store alternatives as metadata)

**Confidence:** ✅ Both providers agreed this is blocking

---

### ⚠️ 4. Payload Structure for Heterogeneous Event Data (Recommended)

**What needs to be decided:**
How to represent events with heterogeneous information content in a unified schema? Should tool-specific information be normalized into generic fields, preserved as-is in nested structures, or handled differently?

**Why it's ambiguous:**
Claude Code execution logs have detailed tool invocation parameters, git history has only commit metadata, different tools have different payloads. The requirement specifies `payload` field but underspecifies structure for heterogeneous data.

**Provider synthesis:**
- **Gemini:** DuckDB `events` table `payload` column should be JSON type (or struct) containing: `text` (raw visible text), `reasoning` (extracted CoT), `tool_name`, `tool_args`, `file_diff`. This prevents complex parsing during analysis phase.
- **Perplexity:** Preserve heterogeneous information in payload as JSON with required `payload.common` sub-object (normalized fields: error_message, tool_name, duration_ms) while allowing `payload.details` for tool-specific nested structures. Payload schema should be part of config.yaml, allowing evolution without code changes.

**Proposed implementation decision:**
**Structured payload with common + tool-specific sections:**
```json
{
  "common": {
    "text": "raw visible text",
    "reasoning": "extracted CoT if available",
    "tool_name": "if applicable",
    "duration_ms": 123,
    "error_message": "if error occurred"
  },
  "details": {
    "git": { "commit_hash": "abc123", "files_changed": [...] },
    "test": { "passed": 5, "failed": 2, "output": "..." }
  }
}
```
- Define `payload.common` schema in config.yaml with required/optional fields
- Allow `payload.details` to contain tool-specific nested structures
- This enables consistent queries over common fields while preserving information fidelity

**Open questions:**
- Which fields should be in `common` vs `details`? (Proposal: Start with minimal common set, expand based on query needs)
- How to handle CoT/thinking blocks that are sometimes suppressed? (Proposal: Optional field, empty string if unavailable)
- Should `details` have sub-schemas for each tool type? (Proposal: Yes, defined in config.yaml)

**Confidence:** ⚠️ Perplexity emphasized, Gemini touched on

---

### ⚠️ 5. Risk Model Configuration and T_RISKY Detection (Recommended)

**What needs to be decided:**
How should the system match `T_RISKY` patterns? Does it match against tool name, arguments, or file paths? How should risk be quantified?

**Why it's ambiguous:**
DATA-03 mentions "protected paths" and "risk model" but provides no specification. Is `rm -rf /` risky? (Yes - command-based). Is `rm -rf ./temp` risky? (Maybe not). Is `edit config/secrets.yaml` risky? (Yes - path-based). Complexity increases if we must parse shell command arguments to find paths.

**Provider synthesis:**
- **Gemini:** **Dual-Layer Risk Config** — Define `risky_tools` (exact matches on tool names) and `protected_paths` (regex matches on entire payload string). This rough heuristic is acceptable for Phase 1 to ensure aggressive safety/boundary detection. T_RISKY triggers automatic episode break even if operation succeeded (high-stakes decisions should be isolated episodes).
- **Perplexity:** Define risk model as configurable set of risk factors, each with detection method (file pattern, operation type, code pattern, consequence pattern) and risk weight (0.0 to 1.0). Assess event risk by checking which factors apply and aggregating weights. Store risk assessments as event attributes (event.risk_score, event.risk_factors), not as classifications.

**Proposed implementation decision:**
**Hybrid risk model with dual-layer detection and scoring:**
- Implement Gemini's dual-layer detection (risky_tools + protected_paths) as first tier
- Add Perplexity's risk factor framework for second tier (risk_score, risk_factors metadata)
- T_RISKY classification = binary (risky or not), based on whether any detection rule fires
- Risk scoring = continuous (0.0 to 1.0), based on aggregated risk factors
- Store both classification and score as separate attributes
- T_RISKY triggers episode boundary (Gemini's insight)

**Open questions:**
- Should false positives (detecting "secrets.yaml" in a print statement) be tolerated for Phase 1? (Proposal: Yes, aggressive is better than missing risks)
- How should risk factors combine? (max, sum, weighted average) (Proposal: max for classification threshold, weighted average for score)
- What risk score threshold should trigger T_RISKY classification? (Proposal: ≥0.7)

**Confidence:** ⚠️ Both providers discussed, Gemini provided concrete dual-layer approach

---

### ⚠️ 6. Deduplication and Idempotency in Log Normalization (Recommended)

**What needs to be decided:**
How should duplicates be detected and eliminated during normalization without losing information about retries, replayed actions, or legitimate repetitions?

**Why it's ambiguous:**
If Claude Code session logs are backed up, recovered, or re-ingested, raw logs may contain duplicate records. Git history is inherently deduplicatable (commits have unique hashes) but re-running git log can produce overlapping results.

**Provider synthesis:**
- **Perplexity:** Assign event_id as deterministic hash of (source, source_id, timestamp, actor, action_type). For git commits, use commit hash directly as source_id. For Claude Code actions, use session-local action ID. Implement idempotent ingestion so same event ingested twice produces same row in DuckDB. This follows exactly-once processing semantics where duplicates are detected and ignored.

**Proposed implementation decision:**
**Deterministic event_id with idempotent ingestion:**
- event_id = hash(source_system, source_id, ts_utc, actor, type)
- For git: source_id = commit_hash (globally unique)
- For JSONL: source_id = session_id + turn_id (session-local unique)
- DuckDB uses event_id as primary key with ON CONFLICT IGNORE
- This ensures re-ingesting same logs produces identical events without duplicates

**Open questions:**
- Should we track ingestion metadata (first_seen, last_seen timestamps)? (Proposal: Yes, for debugging)
- How to handle events that are legitimately repeated (same action run twice)? (Proposal: Different turn_id makes different event_id)
- Should we log when duplicates are detected? (Proposal: Yes, at debug level)

**Confidence:** ⚠️ Perplexity emphasized with concrete proposal

---

### 🔍 7. Handling Chain-of-Thought and Thinking Blocks (Needs Clarification)

**What needs to be decided:**
How to store and tag "Thinking" blocks or "Hidden Reasoning" found in raw logs. Are they separate events or part of the payload of the final response?

**Why it's ambiguous:**
The orchestrator's value lies in how it decided. If logs separate reasoning (e.g., `<thinking>...</thinking>`) from tool call, treating them as one blob obscures the "Decision Point". But creating separate events for thinking might create episodes with only thinking and no action.

**Provider synthesis:**
- **Gemini:** **Extraction as Payload Attribute** — Do NOT create separate `type: THINKING` event. Instead, payload structure should have dedicated `reasoning` field. This ensures every Action event carries its justification directly attached.

**Proposed implementation decision:**
**Extract reasoning into payload.common.reasoning field:**
- Do not create separate THINKING event types
- Extract `<thinking>...</thinking>` blocks (if present) into `payload.common.reasoning`
- Action events (X_PROPOSE, tool calls) carry their reasoning attached
- This simplifies decision-point analysis — decision + reasoning are together

**Open questions:**
- Does Claude Code JSONL format consistently expose reasoning blocks, or are they sometimes suppressed? (Need to inspect actual JSONL samples)
- Should reasoning be used in classification rules? (Proposal: No for Phase 1, but store for future use)
- What if reasoning is extremely long (>10KB)? (Proposal: Store full text, add summary field if needed)

**Confidence:** 🔍 Gemini unique insight, potentially important

---

### ⚠️ 8. Error Handling and Data Validation Strategy (Recommended)

**What needs to be decided:**
When errors are encountered during normalization, classification, or boundary detection, should the system fail fast (stop processing), degrade gracefully (skip problematic events), or attempt recovery (infer missing information)?

**Why it's ambiguous:**
Raw logs may contain incomplete data (missing fields), corrupted data (malformed JSON, invalid timestamps), inconsistent data (contradictory information), or ambiguous data (events classified multiple ways). Each error type requires different handling.

**Provider synthesis:**
- **Perplexity:** Implement multi-level error handling: (1) Schema validation at ingestion rejects obviously invalid data; (2) Classifier handles missing optional fields by inferring or marking low-confidence; (3) Boundary detection handles ambiguous triggers by using alternatives or marking uncertainty; (4) Comprehensive error logging tracks issues; (5) Summary statistics report data quality metrics.

**Proposed implementation decision:**
**Multi-level error handling with quality metrics:**
- **Level 1 (Reject):** Schema validation rejects non-JSON, missing required fields after normalization
- **Level 2 (Degrade):** Classifier infers missing optional fields or marks low-confidence
- **Level 3 (Alternative):** Boundary detection uses alternative triggers when ambiguous
- **Level 4 (Logging):** Comprehensive error logging with affected event IDs
- **Level 5 (Metrics):** Report data quality (% complete data, % multi-class events, etc.)
- Validation severity levels: "error" (reject), "warning" (log + continue), "info" (informational)

**Open questions:**
- What percentage of invalid events is acceptable before aborting? (Proposal: >10% invalid → abort with error report)
- Should users be able to configure validation strictness? (Proposal: Yes, via config.yaml)
- How to handle temporal anomalies (out-of-order events)? (Proposal: Tolerate + flag, use explicit links)

**Confidence:** ⚠️ Perplexity emphasized with comprehensive framework

---

### ⚠️ 9. Configuration Schema Design and Versioning (Recommended)

**What needs to be decided:**
How should configuration be structured, validated, and versioned to ensure changes don't break historical episodes?

**Why it's ambiguous:**
Configuration affects all phases (normalization rules, classification rules, boundary detection, risk model). If configuration changes, re-running extraction produces different output, potentially invalidating historical episodes.

**Provider synthesis:**
- **Perplexity:** Use JSON Schema to formally define configuration schema. Validate YAML by converting to JSON, then validating. Version configuration and include version (and hash) as metadata with every extracted episode. When configuration changes, mark episodes with old config as "legacy". Provide utilities for re-extraction but don't auto-update.

**Proposed implementation decision:**
**Versioned configuration with schema validation:**
- Define configuration schema using JSON Schema
- Validate config.yaml by converting to JSON and validating against schema
- Embed config version + hash in every extracted episode metadata
- When config changes, mark old episodes as "legacy"
- Provide re-extraction utilities without auto-update
- Document major changes in CHANGELOG
- This ensures reproducibility (logs + config version → deterministic output)

**Open questions:**
- Should configuration support "overlays" or "profiles" for experimentation? (Proposal: Yes, via config inheritance)
- How to notify users of configuration changes? (Proposal: Git commit + CHANGELOG entry)
- Should schema validation be strict or permissive by default? (Proposal: Strict in production, permissive in dev)

**Confidence:** ⚠️ Perplexity emphasized, critical for long-term maintainability

---

## Summary: Decision Checklist

Before planning Phase 1 implementation, confirm decisions on:

**Tier 1 (Blocking):**
- [ ] Temporal alignment strategy (causal windowing vs link-based vs hybrid)
- [ ] Episode boundary definition (fail-fast, configurable, minimal vs maximal)
- [ ] Event classification label semantics (O_DIR, O_GATE, O_CORR, X_PROPOSE, X_ASK, etc.)
- [ ] Payload structure (common + details, schema definition)

**Tier 2 (Important):**
- [ ] Risk model configuration (dual-layer detection, risk scoring, T_RISKY criteria)
- [ ] Deduplication strategy (deterministic event_id, idempotency)
- [ ] Error handling levels (reject, degrade, alternative, log, metrics)
- [ ] Configuration schema design (validation, versioning, reproducibility)

**Tier 3 (Polish):**
- [ ] CoT/thinking block handling (payload field vs separate event)
- [ ] Multi-label classification (primary + secondary labels)
- [ ] Boundary validation (post-hoc adjustment for problematic boundaries)

---

## Next Steps

**Non-YOLO Mode (current):**
1. Review this CONTEXT.md
2. Answer questions in CLARIFICATIONS-NEEDED.md
3. Create CLARIFICATIONS-ANSWERED.md with your decisions
4. Run `/gsd:plan-phase 1` to create execution plan

**Alternative (YOLO Mode):**
Run `/meta-gsd:discuss-phase-ai 1 --yolo` to auto-generate answers

---

*Multi-provider synthesis by: Gemini Pro, Perplexity Sonar Deep Research*
*OpenAI provider: Model detection succeeded but response empty (excluded from synthesis)*
*Generated: 2026-02-10*
