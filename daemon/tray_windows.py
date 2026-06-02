#!/usr/bin/env python3
"""Windows system-tray entry and state bridge for Clawdmeter — APP-01.

Provides:
  TrayState   — thread-safe scalar bridge (daemon loop writes, tray reads)
  header_text — pure helper producing the D-05 status-header string
  main()      — tray entry: builds per-state icons, runs the daemon loop in a
                bg thread, and runs pystray.Icon on the main thread

The daemon loop (claude_usage_daemon_windows.main) is UNCHANGED in logic;
this module injects only additive state-setter calls at existing branch points.

Usage::

    python tray_windows.py

Run: python -m pytest daemon/tests/test_windows_tray.py -x -q
"""

import threading
import time

# ---------------------------------------------------------------------------
# TrayState — thread-safe scalar bridge (loop -> tray)
# ---------------------------------------------------------------------------

class TrayState:
    """Shared state object bridging the daemon asyncio loop to the tray.

    The daemon loop writes state via the set_* methods; the tray reads the
    scalar attributes.  No lock is needed — writes are atomic attribute
    assignments of simple Python scalars, and the tray only ever reads them.

    The loop populates `loop` and `stop_event` at startup (inside
    daemon_main()) so the tray's Quit handler can route through
    loop.call_soon_threadsafe (RESEARCH Pitfall 2 / Anti-Pattern).
    """

    def __init__(self) -> None:
        self.state: str = "scanning"       # "connected" | "scanning" | "error"
        self.reason: str = ""              # error reason string (D-04)
        self.last_sync: float | None = None  # time.time() of last successful write

        # Populated by daemon main() at startup:
        self.loop = None        # asyncio running loop (for call_soon_threadsafe)
        self.stop_event = None  # asyncio.Event (the existing clean-shutdown hook)

    def set_connected(self, ts: float) -> None:
        """Called after write_payload returns True.  ts = time.time()."""
        self.state = "connected"
        self.reason = ""
        self.last_sync = ts

    def set_scanning(self) -> None:
        """Called in scan/reconnect branches.  BLE churn stays Scanning (D-01)."""
        self.state = "scanning"
        self.reason = ""

    def set_error(self, why: str) -> None:
        """Called on token-expired / API auth failure (D-01 Error = actionable only)."""
        self.state = "error"
        self.reason = why


# ---------------------------------------------------------------------------
# header_text — pure D-05 status header string
# ---------------------------------------------------------------------------

def header_text(ts: TrayState) -> str:
    """Return the D-05 menu status-header string for the current TrayState.

    Shapes:
      "Connected · last update HH:MM"  (ts.last_sync is a float)
      "Connected · last update never"  (ts.last_sync is None)
      "Scanning…"
      "Error: {reason}"
    """
    if ts.state == "connected":
        if ts.last_sync is not None:
            when = time.strftime("%H:%M", time.localtime(ts.last_sync))
        else:
            when = "never"
        return f"Connected · last update {when}"
    if ts.state == "scanning":
        return "Scanning…"   # "Scanning…"
    return f"Error: {ts.reason}"


# ---------------------------------------------------------------------------
# main() — tray entry (pystray on main thread, daemon loop in bg thread)
# ---------------------------------------------------------------------------

def main() -> None:
    """Tray entry point: build icons, start daemon bg thread, run pystray.

    `import pystray` is intentionally INSIDE this function (not at module top)
    so the module can be imported on a GTK-less Linux dev box for unit tests
    of the pure helpers (TrayState, header_text) without pystray failing.
    """
    import asyncio as _asyncio
    import pystray
    from pystray import Menu, MenuItem

    import daemon.autostart_windows as autostart
    from daemon.claude_usage_daemon_windows import main as daemon_main
    from daemon.icon_assets import load_logo_rgba, build_state_icons

    # Build per-state icons once at startup; swap icon.icon per tick (never recomposite).
    base = load_logo_rgba("firmware/src/logo.h")
    images = build_state_icons(base)

    ts = TrayState()
    icon = pystray.Icon("Clawdmeter", images["scanning"], "Clawdmeter")

    # --- background thread: asyncio loop ---
    def _run_daemon() -> None:
        _asyncio.run(daemon_main(tray_state=ts))

    threading.Thread(target=_run_daemon, daemon=True).start()

    # --- menu ---
    def _on_quit(icon_ref, _item) -> None:
        # NEVER call ts.stop_event.set() directly from the tray thread;
        # asyncio.Event is NOT thread-safe (RESEARCH Pitfall 2).
        ts.loop.call_soon_threadsafe(ts.stop_event.set)
        icon_ref.stop()

    def _on_toggle(_icon_ref, _item) -> None:
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()
        icon.update_menu()

    icon.menu = Menu(
        # Non-clickable status header; text updates via update_menu() on state change.
        MenuItem(lambda _item: header_text(ts), None, enabled=False),
        # Start-at-login toggle: checked= is a CALLABLE for live query (Pitfall 6).
        MenuItem("Start at login", _on_toggle, checked=lambda _item: autostart.is_enabled()),
        MenuItem("Quit", _on_quit),
    )

    # --- setup callback (runs in pystray's setup thread, 1s poll) ---
    prev_state: dict = {"state": None}

    def _refresh(_icon: pystray.Icon) -> None:
        _icon.visible = True
        while _icon._running:  # type: ignore[attr-defined]
            current = ts.state
            if current != prev_state["state"]:
                _icon.icon = images[current]
                _icon.title = header_text(ts)
                # D-04: toast ONLY on transition INTO error, not on every error tick.
                if current == "error" and prev_state["state"] != "error":
                    _icon.notify(ts.reason or "Clawdmeter error", "Clawdmeter")
                prev_state["state"] = current
                _icon.update_menu()
            time.sleep(1.0)

    # Blocks the main thread until icon.stop() is called from _on_quit.
    icon.run(setup=_refresh)


if __name__ == "__main__":
    main()
