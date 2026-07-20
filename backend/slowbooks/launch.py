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

from slowbooks.main import app


def _free_port() -> int:
    """An OS-assigned free port. Sidesteps the "port 8000 is taken" class of failure
    entirely -- the tester never has to know what a port is."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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

    threading.Thread(target=_open_when_ready, args=(url, port), daemon=True).start()

    print("SlowBooks is running.")
    print(f"  It should open in your browser at {url}")
    print("  Keep this window open while you use it. Close it to stop SlowBooks.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
