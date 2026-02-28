"""Spike tests validating reactivex v4 patterns against OPE-specific shapes.

Phase 27 go/no-go gate: all three adoption patterns must pass before any
production code is modified.

Pattern A: External operator pattern (StreamProcessor shape)
Pattern B: map+merge fan-out with sync DuckDB writes (batch runner shape)
Pattern C: ThreadPoolScheduler for CPU-bound work (embedder shape)

Phase 18 axioms inherited (NOT re-tested):
- ops.flat_map(max_concurrent=N) does not exist
- ops.retry_when does not exist
- .run() forbidden in async context
- ops.catch not ops.catch_error
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import duckdb
import reactivex as rx
from reactivex import operators as ops
from reactivex.scheduler import ThreadPoolScheduler


# ---------------------------------------------------------------------------
# Test A fixtures: minimal stateful processor mimicking StreamProcessor shape
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    """Minimal signal matching GovernanceSignal shape."""

    signal_type: str
    payload: dict[str, Any] = field(default_factory=dict)


class MinimalProcessor:
    """Stateful processor that accumulates a counter.

    Mimics StreamProcessor.process_event() -> list[Signal] interface.
    """

    def __init__(self) -> None:
        self._counter: int = 0

    def process_event(self, event: dict[str, Any]) -> list[Signal]:
        self._counter += 1
        signals: list[Signal] = []
        event_type = event.get("type", "")
        if event_type == "escalation":
            signals.append(
                Signal(
                    signal_type="escalation_detected",
                    payload={"count": self._counter, "event": event},
                )
            )
        elif event_type == "boundary":
            signals.append(
                Signal(
                    signal_type="episode_boundary",
                    payload={"count": self._counter},
                )
            )
            # Boundary events emit TWO signals to test multi-emission
            signals.append(
                Signal(
                    signal_type="boundary_flush",
                    payload={"count": self._counter},
                )
            )
        # "normal" type events produce no signals (tests filtering)
        return signals


def create_processor_operator(
    processor_factory,
):
    """External operator pattern from CONTEXT.md.

    Each subscription creates a fresh processor instance (cold semantics).
    """

    def _operator(source):
        def subscribe(observer, scheduler=None):
            processor = processor_factory()

            def on_next(event):
                try:
                    signals = processor.process_event(event)
                    for sig in signals:
                        observer.on_next(sig)
                except Exception as e:
                    observer.on_error(e)

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
                scheduler=scheduler,
            )

        return rx.create(subscribe)

    return _operator


# ---------------------------------------------------------------------------
# Test A: External operator pattern (StreamProcessor shape)
# ---------------------------------------------------------------------------


class TestExternalOperatorPattern:
    """Validate external operator produces identical signal sequence."""

    def _make_events(self) -> list[dict[str, Any]]:
        return [
            {"type": "normal", "id": 1},
            {"type": "escalation", "id": 2},
            {"type": "normal", "id": 3},
            {"type": "boundary", "id": 4},
            {"type": "normal", "id": 5},
            {"type": "escalation", "id": 6},
            {"type": "normal", "id": 7},
            {"type": "boundary", "id": 8},
            {"type": "normal", "id": 9},
            {"type": "escalation", "id": 10},
        ]

    def test_signal_sequence_matches_direct_calls(self):
        """Observable signal sequence is IDENTICAL to direct for-loop."""
        events = self._make_events()

        # Direct for-loop (baseline)
        direct_processor = MinimalProcessor()
        direct_signals: list[Signal] = []
        for event in events:
            direct_signals.extend(direct_processor.process_event(event))

        # Observable pipeline
        operator = create_processor_operator(MinimalProcessor)
        rx_signals: list[Signal] = []
        errors: list[Exception] = []
        completed = threading.Event()

        rx.from_iterable(events).pipe(operator).subscribe(
            on_next=rx_signals.append,
            on_error=errors.append,
            on_completed=lambda: completed.set(),
        )
        completed.wait(timeout=5.0)

        assert not errors, f"Observable errored: {errors}"
        assert len(rx_signals) == len(direct_signals)
        for rx_sig, direct_sig in zip(rx_signals, direct_signals):
            assert rx_sig.signal_type == direct_sig.signal_type
            assert rx_sig.payload == direct_sig.payload

    def test_cold_semantics_independent_state(self):
        """Two subscriptions to same source get independent processor state."""
        events = self._make_events()
        source = rx.from_iterable(events)
        operator = create_processor_operator(MinimalProcessor)

        signals_a: list[Signal] = []
        signals_b: list[Signal] = []
        completed_a = threading.Event()
        completed_b = threading.Event()

        source.pipe(operator).subscribe(
            on_next=signals_a.append,
            on_completed=lambda: completed_a.set(),
        )
        source.pipe(operator).subscribe(
            on_next=signals_b.append,
            on_completed=lambda: completed_b.set(),
        )
        completed_a.wait(timeout=5.0)
        completed_b.wait(timeout=5.0)

        # Both subscriptions should produce identical sequences
        assert len(signals_a) == len(signals_b)
        for a, b in zip(signals_a, signals_b):
            assert a.signal_type == b.signal_type
            assert a.payload == b.payload

        # Counter values confirm independent state (not shared)
        escalation_counts_a = [
            s.payload["count"]
            for s in signals_a
            if s.signal_type == "escalation_detected"
        ]
        escalation_counts_b = [
            s.payload["count"]
            for s in signals_b
            if s.signal_type == "escalation_detected"
        ]
        assert escalation_counts_a == escalation_counts_b


# ---------------------------------------------------------------------------
# Test B: map+merge fan-out with sync DuckDB writes (batch runner shape)
# ---------------------------------------------------------------------------


class TestMapMergeFanOut:
    """Validate map+merge with sync DuckDB writes inside observable."""

    def _setup_db(self):
        conn = duckdb.connect(":memory:")
        conn.execute(
            "CREATE TABLE test_results (session_id TEXT, value INT)"
        )
        return conn

    def _create_session_observable(self, conn, session_id: str):
        """Factory: returns an observable that does a sync DuckDB write."""

        def subscribe(observer, scheduler=None):
            try:
                value = hash(session_id) % 1000
                conn.execute(
                    "INSERT INTO test_results VALUES (?, ?)",
                    [session_id, value],
                )
                observer.on_next(
                    {"session_id": session_id, "value": value, "status": "ok"}
                )
                observer.on_completed()
            except Exception as e:
                observer.on_error(e)

        return rx.create(subscribe)

    def test_sequential_fanout_max_concurrent_1(self):
        """Fan-out with max_concurrent=1 writes all rows sequentially."""
        conn = self._setup_db()
        session_ids = ["s1", "s2", "s3", "s4", "s5"]

        results: list[dict] = []
        errors: list[Exception] = []
        completed = threading.Event()

        rx.from_iterable(session_ids).pipe(
            ops.map(lambda sid: self._create_session_observable(conn, sid)),
            ops.merge(max_concurrent=1),
        ).subscribe(
            on_next=results.append,
            on_error=errors.append,
            on_completed=lambda: completed.set(),
        )
        completed.wait(timeout=10.0)

        assert not errors, f"Observable errored: {errors}"
        assert len(results) == 5

        # Verify DuckDB state
        rows = conn.execute(
            "SELECT session_id FROM test_results ORDER BY session_id"
        ).fetchall()
        db_session_ids = sorted([r[0] for r in rows])
        assert db_session_ids == sorted(session_ids)

    def test_concurrent_fanout_max_concurrent_3(self):
        """Fan-out with max_concurrent=3 produces same final state.

        Note: DuckDB in-memory with single connection serializes writes
        internally, so concurrent=3 is safe here. Production code uses
        file-backed DB with single-writer invariant (Phase 14).
        """
        conn = self._setup_db()
        session_ids = ["s1", "s2", "s3", "s4", "s5"]

        results: list[dict] = []
        errors: list[Exception] = []
        completed = threading.Event()

        rx.from_iterable(session_ids).pipe(
            ops.map(lambda sid: self._create_session_observable(conn, sid)),
            ops.merge(max_concurrent=3),
        ).subscribe(
            on_next=results.append,
            on_error=errors.append,
            on_completed=lambda: completed.set(),
        )
        completed.wait(timeout=10.0)

        assert not errors, f"Observable errored: {errors}"
        assert len(results) == 5

        # Same rows regardless of concurrency
        rows = conn.execute(
            "SELECT session_id FROM test_results ORDER BY session_id"
        ).fetchall()
        db_session_ids = sorted([r[0] for r in rows])
        assert db_session_ids == sorted(session_ids)

        # All result dicts have correct shape
        for r in results:
            assert "session_id" in r
            assert "value" in r
            assert r["status"] == "ok"


# ---------------------------------------------------------------------------
# Test C: ThreadPoolScheduler for CPU-bound work (embedder shape)
# ---------------------------------------------------------------------------


class TestThreadPoolSchedulerEmbedder:
    """Validate ThreadPoolScheduler offloads CPU-bound work from sync context.

    CONTEXT.md specified run_in_executor; spike research confirmed
    embed_episodes() is called from sync CLI code with no asyncio event
    loop. ThreadPoolScheduler is the correct sync-compatible pattern.
    """

    @staticmethod
    def _cpu_bound_computation(text: str) -> list[float]:
        """Simulate model.encode() -- CPU-bound blocking computation.

        Returns a deterministic "embedding" based on text content so we
        can verify correctness.
        """
        # Deterministic hash-based fake embedding (3 dimensions)
        h = hash(text)
        return [float((h >> i) & 0xFFFF) / 65536.0 for i in range(3)]

    def test_threadpool_produces_correct_results(self):
        """ThreadPoolScheduler offload produces identical results to sequential."""
        rows = [
            ("ep1", "The governance signal was detected"),
            ("ep2", "Episode boundary confirmed at timestamp"),
            ("ep3", "Escalation pattern matched in session"),
            ("ep4", "Policy violation detected by checker"),
        ]

        # Sequential baseline
        sequential_results = {}
        for episode_id, text in rows:
            embedding = self._cpu_bound_computation(text)
            sequential_results[episode_id] = embedding

        # ThreadPoolScheduler observable pipeline
        scheduler = ThreadPoolScheduler(max_workers=4)
        rx_results: list[dict] = []
        errors: list[Exception] = []
        completed = threading.Event()

        def create_embedding_observable(row):
            episode_id, text = row

            def subscribe(observer, sched=None):
                try:
                    embedding = self._cpu_bound_computation(text)
                    observer.on_next(
                        {"episode_id": episode_id, "embedding": embedding}
                    )
                    observer.on_completed()
                except Exception as e:
                    observer.on_error(e)

            return rx.create(subscribe).pipe(
                ops.subscribe_on(scheduler),
            )

        rx.from_iterable(rows).pipe(
            ops.map(create_embedding_observable),
            ops.merge(max_concurrent=4),
        ).subscribe(
            on_next=rx_results.append,
            on_error=errors.append,
            on_completed=lambda: completed.set(),
        )
        completed.wait(timeout=10.0)

        assert not errors, f"Observable errored: {errors}"
        assert len(rx_results) == 4

        # Verify all episodes present with correct embeddings
        rx_results_map = {r["episode_id"]: r["embedding"] for r in rx_results}
        for episode_id, expected_embedding in sequential_results.items():
            assert episode_id in rx_results_map, (
                f"Missing episode: {episode_id}"
            )
            assert rx_results_map[episode_id] == expected_embedding

        scheduler.executor.shutdown(wait=False)

    def test_runs_without_asyncio_event_loop(self):
        """Validates ThreadPoolScheduler works in sync-only context.

        This test itself runs without asyncio -- proving the pattern is
        sync-compatible. If this test passes, the embedder can use it
        from the sync CLI entry point.
        """
        scheduler = ThreadPoolScheduler(max_workers=2)
        results: list[int] = []
        completed = threading.Event()

        def create_work(value: int):
            def subscribe(observer, sched=None):
                # Blocking CPU work
                result = sum(range(value * 100_000))
                observer.on_next(result)
                observer.on_completed()

            return rx.create(subscribe).pipe(
                ops.subscribe_on(scheduler),
            )

        rx.from_iterable([1, 2, 3, 4]).pipe(
            ops.map(create_work),
            ops.merge(max_concurrent=4),
        ).subscribe(
            on_next=results.append,
            on_completed=lambda: completed.set(),
        )
        completed.wait(timeout=10.0)

        assert len(results) == 4

        # Verify correct values (order may vary due to threading)
        expected = {sum(range(v * 100_000)) for v in [1, 2, 3, 4]}
        assert set(results) == expected

        # Confirm we actually ran on threads (not main thread)
        # The fact that this test completes without asyncio is the proof

        scheduler.executor.shutdown(wait=False)

    def test_thread_offload_uses_worker_threads(self):
        """Verify computation actually runs on non-main threads."""
        scheduler = ThreadPoolScheduler(max_workers=2)
        thread_names: list[str] = []
        main_thread = threading.current_thread().name
        completed = threading.Event()

        def create_work(value: int):
            def subscribe(observer, sched=None):
                thread_names.append(threading.current_thread().name)
                observer.on_next(value * 2)
                observer.on_completed()

            return rx.create(subscribe).pipe(
                ops.subscribe_on(scheduler),
            )

        rx.from_iterable([1, 2, 3]).pipe(
            ops.map(create_work),
            ops.merge(max_concurrent=2),
        ).subscribe(
            on_next=lambda _: None,
            on_completed=lambda: completed.set(),
        )
        completed.wait(timeout=10.0)

        # At least some work ran on non-main threads
        non_main = [t for t in thread_names if t != main_thread]
        assert len(non_main) > 0, (
            f"Expected work on worker threads, all ran on {main_thread}"
        )

        scheduler.executor.shutdown(wait=False)
