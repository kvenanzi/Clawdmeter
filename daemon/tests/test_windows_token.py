#!/usr/bin/env python3
"""Unit tests for daemon/claude_usage_daemon_windows.py — TOKEN-01.

Run: python -m pytest daemon/tests/test_windows_token.py -x -q
"""
import json
import subprocess
import sys
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


# --- WR-03: regression guard for CR-01 (empty/blank token must not be accepted) ---

def test_extract_empty_token_is_none():
    """_extract_access_token returns None for empty accessToken (CR-01 regression guard)."""
    assert _extract_access_token('{"accessToken": ""}') is None
    assert _extract_access_token('{}') is None



def test_read_token_empty_credential_file_returns_none(tmp_path, monkeypatch):
    """read_token() returns None (not empty string) when credential file has empty accessToken."""
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"accessToken": ""}))
    monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(creds))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert read_token() is None


# --- WR-01: regression guard for _read_expiry with non-dict top-level JSON ---

def test_read_expiry_non_dict_json_returns_unknown(tmp_path, monkeypatch):
    """_read_expiry() returns 'expiry unknown' (not crash) for non-dict top-level JSON (WR-01)."""
    creds = tmp_path / ".credentials.json"
    creds.write_text("[1, 2, 3]")
    monkeypatch.setenv("CLAUDE_CREDENTIALS_PATH", str(creds))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert _read_expiry() == "expiry unknown"


# --- WR-02: D-06 redaction requirement must be tested ---

def test_main_output_redacts_token(monkeypatch):
    """__main__ prints only the last-4 redacted form; full token must never appear in stdout (D-06)."""
    env = {**__import__("os").environ, "CLAUDE_CREDENTIALS_PATH": str(FIXTURES / "credentials_nested.json")}
    env.pop("CLAUDE_CONFIG_DIR", None)
    module = str(Path(__file__).parent.parent / "claude_usage_daemon_windows.py")
    result = subprocess.run(
        [sys.executable, module],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"
    # Full token must NOT appear in stdout
    assert "sk-ant-test-1234" not in result.stdout, "Full token leaked to stdout (D-06 violation)"
    # Redacted last-4 suffix MUST appear
    assert "…1234" in result.stdout or "1234" in result.stdout, (
        f"Expected last-4 chars '1234' in stdout, got: {result.stdout!r}"
    )


def test_main_empty_token_exits_one(tmp_path, monkeypatch):
    """__main__ exits 1 with actionable message when credential file contains empty accessToken."""
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"accessToken": ""}))
    env = {**__import__("os").environ, "CLAUDE_CREDENTIALS_PATH": str(creds)}
    env.pop("CLAUDE_CONFIG_DIR", None)
    module = str(Path(__file__).parent.parent / "claude_usage_daemon_windows.py")
    result = subprocess.run(
        [sys.executable, module],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"
    assert "No Windows token found" in result.stdout
