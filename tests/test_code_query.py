"""Tests for code query subprocess search backend.

Uses tmp_path for controlled filesystem testing. Real subprocess calls
(no mocking) for most tests; mock only for grep fallback verification.
"""

from __future__ import annotations

from unittest.mock import patch

from src.pipeline.code_query import query_code


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_test_file(tmp_path, filename, content):
    """Write a file with known content for search testing."""
    f = tmp_path / filename
    f.write_text(content)
    return f


# ---------------------------------------------------------------------------
# Basic search tests (tmp_path with real subprocess)
# ---------------------------------------------------------------------------


class TestCodeSearchBasic:
    """Tests using tmp_path with real subprocess calls."""

    def test_finds_match_in_py_file(self, tmp_path):
        _write_test_file(tmp_path, "example.py", "def episode_populator():\n    pass\n")
        results = query_code("episode_populator", search_dir=str(tmp_path))
        assert len(results) > 0
        assert results[0]["source"] == "code"

    def test_finds_match_in_md_file(self, tmp_path):
        _write_test_file(tmp_path, "docs.md", "# Episode Populator Design\n\nDetails here.\n")
        results = query_code("Episode Populator", search_dir=str(tmp_path))
        assert len(results) > 0

    def test_result_dict_shape(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "# episode_search_text table\n")
        results = query_code("episode_search_text", search_dir=str(tmp_path))
        assert len(results) > 0
        r = results[0]
        required_keys = {"source", "file_path", "line_number", "content_preview", "match_reason"}
        assert set(r.keys()) == required_keys

    def test_line_number_is_int(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "line1\nfoobar\nline3\n")
        results = query_code("foobar", search_dir=str(tmp_path))
        assert len(results) > 0
        assert isinstance(results[0]["line_number"], int)
        assert results[0]["line_number"] == 2

    def test_match_reason_is_text_match(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "some content\n")
        results = query_code("some content", search_dir=str(tmp_path))
        assert len(results) > 0
        assert results[0]["match_reason"] == "text match"

    def test_top_n_limits_results(self, tmp_path):
        content = "\n".join(f"match_line_{i}" for i in range(20))
        _write_test_file(tmp_path, "many.py", content)
        results = query_code("match_line", search_dir=str(tmp_path), top_n=3)
        assert len(results) <= 3

    def test_content_preview_truncated(self, tmp_path):
        long_line = "x" * 200 + " searchterm " + "y" * 200
        _write_test_file(tmp_path, "long.py", long_line + "\n")
        results = query_code("searchterm", search_dir=str(tmp_path))
        assert len(results) > 0
        assert len(results[0]["content_preview"]) <= 120

    def test_no_matches_returns_empty(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "nothing relevant here\n")
        results = query_code("xyznonexistent42", search_dir=str(tmp_path))
        assert results == []

    def test_case_insensitive_search(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "Episode Populator\n")
        results = query_code("episode populator", search_dir=str(tmp_path))
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Edge case / fail-open tests
# ---------------------------------------------------------------------------


class TestCodeSearchEdgeCases:
    """Tests for edge cases and fail-open behavior."""

    def test_empty_query_returns_empty(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "content\n")
        assert query_code("", search_dir=str(tmp_path)) == []

    def test_whitespace_query_returns_empty(self, tmp_path):
        assert query_code("   ", search_dir=str(tmp_path)) == []

    def test_nonexistent_dir_returns_empty(self):
        results = query_code("test", search_dir="/nonexistent/path/abc123")
        assert results == []

    def test_source_field_is_code(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "target_string\n")
        results = query_code("target_string", search_dir=str(tmp_path))
        assert len(results) > 0
        for r in results:
            assert r["source"] == "code"


# ---------------------------------------------------------------------------
# Real src/ directory test
# ---------------------------------------------------------------------------


class TestCodeSearchRealSrc:
    """Smoke test against the real src/ directory."""

    def test_finds_episode_search_text_in_src(self):
        results = query_code("episode_search_text", search_dir="src/")
        assert len(results) > 0
        # Should find at least the retriever.py and session_query.py references
        file_paths = {r["file_path"] for r in results}
        assert any("retriever" in fp or "session_query" in fp for fp in file_paths)


# ---------------------------------------------------------------------------
# Grep fallback test (mocked)
# ---------------------------------------------------------------------------


class TestGrepFallback:
    """Test that grep is used when rg is not available."""

    def test_grep_fallback_when_rg_missing(self, tmp_path):
        _write_test_file(tmp_path, "test.py", "fallback_target\n")
        with patch("src.pipeline.code_query.shutil.which", return_value=None):
            results = query_code("fallback_target", search_dir=str(tmp_path))
            assert len(results) > 0
            assert results[0]["match_reason"] == "text match"
