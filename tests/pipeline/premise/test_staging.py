"""Tests for premise staging JSONL writer.

Tests:
- append_to_staging creates file and writes records
- read_staging reads back correctly
- clear_staging empties file and returns count
- Append is truly append (write twice, read all)
- Corrupt line handling
"""

from __future__ import annotations

import json

import pytest

from src.pipeline.premise.staging import (
    append_to_staging,
    clear_staging,
    read_staging,
)


class TestAppendToStaging:
    """Tests for append_to_staging."""

    def test_creates_file_and_writes_records(self, tmp_path):
        """Should create the staging file and write records."""
        staging = str(tmp_path / "staging.jsonl")
        records = [
            {"premise_id": "abc123", "claim": "test claim"},
            {"premise_id": "def456", "claim": "another claim"},
        ]

        written = append_to_staging(records, staging_path=staging)
        assert written == 2
        assert (tmp_path / "staging.jsonl").exists()

    def test_creates_parent_directory(self, tmp_path):
        """Should create parent directories if needed."""
        staging = str(tmp_path / "subdir" / "staging.jsonl")
        records = [{"premise_id": "abc", "claim": "test"}]

        written = append_to_staging(records, staging_path=staging)
        assert written == 1
        assert (tmp_path / "subdir" / "staging.jsonl").exists()

    def test_empty_records_writes_nothing(self, tmp_path):
        """Should return 0 and not create file for empty records."""
        staging = str(tmp_path / "staging.jsonl")
        written = append_to_staging([], staging_path=staging)
        assert written == 0

    def test_records_are_valid_json_lines(self, tmp_path):
        """Each line should be valid JSON."""
        staging = str(tmp_path / "staging.jsonl")
        records = [
            {"premise_id": "abc", "claim": "test", "scope": "project"},
        ]
        append_to_staging(records, staging_path=staging)

        with open(staging) as f:
            lines = f.readlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["premise_id"] == "abc"
        assert parsed["claim"] == "test"

    def test_truly_appends(self, tmp_path):
        """Writing twice should result in all records present."""
        staging = str(tmp_path / "staging.jsonl")

        append_to_staging(
            [{"premise_id": "first", "claim": "one"}], staging_path=staging
        )
        append_to_staging(
            [{"premise_id": "second", "claim": "two"}], staging_path=staging
        )

        with open(staging) as f:
            lines = f.readlines()
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["premise_id"] == "first"
        assert second["premise_id"] == "second"


class TestReadStaging:
    """Tests for read_staging."""

    def test_reads_back_records(self, tmp_path):
        """Should read all records that were written."""
        staging = str(tmp_path / "staging.jsonl")
        records = [
            {"premise_id": "abc", "claim": "test claim"},
            {"premise_id": "def", "claim": "another"},
        ]
        append_to_staging(records, staging_path=staging)

        result = read_staging(staging_path=staging)
        assert len(result) == 2
        assert result[0]["premise_id"] == "abc"
        assert result[1]["premise_id"] == "def"

    def test_returns_empty_for_nonexistent_file(self, tmp_path):
        """Should return empty list for non-existent file."""
        staging = str(tmp_path / "nonexistent.jsonl")
        assert read_staging(staging_path=staging) == []

    def test_skips_corrupt_lines(self, tmp_path):
        """Should skip corrupt lines and read valid ones."""
        staging = str(tmp_path / "staging.jsonl")
        with open(staging, "w") as f:
            f.write(json.dumps({"premise_id": "good1", "claim": "ok"}) + "\n")
            f.write("this is not json\n")
            f.write(json.dumps({"premise_id": "good2", "claim": "ok"}) + "\n")

        result = read_staging(staging_path=staging)
        assert len(result) == 2
        assert result[0]["premise_id"] == "good1"
        assert result[1]["premise_id"] == "good2"

    def test_skips_empty_lines(self, tmp_path):
        """Should skip empty lines."""
        staging = str(tmp_path / "staging.jsonl")
        with open(staging, "w") as f:
            f.write(json.dumps({"premise_id": "a"}) + "\n")
            f.write("\n")
            f.write("\n")
            f.write(json.dumps({"premise_id": "b"}) + "\n")

        result = read_staging(staging_path=staging)
        assert len(result) == 2


class TestClearStaging:
    """Tests for clear_staging."""

    def test_clears_file_and_returns_count(self, tmp_path):
        """Should truncate file and return previous record count."""
        staging = str(tmp_path / "staging.jsonl")
        records = [
            {"premise_id": "a", "claim": "one"},
            {"premise_id": "b", "claim": "two"},
            {"premise_id": "c", "claim": "three"},
        ]
        append_to_staging(records, staging_path=staging)

        count = clear_staging(staging_path=staging)
        assert count == 3

        # File should now be empty
        result = read_staging(staging_path=staging)
        assert result == []

    def test_returns_zero_for_nonexistent_file(self, tmp_path):
        """Should return 0 for non-existent file."""
        staging = str(tmp_path / "nonexistent.jsonl")
        count = clear_staging(staging_path=staging)
        assert count == 0

    def test_returns_zero_for_empty_file(self, tmp_path):
        """Should return 0 for already empty file."""
        staging = str(tmp_path / "staging.jsonl")
        with open(staging, "w") as f:
            pass

        count = clear_staging(staging_path=staging)
        assert count == 0
