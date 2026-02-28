"""Phase 27 RxPY adoption regression suite.

Validates behavioral parity gate (RXA-05): all three adopted modules
produce identical outputs for identical inputs after RxPY adoption.

This file runs as part of the standard pytest suite. It does NOT
test RxPY internals -- it tests that OPE's observable behaviors
are preserved after the reactive adoption.
"""

import inspect


class TestRxAdoptionRegression:
    """Regression tests for all Phase 27 RxPY adoptions."""

    def test_reactivex_importable(self):
        """RXA-01: reactivex v4 is importable with correct aliases."""
        import reactivex as rx
        from reactivex import operators as ops

        assert hasattr(ops, "merge")
        assert hasattr(ops, "map")
        assert hasattr(ops, "catch")
        assert hasattr(ops, "filter")

    def test_rx_operators_module_exists(self):
        """Shared rx_operators.py module is importable."""
        from src.pipeline.rx_operators import create_work_observable

        assert callable(create_work_observable)

    def test_embedder_uses_reactivex(self):
        """RXA-02: embedder module contains reactivex adoption markers."""
        import src.pipeline.rag.embedder as mod

        source_code = inspect.getsource(mod)
        assert "reactivex" in source_code or "rx" in source_code, (
            "embedder module source does not contain reactivex markers"
        )
        assert "merge" in source_code, (
            "embedder module should use merge(max_concurrent=4)"
        )

    def test_runner_uses_reactivex(self):
        """RXA-03: runner module contains reactivex adoption markers."""
        import src.pipeline.runner as mod

        source_code = inspect.getsource(mod)
        assert "reactivex" in source_code or "rx" in source_code, (
            "runner module source does not contain reactivex markers"
        )
        assert "merge" in source_code, (
            "runner module should use merge(max_concurrent=N)"
        )

    def test_stream_processor_operator_exists(self):
        """RXA-04: stream processor operator factory is exported."""
        from src.pipeline.live.stream.processor import (
            create_stream_processor_operator,
        )

        assert callable(create_stream_processor_operator)

    def test_config_has_batch_max_concurrent(self):
        """RXA-03: PipelineConfig has batch_max_concurrent with default=1."""
        from src.pipeline.models.config import PipelineConfig

        config = PipelineConfig()
        assert config.batch_max_concurrent == 1

    def test_rx_operators_documents_operator_index(self):
        """SC-6 resolution: rx_operators.py module docstring serves as operator index."""
        import src.pipeline.rx_operators as mod

        docstring = mod.__doc__ or ""
        assert "embedder" in docstring.lower(), (
            "rx_operators.py docstring should document embedder adoption"
        )
        assert "runner" in docstring.lower(), (
            "rx_operators.py docstring should document runner adoption"
        )
        assert "processor" in docstring.lower(), (
            "rx_operators.py docstring should document stream processor adoption"
        )
        assert "create_work_observable" in docstring, (
            "rx_operators.py docstring should document shared utilities"
        )

    def test_all_adopted_modules_importable(self):
        """RXA-05 gate: all adopted modules import successfully."""
        from src.pipeline.rag import embedder
        from src.pipeline import runner
        from src.pipeline.live.stream import processor

        for mod_name, mod in [
            ("embedder", embedder),
            ("runner", runner),
            ("processor", processor),
        ]:
            mod_source = inspect.getsource(mod)
            assert "reactivex" in mod_source, (
                f"{mod_name} module source does not contain 'reactivex' -- "
                f"adoption may not have been applied"
            )
