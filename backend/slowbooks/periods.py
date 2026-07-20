"""Closing the books through a date.

ADR 0009 shipped reconciliation and admitted its own hole: it *detects* an entry
backdated into a reconciled period but cannot prevent one. This is the prevention.

The gap mattered because of how it fails. Post a January fee into a reconciled January
and ledger_balanced is true, the trial balance balances, the Balance Sheet balances --
and January is silently wrong. Closing makes that impossible rather than merely visible,
which is what lets a P&L you handed to a bank in February still mean the same thing in
June. See ADR 0011.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta


class PeriodError(Exception):
    pass


@dataclass(frozen=True)
class PeriodClose:
    id: int
    closed_through: str
    closed_at: str
    note: str | None
    reopens_id: int | None


def closed_through(conn: sqlite3.Connection) -> str | None:
    """The date the books are closed through, or None if nothing is closed.

    "In force" means the latest close that isn't itself a reopen and hasn't been
    reopened. The SQL is duplicated in the lock trigger on purpose -- the trigger cannot
    call Python, and the trigger is the one that actually enforces anything (ADR 0011).
    """
    row = conn.execute(
        """SELECT MAX(p.closed_through) AS through FROM period_closes p
            WHERE p.reopens_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM period_closes r WHERE r.reopens_id = p.id)"""
    ).fetchone()
    return row["through"] if row and row["through"] else None


def is_closed(conn: sqlite3.Connection, entry_date: date | str) -> bool:
    iso = entry_date.isoformat() if isinstance(entry_date, date) else entry_date
    lock = closed_through(conn)
    return lock is not None and iso <= lock


def first_open_date(conn: sqlite3.Connection) -> str:
    """The earliest date something can still be posted to.

    Today, unless the books are closed past today, in which case the day after the lock.
    This is where a correction to a closed period lands (ADR 0011).
    """
    today = date.today()
    lock = closed_through(conn)
    if lock is None:
        return today.isoformat()
    day_after = date.fromisoformat(lock) + timedelta(days=1)
    return max(today, day_after).isoformat()


def readiness(conn: sqlite3.Connection, through: date | str) -> dict[str, object]:
    """What the user should know before closing through this date.

    Advisory, never a veto. A user may close knowing an account isn't reconciled -- the
    statement might not have arrived. Refusing would make us the boss of their books;
    letting them do it blind would be worse. So: tell them, loudly, then obey (ADR 0011).
    """
    from slowbooks import accounts, reconciliation

    iso = through.isoformat() if isinstance(through, date) else through

    unreconciled = []
    for account in accounts.list_statement_accounts(conn):
        # Skip accounts with nothing in them. An account with no transactions through
        # this date has nothing to reconcile, and warning about it is a false alarm --
        # four warnings where one is real dilutes the one that matters, which is the
        # same signal-dilution problem as badge fatigue (ADR 0006).
        activity = conn.execute(
            """SELECT COUNT(*) AS n
                 FROM journal_lines l
                 JOIN journal_entries e ON e.id = l.entry_id
                WHERE l.account_id = ? AND e.posted_at IS NOT NULL
                  AND e.entry_date <= ?""",
            (account.id, iso),
        ).fetchone()["n"]
        if activity == 0:
            continue

        latest = reconciliation.latest(conn, account.id)
        if latest is None or latest.statement_date < iso:
            unreconciled.append({
                "account": f"{account.code} {account.name}",
                "reconciled_through": latest.statement_date if latest else None,
            })

    uncategorized = conn.execute(
        """SELECT COUNT(*) AS n FROM staged_transactions
            WHERE status = 'pending' AND txn_date <= ?""",
        (iso,),
    ).fetchone()["n"]

    return {
        "through": iso,
        "unreconciled_accounts": unreconciled,
        "uncategorized_transactions": uncategorized,
        # Not "can_close" -- nothing here blocks. These are things worth knowing.
        "is_tidy": not unreconciled and uncategorized == 0,
    }


def close(
    conn: sqlite3.Connection, through: date | str, note: str | None = None
) -> int:
    """Close the books through `through`. Returns the close id."""
    iso = through.isoformat() if isinstance(through, date) else through
    try:
        date.fromisoformat(iso)
    except ValueError as exc:
        raise PeriodError(f"{iso!r} is not a date") from exc

    existing = closed_through(conn)
    if existing is not None and iso <= existing:
        raise PeriodError(
            f"the books are already closed through {existing}; closing through {iso} "
            f"would move the line backwards, which is what reopening is for"
        )

    cursor = conn.execute(
        "INSERT INTO period_closes (closed_through, note) VALUES (?, ?)", (iso, note)
    )
    return cursor.lastrowid


def reopen(conn: sqlite3.Connection, close_id: int, reason: str | None = None) -> int:
    """Reopen a closed period with a new record. Returns the reopening record's id.

    Append-only, like everything else that matters here. Reopening moves the line back
    to the previous close -- it does not erase the fact that the period was closed, or
    that someone changed their mind.
    """
    record = get(conn, close_id)
    if record is None:
        raise PeriodError(f"no period close with id {close_id}")
    if record.reopens_id is not None:
        raise PeriodError("that record is itself a reopening, so there is nothing to reopen")

    already = conn.execute(
        "SELECT id FROM period_closes WHERE reopens_id = ?", (close_id,)
    ).fetchone()
    if already:
        raise PeriodError(f"period close {close_id} was already reopened")

    cursor = conn.execute(
        """INSERT INTO period_closes (closed_through, note, reopens_id)
           VALUES (?, ?, ?)""",
        (record.closed_through, f"Reopened: {reason}" if reason else "Reopened", close_id),
    )
    return cursor.lastrowid


def get(conn: sqlite3.Connection, close_id: int) -> PeriodClose | None:
    row = conn.execute(
        """SELECT id, closed_through, closed_at, note, reopens_id
             FROM period_closes WHERE id = ?""",
        (close_id,),
    ).fetchone()
    return PeriodClose(**dict(row)) if row else None


def current(conn: sqlite3.Connection) -> PeriodClose | None:
    """The close currently in force, if any."""
    row = conn.execute(
        """SELECT p.id, p.closed_through, p.closed_at, p.note, p.reopens_id
             FROM period_closes p
            WHERE p.reopens_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM period_closes r WHERE r.reopens_id = p.id)
            ORDER BY p.closed_through DESC, p.id DESC
            LIMIT 1"""
    ).fetchone()
    return PeriodClose(**dict(row)) if row else None


def history(conn: sqlite3.Connection) -> list[PeriodClose]:
    return [
        PeriodClose(**dict(row))
        for row in conn.execute(
            """SELECT id, closed_through, closed_at, note, reopens_id
                 FROM period_closes ORDER BY closed_at DESC, id DESC"""
        )
    ]
