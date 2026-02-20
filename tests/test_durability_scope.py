"""Tests for session scope extraction from event payloads.

Covers:
- Extract file paths from Read/Edit/Write tool payloads (details.file_path)
- Extract file paths from Bash command text (common.text)
- Handle both dict and JSON string payload formats
- Return empty list when no file paths found
- Deduplicate and sort paths
- Handle malformed payloads gracefully
"""

from __future__ import annotations

import json

import pytest

from src.pipeline.durability.scope_extractor import extract_session_scope


class TestExtractSessionScope:
    """Tests for extract_session_scope() function."""

    def test_extracts_from_read_tool_dict_payload(self):
        """Extract file_path from Read tool payload as dict."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "details": {"file_path": "src/pipeline/config.py"},
                    "common": {"text": "Reading config file"},
                },
            }
        ]
        result = extract_session_scope(events)
        assert result == ["src/pipeline/config.py"]

    def test_extracts_from_write_tool_dict_payload(self):
        """Extract file_path from Write tool payload as dict."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "details": {"file_path": "src/pipeline/storage/writer.py"},
                    "common": {"text": "Writing to file"},
                },
            }
        ]
        result = extract_session_scope(events)
        assert result == ["src/pipeline/storage/writer.py"]

    def test_extracts_from_json_string_payload(self):
        """Extract file_path from payload stored as JSON string (DuckDB)."""
        payload = json.dumps(
            {
                "details": {"file_path": "tests/test_writer.py"},
                "common": {"text": "Running tests"},
            }
        )
        events = [{"event_id": "e1", "payload": payload}]
        result = extract_session_scope(events)
        assert result == ["tests/test_writer.py"]

    def test_extracts_from_bash_command_text(self):
        """Extract file paths from Bash command text in common.text."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "common": {
                        "text": "python -m pytest tests/test_config.py -v"
                    },
                },
            }
        ]
        result = extract_session_scope(events)
        assert "tests/test_config.py" in result

    def test_extracts_multiple_paths_from_bash(self):
        """Extract multiple file paths from a single Bash command."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "common": {
                        "text": "cp src/pipeline/runner.py src/pipeline/runner_backup.py"
                    },
                },
            }
        ]
        result = extract_session_scope(events)
        assert "src/pipeline/runner.py" in result
        assert "src/pipeline/runner_backup.py" in result

    def test_returns_empty_list_when_no_paths(self):
        """Return empty list when no file paths are found."""
        events = [
            {
                "event_id": "e1",
                "payload": {"common": {"text": "echo hello world"}},
            }
        ]
        result = extract_session_scope(events)
        assert result == []

    def test_returns_empty_list_for_empty_events(self):
        """Return empty list for empty event list."""
        result = extract_session_scope([])
        assert result == []

    def test_deduplicates_paths(self):
        """Deduplicate paths from multiple events touching same file."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "details": {"file_path": "src/pipeline/config.py"},
                },
            },
            {
                "event_id": "e2",
                "payload": {
                    "details": {"file_path": "src/pipeline/config.py"},
                },
            },
        ]
        result = extract_session_scope(events)
        assert result == ["src/pipeline/config.py"]

    def test_sorts_paths(self):
        """Return sorted list of paths."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "details": {"file_path": "tests/test_writer.py"},
                },
            },
            {
                "event_id": "e2",
                "payload": {
                    "details": {"file_path": "src/pipeline/config.py"},
                },
            },
            {
                "event_id": "e3",
                "payload": {
                    "details": {"file_path": "data/config.yaml"},
                },
            },
        ]
        result = extract_session_scope(events)
        assert result == sorted(result)

    def test_normalizes_leading_dot_slash(self):
        """Normalize paths by stripping leading ./."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "details": {"file_path": "./src/pipeline/config.py"},
                },
            }
        ]
        result = extract_session_scope(events)
        assert result == ["src/pipeline/config.py"]

    def test_handles_malformed_payload_gracefully(self):
        """Handle malformed payloads without crashing."""
        events = [
            {"event_id": "e1", "payload": None},
            {"event_id": "e2", "payload": 42},
            {"event_id": "e3", "payload": "not valid json{"},
            {"event_id": "e4"},  # No payload key at all
            {"event_id": "e5", "payload": {"details": "not a dict"}},
            {"event_id": "e6", "payload": {"details": {"file_path": ""}}},
            {"event_id": "e7", "payload": {"details": {"file_path": 123}}},
        ]
        # Should not raise
        result = extract_session_scope(events)
        assert isinstance(result, list)

    def test_combines_details_and_bash_paths(self):
        """Combine paths from both details.file_path and Bash commands."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "details": {"file_path": "src/pipeline/config.py"},
                },
            },
            {
                "event_id": "e2",
                "payload": {
                    "common": {
                        "text": "python -m pytest tests/test_config.py"
                    },
                },
            },
        ]
        result = extract_session_scope(events)
        assert "src/pipeline/config.py" in result
        assert "tests/test_config.py" in result

    def test_json_string_details(self):
        """Handle details stored as JSON string within payload dict."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "details": json.dumps(
                        {"file_path": "src/pipeline/utils.py"}
                    ),
                },
            }
        ]
        result = extract_session_scope(events)
        assert result == ["src/pipeline/utils.py"]

    def test_json_string_common(self):
        """Handle common stored as JSON string within payload dict."""
        events = [
            {
                "event_id": "e1",
                "payload": {
                    "common": json.dumps(
                        {"text": "python src/pipeline/runner.py"}
                    ),
                },
            }
        ]
        result = extract_session_scope(events)
        assert "src/pipeline/runner.py" in result
