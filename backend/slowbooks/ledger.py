"""The double-entry ledger. The only writer of journal entries.

Two rules, both enforced by database triggers rather than by trust (see db.py):
  1. Every posted entry balances: debits == credits.
  2. Posted entries are immutable. Corrections are reversals.

See docs/decisions/0004-double-entry-immutable-ledger.md.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from slowbooks.money import Minor


class LedgerError(Exception):
    """An operation would have violated the ledger's invariants."""


@dataclass(frozen=True)
class Line:
    """One side of an entry.

    amount_minor is signed cents: positive debits, negative credits. Callers who
    think in debit/credit should use the debit()/credit() helpers rather than
    juggling signs by hand.
    """

    account_id: int
    amount_minor: Minor
    memo: str | None = None


def debit(account_id: int, amount_minor: Minor, memo: str | None = None) -> Line:
    if amount_minor < 0:
        raise ValueError("debit amount must be positive; use credit() instead")
    return Line(account_id, amount_minor, memo)


def credit(account_id: int, amount_minor: Minor, memo: str | None = None) -> Line:
    if amount_minor < 0:
        raise ValueError("credit amount must be positive; use debit() instead")
    return Line(account_id, -amount_minor, memo)


@dataclass(frozen=True)
class Entry:
    id: int
    entry_date: str
    description: str
    source: str
    posted_at: str | None
    reverses_entry_id: int | None


def post(
    conn: sqlite3.Connection,
    entry_date: date | str,
    description: str,
    lines: list[Line],
    *,
    source: str = "manual",
    reverses_entry_id: int | None = None,
) -> int:
    """Post a balanced entry. Returns the entry id.

    Draft-then-post is not ceremony: it is what lets the balance trigger fire at the
    moment a draft becomes a financial fact, with every line present. All of it runs
    in one transaction, so a rejected entry leaves nothing behind.
    """
    if len(lines) < 2:
        raise LedgerError("an entry needs at least two lines")

    total = sum(line.amount_minor for line in lines)
    if total != 0:
        # The trigger would catch this anyway, but failing here gives a message that
        # names the actual imbalance instead of a bare SQL abort.
        raise LedgerError(
            f"entry does not balance: debits - credits = {total} cents (must be 0)"
        )

    iso_date = entry_date.isoformat() if isinstance(entry_date, date) else entry_date

    # Same reasoning as the balance check above: the trigger is what actually enforces
    # this (ADR 0011), but a bare SQL abort is a terrible thing to show someone. Say
    # which date is closed and how to get past it.
    from slowbooks import periods

    lock = periods.closed_through(conn)
    if lock is not None and iso_date <= lock:
        raise LedgerError(
            f"the books are closed through {lock}, so nothing dated {iso_date} can be "
            f"recorded. Reopen that period first, or date this entry later."
        )

    try:
        conn.execute("BEGIN")
        cursor = conn.execute(
            """INSERT INTO journal_entries
                   (entry_date, description, source, reverses_entry_id, posted_at)
               VALUES (?, ?, ?, ?, NULL)""",
            (iso_date, description, source, reverses_entry_id),
        )
        entry_id = cursor.lastrowid

        conn.executemany(
            """INSERT INTO journal_lines (entry_id, account_id, amount_minor, memo)
               VALUES (?, ?, ?, ?)""",
            [(entry_id, ln.account_id, ln.amount_minor, ln.memo) for ln in lines],
        )

        # Flipping posted_at is what arms the balance trigger.
        conn.execute(
            "UPDATE journal_entries SET posted_at = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), entry_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return entry_id


def void(conn: sqlite3.Connection, entry_id: int, reason: str | None = None) -> int:
    """Void an entry by posting its mirror image. Returns the reversing entry id.

    Nothing is deleted -- this is how the audit trail survives while the UI can still
    offer users something that behaves like a delete button (ADR 0004).
    """
    original = get(conn, entry_id)
    if original is None:
        raise LedgerError(f"no entry with id {entry_id}")
    if original.posted_at is None:
        raise LedgerError("cannot void a draft entry; delete it instead")

    existing = conn.execute(
        "SELECT id FROM journal_entries WHERE reverses_entry_id = ?", (entry_id,)
    ).fetchone()
    if existing is not None:
        raise LedgerError(f"entry {entry_id} is already voided by entry {existing['id']}")

    lines = [
        Line(row["account_id"], -row["amount_minor"], row["memo"])
        for row in conn.execute(
            "SELECT account_id, amount_minor, memo FROM journal_lines WHERE entry_id = ?",
            (entry_id,),
        )
    ]

    note = f"Void: {original.description}"
    if reason:
        note += f" ({reason})"

    # The rule inverts at the lock line, and this is the subtle part of ADR 0011.
    #
    # In an open period, the reversal matches the original's date so that period's
    # reports stay truthful. In a *closed* one that is exactly wrong: it would change a
    # closed period, which is the thing closing exists to prevent. So the correction
    # falls forward into the first open period instead -- which is what real accounting
    # does, and why "closed" and "correctable" are not in conflict.
    from slowbooks import periods

    if periods.is_closed(conn, original.entry_date):
        reversal_date = periods.first_open_date(conn)
        note += f" — originally dated {original.entry_date}, in a closed period"
    else:
        reversal_date = original.entry_date

    return post(
        conn, reversal_date, note, lines,
        source="void", reverses_entry_id=entry_id,
    )


def get(conn: sqlite3.Connection, entry_id: int) -> Entry | None:
    row = conn.execute(
        """SELECT id, entry_date, description, source, posted_at, reverses_entry_id
           FROM journal_entries WHERE id = ?""",
        (entry_id,),
    ).fetchone()
    return Entry(**dict(row)) if row else None


def account_balance(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    as_of: date | str | None = None,
) -> Minor:
    """Signed balance for one account. Positive = net debit, negative = net credit."""
    sql = """SELECT COALESCE(SUM(l.amount_minor), 0) AS balance
               FROM journal_lines l
               JOIN journal_entries e ON e.id = l.entry_id
              WHERE l.account_id = ? AND e.posted_at IS NOT NULL"""
    params: list[object] = [account_id]

    if as_of is not None:
        sql += " AND e.entry_date <= ?"
        params.append(as_of.isoformat() if isinstance(as_of, date) else as_of)

    return conn.execute(sql, params).fetchone()["balance"]


def is_balanced(conn: sqlite3.Connection) -> bool:
    """Every posted entry sums to zero.

    Should be impossible to violate given the triggers -- which is exactly why it is
    worth asserting in tests. An invariant nobody checks is a hope.
    """
    row = conn.execute(
        """SELECT COUNT(*) AS bad FROM (
               SELECT e.id FROM journal_entries e
                 JOIN journal_lines l ON l.entry_id = e.id
                WHERE e.posted_at IS NOT NULL
                GROUP BY e.id
               HAVING SUM(l.amount_minor) <> 0
           )"""
    ).fetchone()
    return row["bad"] == 0
