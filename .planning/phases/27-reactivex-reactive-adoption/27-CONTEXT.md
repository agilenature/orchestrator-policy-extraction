# Phase 27: ReactiveX Reactive Adoption — Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Adopt `reactivex` v4 (ReactiveX for Python) in OPE's source code **where the programming model already expresses observable semantics imperatively**. This is an **adoption phase, not a migration** — OPE has one production async file (`bus/server.py`, Starlette ASGI framework-imposed) and is otherwise a synchronous batch pipeline. Phase 27 introduces RxPY only where modules have latent reactive structure: a natural stream of events, a concurrent fan-out, or a reactive dependency expressed as a loop.

**Out of scope:** wrapping synchronous DuckDB queries in `rx.from_callable()` for one-shot calls — that adds complexity without value. The gate question for every module: "Does this module already have observable semantics being expressed imperatively?"

**Applicable modules (verdict from source inventory):**
1. `live/stream/processor.py` — Tier 1 (primary target; IS a reactive pipeline in concept)
2. `runner.py:run_batch()` — Tier 2 (fan-out with concurrency control for session parallelism)
3. `rag/embedder.py:embed_episodes()` — Tier 3 (CPU-bound sequential loop over episodes → parallelizable)

**Not applicable (explicitly excluded):**
- `live/bus/server.py` — ASGI framework-imposed async; Starlette handles concurrency
- `ddf/deposit.py` — single DuckDB write per call; no observable semantics
- `assessment/session_runner.py` — sequential by design (subprocess.run waits for Actor)
- All DuckDB query calls — one-shot awaitable wrapping adds no value
- `live/governor/daemon.py` — stateless request-response; no stream composition

</domain>

<decisions>
## Implementation Decisions

### RxPY Version: reactivex v4 (locked)
- Use `reactivex>=4.0` (NOT `rx` v3)
- Import pattern: `import reactivex as rx`, `from reactivex import operators as ops`
- v4 uses `ops.catch` (not `ops.catch_error`), `ops.filter` (not `ops.filter_`)
- v4 has type annotations, no Python 3.12 `datetime.utcnow()` deprecation warnings
- Add `"reactivex>=4.0"` to `pyproject.toml` project dependencies

### StreamProcessor Observable Interface: External Operator Pattern (locked)
Research verdict (Perplexity deep research, 2026-02-28):
- **Pattern**: External operator pattern, NOT Subject wrapping
- **Operator**: `ops.concat_map` (NOT `flat_map`) — ensures ordering for stateful processor
- **Semantics**: Cold observable — each subscription creates a fresh `StreamProcessor` instance; one subscription = one session
- **Interface**: Keep `process_event(event) -> list[GovernanceSignal]` unchanged; add `create_stream_processor_operator(session_id, run_id)` factory that wraps it in an RxPY pipeline
- **Rationale**: StreamProcessor IS a transformation (not a source); it must process events in order (state machine depends on prior state); single subscription guarantees sequential execution regardless of scheduler

**Concrete pipeline structure:**
```python
def create_stream_processor_operator(session_id: str, run_id: str):
    def _operator(source):
        def subscribe(observer, scheduler=None):
            processor = StreamProcessor(session_id=session_id, run_id=run_id)
            def on_next(event):
                try:
                    signals = processor.process_event(event)
                    for sig in signals: observer.on_next(sig)
                except Exception as e:
                    observer.on_error(e)
            return source.subscribe(on_next, observer.on_error, observer.on_completed)
        return rx.create(subscribe)
    return _operator
```

**No concatMap needed at the top level** because `process_event()` is synchronous and list emission is inline — the `on_next` loop in the subscribe function is already sequential. `concat_map` would be needed if converting the list to a nested Observable, but direct iteration in `on_next` is simpler and equivalent.

### Batch Runner Fan-out (run_batch): Tier 2
- Replace sequential `for` loop over sessions with `ops.map(factory).pipe(ops.merge(max_concurrent=N))`
- Default `max_concurrent=1` (preserves current sequential behavior)
- Config-controlled `max_concurrent` via `PipelineConfig` — unlocks future parallelism without code change
- DuckDB single-writer invariant must be preserved: sessions write to different episode/segment rows, but concurrent writes to the same table need coordination. Research must confirm DuckDB's concurrent-write behavior before setting `max_concurrent > 1`

### Embedder Parallelism (embed_episodes): Tier 3
- Replace sequential `for row in rows: embedding = model.encode(text)` with `run_in_executor` observable
- Pattern (inherited from Phase 18 Tier 3): Future-based subscription with `loop.run_in_executor(None, model.encode, text)`
- **NOT `.run()` inside async context** (Phase 18 locked decision: blocks event loop)
- Concurrency: `merge(max_concurrent=4)` — `model.encode()` is CPU-bound; GIL limits true parallelism, but threading still helps for I/O-adjacent overhead

### Phase Structure: 4 plans (spike-first, bottom-up)
- **27-01**: Scope gate + short spike — validate reactivex v4 patterns specific to OPE: (a) `run_in_executor` Future-based subscribe with reactivex v4 API, (b) `concat_map` / external operator with sync DuckDB writes inside observable, (c) Starlette ASGI context — can a Subject emit from an async ASGI handler? Hostile posture. Go/no-go gate before any production code.
- **27-02**: Tier 3 adoption — `rag/embedder.py` (simplest; pure CPU-bound parallelism, no state)
- **27-03**: Tier 2 adoption — `runner.py:run_batch()` fan-out with configurable `max_concurrent`
- **27-04**: Tier 1 adoption + validation — `live/stream/processor.py` external operator; Canon.json update; regression tests; behavioral parity gate

### Inherited Locked Decisions from Phase 18 (do NOT re-discover in spike)
These were validated with hostile evidence in Phase 18-01 spike. Treat as axioms:
1. `ops.flat_map(max_concurrent=N)` does **not** exist → use `ops.map(factory).pipe(ops.merge(max_concurrent=N))`
2. `ops.retry_when` does **not** exist in RxPY 3.x (also verify in v4; custom `make_retrying_observable` may still be needed)
3. `.run()` is **forbidden inside async contexts** → use Future-based subscription pattern
4. Sources for dynamic concurrency control MUST emit **coroutine factories**, not pre-started futures
5. `shutdown_gate` is a two-signal composition pattern (`stop_accepting$` before flat_map, `force_kill$` after)
6. `AsyncIOScheduler` must be instantiated in the async lifecycle method, NOT in `__init__`

### Behavioral Parity Gate (applies to all plans)
- Capture the behavioral contract for each module BEFORE writing migration code
- Gate = behavioral parity (identical outputs for identical inputs), NOT test coverage
- For stream processor: same `GovernanceSignal` sequence for same `event` sequence
- For batch runner: same DuckDB state after processing same session set
- For embedder: same embeddings in `episode_embeddings` table for same episodes

### Claude's Discretion
- Exact `max_concurrent` default for embedder (4 is a reasonable starting point)
- Whether `create_stream_processor_operator` lives in `live/stream/rx_operators.py` or inline in `processor.py`
- Specific timing of spike vs whether Phase 18 patterns are sufficient to skip spike for v4 (spike is short — do it anyway)
- Whether to add `ops.share()` to multicast the stream processor observable if multiple subscribers needed

</decisions>

<specifics>
## Specific Ideas

- Phase 18's 5-plan structure (18-01 spike → 18-02 Tier3 → 18-03 Tier2 → 18-04 Tier1 → 18-05 validation) is the template, compressed to 4 plans because OPE's scope is narrower
- The `_operators.py` pattern from Phase 18 (`src/objlib/upload/_operators.py`) should be replicated: create `src/pipeline/live/rx_operators.py` (or `src/pipeline/rx_operators.py`) as the shared operator module
- `defer_task()` wrapper from Phase 17/18 is the template for the `run_in_executor` bridge
- Phase 18's `subscribe_awaitable` pattern (bridge from sync observable to async context) may be needed for any place the embedder is called from an async context

</specifics>

<deferred>
## Deferred Ideas

- RxPY marble testing / TestScheduler (virtual clock) — Phase 18 excluded this; Phase 27 follows the same decision: real-time behavioral tests only
- Thread-safe scheduler variants — not needed until OPE requires true multi-threaded event processing
- `BehaviorSubject`-based governance bus event stream (treating all `/api/check` calls as a shared observable stream) — could be added if co-pilot interventions become real-time; stub until then (GovernorDaemon is stateless by design)
- DDF deposit observable (write-on-detect as reactive trigger) — `ddf/deposit.py` is a single synchronous write; wrapping makes it more complex, not simpler; defer until the deposit loop has multiple sources to compose
- `asyncio.Queue`-based event bus for session coordination — a future architecture if OPE becomes multi-session concurrent; not applicable to current single-writer architecture

</deferred>

---

*Phase: 27-reactivex-reactive-adoption*
*Context gathered: 2026-02-28*
*Predecessor: Phase 18 (objectivism-library-semantic-search) — spike learnings inherited as locked decisions*
*Research source: Perplexity deep research (StreamProcessor interface) + Phase 18 CONTEXT.md + Phase 18 spike/design_doc.md*
