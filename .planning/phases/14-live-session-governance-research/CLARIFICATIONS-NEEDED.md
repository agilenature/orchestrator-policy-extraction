# CLARIFICATIONS-NEEDED.md

## Phase 14: Live Session Governance Research — Decisions Required for 14-04 and 14-05

**Generated:** 2026-02-23
**Mode:** Multi-provider synthesis (Gemini Pro 2.5, Perplexity Sonar Deep Research)
**Context:** Plans 14-01 through 14-03 are fully designed (hook contracts, stream processor, bus, governing session, DDF co-pilot architecture). These questions apply to the remaining two plans: 14-04 (OpenClaw bus spike) and 14-05 (Phase 15+16 blueprint).

---

## Decision Summary

**Total questions:** 8
**Tier 1 (Blocking):** 3 — must answer before writing 14-04/14-05
**Tier 2 (Important):** 3 — should answer for quality
**Tier 3 (Polish):** 2 — can defer to implementation

---

## Tier 1: Blocking Decisions

### Q1: Is 14-04 a validation spike or a selection spike?

**Question:** Plan 14-04's stated scope includes "evaluating bus transport options (local HTTP vs NATS vs Redis Streams vs Mattermost)." But Plans 14-01/14-02 already commit to Unix socket + uvicorn/starlette. Does 14-04 re-open the transport choice, or does it validate an already-made decision?

**Why it matters:** If 14-04 treats NATS/Redis as live candidates, the spike design must include parallel implementations to compare — adding significant scope. If it's a validation spike for the already-selected Unix socket bus, the scope is: (a) confirm p99 latency < 50ms under real sessions, (b) confirm OPE pipeline processes worker JSONL files correctly. These are very different plans.

**Options:**

**A. Validation spike (transport is locked)**
- 14-04 validates Unix socket bus works end-to-end with real Claude Code sessions
- Spike criteria: latency, throughput, OPE pipeline integration
- NATS/Redis documented as Phase 15+ evolution for cross-host governance
- Mattermost documented as Phase 16 audit trail (not transport)
- *(Proposed by: Gemini, Perplexity)*

**B. Selection spike (transport still open)**
- 14-04 implements a thin HTTP prototype and optionally NATS alongside
- Spike criteria includes transport comparison
- Delays 14-04 scope significantly

**Synthesis recommendation:** ✅ **Option A — Validation spike**
- Plans 14-01/14-02 made binding transport decisions with full rationale
- uvicorn+starlette already installed; re-opening would be unactionable churn
- NATS is a Phase 15 migration path when cross-host governance is needed, not a Phase 14 question

**Sub-questions:**
- What quantitative latency gate defines "spike passed"? (Suggest: p99 < 50ms for constraint check round-trip, throughput > 100 signals/sec, memory < 10MB under 5 concurrent sessions)

---

### Q2: How does the DDF co-pilot intervention reach the user?

**Question:** When the governing daemon detects an O_AXS, Fringe, or Affect Spike signal, how does the intervention actually reach the user? Three options: (a) hook stdout injection, (b) next-SessionStart briefing, (c) silent write-only (memory_candidates is the terminal output, no immediate prompt).

**Why it matters:** This is the only unresolved delivery mechanism in LIVE-06. The three co-pilot intervention types are designed, the memory_candidates write is designed — but the user-visible prompt channel isn't locked. Phase 15 Wave 1 implementers will block on this.

**Options:**

**A. Hook stdout injection**
- Daemon queues the intervention prompt to bus
- Next PreToolUse or PostToolUse hook call reads the queue and prints to stdout
- Claude Code renders hook stdout as "Tool Output" block (verified by PAG hook in Phase 14.1)
- User sees prompt in real-time during session
- *(Proposed by: Gemini)*

**B. Next-SessionStart briefing**
- Daemon writes detected insight to a `pending_interventions.jsonl` file
- Next SessionStart hook reads it and includes it in the briefing
- Not real-time (next session), but zero risk of TUI corruption
- Suitable for O_AXS/Fringe/Affect Spike that don't need immediate response

**C. Silent write-only (load-bearing is the deposit, prompt is scaffolding)**
- memory_candidates write is the terminal output per deposit-not-detect principle
- User-visible prompt is optional scaffolding — implement if hook stdout renders, skip if not
- Defer the prompt delivery mechanism decision to Phase 15 implementation
- *(Proposed by: Perplexity synthesis)*

**Synthesis recommendation:** ✅ **Option C — Silent write-only for Phase 14 design, with hook stdout as Phase 15 enhancement**
- Rationale: deposit-not-detect governing axis from 14-CONTEXT.md. The write-on-detect to memory_candidates is the terminal output. The user-visible prompt is instrumental scaffolding.
- Phase 14 design must specify the write path. Phase 15 implementation decides whether to add hook stdout delivery based on PAG hook experience.
- Spike item for 14-04: explicitly test whether PostToolUse hook stdout renders in Claude Code TUI.

**Sub-questions:**
- If hook stdout renders (confirmed by spike), should all three intervention types use it, or only O_AXS (the highest-signal intervention)?
- Should the memory_candidates entry include a `user_notified: bool` field to track whether the user saw the prompt?

---

### Q3: Which components run real-time vs. post-task in the DDF co-pilot architecture?

**Question:** LIVE-06 requires real-time DDF detection. The OPE pipeline is batch. These must be cleanly separated so Phase 15 implementers know which detectors belong to which path.

**Why it matters:** If this split isn't documented in 14-05, Phase 15 implementation may accidentally try to run EpisodePopulator or ConstraintExtractor in the hook path, which will exceed all latency budgets.

**Options:**

**A. Strict real-time/post-task split**
- Real-time path: LiveEventAdapter + keyword/regex heuristic detectors + write-on-detect to memory_candidates.jsonl. No LLM calls. No EpisodePopulator. Budget: < 5ms per event.
- Post-task path: full OPE pipeline (`src.pipeline.cli extract`) triggered at CONFIRMED_END. Produces DuckDB episodes, constraints, amnesia events. May also enrich memory_candidates entries.
- *(Proposed by: Gemini, Perplexity)*

**B. Unified path (real-time runs full OPE in background thread)**
- Stream processor spawns a background thread running the full pipeline per event
- Slower, but single code path
- Risk: blocks memory_candidates write if pipeline takes > 200ms

**C. Two-pass real-time + enrichment**
- Real-time: write-on-detect with low-confidence placeholder entries
- Post-task: update entries with higher-fidelity data (richer flood_example, better confidence score)

**Synthesis recommendation:** ✅ **Option A — Strict split, with Option C as a Phase 16 enhancement**
- Real-time heuristic detectors (keyword/regex/simple pattern matching) are the LIVE-06 implementation.
- Post-task full OPE pipeline is the memory layer validation from 14-04 scope.
- Phase 16 can add "enrichment pass" that updates real-time entries with post-task analysis.

**Sub-questions:**
- Should the real-time DDF detectors use pre-compiled regex only, or can they use a local embedding model (no network, no LLM) for higher fidelity?
- Who triggers the post-task OPE run — the governing daemon on CONFIRMED_END, or a manual CLI command?

---

## Tier 2: Important Decisions

### Q4: Fixed or dynamic CONFIRMED_END timeout for Phase 14 design?

**Question:** The stream processor's episode boundary state machine uses a 30-minute TTL. Should the 14-04 spike test dynamic timeout learning, or lock the fixed TTL as a Phase 14 constant?

**Options:**

**A. Fixed 30-minute TTL for Phase 14, dynamic in Phase 15**
- Simpler spike design; dynamic learning is a Phase 15 enhancement
- Document known limitation: pause-and-reflect sessions may hold state longer than necessary
- *(Suggested by Gemini)*

**B. Dynamic timeout in Phase 14 spike**
- Baseline = 90th percentile of inter-event duration for first 5 minutes
- Timeout = 2× baseline, updated every 20 minutes
- Add burst mode: suppress TENTATIVE_END during tool bursts (10+ events/2 seconds)
- *(Proposed by Perplexity)*

**Synthesis recommendation:** ⚠️ **Option A — Fixed TTL for Phase 14 design, with configurable override in Phase 15**

**Sub-questions:**
- Should the fixed TTL be 30 minutes (current) or a shorter value given that the PAG hook experience shows sessions often end within 1-2 hours?

---

### Q5: What does the Phase 15 wave ordering look like for deposit-first?

**Question:** Plan 14-05 must produce the Phase 15+16 blueprint. The deposit-not-detect governing axis requires that write-on-detect to memory_candidates precede TransportEfficiency metrics. Should 14-05 explicitly enforce this wave ordering?

**Options:**

**A. 14-05 encodes the deposit-first wave ordering explicitly**
- Wave 1: flame_events schema + heuristic detectors + write-on-detect to memory_candidates.jsonl (load-bearing)
- Wave 2: ai_flame_events + IntelligenceProfile (scaffolding, deferrable)
- Wave 3: Phase 16 TransportEfficiency (instrumental, cannot precede deposit)
- *(Proposed by Perplexity, aligned with 14-CONTEXT.md)*

**B. 14-05 describes capabilities, leaves wave ordering to Phase 15 planner**
- More flexible but risks planner missing the deposit-first constraint

**Synthesis recommendation:** ✅ **Option A — Encode ordering as a must-have constraint in 14-05**

---

### Q6: memory_candidates deduplication strategy when real-time DDF and post-task OPE overlap?

**Question:** Both paths may generate memory_candidates entries for the same session and same CCD axis. What's the dedup strategy?

**Options:**

**A. Hash-based insert-once dedup**
- Dedup key = SHA-256(ccd_axis + scope_rule + session_id)
- ON CONFLICT DO NOTHING (DuckDB syntax, matches existing OPE pattern)
- Post-task OPE cannot overwrite real-time entries

**B. Last-write-wins with fidelity tracking**
- Each entry carries a `fidelity: int` field (1=real-time heuristic, 2=post-task OPE)
- Post-task OPE can UPDATE existing entries when it has higher fidelity
- Both `session_id` and `origin` field distinguish sources

**C. Separate tables (real-time vs post-task)**
- Real-time writes to `memory_candidates_realtime`, post-task writes to `memory_candidates_batch`
- Review CLI surfaces both; human decides which to accept

**Synthesis recommendation:** ✅ **Option B — Last-write-wins with fidelity tracking**
- Aligns with existing OPE upsert pattern
- Preserves the real-time entry's ground_truth_pointer while allowing post-task enrichment

---

## Tier 3: Polish Decisions

### Q7: Should 14-04 and 14-03 share a test harness?

**Question:** Both spikes run in Wave 2 (parallel). 14-03 tests per-prompt DDF detection via UserPromptSubmit hook. 14-04 tests full-session batch DDF signal density + bus integration. Do they share infrastructure?

**Recommendation:** ⚠️ **Shared prerequisite only** — both require the bus to be running. Otherwise independent. Both write spike results to a shared `14-SPIKE-RESULTS.md` that 14-05 synthesizes.

---

### Q8: What governance signals must survive daemon restart?

**Question:** If the governing daemon crashes mid-session, which in-flight signals must be preserved vs. accepted as lost?

**Recommendation:** ⚠️ **Accept ephemeral state as Phase 14 limitation.** Governance decisions (blocks, broadcasts) written to DuckDB governance_signals table before acknowledgment survive restart. Pending broadcasts that haven't been acknowledged are lost — acceptable for solo developer workflow. Document as known limitation.

---

## Next Steps

1. **Review questions Q1, Q2, Q3** (Tier 1 — blocking) before writing 14-04 and 14-05 plan files
2. **Create CLARIFICATIONS-ANSWERED.md** with your decisions
3. **Then run:** `/gsd:plan-phase 14` or `/gsd:execute-phase 14` to create/execute plans 14-04 and 14-05

---

*Multi-provider synthesis: Gemini Pro 2.5, Perplexity Sonar Deep Research*
*Generated: 2026-02-23*
*Non-YOLO mode: Human decisions required for Q1, Q2, Q3 before planning*
