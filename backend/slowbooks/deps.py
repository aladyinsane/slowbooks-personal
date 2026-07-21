"""Database wiring for the API.

One connection per thread, all pointing at the same file.

The obvious design -- one cached connection for the whole process, since ADR 0001 makes
this a single-user app -- is wrong, and wrong in a way that took two attempts to see:

  1. First failure: connections created in one thread and used in another. FastAPI runs
     sync endpoints in a worker threadpool, so this happens on request #1. "Fixed" with
     check_same_thread=False.
  2. Second failure: two threads running the *same SQL* got the same entry from
     sqlite3's statement cache. Thread B's execute() reset the prepared statement out
     from under thread A, and A's fetchone() then returned None -- so a COUNT(*) came
     back as no row at all, and /api/health died on None subscripting.

sqlite3.threadsafety is 3 here, so sharing a connection is "allowed" at the C level.
That is what makes this trap good: nothing errors, the statement cache just quietly
hands two threads the same cursor state. The failure surfaces as absurd data rather than
as a crash -- a COUNT with no row -- which in an accounting system is the worst possible
shape for a bug.

Thread-local connections fix it properly: each thread gets its own statement cache and
its own transaction state (ledger.post does explicit BEGIN/COMMIT, which is only
coherent per-connection). WAL mode gives concurrent readers, and busy_timeout makes the
single writer wait rather than fail.

ADR 0001 makes this single-*user*. It does not make it single-threaded.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
from pathlib import Path

from slowbooks import db

# Each thread gets its own connection; sharing one is what caused both bugs above.
_local = threading.local()

_lock = threading.Lock()

# Schema setup must happen exactly once per file, not once per thread -- two threads
# both finding an empty accounts table would both seed the default chart.
_state: dict[str, object] = {"path": None, "initialized": False, "generation": 0}

# Every connection handed out, so reset_connection() can actually close them all.
_connections: list[sqlite3.Connection] = []


def database_path() -> Path:
    """Where the user's books live.

    A path they can see, copy, and back up. That is the whole product promise
    (ADR 0001), so it is deliberately not hidden in an app-data folder.

    Resolution order: an explicit ``SLOWBOOKS_DB`` always wins, then the default for how
    we're running.
    """
    override = os.environ.get("SLOWBOOKS_DB")
    if override:
        return Path(override)
    return _default_database_path()


def _default_database_path() -> Path:
    """Next to the executable in a packaged build; the home folder in development.

    Packaged, the book sits beside the executable so the two travel together -- copy the
    folder to a USB stick or a new machine and your books come with the program. That is
    ADR 0001 made literal. ``sys.executable`` is the real exe (not PyInstaller's temp
    unpack dir), so ``.parent`` is the folder the user actually put the program in.

    In development there is no meaningful "next to" -- the entry point is a `uvicorn`
    process deep in a venv -- so home keeps a dev's tree tidy and matches the documented
    workflow ([ADR 0013](../../docs/decisions/0013-ship-as-a-double-click-app.md)).

    Filename is ``slowbooks-personal.db``, not ``slowbooks.db``: this fork and the
    original small-business SlowBooks default to the same home directory when both are
    installed on one machine, and shared filenames would mean one silently overwrites the
    other's books. `SLOWBOOKS_DB` still overrides this for anyone who wants a different
    path or filename entirely.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "slowbooks-personal.db"
    return Path.home() / "slowbooks-personal.db"


def get_db() -> sqlite3.Connection:
    generation = _state["generation"]
    existing = getattr(_local, "conn", None)
    # Fast path: this thread already has a live connection from the current generation.
    if existing is not None and getattr(_local, "generation", None) == generation:
        return existing

    with _lock:
        path = database_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = db.connect(path)

        if not _state["initialized"] or _state["path"] != path:
            db.initialize(conn)
            _state["initialized"] = True
            _state["path"] = path

        _connections.append(conn)
        generation = _state["generation"]

    _local.conn = conn
    _local.generation = generation
    return conn


def reset_connection() -> None:
    """Close every connection and force re-open. For tests and for switching books.

    Bumping the generation is what makes other threads notice: their thread-local
    connection is closed underneath them, and the mismatch sends them back through
    get_db() rather than onto a dead handle.
    """
    with _lock:
        for conn in _connections:
            try:
                conn.close()
            except sqlite3.Error:
                pass  # already closed, or closed from another thread
        _connections.clear()
        _state["initialized"] = False
        _state["path"] = None
        _state["generation"] = int(_state["generation"]) + 1

    if hasattr(_local, "conn"):
        del _local.conn
