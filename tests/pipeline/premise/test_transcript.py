"""Tests for transcript backward scanner.

Tests:
- read_recent_assistant_text returns text content from assistant entries
- count_validation_calls_since_last_user counts Read/Grep/Glob/WebFetch correctly
- Handles empty files, non-existent files, and mixed entry types
"""

from __future__ import annotations

import json

import pytest

from src.pipeline.premise.transcript import (
    count_validation_calls_since_last_user,
    read_recent_assistant_text,
)


def _write_jsonl(path, entries: list[dict]) -> None:
    """Write entries as JSONL to the given path."""
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _assistant_text(text: str, uuid: str = "abc") -> dict:
    """Create a JSONL entry mimicking an assistant text entry."""
    return {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
        "uuid": uuid,
    }


def _assistant_tool_use(
    name: str, tool_id: str = "toolu_01", uuid: str = "def"
) -> dict:
    """Create a JSONL entry mimicking an assistant tool_use entry."""
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": tool_id, "name": name, "input": {}}
            ]
        },
        "uuid": uuid,
    }


def _user_entry(text: str = "do something", uuid: str = "usr") -> dict:
    """Create a JSONL entry mimicking a user entry."""
    return {
        "type": "user",
        "message": {"content": [{"type": "text", "text": text}]},
        "uuid": uuid,
    }


def _system_entry(uuid: str = "sys") -> dict:
    """Create a JSONL entry mimicking a system entry."""
    return {
        "type": "system",
        "message": {"content": "system info"},
        "uuid": uuid,
    }


class TestReadRecentAssistantText:
    """Tests for read_recent_assistant_text."""

    def test_returns_text_from_assistant_entries(self, tmp_path):
        """Should extract text content from assistant entries."""
        entries = [
            _assistant_text("Hello world"),
            _assistant_text("PREMISE: something is true\nVALIDATED_BY: Read output\n"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        texts = read_recent_assistant_text(str(path))
        assert len(texts) == 2
        assert texts[0] == "Hello world"
        assert "PREMISE: something is true" in texts[1]

    def test_returns_empty_for_nonexistent_file(self, tmp_path):
        """Should return empty list when file doesn't exist."""
        path = tmp_path / "nonexistent.jsonl"
        assert read_recent_assistant_text(str(path)) == []

    def test_returns_empty_for_empty_file(self, tmp_path):
        """Should return empty list for an empty file."""
        path = tmp_path / "empty.jsonl"
        path.touch()
        assert read_recent_assistant_text(str(path)) == []

    def test_skips_non_json_lines(self, tmp_path):
        """Should skip lines that aren't valid JSON."""
        path = tmp_path / "session.jsonl"
        with open(path, "w") as f:
            f.write("not json\n")
            f.write(json.dumps(_assistant_text("valid text")) + "\n")
            f.write("also not json\n")

        texts = read_recent_assistant_text(str(path))
        assert texts == ["valid text"]

    def test_skips_non_assistant_entries(self, tmp_path):
        """Should only extract text from assistant entries."""
        entries = [
            _user_entry("user message"),
            _assistant_text("assistant text"),
            _system_entry(),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        texts = read_recent_assistant_text(str(path))
        assert texts == ["assistant text"]

    def test_skips_tool_use_content(self, tmp_path):
        """Should only extract text content, not tool_use content."""
        entries = [
            _assistant_text("text content"),
            _assistant_tool_use("Edit"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        texts = read_recent_assistant_text(str(path))
        assert texts == ["text content"]

    def test_handles_missing_content_field(self, tmp_path):
        """Should skip entries with missing or malformed content."""
        entries = [
            {"type": "assistant", "message": {}},
            {"type": "assistant", "message": {"content": "not a list"}},
            _assistant_text("good text"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        texts = read_recent_assistant_text(str(path))
        assert texts == ["good text"]

    def test_chronological_order(self, tmp_path):
        """Should return texts in chronological order (oldest first)."""
        entries = [
            _assistant_text("first"),
            _assistant_text("second"),
            _assistant_text("third"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        texts = read_recent_assistant_text(str(path))
        assert texts == ["first", "second", "third"]

    def test_max_lines_limit(self, tmp_path):
        """Should only read up to max_lines lines."""
        entries = [_assistant_text(f"line {i}") for i in range(100)]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        texts = read_recent_assistant_text(str(path), max_lines=10)
        # Should return texts from the LAST 10 lines
        assert len(texts) == 10
        assert texts[0] == "line 90"
        assert texts[-1] == "line 99"

    def test_mixed_entry_types(self, tmp_path):
        """Should handle a realistic mix of entry types."""
        entries = [
            _user_entry("please edit the file"),
            _assistant_text("PREMISE: file exists\nVALIDATED_BY: Read\nFOIL: wrong path\nSCOPE: project\n"),
            _assistant_tool_use("Read", uuid="r1"),
            _assistant_text("Let me edit the file."),
            _assistant_tool_use("Edit", uuid="e1"),
            _system_entry(),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        texts = read_recent_assistant_text(str(path))
        assert len(texts) == 2
        assert "PREMISE: file exists" in texts[0]
        assert "Let me edit the file." in texts[1]


class TestCountValidationCallsSinceLastUser:
    """Tests for count_validation_calls_since_last_user."""

    def test_counts_validation_tools(self, tmp_path):
        """Should count Read, Grep, Glob, WebFetch tool_use entries."""
        entries = [
            _user_entry("check something"),
            _assistant_tool_use("Read", uuid="r1"),
            _assistant_tool_use("Grep", uuid="r2"),
            _assistant_tool_use("Glob", uuid="r3"),
            _assistant_tool_use("WebFetch", uuid="r4"),
            _assistant_text("PREMISE: something"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        count = count_validation_calls_since_last_user(str(path))
        assert count == 4

    def test_stops_at_user_boundary(self, tmp_path):
        """Should stop counting at the most recent user entry."""
        entries = [
            _assistant_tool_use("Read", uuid="r0"),  # Before user -- should NOT count
            _user_entry("do something"),
            _assistant_tool_use("Read", uuid="r1"),
            _assistant_tool_use("Grep", uuid="r2"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        count = count_validation_calls_since_last_user(str(path))
        assert count == 2

    def test_ignores_write_class_tools(self, tmp_path):
        """Should not count Edit, Write, Bash."""
        entries = [
            _user_entry("edit file"),
            _assistant_tool_use("Read", uuid="r1"),
            _assistant_tool_use("Edit", uuid="e1"),
            _assistant_tool_use("Write", uuid="w1"),
            _assistant_tool_use("Bash", uuid="b1"),
            _assistant_tool_use("Grep", uuid="g1"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        count = count_validation_calls_since_last_user(str(path))
        assert count == 2  # Only Read and Grep

    def test_returns_zero_for_nonexistent_file(self, tmp_path):
        """Should return 0 for non-existent files."""
        path = tmp_path / "nonexistent.jsonl"
        assert count_validation_calls_since_last_user(str(path)) == 0

    def test_returns_zero_for_empty_file(self, tmp_path):
        """Should return 0 for empty files."""
        path = tmp_path / "empty.jsonl"
        path.touch()
        assert count_validation_calls_since_last_user(str(path)) == 0

    def test_no_user_entry_counts_all(self, tmp_path):
        """Should count all validation calls if no user entry found."""
        entries = [
            _assistant_tool_use("Read", uuid="r1"),
            _assistant_tool_use("Grep", uuid="r2"),
            _assistant_tool_use("Read", uuid="r3"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        count = count_validation_calls_since_last_user(str(path))
        assert count == 3

    def test_zero_validation_calls(self, tmp_path):
        """Should return 0 when only write-class tools used."""
        entries = [
            _user_entry("write something"),
            _assistant_text("PREMISE: claim"),
            _assistant_tool_use("Edit", uuid="e1"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        count = count_validation_calls_since_last_user(str(path))
        assert count == 0

    def test_skips_text_entries_in_count(self, tmp_path):
        """Should not count assistant text entries as validation calls."""
        entries = [
            _user_entry("check file"),
            _assistant_text("Let me check that."),
            _assistant_tool_use("Read", uuid="r1"),
            _assistant_text("PREMISE: file exists"),
        ]
        path = tmp_path / "session.jsonl"
        _write_jsonl(path, entries)

        count = count_validation_calls_since_last_user(str(path))
        assert count == 1
