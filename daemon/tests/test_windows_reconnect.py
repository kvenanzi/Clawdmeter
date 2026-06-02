#!/usr/bin/env python3
"""Unit tests for connect_and_run reconnect hardening — BLE-03.

Covers:
  D-01: connect-retry wrapper (post-wake WinRT failure modes)
  D-03: zombie-link consecutive-failure break (stale is_connected)

Run: python -m pytest daemon/tests/test_windows_reconnect.py -x -q
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from daemon.claude_usage_daemon_windows import connect_and_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously for synchronous test functions."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_device(address="AA:BB:CC:DD:EE:FF"):
    """Build a minimal fake BLEDevice."""
    device = MagicMock()
    device.address = address
    return device


async def _make_event(set_):
    ev = asyncio.Event()
    if set_:
        ev.set()
    return ev


# ---------------------------------------------------------------------------
# D-01: connect-retry wrapper tests
# ---------------------------------------------------------------------------

def test_connect_retry_exhaustion_on_bleak_error(monkeypatch, capsys):
    """BleakError on every connect attempt exhausts CONNECT_RETRIES then returns False."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=BleakError("Unreachable"))
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        result = _run(connect_and_run(device, stop_event))

    assert result is False
    assert mock_client.connect.call_count == mod.CONNECT_RETRIES


def test_connect_retry_exhaustion_on_timeout_error(monkeypatch, capsys):
    """asyncio.TimeoutError on every connect attempt is treated same as BleakError."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        result = _run(connect_and_run(device, stop_event))

    assert result is False
    assert mock_client.connect.call_count == mod.CONNECT_RETRIES


def test_connect_retry_calls_disconnect_between_attempts(monkeypatch):
    """Guarded disconnect() is called between failed connect attempts."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=BleakError("Unreachable"))
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        _run(connect_and_run(device, stop_event))

    # disconnect is called between attempts (at least CONNECT_RETRIES - 1 times)
    assert mock_client.disconnect.call_count >= mod.CONNECT_RETRIES - 1


def test_connect_success_on_first_attempt_no_extra_retries(monkeypatch):
    """First-attempt success consumes exactly 1 connect call and proceeds past connect block."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    # stop_event is set so the loop exits immediately after connecting
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(True))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(return_value=None)  # success
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock()
    mock_client.start_notify = AsyncMock()
    mock_client.write_gatt_char = AsyncMock(return_value=None)

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value="fake-token"), \
         patch("daemon.claude_usage_daemon_windows.poll_api", new=AsyncMock(return_value={"ok": True})):
        _run(connect_and_run(device, stop_event))

    assert mock_client.connect.call_count == 1


def test_connect_retry_exhaustion_does_not_log_token(monkeypatch, capsys):
    """On exhaustion, no log line contains the patched token sentinel (T-03-01)."""
    import daemon.claude_usage_daemon_windows as mod

    TOKEN_SENTINEL = "sk-ant-SUPERSECRET-DO-NOT-LOG-12345"
    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=BleakError("Unreachable"))
    mock_client.is_connected = False
    mock_client.disconnect = AsyncMock()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value=TOKEN_SENTINEL), \
         patch("daemon.claude_usage_daemon_windows.asyncio.sleep", new=AsyncMock()):
        _run(connect_and_run(device, stop_event))

    captured = capsys.readouterr()
    assert TOKEN_SENTINEL not in captured.out, "Token sentinel leaked to stdout (T-03-01)"
    assert TOKEN_SENTINEL not in captured.err, "Token sentinel leaked to stderr (T-03-01)"


# ---------------------------------------------------------------------------
# D-03: zombie-link consecutive-failure break tests
# ---------------------------------------------------------------------------

def _make_zombie_client():
    """Build a mock BleakClient that connects successfully but has is_connected stuck True."""
    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(return_value=None)
    mock_client.is_connected = True   # stale flag — never goes False
    mock_client.disconnect = AsyncMock()
    mock_client.start_notify = AsyncMock()
    return mock_client


def test_zombie_link_break_after_limit_consecutive_failures(monkeypatch):
    """Loop breaks after exactly ZOMBIE_BREAK_LIMIT consecutive False writes (default 1)."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))
    mock_client = _make_zombie_client()

    write_call_count = [0]

    async def fake_write_payload(payload):
        write_call_count[0] += 1
        return False  # always fail — zombie link

    fake_session = AsyncMock()
    fake_session.write_payload = fake_write_payload
    fake_session.refresh_requested = MagicMock()
    fake_session.refresh_requested.is_set = MagicMock(return_value=False)
    fake_session.refresh_requested.clear = MagicMock()
    fake_session.refresh_requested.wait = AsyncMock()

    # Force elapsed >= POLL_INTERVAL immediately
    monkeypatch.setattr(mod, "POLL_INTERVAL", 0)

    async def fast_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.Session", return_value=fake_session), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value="fake-token"), \
         patch("daemon.claude_usage_daemon_windows.poll_api",
               new=AsyncMock(return_value={"ok": True})), \
         patch("daemon.claude_usage_daemon_windows.asyncio.wait_for",
               side_effect=fast_wait_for):
        result = _run(connect_and_run(device, stop_event))

    # With ZOMBIE_BREAK_LIMIT=1, one False write should break the loop
    assert write_call_count[0] == mod.ZOMBIE_BREAK_LIMIT
    # Should return used_successfully=False (no successful write)
    assert result is False


def test_zombie_counter_resets_on_success_with_raised_limit(monkeypatch):
    """A failed write followed by success resets counter (limit raised to 2 to exercise reset)."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))
    mock_client = _make_zombie_client()

    # Sequence: False (counter=1), True (counter reset to 0), False (counter=1 again), break
    write_results = iter([False, True, False])
    write_call_count = [0]

    async def fake_write_payload(payload):
        write_call_count[0] += 1
        try:
            return next(write_results)
        except StopIteration:
            return False

    # After success, subsequent False write breaks at limit=2 (requires 2 consecutive)
    # With limit=2: False (1), True (reset to 0), False (1), False (2 -> break)
    # But we only have 3 items in write_results; after StopIteration returns False.
    # Let's use a longer sequence to ensure reset-then-2-failures trip the break.
    write_results2 = [False, True, False, False]
    write_call_count2 = [0]

    async def fake_write_payload2(payload):
        write_call_count2[0] += 1
        if write_call_count2[0] - 1 < len(write_results2):
            return write_results2[write_call_count2[0] - 1]
        return False

    fake_session = AsyncMock()
    fake_session.write_payload = fake_write_payload2
    fake_session.refresh_requested = MagicMock()
    fake_session.refresh_requested.is_set = MagicMock(return_value=False)
    fake_session.refresh_requested.clear = MagicMock()
    fake_session.refresh_requested.wait = AsyncMock()

    monkeypatch.setattr(mod, "POLL_INTERVAL", 0)
    monkeypatch.setattr(mod, "ZOMBIE_BREAK_LIMIT", 2)  # raise limit to test reset logic

    async def fast_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.Session", return_value=fake_session), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value="fake-token"), \
         patch("daemon.claude_usage_daemon_windows.poll_api",
               new=AsyncMock(return_value={"ok": True})), \
         patch("daemon.claude_usage_daemon_windows.asyncio.wait_for",
               side_effect=fast_wait_for):
        result = _run(connect_and_run(device, stop_event))

    # With limit=2 and sequence [False, True, False, False]:
    # cycle 1: False -> consecutive_failures=1 (no break, limit=2)
    # cycle 2: True  -> consecutive_failures=0 (reset)
    # cycle 3: False -> consecutive_failures=1 (no break)
    # cycle 4: False -> consecutive_failures=2 -> break
    assert write_call_count2[0] == 4, (
        f"Expected 4 write calls (reset-on-success logic), got {write_call_count2[0]}"
    )
    # used_successfully=True because cycle 2 succeeded
    assert result is True


def test_zombie_break_disconnect_called_in_finally(monkeypatch):
    """The finally block calls client.disconnect() exactly once on the zombie-break path."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))
    mock_client = _make_zombie_client()

    async def fake_write_payload(payload):
        return False  # always fail

    fake_session = AsyncMock()
    fake_session.write_payload = fake_write_payload
    fake_session.refresh_requested = MagicMock()
    fake_session.refresh_requested.is_set = MagicMock(return_value=False)
    fake_session.refresh_requested.clear = MagicMock()
    fake_session.refresh_requested.wait = AsyncMock()

    monkeypatch.setattr(mod, "POLL_INTERVAL", 0)

    async def fast_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.Session", return_value=fake_session), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value="fake-token"), \
         patch("daemon.claude_usage_daemon_windows.poll_api",
               new=AsyncMock(return_value={"ok": True})), \
         patch("daemon.claude_usage_daemon_windows.asyncio.wait_for",
               side_effect=fast_wait_for):
        _run(connect_and_run(device, stop_event))

    # The finally block calls disconnect() exactly once
    assert mock_client.disconnect.call_count == 1


def test_zombie_break_returns_used_successfully_false(monkeypatch):
    """connect_and_run returns used_successfully=False after zombie break with no writes."""
    import daemon.claude_usage_daemon_windows as mod

    device = _make_device()
    stop_event = asyncio.get_event_loop().run_until_complete(_make_event(False))
    mock_client = _make_zombie_client()

    async def fake_write_payload(payload):
        return False

    fake_session = AsyncMock()
    fake_session.write_payload = fake_write_payload
    fake_session.refresh_requested = MagicMock()
    fake_session.refresh_requested.is_set = MagicMock(return_value=False)
    fake_session.refresh_requested.clear = MagicMock()
    fake_session.refresh_requested.wait = AsyncMock()

    monkeypatch.setattr(mod, "POLL_INTERVAL", 0)

    async def fast_wait_for(coro, timeout):
        raise asyncio.TimeoutError()

    with patch("daemon.claude_usage_daemon_windows.BleakClient", return_value=mock_client), \
         patch("daemon.claude_usage_daemon_windows.Session", return_value=fake_session), \
         patch("daemon.claude_usage_daemon_windows.read_token", return_value="fake-token"), \
         patch("daemon.claude_usage_daemon_windows.poll_api",
               new=AsyncMock(return_value={"ok": True})), \
         patch("daemon.claude_usage_daemon_windows.asyncio.wait_for",
               side_effect=fast_wait_for):
        result = _run(connect_and_run(device, stop_event))

    # main() uses this return value to route into reconnect branch
    assert result is False
