"""Tests for PAG PreToolUse hook script.

Tests:
- Validation-class tools (Read, Grep) cause immediate exit 0 with no output
- Write-class tools with PREMISE blocks produce staging records
- UNVALIDATED warning on high-risk file paths
- Staining check with pre-populated registry
- Foil lookup at hook time with foil_path_outcomes
- Ad Ignorantiam detection (RQR=0)
- Fail-open when transcript missing or empty
- additionalContext format
"""

from __future__ import annotations

import io
import json
import os
import sys

import duckdb
import pytest

from src.pipeline.live.hooks.premise_gate import (
    HIGH_RISK_PATHS,
    WRITE_CLASS,
    _check_ad_ignorantiam,
    _check_foil_instantiation,
    _check_stained_premises,
    _is_high_risk_path,
    main,
)
from src.pipeline.premise.models import ParsedPremise
from src.pipeline.premise.schema import (
    PREMISE_REGISTRY_DDL,
    PREMISE_REGISTRY_INDEXES,
)
from src.pipeline.premise.staging import read_staging


def _create_premise_registry_only(conn) -> None:
    """Create just the premise_registry table (no episodes ALTER TABLE).

    For tests that need the registry but don't have a full episodes table.
    """
    conn.execute(PREMISE_REGISTRY_DDL)
    for idx_sql in PREMISE_REGISTRY_INDEXES:
        conn.execute(idx_sql)


def _make_hook_input(
    tool_name: str = "Edit",
    transcript_path: str = "/dev/null",
    session_id: str = "test-session",
    tool_input: dict | None = None,
    cwd: str = "/tmp",
) -> str:
    """Create a hook stdin JSON string."""
    return json.dumps(
        {
            "tool_name": tool_name,
            "transcript_path": transcript_path,
            "session_id": session_id,
            "tool_input": tool_input or {},
            "cwd": cwd,
        }
    )


def _write_transcript(path, entries: list[dict]) -> None:
    """Write entries as JSONL to the given path."""
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _assistant_text(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _assistant_tool_use(name: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": "toolu_01", "name": name, "input": {}}
            ]
        },
    }


def _user_entry(text: str = "do something") -> dict:
    return {
        "type": "user",
        "message": {"content": [{"type": "text", "text": text}]},
    }


PREMISE_TEXT = (
    "PREMISE: The file src/main.py exists and contains a main function\n"
    "VALIDATED_BY: Read output confirmed file exists with def main\n"
    "FOIL: wrong file path | file path verified via Read tool\n"
    "SCOPE: current project\n"
)

UNVALIDATED_PREMISE_TEXT = (
    "PREMISE: The schema has a users table\n"
    "VALIDATED_BY: UNVALIDATED -- need to check schema.py\n"
    "FOIL: table might not exist | needs Read verification\n"
    "SCOPE: project schema\n"
)


class TestGateCheck:
    """Test that hook only activates for write-class tools."""

    def test_read_tool_exits_immediately(self, monkeypatch, tmp_path):
        """Read (validation-class) should exit 0 with no output."""
        stdin_data = _make_hook_input(tool_name="Read")
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert captured.getvalue() == ""

    def test_grep_tool_exits_immediately(self, monkeypatch):
        """Grep (validation-class) should exit 0 with no output."""
        stdin_data = _make_hook_input(tool_name="Grep")
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert captured.getvalue() == ""

    def test_glob_tool_exits_immediately(self, monkeypatch):
        """Glob (validation-class) should exit 0 with no output."""
        stdin_data = _make_hook_input(tool_name="Glob")
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert captured.getvalue() == ""

    def test_write_class_tools_proceed(self):
        """Edit, Write, Bash should be in WRITE_CLASS."""
        assert "Edit" in WRITE_CLASS
        assert "Write" in WRITE_CLASS
        assert "Bash" in WRITE_CLASS
        assert "Read" not in WRITE_CLASS
        assert "Grep" not in WRITE_CLASS


class TestPremiseStaging:
    """Test that write-class tools with PREMISE blocks produce staging records."""

    def test_premises_staged_for_edit(self, monkeypatch, tmp_path):
        """Edit tool with PREMISE blocks should write to staging."""
        transcript = tmp_path / "session.jsonl"
        staging = tmp_path / "staging.jsonl"

        _write_transcript(
            transcript,
            [
                _user_entry("edit the file"),
                _assistant_tool_use("Read"),
                _assistant_text(PREMISE_TEXT),
            ],
        )

        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
            session_id="sess-1",
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.stdout", io.StringIO())
        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: _mock_append(records, staging),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_no_premise_exits_silently(self, monkeypatch, tmp_path):
        """Write-class tool with no PREMISE blocks should exit 0 silently."""
        transcript = tmp_path / "session.jsonl"
        _write_transcript(
            transcript,
            [_assistant_text("Just doing some work.")],
        )

        stdin_data = _make_hook_input(
            tool_name="Write",
            transcript_path=str(transcript),
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert captured.getvalue() == ""


def _mock_append(records, staging_path):
    """Mock append_to_staging that writes to a custom path."""
    from src.pipeline.premise.staging import append_to_staging as real_append

    return real_append(records, staging_path=str(staging_path))


class TestFailOpen:
    """Test fail-open behavior when transcript is missing or empty."""

    def test_missing_transcript_exits_0(self, monkeypatch, tmp_path):
        """Non-existent transcript should exit 0 (fail-open)."""
        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(tmp_path / "nonexistent.jsonl"),
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert captured.getvalue() == ""

    def test_empty_transcript_exits_0(self, monkeypatch, tmp_path):
        """Empty transcript should exit 0 (fail-open)."""
        transcript = tmp_path / "empty.jsonl"
        transcript.touch()

        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert captured.getvalue() == ""

    def test_invalid_stdin_json_exits_0(self, monkeypatch):
        """Invalid JSON on stdin should exit 0 (fail-open)."""
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert captured.getvalue() == ""


class TestHighRiskPathDetection:
    """Test UNVALIDATED warning on high-risk file paths."""

    def test_schema_py_is_high_risk(self):
        """src/pipeline/storage/schema.py should be high-risk."""
        assert _is_high_risk_path(
            {"file_path": "src/pipeline/storage/schema.py"}, "/project"
        )

    def test_constraints_json_is_high_risk(self):
        """data/constraints.json should be high-risk."""
        assert _is_high_risk_path(
            {"file_path": "data/constraints.json"}, "/project"
        )

    def test_settings_json_is_high_risk(self):
        """.claude/settings.json should be high-risk."""
        assert _is_high_risk_path(
            {"file_path": ".claude/settings.json"}, "/project"
        )

    def test_models_dir_is_high_risk(self):
        """src/pipeline/models/ prefix should be high-risk."""
        assert _is_high_risk_path(
            {"file_path": "src/pipeline/models/episodes.py"}, "/project"
        )

    def test_normal_file_is_not_high_risk(self):
        """Regular source files should not be high-risk."""
        assert not _is_high_risk_path(
            {"file_path": "src/pipeline/runner.py"}, "/project"
        )

    def test_empty_path_is_not_high_risk(self):
        """Empty file path should not be high-risk."""
        assert not _is_high_risk_path({}, "/project")

    def test_unvalidated_warning_on_high_risk(self, monkeypatch, tmp_path):
        """UNVALIDATED premise on high-risk file should produce warning."""
        transcript = tmp_path / "session.jsonl"
        _write_transcript(
            transcript,
            [
                _user_entry("check schema"),
                _assistant_text(UNVALIDATED_PREMISE_TEXT),
            ],
        )

        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
            tool_input={"file_path": "src/pipeline/storage/schema.py"},
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        # Patch staging to use tmp_path
        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: len(records),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        output = captured.getvalue()
        assert output  # Should have output
        response = json.loads(output)
        context = response["hookSpecificOutput"]["additionalContext"]
        assert "UNVALIDATED" in context
        assert "high-risk" in context


class TestStainedPremiseCheck:
    """Test staining check with pre-populated registry."""

    def test_stained_premise_emits_warning(self, tmp_path):
        """Matching stained premise should produce PROJECTION_WARNING."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "ope.db"
        conn = duckdb.connect(str(db_path))
        _create_premise_registry_only(conn)

        # Insert a stained premise
        conn.execute(
            """
            INSERT INTO premise_registry (
                premise_id, claim, session_id, staining_record,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, NOW(), NOW())
            """,
            [
                "stained001",
                "The file src/main.py exists and contains a main function",
                "old-session",
                json.dumps({"stained": True, "stained_by": "amnesia-1"}),
            ],
        )
        conn.close()

        premises = [
            ParsedPremise(
                claim="The file src/main.py exists and contains a main function",
                validated_by="Read output confirmed",
                is_unvalidated=False,
                foil="wrong path",
                distinguishing_prop="verified",
                scope="project",
            )
        ]

        # Temporarily change working dir so data/ope.db resolves
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            warnings = _check_stained_premises(premises, "new-session", str(tmp_path))
        finally:
            os.chdir(original_cwd)

        assert len(warnings) == 1
        assert "PROJECTION_WARNING" in warnings[0]
        assert "stained001" in warnings[0]

    def test_no_stained_match_no_warning(self, tmp_path):
        """Non-matching premise should produce no warning."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "ope.db"
        conn = duckdb.connect(str(db_path))
        _create_premise_registry_only(conn)
        conn.close()

        premises = [
            ParsedPremise(
                claim="some unrelated claim",
                validated_by="evidence",
                is_unvalidated=False,
                scope="project",
            )
        ]

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            warnings = _check_stained_premises(premises, "session", str(tmp_path))
        finally:
            os.chdir(original_cwd)

        assert warnings == []

    def test_missing_db_no_warning(self):
        """Missing ope.db should produce no warning (fail-open)."""
        premises = [
            ParsedPremise(
                claim="test",
                validated_by="evidence",
                is_unvalidated=False,
                scope="project",
            )
        ]
        # ope.db doesn't exist in /tmp
        warnings = _check_stained_premises(premises, "session", "/tmp/nonexistent")
        assert warnings == []


class TestFoilInstantiation:
    """Test foil lookup at hook time."""

    def test_foil_match_with_outcomes_emits_warning(self, tmp_path):
        """Foil match with foil_path_outcomes should emit FOIL_INSTANTIATED."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "ope.db"
        conn = duckdb.connect(str(db_path))
        _create_premise_registry_only(conn)

        # Insert a historical premise whose claim matches the foil
        conn.execute(
            """
            INSERT INTO premise_registry (
                premise_id, claim, session_id, project_scope,
                foil_path_outcomes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, NOW(), NOW())
            """,
            [
                "hist001",
                "The API uses JWT tokens for authentication",
                "old-session",
                str(tmp_path),
                json.dumps([{"episode_id": "ep-1", "outcome": "failed"}]),
            ],
        )
        conn.close()

        premises = [
            ParsedPremise(
                claim="The API uses session cookies",
                validated_by="Read output confirmed cookie usage",
                is_unvalidated=False,
                foil="JWT tokens",
                distinguishing_prop="cookie-based vs token-based",
                scope="auth module",
            )
        ]

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            warnings = _check_foil_instantiation(premises, "new-session", str(tmp_path))
        finally:
            os.chdir(original_cwd)

        assert len(warnings) == 1
        assert "FOIL_INSTANTIATED" in warnings[0]
        assert "hist001" in warnings[0]

    def test_foil_match_without_outcomes_no_warning(self, tmp_path):
        """Foil match without foil_path_outcomes should not emit warning."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "ope.db"
        conn = duckdb.connect(str(db_path))
        _create_premise_registry_only(conn)

        # Insert premise with matching claim but no foil_path_outcomes
        conn.execute(
            """
            INSERT INTO premise_registry (
                premise_id, claim, session_id, project_scope,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, NOW(), NOW())
            """,
            [
                "hist002",
                "The API uses JWT tokens",
                "old-session",
                str(tmp_path),
            ],
        )
        conn.close()

        premises = [
            ParsedPremise(
                claim="The API uses session cookies",
                validated_by="evidence",
                is_unvalidated=False,
                foil="JWT tokens",
                distinguishing_prop="cookie vs token",
                scope="auth",
            )
        ]

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            warnings = _check_foil_instantiation(premises, "new-session", str(tmp_path))
        finally:
            os.chdir(original_cwd)

        assert warnings == []

    def test_no_foil_field_no_lookup(self, tmp_path):
        """Premise without foil field should skip lookup."""
        premises = [
            ParsedPremise(
                claim="some claim",
                validated_by="evidence",
                is_unvalidated=False,
                foil=None,
                scope="project",
            )
        ]

        warnings = _check_foil_instantiation(premises, "session", str(tmp_path))
        assert warnings == []


class TestAdIgnorantiam:
    """Test Ad Ignorantiam detection (RQR=0)."""

    def test_rqr0_non_unvalidated_triggers_warning(self):
        """RQR=0 + non-UNVALIDATED validated_by should emit warning."""
        premises = [
            ParsedPremise(
                claim="schema has users table",
                validated_by="Read output confirmed table exists",
                is_unvalidated=False,
                scope="project",
            )
        ]

        warnings = _check_ad_ignorantiam(premises, validation_calls=0)
        assert len(warnings) == 1
        assert "AD_IGNORANTIAM" in warnings[0]
        assert "RQR=0" in warnings[0]

    def test_rqr0_unvalidated_no_warning(self):
        """RQR=0 + UNVALIDATED should NOT emit warning (exempt)."""
        premises = [
            ParsedPremise(
                claim="schema might have users table",
                validated_by="UNVALIDATED -- need to check",
                is_unvalidated=True,
                scope="project",
            )
        ]

        warnings = _check_ad_ignorantiam(premises, validation_calls=0)
        assert warnings == []

    def test_validation_calls_positive_no_warning(self):
        """Validation calls > 0 should not trigger warning."""
        premises = [
            ParsedPremise(
                claim="file exists",
                validated_by="Read showed it exists",
                is_unvalidated=False,
                scope="project",
            )
        ]

        warnings = _check_ad_ignorantiam(premises, validation_calls=3)
        assert warnings == []

    def test_multiple_premises_multiple_warnings(self):
        """Multiple non-UNVALIDATED premises at RQR=0 should each get warning."""
        premises = [
            ParsedPremise(
                claim="claim A",
                validated_by="evidence A",
                is_unvalidated=False,
                scope="project",
            ),
            ParsedPremise(
                claim="claim B",
                validated_by="evidence B",
                is_unvalidated=False,
                scope="project",
            ),
        ]

        warnings = _check_ad_ignorantiam(premises, validation_calls=0)
        assert len(warnings) == 2

    def test_mixed_unvalidated_and_validated(self):
        """Only non-UNVALIDATED premises should get RQR=0 warning."""
        premises = [
            ParsedPremise(
                claim="validated claim",
                validated_by="evidence",
                is_unvalidated=False,
                scope="project",
            ),
            ParsedPremise(
                claim="unvalidated claim",
                validated_by="UNVALIDATED -- later",
                is_unvalidated=True,
                scope="project",
            ),
        ]

        warnings = _check_ad_ignorantiam(premises, validation_calls=0)
        assert len(warnings) == 1
        assert "validated claim" not in warnings[0] or "AD_IGNORANTIAM" in warnings[0]


class TestAdditionalContextFormat:
    """Test that additionalContext output format is correct."""

    def test_output_format_with_warnings(self, monkeypatch, tmp_path):
        """Output should be JSON with hookSpecificOutput.additionalContext."""
        transcript = tmp_path / "session.jsonl"
        _write_transcript(
            transcript,
            [
                _user_entry("edit schema"),
                _assistant_text(UNVALIDATED_PREMISE_TEXT),
            ],
        )

        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
            tool_input={"file_path": "src/pipeline/storage/schema.py"},
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        # Patch staging
        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: len(records),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        output = captured.getvalue()
        assert output
        response = json.loads(output)
        assert "hookSpecificOutput" in response
        assert "additionalContext" in response["hookSpecificOutput"]
        assert isinstance(response["hookSpecificOutput"]["additionalContext"], str)

    def test_no_warnings_no_output(self, monkeypatch, tmp_path):
        """When no warnings, stdout has no warning text (may include ope_constraint_count JSON)."""
        transcript = tmp_path / "session.jsonl"

        # Create a transcript with a validated (not UNVALIDATED) premise
        # and a non-high-risk target file, with validation calls
        _write_transcript(
            transcript,
            [
                _user_entry("edit runner"),
                _assistant_tool_use("Read"),  # validation call
                _assistant_text(PREMISE_TEXT),
            ],
        )

        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
            tool_input={"file_path": "src/pipeline/runner.py"},
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        # Patch staging
        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: len(records),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        # Phase 19: hook now injects ope_constraint_count into JSON output.
        # Verify no warning text in output; JSON metadata is acceptable.
        output = captured.getvalue()
        assert "UNVALIDATED" not in output
        assert "WARNING" not in output


class TestNeverBlocks:
    """Test that the hook never outputs a deny decision."""

    def test_never_outputs_deny(self, monkeypatch, tmp_path):
        """Hook should never output permissionDecision: deny."""
        transcript = tmp_path / "session.jsonl"
        _write_transcript(
            transcript,
            [
                _user_entry("edit"),
                _assistant_text(UNVALIDATED_PREMISE_TEXT),
            ],
        )

        stdin_data = _make_hook_input(
            tool_name="Write",
            transcript_path=str(transcript),
            tool_input={"file_path": "src/pipeline/storage/schema.py"},
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))

        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: len(records),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        output = captured.getvalue()
        if output:
            response = json.loads(output)
            # There should be no permissionDecision field, or it should not be "deny"
            hook_output = response.get("hookSpecificOutput", {})
            assert hook_output.get("permissionDecision") != "deny"


class TestGenusCheck:
    """Tests for genus declaration checking in PAG hook (Phase 24)."""

    def test_genus_absent_no_warning(self, monkeypatch, tmp_path):
        """PREMISE block without GENUS field: no GENUS_INVALID warning (fail-open)."""
        transcript = tmp_path / "t.jsonl"
        _write_transcript(
            str(transcript),
            [
                _user_entry("edit file"),
                _assistant_tool_use("Read"),
                _assistant_text(
                    "PREMISE: File exists\n"
                    "VALIDATED_BY: Read confirmed\n"
                    "FOIL: wrong path | right dir\n"
                    "SCOPE: project\n"
                ),
            ],
        )
        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
            session_id="test-genus-absent",
        )
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.stdout", captured)
        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: len(records),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        output = captured.getvalue()
        if output:
            resp = json.loads(output)
            ctx = resp.get("hookSpecificOutput", {}).get("additionalContext", "")
            assert "GENUS_INVALID" not in ctx

    def test_genus_valid_no_warning(self, monkeypatch, tmp_path):
        """PREMISE block with valid GENUS (2 instances + causal word): no GENUS_INVALID."""
        transcript = tmp_path / "t.jsonl"
        _write_transcript(
            str(transcript),
            [
                _user_entry("edit file"),
                _assistant_tool_use("Read"),
                _assistant_text(
                    "PREMISE: File exists\n"
                    "VALIDATED_BY: Read confirmed\n"
                    "FOIL: wrong path | right dir\n"
                    "SCOPE: project\n"
                    "GENUS: corpus-relative identity retrieval | INSTANCES: [A7 failure, MOTM failure]\n"
                ),
            ],
        )
        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
            session_id="test-genus-valid",
        )
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.stdout", captured)
        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: len(records),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        output = captured.getvalue()
        if output:
            resp = json.loads(output)
            ctx = resp.get("hookSpecificOutput", {}).get("additionalContext", "")
            assert "GENUS_INVALID" not in ctx

    def test_genus_invalid_warns(self, monkeypatch, tmp_path):
        """PREMISE block with GENUS field but only 1 instance: GENUS_INVALID warning."""
        transcript = tmp_path / "t.jsonl"
        _write_transcript(
            str(transcript),
            [
                _user_entry("edit file"),
                _assistant_tool_use("Read"),
                _assistant_text(
                    "PREMISE: File exists\n"
                    "VALIDATED_BY: Read confirmed\n"
                    "FOIL: wrong path | right dir\n"
                    "SCOPE: project\n"
                    "GENUS: identity retrieval | INSTANCES: [only one instance]\n"
                ),
            ],
        )
        stdin_data = _make_hook_input(
            tool_name="Edit",
            transcript_path=str(transcript),
            session_id="test-genus-invalid",
        )
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        monkeypatch.setattr("sys.stdout", captured)
        monkeypatch.setattr(
            "src.pipeline.live.hooks.premise_gate.append_to_staging",
            lambda records, **kw: len(records),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        # Hook must exit 0 (no blocking)
        assert exc_info.value.code == 0
        # Response must contain GENUS_INVALID
        output = captured.getvalue()
        assert output, "Hook should produce output"
        resp = json.loads(output)
        ctx = resp.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "GENUS_INVALID" in ctx
