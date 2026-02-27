"""Tests for src.pipeline.doc_indexer -- 3-tier axis extraction engine.

Covers:
  - Tier 1 (frontmatter) parsing with Pitfall 4 edge cases
  - Tier 2 (regex) header/comment matching
  - Tier 3 (keyword) token matching with Pitfall 5 stopword exclusion
  - extract_axes cascade integration
  - Description extraction and content hashing
  - reindex_docs end-to-end with DuckDB verification
  - CLI integration via CliRunner
"""

from __future__ import annotations

import duckdb
import pytest
from click.testing import CliRunner

from src.pipeline.doc_indexer import (
    _axis_in_headers_or_comments,
    _axis_token_match,
    _content_hash,
    _extract_description,
    _parse_frontmatter_axes,
    extract_axes,
    load_axis_vocabulary,
    reindex_docs,
)

# =========================================================================
# Tier 1 -- Frontmatter
# =========================================================================


class TestTier1Frontmatter:
    """Frontmatter axis extraction (conf=1.0)."""

    def test_parse_frontmatter_axes_valid(self):
        content = "---\naxes: [a, b]\n---\n# Title"
        assert _parse_frontmatter_axes(content) == ["a", "b"]

    def test_parse_frontmatter_axes_yaml_list(self):
        content = "---\naxes:\n  - a\n  - b\n---"
        assert _parse_frontmatter_axes(content) == ["a", "b"]

    def test_parse_frontmatter_no_frontmatter(self):
        content = "# Title\nContent"
        assert _parse_frontmatter_axes(content) == []

    def test_parse_frontmatter_horizontal_rule_not_frontmatter(self):
        """Pitfall 4: --- as horizontal rule mid-file is NOT frontmatter."""
        content = "# Title\n\n---\nsome text\n---"
        assert _parse_frontmatter_axes(content) == []

    def test_parse_frontmatter_no_axes_key(self):
        content = "---\ntitle: Foo\n---"
        assert _parse_frontmatter_axes(content) == []


# =========================================================================
# Tier 2 -- Regex (headers / comments)
# =========================================================================


class TestTier2Regex:
    """Header/comment axis matching (conf=0.7)."""

    def test_axis_in_h1_header(self):
        content = "# Cross-Domain CCD: deposit-not-detect"
        assert _axis_in_headers_or_comments(content, "deposit-not-detect") is True

    def test_axis_in_h2_header(self):
        content = "## deposit-not-detect"
        assert _axis_in_headers_or_comments(content, "deposit-not-detect") is True

    def test_axis_in_html_comment(self):
        content = "<!-- ccd: deposit-not-detect -->"
        assert _axis_in_headers_or_comments(content, "deposit-not-detect") is True

    def test_axis_not_in_h3_header(self):
        """H3 headers do NOT match (H1/H2 only)."""
        content = "### deposit-not-detect"
        assert _axis_in_headers_or_comments(content, "deposit-not-detect") is False

    def test_axis_not_in_body_text(self):
        """Body text does NOT trigger Tier 2 regex."""
        content = "Some deposit-not-detect discussion"
        assert _axis_in_headers_or_comments(content, "deposit-not-detect") is False


# =========================================================================
# Tier 3 -- Keyword token matching
# =========================================================================


class TestTier3Keyword:
    """Token frequency matching (conf=0.4)."""

    def test_axis_token_match_sufficient(self):
        """3+ tokens, 3+ total occurrences -> True."""
        content = (
            "The raven has a cost function that is absent. "
            "The cost is absent in the raven."
        )
        assert _axis_token_match(content, "raven-cost-function-absent") is True

    def test_axis_token_match_insufficient_tokens(self):
        """Only 1 non-stopword token matched -> False."""
        content = "The raven flew away."
        assert _axis_token_match(content, "raven-cost-function-absent") is False

    def test_axis_token_match_insufficient_count(self):
        """2 tokens matched but only 2 total occurrences -> False."""
        content = "The raven has a cost."
        assert _axis_token_match(content, "raven-cost-function-absent") is False

    def test_axis_token_match_stopwords_excluded(self):
        """Pitfall 5: 'vs' is a stopword -- only 'terminal' and 'instrumental' count."""
        content = (
            "Terminal values differ from instrumental values. "
            "The terminal instrumental distinction is important."
        )
        assert _axis_token_match(content, "terminal-vs-instrumental") is True

    def test_axis_token_match_short_axis(self):
        """Axis with <2 non-stopword tokens returns False."""
        assert _axis_token_match("lots of text", "a-to") is False


# =========================================================================
# extract_axes cascade
# =========================================================================


class TestExtractAxes:
    """3-tier cascade integration."""

    def test_extract_axes_frontmatter_wins(self):
        """Frontmatter axis is NOT re-found by regex/keyword."""
        content = "---\naxes: [deposit-not-detect]\n---\n# deposit-not-detect\ndeposit not detect deposit not detect"
        axes = ["deposit-not-detect"]
        results = extract_axes(content, axes)
        assert len(results) == 1
        assert results[0]["association_type"] == "frontmatter"
        assert results[0]["extracted_confidence"] == 1.0

    def test_extract_axes_regex_fallback(self):
        """No frontmatter -> header match at conf=0.7."""
        content = "# Cross-Domain CCD: deposit-not-detect\nSome body text."
        results = extract_axes(content, ["deposit-not-detect"])
        assert len(results) == 1
        assert results[0]["association_type"] == "regex"
        assert results[0]["extracted_confidence"] == 0.7

    def test_extract_axes_keyword_fallback(self):
        """No frontmatter, no header -> keyword match at conf=0.4."""
        content = "The raven has a cost function. Cost is raven cost."
        results = extract_axes(content, ["raven-cost-function-absent"])
        assert len(results) == 1
        assert results[0]["association_type"] == "keyword"
        assert results[0]["extracted_confidence"] == 0.4

    def test_extract_axes_unclassified(self):
        """No tiers fire -> unclassified at conf=0.0."""
        content = "This doc has nothing relevant."
        results = extract_axes(content, ["deposit-not-detect"])
        assert len(results) == 1
        assert results[0]["ccd_axis"] == "unclassified"
        assert results[0]["association_type"] == "unclassified"
        assert results[0]["extracted_confidence"] == 0.0

    def test_extract_axes_multi_axis(self):
        """Frontmatter gives one axis, regex finds another -> both returned."""
        content = (
            "---\naxes: [alpha]\n---\n"
            "# Cross-Domain CCD: deposit-not-detect\n"
            "Body text."
        )
        results = extract_axes(content, ["deposit-not-detect", "alpha"])
        axes_found = {r["ccd_axis"] for r in results}
        assert "alpha" in axes_found
        assert "deposit-not-detect" in axes_found
        # alpha from frontmatter
        alpha = next(r for r in results if r["ccd_axis"] == "alpha")
        assert alpha["association_type"] == "frontmatter"
        # deposit-not-detect from regex
        dnd = next(r for r in results if r["ccd_axis"] == "deposit-not-detect")
        assert dnd["association_type"] == "regex"


# =========================================================================
# Description + hash
# =========================================================================


class TestDescriptionAndHash:
    """Description extraction and content hashing."""

    def test_extract_description_skips_frontmatter(self):
        content = "---\ntitle: Foo\n---\n# Heading\n\nThis is the description."
        desc = _extract_description(content)
        assert desc == "This is the description."

    def test_extract_description_skips_headings(self):
        content = "# Heading 1\n## Heading 2\n\nProse paragraph here."
        desc = _extract_description(content)
        assert desc == "Prose paragraph here."

    def test_extract_description_truncation(self):
        content = "# Title\n\n" + "A" * 250
        desc = _extract_description(content)
        assert len(desc) == 200
        assert desc.endswith("...")

    def test_content_hash_deterministic(self):
        h1 = _content_hash("hello")
        h2 = _content_hash("hello")
        assert h1 == h2
        assert len(h1) == 16
        # Hex chars only
        assert all(c in "0123456789abcdef" for c in h1)


# =========================================================================
# Bus safety + reindex
# =========================================================================


class TestReindexDocs:
    """reindex_docs end-to-end with DuckDB."""

    def _create_memory_candidates(self, conn: duckdb.DuckDBPyConnection):
        """Create a minimal memory_candidates table with known axes."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_candidates (
                id VARCHAR PRIMARY KEY,
                ccd_axis VARCHAR NOT NULL,
                scope_rule VARCHAR,
                flood_example VARCHAR,
                status VARCHAR DEFAULT 'pending'
            )
        """)
        conn.execute(
            "INSERT INTO memory_candidates (id, ccd_axis, scope_rule) VALUES "
            "('mc1', 'deposit-not-detect', 'scope'), "
            "('mc2', 'raven-cost-function-absent', 'scope')"
        )

    def test_reindex_docs_populates_table(self, tmp_path):
        # Setup: temp docs + temp DB
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "with_fm.md").write_text(
            "---\naxes: [deposit-not-detect]\n---\n# Doc A\nBody text."
        )
        (docs_dir / "plain.md").write_text(
            "# Just a plain doc\nNothing relevant here."
        )
        (docs_dir / "subdir").mkdir()
        (docs_dir / "subdir" / "nested.md").write_text(
            "## raven-cost-function-absent\nSome content."
        )

        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        self._create_memory_candidates(conn)
        conn.close()

        result = reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
            memory_md_path=None,
        )

        assert result["total_files"] == 3
        assert result["indexed_rows"] >= 3

        # Verify DuckDB contents
        conn = duckdb.connect(db_path)
        rows = conn.execute("SELECT * FROM doc_index").fetchall()
        conn.close()
        assert len(rows) >= 3

    def test_reindex_docs_idempotent(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("---\naxes: [x]\n---\n# Doc")

        db_path = str(tmp_path / "test.db")

        result1 = reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
        )
        result2 = reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
        )

        assert result1["indexed_rows"] == result2["indexed_rows"]

        # Verify same row count in DB
        conn = duckdb.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM doc_index").fetchone()[0]
        conn.close()
        assert count == result2["indexed_rows"]

    def test_reindex_docs_unclassified_fallback(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "nothing.md").write_text("# Random\nNothing here.")

        db_path = str(tmp_path / "test.db")

        result = reindex_docs(
            db_path=db_path,
            docs_dir=str(docs_dir),
            socket_path="/nonexistent-socket",
        )

        assert result["unclassified_files"] == 1

        conn = duckdb.connect(db_path)
        rows = conn.execute(
            "SELECT ccd_axis FROM doc_index WHERE ccd_axis = 'unclassified'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1


# =========================================================================
# CLI integration
# =========================================================================


class TestCLI:
    """CLI docs group integration tests."""

    def test_cli_docs_reindex(self, tmp_path):
        from src.pipeline.cli.docs import docs_group

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.md").write_text("---\naxes: [alpha]\n---\n# Test")

        db_path = str(tmp_path / "test.db")

        runner = CliRunner()
        result = runner.invoke(
            docs_group,
            [
                "reindex",
                "--db", db_path,
                "--docs-dir", str(docs_dir),
                "--socket", "/nonexistent-socket",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Reindexing" in result.output
        assert "Indexed" in result.output


# =========================================================================
# load_axis_vocabulary
# =========================================================================


class TestLoadAxisVocabulary:
    """Axis vocabulary loading from DuckDB or MEMORY.md."""

    def test_load_from_duckdb(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE memory_candidates (
                id VARCHAR PRIMARY KEY,
                ccd_axis VARCHAR NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO memory_candidates VALUES ('m1', 'axis-one'), ('m2', 'axis-two')"
        )
        conn.close()

        result = load_axis_vocabulary(db_path=db_path, memory_md_path="/nonexistent")
        assert "always-show" in result
        assert "axis-one" in result
        assert "axis-two" in result

    def test_load_fallback_memory_md(self, tmp_path):
        md_path = tmp_path / "MEMORY.md"
        md_path.write_text(
            "## Entry\n\n"
            "**CCD axis:** `test-axis-one`\n"
            "**CCD axis:** `test-axis-two`\n"
        )

        result = load_axis_vocabulary(
            db_path="/nonexistent/db",
            memory_md_path=str(md_path),
        )
        assert "always-show" in result
        assert "test-axis-one" in result
        assert "test-axis-two" in result

    def test_load_always_includes_always_show(self, tmp_path):
        """Even with no data sources, always-show is present."""
        result = load_axis_vocabulary(
            db_path="/nonexistent/db",
            memory_md_path="/nonexistent/md",
        )
        assert result == ["always-show"]
