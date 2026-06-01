#!/usr/bin/env python3
"""Unit tests for daemon/claude_usage_daemon_windows.py — TOKEN-01.

Run: python -m pytest daemon/tests/test_windows_token.py -x -q
"""
import json
from pathlib import Path

import pytest

from daemon.claude_usage_daemon_windows import _extract_access_token, read_token, _windows_credential_candidates, _read_expiry


FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_nested_shape():
    """_extract_access_token handles the real Windows claudeAiOauth nested shape."""
    blob = (FIXTURES / "credentials_nested.json").read_text()
    assert _extract_access_token(blob) == "sk-ant-test-1234"


def test_extract_direct_shape():
    """_extract_access_token handles the legacy direct accessToken shape."""
    blob = (FIXTURES / "credentials_direct.json").read_text()
    assert _extract_access_token(blob) == "sk-ant-test-5678"


def test_read_token_env_override(tmp_path, monkeypatch):
    """read_token() honours CLAUDE_CREDENTIALS_PATH env override (D-03)."""
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"accessToken": "sk-ant-test-ENV"}))
    monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(creds))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert read_token() == "sk-ant-test-ENV"


def test_read_token_primary_path(tmp_path, monkeypatch):
    """read_token() reads from the primary candidate path (first hit wins)."""
    creds = tmp_path / ".claude" / ".credentials.json"
    creds.parent.mkdir(parents=True)
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-test-PRIMARY"}}))
    monkeypatch.delenv("CLAUDE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # Monkeypatch _windows_credential_candidates to return only our tmp path
    import daemon.claude_usage_daemon_windows as mod
    monkeypatch.setattr(mod, "_windows_credential_candidates", lambda: [creds])
    assert read_token() == "sk-ant-test-PRIMARY"


def test_read_token_localappdata_fallback(tmp_path, monkeypatch):
    """read_token() falls back to %LOCALAPPDATA%/Claude/.credentials.json when primary is absent."""
    missing_primary = tmp_path / "nonexistent_primary" / ".credentials.json"
    present_localappdata = tmp_path / "localappdata" / ".credentials.json"
    missing_appdata = tmp_path / "nonexistent_appdata" / ".credentials.json"

    present_localappdata.parent.mkdir(parents=True)
    present_localappdata.write_text(json.dumps({"accessToken": "sk-ant-test-LA"}))

    import daemon.claude_usage_daemon_windows as mod
    monkeypatch.setattr(
        mod,
        "_windows_credential_candidates",
        lambda: [missing_primary, present_localappdata, missing_appdata],
    )
    assert read_token() == "sk-ant-test-LA"


def test_read_token_appdata_fallback(tmp_path, monkeypatch):
    """read_token() falls back to %APPDATA%/Claude/.credentials.json when primary and LOCALAPPDATA are absent."""
    missing_primary = tmp_path / "nonexistent_primary" / ".credentials.json"
    missing_localappdata = tmp_path / "nonexistent_localappdata" / ".credentials.json"
    present_appdata = tmp_path / "appdata" / ".credentials.json"

    present_appdata.parent.mkdir(parents=True)
    present_appdata.write_text(json.dumps({"accessToken": "sk-ant-test-APP"}))

    import daemon.claude_usage_daemon_windows as mod
    monkeypatch.setattr(
        mod,
        "_windows_credential_candidates",
        lambda: [missing_primary, missing_localappdata, present_appdata],
    )
    assert read_token() == "sk-ant-test-APP"


def test_read_token_no_file(tmp_path, monkeypatch):
    """read_token() returns None when no credential file can be found."""
    monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(tmp_path / "nonexistent.json"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert read_token() is None


def test_read_token_config_dir_override(tmp_path, monkeypatch):
    """read_token() honours the official CLAUDE_CONFIG_DIR env override."""
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"accessToken": "sk-ant-test-CFGDIR"}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CREDENTIALS_PATH", raising=False)
    assert read_token() == "sk-ant-test-CFGDIR"


def test_read_expiry_decodes_milliseconds(monkeypatch):
    """_read_expiry() divides expiresAt by 1000 (ms -> s); fixture 9999999999000 -> year 2286."""
    monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(FIXTURES / "credentials_nested.json"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    result = _read_expiry()
    assert result.startswith("2286-"), f"Expected year 2286, got: {result}"
