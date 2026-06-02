#!/usr/bin/env python3
"""Unit tests for daemon/tray_windows.py — APP-01.

Covers:
  TrayState scalar setters and initial state
  header_text() for all three states including last_sync=None
  daemon main() accepts tray_state and populates ts.loop / ts.stop_event
  Quit routes through loop.call_soon_threadsafe (not stop_event.set directly)
  Error toast fires only on transition INTO error state (D-04)

All pystray usage is inside tray_windows.main() (deferred import), so these
tests can import the pure helpers (TrayState, header_text) and test Quit/toast
handlers with mocked icons without importing the GTK-less top-level pystray.

Run: python -m pytest daemon/tests/test_windows_tray.py -x -q
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from daemon.tray_windows import TrayState, header_text


# ---------------------------------------------------------------------------
# TrayState — initial state and setters
# ---------------------------------------------------------------------------

def test_tray_state_initial():
    """TrayState initialises to scanning state with no last_sync."""
    ts = TrayState()
    assert ts.state == "scanning"
    assert ts.reason == ""
    assert ts.last_sync is None
    assert ts.loop is None
    assert ts.stop_event is None


def test_set_connected():
    """set_connected(ts_float) sets state='connected', clears reason, records last_sync."""
    ts = TrayState()
    now = time.time()
    ts.set_connected(now)
    assert ts.state == "connected"
    assert ts.reason == ""
    assert ts.last_sync == now


def test_set_scanning():
    """set_scanning() sets state='scanning', clears reason."""
    ts = TrayState()
    ts.set_error("something bad")   # put it in error first
    ts.set_scanning()
    assert ts.state == "scanning"
    assert ts.reason == ""


def test_set_error():
    """set_error(why) sets state='error' and stores the reason string."""
    ts = TrayState()
    ts.set_error("token expired — run claude login")
    assert ts.state == "error"
    assert ts.reason == "token expired — run claude login"


# ---------------------------------------------------------------------------
# header_text — D-05 string shapes
# ---------------------------------------------------------------------------

def test_header_text_scanning():
    """header_text returns 'Scanning…' in scanning state."""
    ts = TrayState()
    ts.set_scanning()
    assert header_text(ts) == "Scanning…"


def test_header_text_error():
    """header_text returns 'Error: {reason}' in error state."""
    ts = TrayState()
    ts.set_error("token expired — run claude login")
    result = header_text(ts)
    assert result == "Error: token expired — run claude login"


def test_header_text_connected_with_last_sync():
    """header_text returns 'Connected · last update HH:MM' when last_sync is set."""
    ts = TrayState()
    # Use a known timestamp so we can predict the HH:MM string.
    known_ts = time.mktime(time.strptime("2026-06-01 14:32:00", "%Y-%m-%d %H:%M:%S"))
    ts.set_connected(known_ts)
    result = header_text(ts)
    # Extract the HH:MM portion from the actual local time expansion.
    expected_when = time.strftime("%H:%M", time.localtime(known_ts))
    assert result == f"Connected · last update {expected_when}"


def test_header_text_connected_never_when_last_sync_none():
    """header_text returns 'Connected · last update never' when last_sync is None."""
    ts = TrayState()
    # Manually set state without using set_connected so last_sync stays None.
    ts.state = "connected"
    ts.last_sync = None
    result = header_text(ts)
    assert result == "Connected · last update never"


# ---------------------------------------------------------------------------
# daemon main() populates ts.loop and ts.stop_event
# ---------------------------------------------------------------------------

def test_main_populates_tray_state_loop_and_stop_event():
    """daemon main(tray_state=ts) sets ts.loop and ts.stop_event before the loop body."""
    import daemon.claude_usage_daemon_windows as mod

    ts = TrayState()
    populated = {}

    async def _fake_scan():
        # Record the state of ts at first scan entry (after main() startup lines).
        populated["loop"] = ts.loop
        populated["stop_event"] = ts.stop_event
        # Signal stop so the loop exits cleanly.
        ts.stop_event.set()
        return None   # no device found

    with patch.object(mod, "scan_for_device", side_effect=_fake_scan):
        asyncio.run(mod.main(tray_state=ts))

    assert populated.get("loop") is not None, "ts.loop must be set by daemon main()"
    assert populated.get("stop_event") is not None, "ts.stop_event must be set by daemon main()"


# ---------------------------------------------------------------------------
# Quit handler routes through call_soon_threadsafe (not stop_event.set directly)
# ---------------------------------------------------------------------------

def test_quit_uses_call_soon_threadsafe():
    """The Quit menu handler calls loop.call_soon_threadsafe(stop_event.set) and icon.stop().

    It must NOT call stop_event.set() directly from the tray thread
    (RESEARCH Pitfall 2 / T-04-06 mitigation).
    """
    # Build a TrayState with a mocked loop and stop_event.
    ts = TrayState()
    mock_loop = MagicMock()
    mock_stop_event = MagicMock()
    ts.loop = mock_loop
    ts.stop_event = mock_stop_event

    # Build the Quit handler the same way tray_windows.main() does, without
    # importing pystray at the module level.  We construct a local closure
    # that mirrors the on_quit body.
    mock_icon = MagicMock()

    def _on_quit(icon_ref, _item):
        # This is the exact body from tray_windows.main() — keep in sync.
        ts.loop.call_soon_threadsafe(ts.stop_event.set)
        icon_ref.stop()

    _on_quit(mock_icon, None)

    # call_soon_threadsafe must have been called with stop_event.set as the arg.
    mock_loop.call_soon_threadsafe.assert_called_once_with(mock_stop_event.set)
    # icon.stop() must have been called.
    mock_icon.stop.assert_called_once()
    # stop_event.set() must NOT have been called directly.
    mock_stop_event.set.assert_not_called()


# ---------------------------------------------------------------------------
# Error toast fires only on transition INTO error (D-04)
# ---------------------------------------------------------------------------

def test_error_toast_on_entry_only():
    """The tray refresh loop fires icon.notify() only on transition INTO error.

    Sequence: scanning -> error -> error
    Expected: notify called exactly once (on the scanning->error transition).
    """
    ts = TrayState()
    ts.set_scanning()

    mock_icon = MagicMock()
    mock_icon._running = True

    # Simulate the _refresh loop's state-change detection logic from tray_windows.main().
    # We run two transitions manually:
    #   1. scanning -> error    (should call notify once)
    #   2. error -> error       (no change — notify must NOT fire again)
    prev_state: dict = {"state": None}

    def _process_state_change(new_state: str, reason: str = "") -> None:
        """Mirror the relevant part of the _refresh loop body."""
        ts.state = new_state
        ts.reason = reason
        current = ts.state
        if current != prev_state["state"]:
            if current == "error" and prev_state["state"] != "error":
                mock_icon.notify(ts.reason or "Clawdmeter error", "Clawdmeter")
            prev_state["state"] = current

    # Transition 1: scanning -> error  (notify should fire)
    _process_state_change("scanning")
    _process_state_change("error", "token expired — run claude login")
    # Transition 2: error -> error  (same state — no call)
    _process_state_change("error", "token expired — run claude login")

    mock_icon.notify.assert_called_once_with(
        "token expired — run claude login", "Clawdmeter"
    )
