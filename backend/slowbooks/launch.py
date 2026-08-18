"""Double-click entry point for the packaged app.

Starts the server on a free port, waits until it's actually accepting connections, then
opens the default browser to it. The console window it runs in is the off switch: close
it and the server stops. Deliberately plain -- the fancier native-window version can
come later (pywebview); this is the smallest thing that gets the app in front of a
non-technical tester (ADR 0013).
"""

from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser

import uvicorn

from slowbooks import settings
from slowbooks.deps import get_db
from slowbooks.main import app


def _free_port() -> int:
    """An OS-assigned free port. Sidesteps the "port 8000 is taken" class of failure
    entirely -- the tester never has to know what a port is."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _lan_ip() -> str | None:
    """Best-effort LAN IP for the "your phone can reach it at ..." message.

    The UDP-connect trick: connecting a datagram socket doesn't actually send anything,
    it just makes the OS pick the route (and therefore the local address) it would use
    to reach that address. No traffic leaves the machine.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return None


def _open_when_ready(url: str, port: int) -> None:
    """Open the browser only once the server answers, so the tester never lands on a
    'can't connect' page in the half-second before uvicorn is up."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.1)


def main() -> None:
    # SLOWBOOKS_PORT is an escape hatch for pinning the port (and for automated tests);
    # left unset, we pick a free one.
    port = int(os.environ.get("SLOWBOOKS_PORT") or _free_port())
    url = f"http://127.0.0.1:{port}"

    # Opt-in, off by default (ADR 0001): the app never listens on the network until the
    # user turns this on in Settings. uvicorn's bind host is fixed at process start, so
    # this setting only takes effect on the next launch -- the Settings panel says so.
    conn = get_db()
    lan_enabled = settings.get_bool(conn, settings.LAN_ACCESS_ENABLED)
    host = "0.0.0.0" if lan_enabled else "127.0.0.1"

    # Always open the browser and wait for readiness against loopback -- binding 0.0.0.0
    # still accepts loopback connections, and "open a browser to 0.0.0.0" doesn't work
    # on every OS.
    threading.Thread(target=_open_when_ready, args=(url, port), daemon=True).start()

    print("SlowBooks is running.")
    print(f"  It should open in your browser at {url}")
    if lan_enabled:
        lan_ip = _lan_ip()
        if lan_ip:
            print(f"  On your home Wi-Fi, your phone can reach it at http://{lan_ip}:{port}")
        # access.load() (via main.py's lifespan) hasn't run yet at this point in the
        # process, so read the DB directly rather than the not-yet-populated cache.
        if settings.get(conn, settings.ACCESS_PIN_HASH) is None:
            print("  Set an access PIN in Settings before using this from another device.")
    print("  Keep this window open while you use it. Close it to stop SlowBooks.")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
