# CLARIFICATIONS-ANSWERED.md

## Phase 14: Live Session Governance Research — Decisions for 14-04 and 14-05

**Generated:** 2026-02-23
**Mode:** YOLO (balanced strategy — synthesis recommendations auto-selected)
**Source:** Auto-generated from CLARIFICATIONS-NEEDED.md synthesis recommendations

---

## Tier 1: Blocking Decisions

### Q1: Is 14-04 a validation spike or a selection spike?

**YOLO DECISION:** ✅ **Option A — Validation spike. Transport is locked.**

**Rationale:**
- Plans 14-01/14-02 made the transport decision with full rationale: Unix socket + uvicorn/starlette already installed
- Re-opening to NATS/Redis would require parallel implementations and delay Phase 15
- Confidence: ✅ Consensus (both providers agreed)

**Sub-decisions:**
- Mattermost: **Phase 16 audit trail only** — not a transport layer
- NATS/Redis: **Phase 15+ evolution path** for cross-host governance — document but do not implement in Phase 14
- Spike pass criteria: p99 constraint check latency < 50ms; OPE pipeline processes worker JSONL files correctly; throughput > 100 signals/sec under 5 concurrent sessions

---

### Q2: How does the DDF co-pilot intervention reach the user?

**YOLO DECISION:** ✅ **Option C — Silent write-only. memory_candidates deposit is terminal output.**

**Rationale:**
- deposit-not-detect governing axis from 14-CONTEXT.md: write-on-detect to memory_candidates is load-bearing, user-visible prompt is scaffolding
- Hook stdout may or may not render (PAG hook evidence is incomplete for PostToolUse)
- Confidence: ✅ Aligned with 14-CONTEXT.md governing principle

**Sub-decisions:**
- memory_candidates write: **mandatory and synchronous** on every O_AXS/Fringe/Affect Spike detection
- User-visible prompt: **Phase 15 enhancement** — implement only after spike confirms PostToolUse hook stdout renders
- 14-04 spike item: **explicitly test PostToolUse hook stdout visibility** and document the finding in SPIKE-RESULTS.md

---

### Q3: Which components run real-time vs. post-task?

**YOLO DECISION:** ✅ **Option A — Strict split.**

**Rationale:**
- Real-time heuristic path must stay < 5ms per event; full OPE pipeline cannot run synchronously
- Both write to memory_candidates but with different fidelity levels
- Confidence: ✅ Consensus (both providers agreed)

**Sub-decisions:**
- **Real-time path (DDF co-pilot):** LiveEventAdapter + keyword/regex heuristic detectors + write-on-detect to memory_candidates.jsonl. No LLM calls. No EpisodePopulator. Budget: < 5ms per event.
- **Post-task path (OPE pipeline):** `python -m src.pipeline.cli extract` triggered at CONFIRMED_END. Full episode population, constraint extraction, amnesia detection. Writes to DuckDB. May enrich real-time memory_candidates entries.
- Triggering: governing daemon triggers post-task OPE run on CONFIRMED_END (not manual CLI)
- Dedup: SHA-256(ccd_axis + scope_rule + session_id) as dedup key; post-task can UPDATE (enrich) but not INSERT duplicates

---

## Tier 2: Important Decisions

### Q4: Fixed or dynamic CONFIRMED_END timeout for Phase 14 design?

**YOLO DECISION:** ⚠️ **Option A — Fixed 30-minute TTL for Phase 14, configurable in Phase 15.**

**Rationale:** Simpler spike design; dynamic learning is a Phase 15 Wave 2 enhancement. Document known limitation.

---

### Q5: Phase 15 wave ordering?

**YOLO DECISION:** ✅ **14-05 encodes deposit-first wave ordering explicitly.**

**Wave ordering (Phase 15):**
- Wave 1: flame_events schema + minimal DDF detector stubs + write-on-detect path to memory_candidates.jsonl **(load-bearing — must complete first)**
- Wave 2: ai_flame_events + IntelligenceProfile data structure (scaffolding)
- Wave 3: live governance hooks + bus + governing session (LIVE-01 through LIVE-05)
- Wave 4: MEMORY.md review CLI + TransportEfficiency metrics (Phase 16 territory)

---

### Q6: memory_candidates dedup strategy?

**YOLO DECISION:** ⚠️ **Option B — Last-write-wins with fidelity field.**

- Dedup key: SHA-256(ccd_axis + scope_rule + session_id)
- `fidelity` field: 1 = real-time heuristic, 2 = post-task OPE
- Post-task OPE can UPDATE entries with fidelity=2 when it has higher-confidence data
- Uses existing OPE ON CONFLICT DO UPDATE pattern

---

## Tier 3: Polish Decisions

### Q7: 14-03/14-04 spike independence?

**YOLO DECISION:** ⚠️ **Shared prerequisite only.**
- Both spikes require the bus design to be complete (already in 14-01/14-02)
- Both write results to shared `14-SPIKE-RESULTS.md`
- 14-04 is executable independently of 14-03

### Q8: Which governance signals must survive daemon restart?

**YOLO DECISION:** ⚠️ **Ephemeral in-memory state is acceptable limitation for Phase 14.**
- Governance decisions (blocks, broadcasts) persisted to DuckDB governance_signals table before acknowledgment
- Pending in-memory broadcasts are lost on restart — documented as known limitation
- Sessions re-register within 1 hook call (< 60s) after daemon restart

---

## Summary

| Decision | Answer |
|----------|--------|
| 14-04 scope | Validation spike (transport locked at Unix socket) |
| DDF delivery channel | Silent write-only; hook stdout tested in spike |
| Real-time vs post-task | Strict split (heuristics real-time, OPE post-task) |
| Timeout strategy | Fixed 30-min TTL with configurable override |
| Phase 15 wave ordering | Deposit-first enforced in 14-05 |
| memory_candidates dedup | Last-write-wins with fidelity field |
| Spike independence | Parallel with shared prerequisite |
| Daemon restart | Ephemeral acceptable |

---

*Auto-generated by discuss-phase-ai YOLO mode (balanced strategy)*
*Human review recommended before final implementation*
