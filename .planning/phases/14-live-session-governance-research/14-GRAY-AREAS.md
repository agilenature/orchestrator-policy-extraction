# Gray Areas Synthesis — Phase 14: Live Session Governance Research

**Generated:** 2026-02-23
**Source:** Multi-provider AI analysis (Gemini Pro 2.5, Perplexity Sonar Deep Research)
**Note:** Existing `14-CONTEXT.md` is the architectural design brief (Binswanger framework). This file is the gray areas synthesis for pre-planning clarification.

**Confidence markers:**
- ✅ **Consensus** — Both providers identified this as critical
- ⚠️ **Recommended** — One provider focused on it with strong rationale
- 🔍 **Needs Clarification** — Identified with uncertainty

---

## Gray Areas Identified

---

### ✅ 1. Transport Definitiveness in 14-04 (Consensus)

**What needs to be decided:**
Plans 14-01/14-02 commit to Unix socket + uvicorn/starlette. But 14-04's stated scope includes "evaluate bus transport options (local HTTP vs NATS vs Redis Streams vs Mattermost)." Does 14-04 genuinely re-open the transport question, or is it a validation spike for a decision already made?

**Why it's ambiguous or risky:**
If 14-04 treats NATS/Redis as live candidates, it risks architectural creep that delays Phase 15 implementation. If it treats them as foreclosed, it misses the spike's purpose. Mattermost is conceptually misclassified — it's a notification sink (audit trail), not a transport layer.

**Provider synthesis:**
- **Gemini:** "Strict adherence to UDS. 14-04 should only validate uvicorn on Unix Domain Socket. Reject NATS/Redis explicitly. Reclassify Mattermost as integration endpoint for alerts, not the bus itself."
- **Perplexity:** "Recommend local HTTP bus (FastAPI + Unix socket + SQLite). NATS is Phase 15+ once cross-host governance is needed. Mattermost as future audit trail. Quantitative spike criteria: p99 latency < 50ms, throughput > 100 signals/sec."

**Proposed implementation decision:**
14-04's transport spike has a predetermined answer (Unix socket + starlette, already installed, already designed). The spike's value is **validation, not selection**. The spike criteria should be: (1) confirm p99 constraint check latency < 50ms under 5 concurrent sessions, (2) confirm OPE pipeline processes worker JSONL files correctly as post-task memory layer. NATS/Redis are future evolution paths for cross-host coordination in Phase 15+. Mattermost is Phase 16 audit trail only.

**Open questions:**
- Should 14-04 include a NATS shadow deployment for A/B comparison, or explicitly rule it out?
- What quantitative latency gate determines "spike passed"?

---

### ✅ 2. DDF Co-Pilot Output Channel (Consensus)

**What needs to be decided:**
When the governing daemon detects an O_AXS, Fringe, or Affect Spike signal, how does the intervention actually reach the user? The daemon is a background Python process; Claude Code sessions have their own TUI. Direct stdout from daemon = TUI corruption.

**Why it's ambiguous or risky:**
This is a blocking architectural question for LIVE-06. The design specifies three co-pilot intervention types with prompts ("What just clicked for you?") but does not specify the delivery mechanism. If the channel isn't defined, Phase 15 implementation has no path to complete LIVE-06.

**Provider synthesis:**
- **Gemini:** "The daemon cannot write to stdout directly. It must pass the message back to the PreToolUse or SessionStart hook via the Unix socket. The hook (running in Claude process) then prints the message. Verify from Phase 14.1 PAG hook experience whether Claude Code renders hook stdout as 'Tool Output' or strips it."
- **Perplexity:** "Memory_candidates write is the terminal output — the intervention writes to disk immediately (load-bearing). The 'prompt' to the user is secondary; some interventions may write to memory_candidates silently with the prompt optional or delivered next-session."

**Proposed implementation decision:**
Two-tier delivery: (a) **Write-on-detect to memory_candidates.jsonl is mandatory and synchronous** — this is the load-bearing terminal output per 14-CONTEXT.md deposit-not-detect principle. (b) **User-visible prompt is optional scaffolding** — if Claude Code hook stdout renders (as shown by PAG hook), use it; if not, queue the prompt for next SessionStart briefing. The spike in 14-04 must test: does writing to stdout in a PreToolUse/PostToolUse hook render visibly in the Claude Code TUI?

**Open questions:**
- Does PostToolUse hook stdout render in the Claude Code UI? (PAG hook uses PreToolUse — PostToolUse behavior may differ)
- If hook stdout is suppressed, is queuing prompts for next SessionStart acceptable for all three intervention types?

---

### ✅ 3. Real-Time vs. Post-Task OPE Split (Consensus)

**What needs to be decided:**
The DDF co-pilot must run "in real-time" (LIVE-06). The OPE pipeline (`python -m src.pipeline.cli extract`) is designed for batch processing. 14-04 validates "OPE pipeline as post-task memory layer." These are two different things — but the design conflates them as LIVE-06 requirements.

**Why it's ambiguous or risky:**
If "real-time DDF" requires the full OPE pipeline to run synchronously, it will exceed the 200ms PreToolUse budget by orders of magnitude. The co-pilot design must explicitly define which components run in real-time and which run post-task.

**Provider synthesis:**
- **Gemini:** "Split the architecture: Fast Path (DDF co-pilot, regex/keyword heuristics, <1ms) runs in daemon in real-time for write-on-detect. Slow Path (full OPE pipeline) runs post-session at CONFIRMED_END. 'Real-time' requirement applies only to flagging candidates, not generating consolidated memory."
- **Perplexity:** "Real-time DDF uses lightweight heuristic engine without LLM calls. Post-task OPE pipeline processes JSONL file after session completion, generating higher-fidelity wisdom. Both write to memory_candidates but the post-task pass can enrich real-time entries."

**Proposed implementation decision:**
The split is: (a) **Real-time DDF co-pilot** = LiveEventAdapter + keyword/regex heuristic detectors + immediate write-on-detect to memory_candidates.jsonl. No LLM calls. No full OPE pipeline. (b) **Post-task OPE pipeline** = triggered by CONFIRMED_END (session close), processes full JSONL file with EpisodePopulator + ConstraintExtractor + AmnesiaDete ctor. Writes richer entries to DuckDB. Both are distinct consumers of the same JSONL files.

**Open questions:**
- Should the real-time DDF co-pilot use only regex/keywords, or can it use a local embedding model (no network calls)?
- After post-task OPE completes, should it update/enrich the real-time memory_candidates entries or append separately?

---

### ✅ 4. TENTATIVE_END/CONFIRMED_END Timeout Sensitivity (Consensus)

**What needs to be decided:**
The 30-minute TTL in the stream processor's episode boundary state machine is a global constant. Real Claude Code sessions vary dramatically: pause-and-reflect (45+ second gaps), rapid-iteration (10 events/second bursts), long-wait (builds/API calls, minutes of silence).

**Why it's ambiguous or risky:**
- A fixed 30-minute TTL means the stream processor holds open state for 30 minutes after a session goes quiet mid-episode. This delays memory_candidates writes from episode_level signals (amnesia detection) and creates large memory footprint.
- A short TTL creates false CONFIRMED_END signals during pause-and-reflect sessions, splitting single logical episodes into fragments.

**Provider synthesis:**
- **Gemini:** "Validate whether Claude Code flushes JSONL after every message or batches. This determines actual read latency, not just the 200ms target."
- **Perplexity:** "Implement dynamic per-session timeout: baseline = 90th percentile of inter-event duration for first 5 minutes. Set timeout = 2× baseline. Update every 20 minutes. Add burst mode: suppress TENTATIVE_END during tool bursts (10+ events in 2 seconds). Add minimum floor of 5 seconds to prevent pathological cases."

**Proposed implementation decision:**
For Phase 14 design spike: use fixed 30-minute TTL with configurable override. For Phase 15 implementation: implement dynamic timeout learning (90th percentile baseline × 2). Add burst mode detection. Document the fixed TTL as a known limitation of Wave 1 implementation, with dynamic learning as a Wave 2 enhancement.

**Open questions:**
- Should the CONFIRMED_END TTL be per-project-type configurable (e.g., shorter for rapid-iteration projects)?
- Is burst mode detection needed in Phase 14 design, or deferred to Phase 15?

---

### ⚠️ 5. Phase 15 Wave Sequencing: Deposit vs. Instrumentation (Recommended)

**What needs to be decided:**
Plan 14-05 produces the Phase 15+16 implementation blueprint. The deposit-not-detect principle from 14-CONTEXT.md requires that write-on-detect (terminal) precedes TransportEfficiency metrics (instrumental). But the Phase 15 description currently lists IntelligenceProfile alongside flame_events in the same phase without clear wave ordering.

**Why it's important:**
If Phase 15 Wave 1 builds IntelligenceProfile CLI (scaffolding) before write-on-detect is operational, the instrument has nothing to measure and the load-bearing output is delayed.

**Provider synthesis:**
- **Perplexity:** "Phase 15 wave structure: Wave 1 = DDF detectors + flame_events table + write-on-detect deposit. Wave 2 = ai_flame_events + confidence scoring. Wave 3 = memory_candidates deposit (TERMINAL). Wave 4 = baseline calibration. Wave 16.1 = TransportEfficiency (INSTRUMENTAL)."

**Proposed implementation decision:**
14-05 must enforce in its wave breakdown: **Wave 1 = flame_events table + minimal detector stubs + write-on-detect path to memory_candidates.jsonl (load-bearing, must complete before any other wave)**. IntelligenceProfile CLI = Wave 3 or later (scaffolding, deferrable). This maps directly to deposit-not-detect governing axis.

**Open questions:**
- Does Phase 15 write-on-detect to memory_candidates.jsonl happen before or after the Phase 16 MEMORY.md review CLI is built?
- Should Phase 15 Wave 1 include a mock memory_candidates writer (so Phase 16 can be designed independently)?

---

### ⚠️ 6. memory_candidates Deduplication (Recommended)

**What needs to be decided:**
Both real-time DDF co-pilot and post-task OPE pipeline write to memory_candidates. They process the same session's events at different times and with different fidelity. Without a deduplication strategy, the same conceptual insight gets multiple entries.

**Why it's important:**
The MEMORY.md review CLI (Phase 16) will surface memory_candidates for human review. Duplicate entries pollute the review queue and inflate the apparent richness of the session's conceptual output.

**Provider synthesis:**
- **Perplexity:** "Content-hash keying: hash(ccd_axis + scope_rule + session_id + confidence_rounded_to_2_decimals). Only accept entries with new hashes. Maintain processed_sessions registry to prevent re-processing. DuckDB upsert pattern already used elsewhere in OPE — apply here."

**Proposed implementation decision:**
Use the existing OPE upsert pattern (INSERT OR IGNORE / ON CONFLICT DO NOTHING). Dedup key = SHA-256(ccd_axis + scope_rule + session_id). Post-task OPE pipeline can UPDATE existing entries with higher-fidelity data (e.g., richer flood_example) but not INSERT duplicates.

**Open questions:**
- Should the post-task OPE pipeline enrich real-time entries in place (UPDATE), or append separately and let the review CLI surface both?
- Is there a case where two legitimately different entries should share the same ccd_axis + scope_rule + session_id (different subject/origin)?

---

### ⚠️ 7. Bus State Persistence After Daemon Restart (Recommended)

**What needs to be decided:**
The governing daemon holds in-memory state: constraint cache, session registry, signal ring buffer. If the daemon restarts (crash, OS reboot), this state is lost. Sessions will re-register on their next hook call, but there's a window of governance opacity.

**Why it's important:**
The design brief (14-02-PLAN.md) says "Recovery after restart: on startup, the governor reloads constraints from data/constraints.json, rebuilds the checker, and starts fresh." This is correct for the constraint cache, but doesn't address whether in-progress governance decisions (pending broadcasts, buffered episode_level signals) survive restarts.

**Provider synthesis:**
- **Gemini:** "DuckDB as Hot State: the Blueprint must specify that shared state is not just Python memory, but backed by DuckDB so it survives daemon restarts. Bootstrapping: daemon on startup loads constraints from data/constraints.json into active memory/DB."
- **Perplexity:** "Governing daemon's in-memory state is ephemeral. Restart clears it. DuckDB-persisted decisions survive restart. Design as acceptable limitation for solo developer workflow — document it."

**Proposed implementation decision:**
Accept ephemeral in-memory state as an explicit design choice. Document that daemon restart causes a governance blind spot until sessions re-register (typically within 1 hook call, < 60 seconds). Persist governance decisions (blocks, broadcasts) to DuckDB's governance_signals table for audit trail. This is already in 14-02's design; needs explicit callout in 14-05 blueprint.

**Open questions:**
- Are there governance signals (e.g., active blocks broadcast to sessions) that MUST survive daemon restart? If yes, buffer them to DuckDB before acknowledgment.

---

### 🔍 8. 14-04 Spike Scope vs. 14-03 Spike Overlap (Needs Clarification)

**What needs to be decided:**
Plan 14-03 is "executive spike: real-time DDF detection on UserPromptSubmit hook." Plan 14-04 is "OpenClaw bus spike: inter-session bus selection + OPE pipeline as post-task memory layer." These are described as Wave 2, parallel plans. But both touch DDF detection — one from the hook side (14-03), one from the bus/pipeline side (14-04). Are these actually independent spikes or do they share test infrastructure?

**Why it's ambiguous:**
If the spikes require the same test infrastructure (Claude Code sessions running, JSONL files, bus operational), they may need to be partially sequential (bus up before per-prompt detection test can run through it).

**Proposed implementation decision:**
Treat them as **parallel Wave 2 spikes with a shared prerequisite**: bus must be operational before either spike runs. 14-03 tests per-prompt detection latency (hook-level). 14-04 tests full-session batch context richness (pipeline-level). Both write results to a shared `14-SPIKE-RESULTS.md` that 14-05 synthesizes.

**Open questions:**
- Does 14-03 (executive spike) require the bus to be running, or does it test standalone hook behavior?
- Should 14-04 be renamed "Pipeline + Bus Integration Spike" to clarify its scope vs. 14-03?

---

## Decision Checklist for 14-04 and 14-05 Planning

### Tier 1 (Blocking — must resolve before writing 14-04/14-05):
- [ ] Transport definitiveness: is 14-04 a validation spike or a selection spike?
- [ ] DDF output channel: how does daemon intervention reach the user?
- [ ] Real-time vs post-task OPE split: which components run in which path?

### Tier 2 (Important — should resolve for quality):
- [ ] CONFIRMED_END timeout strategy: fixed vs. dynamic for Phase 14 design?
- [ ] Phase 15 wave ordering: deposit first, then instrumentation?
- [ ] memory_candidates deduplication: strategy for real-time + post-task overlap?

### Tier 3 (Polish — can defer to implementation):
- [ ] Bus state persistence: which signals must survive daemon restart?
- [ ] 14-03/14-04 spike independence: shared test infrastructure or truly parallel?
- [ ] Mattermost classification: confirm it's Phase 16 audit trail, not transport

---

*Multi-provider synthesis: Gemini Pro 2.5, Perplexity Sonar Deep Research*
*Generated: 2026-02-23*
