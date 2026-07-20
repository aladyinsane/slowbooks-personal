"""Bank reconciliation.

Everything else we produce means "these are the numbers, probably." The balance trigger
proves the books are internally *consistent*; it says nothing about whether they're
*complete*. A perfectly balanced set of books can be missing every transaction in March.

Reconciliation is the only thing that closes that gap, and the shape of it matters: a
reconciliation is a durable record of a claim the *user* made -- "on this date the bank
said I had $X" -- not a status we computed. The human assertion is the artifact. See
ADR 0009.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from slowbooks import accounts, ledger, money
from slowbooks.money import Minor


class ReconciliationError(Exception):
    pass


@dataclass(frozen=True)
class Preview:
    """What reconciling this account to this date would involve."""

    account_id: int
    account_code: str
    account_name: str
    statement_date: str
    statement_balance_minor: Minor
    book_balance_minor: Minor
    difference_minor: Minor
    unreconciled_line_count: int
    can_reconcile: bool
    hint: str | None


@dataclass(frozen=True)
class Reconciliation:
    id: int
    account_id: int
    statement_date: str
    statement_balance_minor: Minor
    book_balance_minor: Minor
    reconciled_at: str
    note: str | None
    reverses_id: int | None


def _require_statement_account(conn: sqlite3.Connection, account_id: int) -> None:
    account = conn.execute(
        "SELECT id, name, is_statement_account FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if account is None:
        raise ReconciliationError(f"no account with id {account_id}")
    if not account["is_statement_account"]:
        # You reconcile things that issue statements. ADR 0007 already models exactly
        # that list, which is why this is a lookup and not another heuristic.
        raise ReconciliationError(
            f"{account['name']} does not issue statements, so there is nothing to "
            f"reconcile it against"
        )


def _book_balance(conn: sqlite3.Connection, account_id: int, as_of: str) -> Minor:
    """What SlowBooks thinks the account held at end of `as_of`.

    Signed-to-natural conversion: a credit card is credit-normal, so its raw balance is
    negative when you owe money. Users and banks both say "I owe $900", not "-900", so
    liabilities are flipped to read the way a statement does.
    """
    raw = ledger.account_balance(conn, account_id, as_of=as_of)
    account = accounts.list_all(conn, active_only=False)
    kind = next(a.type for a in account if a.id == account_id)
    return -raw if kind == "liability" else raw


def _difference_hint(difference: Minor) -> str | None:
    """A nudge toward the cause of a gap.

    Deliberately modest -- ADR 0009 is honest that real discrepancy analysis is deferred,
    so this offers the two tells a bookkeeper would check first rather than pretending to
    diagnose.
    """
    if difference == 0:
        return None

    amount = money.format(abs(difference))
    direction = "more" if difference > 0 else "less"
    hint = f"SlowBooks shows {amount} {direction} than the bank does."

    # A transposition (94 typed as 49) always leaves a difference divisible by 9. It's
    # the oldest trick in bookkeeping and it costs nothing to check.
    if abs(difference) % 9 == 0:
        hint += (
            " That difference divides by 9, which often means two digits were swapped"
            " somewhere — worth checking amounts before hunting for a missing"
            " transaction."
        )
    else:
        hint += (
            " Common causes: a transaction the bank has and you haven't imported yet,"
            " a duplicate, or a statement that starts mid-period."
        )
    return hint


def preview(
    conn: sqlite3.Connection,
    account_id: int,
    statement_date: date | str,
    statement_balance_minor: Minor,
) -> Preview:
    """Compare the bank's claim to ours. Changes nothing."""
    _require_statement_account(conn, account_id)
    iso = statement_date.isoformat() if isinstance(statement_date, date) else statement_date

    account = accounts.list_all(conn, active_only=False)
    match = next((a for a in account if a.id == account_id), None)
    if match is None:
        raise ReconciliationError(f"no account with id {account_id}")

    book = _book_balance(conn, account_id, iso)
    difference = book - statement_balance_minor

    unreconciled = conn.execute(
        """SELECT COUNT(*) AS n
             FROM journal_lines l
             JOIN journal_entries e ON e.id = l.entry_id
            WHERE l.account_id = ? AND e.posted_at IS NOT NULL
              AND e.entry_date <= ? AND l.reconciliation_id IS NULL""",
        (account_id, iso),
    ).fetchone()["n"]

    return Preview(
        account_id=account_id,
        account_code=match.code,
        account_name=match.name,
        statement_date=iso,
        statement_balance_minor=statement_balance_minor,
        book_balance_minor=book,
        difference_minor=difference,
        unreconciled_line_count=unreconciled,
        can_reconcile=difference == 0,
        hint=_difference_hint(difference),
    )


def reconcile(
    conn: sqlite3.Connection,
    account_id: int,
    statement_date: date | str,
    statement_balance_minor: Minor,
    note: str | None = None,
) -> int:
    """Record the user's assertion that this account matches the bank. Returns its id.

    Refuses when the difference is non-zero. That refusal is the feature: a
    reconciliation that tolerated a gap would assert something untrue, and the whole
    value of the record is that it is a claim someone stands behind.
    """
    state = preview(conn, account_id, statement_date, statement_balance_minor)

    if not state.can_reconcile:
        raise ReconciliationError(
            f"cannot reconcile: {money.format(state.difference_minor)} difference between "
            f"the book ({money.format(state.book_balance_minor)}) and the statement "
            f"({money.format(state.statement_balance_minor)})"
        )

    existing = latest(conn, account_id)
    if existing and existing.statement_date >= state.statement_date:
        raise ReconciliationError(
            f"{state.account_name} is already reconciled through "
            f"{existing.statement_date}; reconcile a later date, or undo that one first"
        )

    try:
        conn.execute("BEGIN")
        cursor = conn.execute(
            """INSERT INTO reconciliations
                   (account_id, statement_date, statement_balance_minor,
                    book_balance_minor, note)
               VALUES (?, ?, ?, ?, ?)""",
            (account_id, state.statement_date, statement_balance_minor,
             state.book_balance_minor, note),
        )
        reconciliation_id = cursor.lastrowid

        # Stamp the lines this covers. Allowed on posted lines because ADR 0004's
        # immutability is about financial facts -- this is a note about a line, not a
        # change to what it says.
        conn.execute(
            """UPDATE journal_lines
                  SET reconciliation_id = ?
                WHERE reconciliation_id IS NULL
                  AND account_id = ?
                  AND entry_id IN (SELECT id FROM journal_entries
                                    WHERE posted_at IS NOT NULL AND entry_date <= ?)""",
            (reconciliation_id, account_id, state.statement_date),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return reconciliation_id


def undo(conn: sqlite3.Connection, reconciliation_id: int, reason: str | None = None) -> int:
    """Reverse a reconciliation with a new record. Returns the reversing id.

    Append-only, exactly like the ledger (ADR 0004): deleting one would rewrite history,
    reversing one records that the user changed their mind. The distinction matters most
    to whoever audits this later.
    """
    original = get(conn, reconciliation_id)
    if original is None:
        raise ReconciliationError(f"no reconciliation with id {reconciliation_id}")

    already = conn.execute(
        "SELECT id FROM reconciliations WHERE reverses_id = ?", (reconciliation_id,)
    ).fetchone()
    if already:
        raise ReconciliationError(
            f"reconciliation {reconciliation_id} was already undone by {already['id']}"
        )

    try:
        conn.execute("BEGIN")
        cursor = conn.execute(
            """INSERT INTO reconciliations
                   (account_id, statement_date, statement_balance_minor,
                    book_balance_minor, note, reverses_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (original.account_id, original.statement_date,
             original.statement_balance_minor, original.book_balance_minor,
             f"Undo: {reason}" if reason else "Undo", reconciliation_id),
        )
        # Release the lines so they can be reconciled again.
        conn.execute(
            "UPDATE journal_lines SET reconciliation_id = NULL WHERE reconciliation_id = ?",
            (reconciliation_id,),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return cursor.lastrowid


def get(conn: sqlite3.Connection, reconciliation_id: int) -> Reconciliation | None:
    row = conn.execute(
        """SELECT id, account_id, statement_date, statement_balance_minor,
                  book_balance_minor, reconciled_at, note, reverses_id
             FROM reconciliations WHERE id = ?""",
        (reconciliation_id,),
    ).fetchone()
    return Reconciliation(**dict(row)) if row else None


def latest(conn: sqlite3.Connection, account_id: int) -> Reconciliation | None:
    """The most recent reconciliation still in force for this account.

    Undone ones don't count, and neither do the undo records themselves -- an undo is
    bookkeeping about a reconciliation, not a reconciliation.
    """
    row = conn.execute(
        """SELECT r.id, r.account_id, r.statement_date, r.statement_balance_minor,
                  r.book_balance_minor, r.reconciled_at, r.note, r.reverses_id
             FROM reconciliations r
            WHERE r.account_id = ?
              AND r.reverses_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM reconciliations u WHERE u.reverses_id = r.id)
            ORDER BY r.statement_date DESC, r.id DESC
            LIMIT 1""",
        (account_id,),
    ).fetchone()
    return Reconciliation(**dict(row)) if row else None


def history(conn: sqlite3.Connection, account_id: int | None = None) -> list[Reconciliation]:
    sql = """SELECT id, account_id, statement_date, statement_balance_minor,
                    book_balance_minor, reconciled_at, note, reverses_id
               FROM reconciliations"""
    params: list[object] = []
    if account_id is not None:
        sql += " WHERE account_id = ?"
        params.append(account_id)
    sql += " ORDER BY statement_date DESC, id DESC"
    return [Reconciliation(**dict(row)) for row in conn.execute(sql, params)]


def find_backdated_entries(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Entries posted into an already-reconciled period.

    This is why we store book_balance_minor rather than recomputing it. A reconciliation
    is a claim about a moment; if a later entry is backdated in behind it, the claim is
    quietly no longer true, and only the number we wrote down at the time can reveal it.

    Detection, not prevention -- prevention is period locking (v0.2). Worth being clear
    that the user finds out after the fact.
    """
    rows = conn.execute(
        """SELECT e.id AS entry_id, e.entry_date, e.description,
                  a.code AS account_code, a.name AS account_name,
                  r.id AS reconciliation_id, r.statement_date
             FROM journal_lines l
             JOIN journal_entries e ON e.id = l.entry_id
             JOIN accounts a        ON a.id = l.account_id
             JOIN reconciliations r ON r.account_id = l.account_id
            WHERE e.posted_at IS NOT NULL
              AND l.reconciliation_id IS NULL
              AND e.entry_date <= r.statement_date
              AND r.reverses_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM reconciliations u WHERE u.reverses_id = r.id)
            ORDER BY e.entry_date""",
    ).fetchall()
    return [dict(row) for row in rows]
