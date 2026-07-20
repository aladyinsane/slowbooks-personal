"""User-facing app state.

Distinct from `schema_meta`, which describes the database. This is state the *user*
would recognize -- currently just whether they've been shown the starter-rule warning.

Kept in the book file rather than in browser storage on purpose: ADR 0001 says the book
is the unit the user owns and moves. If acknowledgement lived in localStorage, copying
your book to a new machine would resurrect a first-run warning about rules you retired
months ago.
"""

from __future__ import annotations

import sqlite3

# Set once the user has seen and dismissed the first-run starter-rule warning (ADR 0006).
STARTER_RULES_ACKNOWLEDGED = "starter_rules_acknowledged"


def get(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )


def get_bool(conn: sqlite3.Connection, key: str) -> bool:
    return get(conn, key) == "1"


def set_bool(conn: sqlite3.Connection, key: str, value: bool) -> None:
    set_(conn, key, "1" if value else "0")
