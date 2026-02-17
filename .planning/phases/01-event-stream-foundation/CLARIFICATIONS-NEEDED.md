# CLARIFICATIONS-NEEDED.md

## Phase 1: Event Stream Foundation — Stakeholder Decisions Required

**Generated:** 2026-02-10
**Mode:** Multi-provider synthesis (Gemini Pro, Perplexity Sonar Deep Research)
**Source:** 2 AI providers analyzed Phase 1 requirements

---

## Decision Summary

**Total questions:** 21 questions across 9 gray areas
**Tier 1 (Blocking):** 9 questions — Must answer before planning
**Tier 2 (Important):** 9 questions — Should answer for quality
**Tier 3 (Polish):** 3 questions — Can defer to implementation

---

## Tier 1: Blocking Decisions (✅ Consensus)

### Q1: Temporal Alignment — JSONL Commit Hash Availability

**Question:** Does Claude Code JSONL output explicitly contain the resulting Git Commit Hash in tool execution results?

**Why it matters:** Determines whether we can use reliable link-based temporal alignment (if yes) or must use heuristic causal windowing (if no).

**Options identified by providers:**

**A. JSONL includes commit hash**
- Use link-based alignment (Perplexity's approach)
- Explicit causal links via commit ID
- No temporal ambiguity
- _(Proposed by: Perplexity)_

**B. JSONL does NOT include commit hash**
- Use causal windowing (Gemini's approach)
- Search ±2 seconds for matching commit
- Force logical ordering
- _(Proposed by: Gemini)_

**Synthesis recommendation:** ⚠️ **Need actual JSONL sample to confirm**
- Inspect real Claude Code JSONL output
- Choose approach based on what's actually available
- Hybrid: use links when available, windowing when not

**Sub-questions:**
- If windowing is needed, what latency threshold? (Proposed: ±2 seconds)
- How to handle multiple commits within window? (Proposed: pick closest by content similarity)

---

### Q2: Episode Boundaries — Lint Treatment

**Question:** How should `T_LINT` (linting) events be treated in episode boundary detection?

**Why it matters:** Affects episode granularity and whether lint failures create separate episodes vs being treated as observations.

**Options identified by providers:**

**A. Lint as end trigger (like T_TEST)**
- Lint failure creates episode boundary
- Separate episode for "fix lint issues"
- Provides granular training data
- _(Not explicitly proposed, but consistent with fail-fast)_

**B. Lint as observation (not end trigger)**
- Lint is noise/chatter within episode
- Only ends episode if it prevents execution
- Keeps episodes focused on functional decisions
- _(Proposed by: Gemini)_

**Synthesis recommendation:** ✅ **Option B — Lint as observation**
- Lint errors are typically non-blocking
- Treat as intermediate observation unless they prevent code execution
- Reserve episode boundaries for functional decision points

**Sub-questions:**
- What if lint errors ARE blocking (e.g., CI fails)? (Proposed: Then treat as end trigger)

---

### Q3: Episode Boundaries — Nested Decision Points

**Question:** Should nested decision points (user asks clarifying question mid-episode) create sub-episodes or be handled as interruptions?

**Why it matters:** Affects episode structure (flat vs hierarchical) and complexity of downstream policy learning.

**Options identified by providers:**

**A. Hierarchical episodes (nested structure)**
- Preserves full decision structure
- Captures context switches
- More complex to analyze
- _(Not explicitly proposed)_

**B. Flat episodes with metadata (Perplexity's "complex" tag)**
- Simple non-overlapping episodes
- Tag as "simple" (single decision) or "complex" (nested decisions)
- Easier policy learning, preserves hint of nesting
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option B — Flat with metadata**
- Simpler for Phase 1 policy learning
- Metadata allows future hierarchical grouping if needed
- Tag episodes as "simple" or "complex"

**Sub-questions:**
- What metadata should mark nested decision points? (Proposed: interruption_count, context_switches)

---

### Q4: Episode Boundaries — Timeout Value

**Question:** What timeout value (seconds of inactivity) should trigger episode boundary?

**Why it matters:** Too short = artificial boundaries mid-task; too long = unrelated actions grouped together.

**Options identified by providers:**

**A. 30 seconds (Perplexity's proposal)**
- Balances intent capture vs slow operations
- Reasonable for most coding tasks
- _(Proposed by: Perplexity)_

**B. Configurable timeout**
- Different tasks have different pacing
- Allow config.yaml to specify
- _(Implicit in configurable approach)_

**C. No timeout (explicit triggers only)**
- Only O_GATE/O_CORR/O_DIR events end episodes
- Risk: very long episodes if no triggers
- _(Not proposed, but possible)_

**Synthesis recommendation:** ✅ **Option A with B — 30s default, configurable**
- Start with 30-second default
- Make configurable in config.yaml
- Allow experimentation with different values

**Sub-questions:**
- Should timeout scale with episode complexity? (Proposed: No for Phase 1, fixed timeout)

---

### Q5: Event Classification — Label Semantics

**Question:** What do the classification labels X_PROPOSE and X_ASK specifically mean in the context of orchestrator decisions?

**Why it matters:** Without precise definitions, classification will be inconsistent and policy learning will fail.

**Options identified by providers:**

**A. X_PROPOSE = "Orchestrator proposes action to user for approval"**
- Covers: presenting plan, suggesting approach, recommending tool
- Example: "I propose we fix this by editing config.yaml"
- _(Inferred from name)_

**B. X_ASK = "Orchestrator asks user for clarification or decision"**
- Covers: ambiguity resolution, choice presentation, missing information request
- Example: "Should I use React or Vue for this?"
- _(Inferred from name)_

**Synthesis recommendation:** ⚠️ **Need stakeholder confirmation**
- Above interpretations are reasonable but unverified
- Confirm with orchestrator domain expert
- Define concretely in config.yaml with examples

**Sub-questions:**
- Are there other X_ labels we should define? (X_WAIT, X_ESCALATE, etc.)
- Should X_PROPOSE always trigger episode boundary? (Proposed: Yes, it's a decision point)

---

### Q6: Event Classification — O_CORR Detection Confidence

**Question:** Should we use sentiment analysis for O_CORR (correction) detection, or is keyword matching sufficient?

**Why it matters:** Affects classification accuracy and implementation complexity.

**Options identified by providers:**

**A. Keyword matching only (Gemini's proposal)**
- Simple, fast, deterministic
- Match "No", "Wrong", "Stop", "Fix", "Error"
- Good enough for Phase 1
- _(Proposed by: Gemini)_

**B. Sentiment analysis**
- More sophisticated, catches nuance
- "That's not quite right" = correction without keywords
- Higher complexity, non-deterministic
- _(Not proposed, but possible)_

**Synthesis recommendation:** ✅ **Option A — Keyword matching for Phase 1**
- Simpler implementation
- Deterministic classification
- Can add sentiment in future if keyword coverage insufficient

**Sub-questions:**
- What keyword list should we start with? (Proposed: Gemini's list + expand based on real data)
- Should we distinguish polite corrections from harsh ones? (Proposed: No for Phase 1, binary correct/not-correct)

---

### Q7: Payload Structure — Common vs Details Fields

**Question:** Which event fields should be in `payload.common` (normalized across all events) vs `payload.details` (tool-specific)?

**Why it matters:** Common fields enable consistent queries; details preserve tool-specific information.

**Options identified by providers:**

**A. Minimal common (Perplexity's proposal)**
- common: text, reasoning, tool_name, duration_ms, error_message
- details: everything else (tool-specific)
- Start small, expand based on query needs
- _(Proposed by: Perplexity)_

**B. Maximal common (normalize aggressively)**
- common: all queryable fields (input, output, exit_code, files_touched, etc.)
- details: only truly unique tool data
- More normalization work, more query power
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — Minimal common**
- Start with Perplexity's minimal set
- Expand common fields when specific query needs emerge
- Avoids premature normalization

**Sub-questions:**
- Should `files_touched` be in common? (Proposed: Yes if available, for risk detection)
- How to handle tools that don't fit schema? (Proposed: Store entire payload in details)

---

### Q8: Payload Structure — CoT/Thinking Block Availability

**Question:** Does Claude Code JSONL format consistently expose `<thinking>...</thinking>` blocks, or are they sometimes suppressed?

**Why it matters:** Determines whether reasoning can be reliably extracted or should be optional.

**Options identified by providers:**

**A. Always available**
- Make `payload.common.reasoning` required
- Classification can depend on reasoning
- _(Unknown)_

**B. Sometimes suppressed**
- Make `payload.common.reasoning` optional
- Empty string if unavailable
- Classification cannot depend on reasoning
- _(Proposed by: Gemini as uncertainty)_

**Synthesis recommendation:** ⚠️ **Need to inspect actual JSONL samples**
- Check real Claude Code JSONL output
- If always available → required field
- If sometimes suppressed → optional field with empty string default

**Sub-questions:**
- What if reasoning is extremely long (>10KB)? (Proposed: Store full text, add summary if needed)

---

### Q9: Classification Labels — Multiple Primary Candidates

**Question:** When an event could receive multiple valid primary labels, how should the system choose?

**Why it matters:** Affects classification consistency and policy learning signal quality.

**Options identified by providers:**

**A. Highest confidence wins**
- Calculate confidence for each label
- Assign primary = highest confidence
- Store alternatives as metadata
- _(Proposed by: Perplexity via confidence scoring)_

**B. Manual disambiguation rules**
- Define precedence hierarchy (e.g., O_CORR > O_DIR)
- Apply rules to pick one
- Deterministic but may be arbitrary
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — Highest confidence**
- Use Perplexity's confidence scoring framework
- Primary label = highest confidence
- Store alternative labels + scores in metadata for review

**Sub-questions:**
- What if confidence scores are tied? (Proposed: Use precedence as tiebreaker)

---

## Tier 2: Important Decisions (⚠️ Recommended)

### Q10: Risk Model — False Positive Tolerance

**Question:** Should false positives (detecting "secrets.yaml" in a print statement as T_RISKY) be tolerated for Phase 1?

**Why it matters:** Affects risk detection aggressiveness and manual review burden.

**Options identified by providers:**

**A. Tolerate false positives (Gemini's proposal)**
- Aggressive detection is better than missing risks
- Phase 1 can handle manual review
- Simple regex matching on payload string
- _(Proposed by: Gemini)_

**B. Minimize false positives**
- Parse command arguments to find actual file accesses
- More complex, more accurate
- _(Not proposed for Phase 1)_

**Synthesis recommendation:** ✅ **Option A — Tolerate false positives**
- Aggressive is safer for Phase 1
- Mark false positives during manual validation
- Refine detection rules based on real data

**Sub-questions:**
- What false positive rate is acceptable? (Proposed: <20% for Phase 1)

---

### Q11: Risk Model — Risk Factor Combination

**Question:** How should multiple risk factors combine to produce overall risk score?

**Why it matters:** Affects risk assessment sensitivity and T_RISKY classification threshold.

**Options identified by providers:**

**A. Max (highest risk factor wins)**
- Single severe risk triggers high score
- Conservative, favors safety
- _(Proposed by: Perplexity for classification)_

**B. Weighted average**
- Multiple small risks combine
- More nuanced scoring
- _(Proposed by: Perplexity for scoring)_

**C. Sum (additive)**
- All risks accumulate
- Can exceed 1.0 (requires normalization)
- _(Not proposed)_

**Synthesis recommendation:** ✅ **A for classification, B for scoring**
- Use max for binary T_RISKY classification (any factor ≥0.7 → risky)
- Use weighted average for continuous risk_score (0.0 to 1.0)
- This balances safety with nuance

**Sub-questions:**
- What weights should risk factors have? (Proposed: Start equal, adjust based on data)

---

### Q12: Risk Model — T_RISKY Threshold

**Question:** What risk_score threshold should trigger T_RISKY classification?

**Why it matters:** Too low = many false positives; too high = miss real risks.

**Options identified by providers:**

**A. 0.7 (proposed)**
- Moderately conservative
- Room for multiple weighted factors
- _(Proposed by: synthesis)_

**B. 0.5 (balanced)**
- More sensitive, catches more risks
- Higher false positive rate
- _(Not proposed)_

**C. 0.9 (strict)**
- Very conservative
- Only highest-confidence risks
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — 0.7 threshold**
- Start with 0.7 as reasonable balance
- Make configurable for experimentation
- Adjust based on false positive rate in real data

**Sub-questions:**
- Should threshold vary by risk factor type? (Proposed: No for Phase 1, single threshold)

---

### Q13: Deduplication — Ingestion Metadata Tracking

**Question:** Should we track ingestion metadata (first_seen, last_seen timestamps) for debugging?

**Why it matters:** Helps diagnose re-ingestion issues and data lineage.

**Options identified by providers:**

**A. Yes, track metadata**
- first_seen, last_seen, ingestion_count
- Useful for debugging
- Small storage cost
- _(Proposed by: synthesis)_

**B. No, skip metadata**
- Simpler schema
- Idempotency is enough
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — Track metadata**
- Low cost, high debugging value
- Add first_seen, last_seen, ingestion_count to event metadata

**Sub-questions:**
- Should we expose ingestion metadata in queries? (Proposed: Yes, for diagnostics)

---

### Q14: Deduplication — Legitimately Repeated Actions

**Question:** How to handle events that are legitimately repeated (same action run twice intentionally)?

**Why it matters:** Different turn_id should make different event_id, but want to ensure this works as expected.

**Options identified by providers:**

**A. Different turn_id → different event_id**
- Same action at different turns = distinct events
- Deterministic hash includes turn_id
- _(Proposed by: Perplexity)_

**Synthesis recommendation:** ✅ **Option A**
- Confirm this is how session_id + turn_id works
- Test with sample data to verify

**Sub-questions:**
- What if turn_id is missing from logs? (Proposed: Use sequence number or timestamp as fallback)

---

### Q15: Deduplication — Log Duplicate Detection

**Question:** Should we log when duplicate events are detected and ignored?

**Why it matters:** Helps monitor data quality and detect re-ingestion issues.

**Options identified by providers:**

**A. Yes, log at debug level**
- Track duplicate detections
- Monitor for unexpected patterns
- _(Proposed by: synthesis)_

**B. No, silently ignore**
- Simpler, less log noise
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — Log at debug level**
- Low cost, helps debugging
- Can detect if same session is being re-ingested repeatedly

**Sub-questions:**
- Should we alert if duplicate rate exceeds threshold? (Proposed: Yes, if >5% duplicates)

---

### Q16: Error Handling — Invalid Event Abort Threshold

**Question:** What percentage of invalid events should trigger aborting extraction vs continuing with degraded data?

**Why it matters:** Balances robustness (continue with partial data) vs quality (abort if too corrupt).

**Options identified by providers:**

**A. Abort if >10% invalid**
- Catch severe data quality issues early
- Prevent training on garbage data
- _(Proposed by: synthesis)_

**B. Never abort, always log**
- Maximum robustness
- Risk of poor quality training data
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — Abort at 10% threshold**
- Calculate invalid_rate = invalid_events / total_events
- If >10%, abort with detailed error report
- Make threshold configurable

**Sub-questions:**
- What counts as "invalid"? (Proposed: Failed schema validation, missing required fields)
- Should we abort per-session or per-batch? (Proposed: Per-session, continue to next session)

---

### Q17: Error Handling — Validation Strictness Configuration

**Question:** Should users be able to configure validation strictness (strict vs permissive)?

**Why it matters:** Development/testing needs flexibility; production needs quality assurance.

**Options identified by providers:**

**A. Yes, configurable strictness**
- strict mode (reject on warning, production)
- permissive mode (log warnings, development)
- _(Proposed by: Perplexity)_

**B. No, always strict**
- Simpler, less configuration
- Forces quality early
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — Configurable strictness**
- strict mode for production (default)
- permissive mode for development/testing
- Configure in config.yaml

**Sub-questions:**
- Should strictness apply to all validation layers or be granular? (Proposed: Single global setting for Phase 1)

---

### Q18: Error Handling — Temporal Anomaly Handling

**Question:** How to handle temporal anomalies (out-of-order events, duplicate timestamps, clock skew)?

**Why it matters:** Affects event ordering reliability and causal inference accuracy.

**Options identified by providers:**

**A. Tolerate + flag (Perplexity's proposal)**
- Accept out-of-order events
- Add microsecond noise for duplicate timestamps (deterministic, based on content hash)
- Use explicit links instead of timestamp order for causal inference
- Log anomalies for review
- _(Proposed by: Perplexity)_

**B. Correct timestamps**
- Detect clock skew and adjust
- Force chronological ordering
- Risk: introducing errors
- _(Perplexity mentions as option)_

**Synthesis recommendation:** ✅ **Option A — Tolerate + flag + explicit links**
- Don't assume timestamp order is correct
- Use causal links (commit ID, tool call ID) when available
- Log temporal anomalies at warning level
- Add microsecond noise deterministically for duplicates

**Sub-questions:**
- Should we compute median timestamp offset between systems? (Proposed: Yes for reporting, not for correction)

---

## Tier 3: Polish Decisions (🔍 Can Defer)

### Q19: CoT/Thinking — Use in Classification Rules

**Question:** Should reasoning content (from `<thinking>` blocks) be used in classification rules, or only stored for future analysis?

**Why it matters:** Affects classification complexity and whether reasoning is a first-class signal.

**Options identified by providers:**

**A. No, store but don't use for Phase 1**
- Simpler classification rules
- Reasoning available for future enhancement
- _(Proposed by: Gemini)_

**B. Yes, use for classification**
- Richer signal (reasoning reveals intent)
- More complex rules
- _(Not proposed for Phase 1)_

**Synthesis recommendation:** ✅ **Option A — Store, don't use for Phase 1**
- Keep classification rules simple
- Reasoning available for manual validation and future work

**Sub-questions:**
- Should we provide reasoning to human validators? (Proposed: Yes, helps manual labeling)

---

### Q20: CoT/Thinking — Handling Extremely Long Reasoning

**Question:** What if reasoning text is extremely long (>10KB)? Should we summarize or truncate?

**Why it matters:** Storage size and query performance.

**Options identified by providers:**

**A. Store full text, add summary field if needed**
- Preserve complete information
- Add summary later if query performance issues
- _(Proposed by: synthesis)_

**B. Truncate to 10KB**
- Fixed size limit
- Risk: losing important information
- _(Not proposed)_

**Synthesis recommendation:** ✅ **Option A — Store full text**
- DuckDB handles large text efficiently
- Don't truncate unless performance issues emerge

**Sub-questions:**
- What's the 95th percentile reasoning length in real data? (Proposed: Measure and decide based on data)

---

### Q21: Configuration — Overlays and Profiles

**Question:** Should configuration support "overlays" or "profiles" for experimentation (e.g., strict vs lenient, minimal vs maximal episodes)?

**Why it matters:** Enables A/B testing different extraction strategies without duplicating config files.

**Options identified by providers:**

**A. Yes, support config overlays**
- Base config + overlay for variants
- Easier experimentation
- More complex implementation
- _(Proposed by: Perplexity)_

**B. No, use separate config files**
- Simpler implementation
- Copy-paste to experiment
- _(Not proposed, but simpler)_

**Synthesis recommendation:** ⚠️ **Defer to Phase 1 implementation**
- Start with single config file
- Add overlays if experimentation shows clear need
- Not blocking for initial extraction

**Sub-questions:**
- How would overlay inheritance work? (Proposed: JSON merge with override semantics)

---

## Next Steps (Non-YOLO Mode)

**✋ PAUSED — Awaiting Your Decisions**

1. **Review these 21 questions** organized into 3 tiers
2. **Provide answers** — You can:
   - Create CLARIFICATIONS-ANSWERED.md manually
   - Tell Claude your decisions in conversation
   - Choose synthesis recommendations (most marked ✅)
3. **Then run:** `/gsd:plan-phase 1` to create execution plan

---

## Alternative: YOLO Mode

If you want Claude to auto-generate reasonable answers:

```bash
/meta-gsd:discuss-phase-ai 1 --yolo
```

This will:
- Auto-select recommended options (marked ✅ ⚠️ above)
- Generate CLARIFICATIONS-ANSWERED.md automatically
- Proceed to planning without pause

---

*Multi-provider synthesis: Gemini Pro + Perplexity Sonar Deep Research (with 60+ industry citations)*
*Generated: 2026-02-10*
*Non-YOLO mode: Human input required*
