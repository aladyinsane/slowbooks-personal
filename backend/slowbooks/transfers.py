"""Transfers between the user's own accounts.

Moving $5,000 from checking to savings is not income and not an expense. It must have
zero P&L impact and must post exactly ONE journal entry no matter how many of your
statements it shows up on. See ADR 0007.

The trap this module exists to prevent: a transfer between two imported accounts
produces two rows (-5,000 in checking, +5,000 in savings). Each one, categorized
independently and *correctly*, yields the same entry -- debit savings, credit checking.
Post both and you have moved $10,000. The books still balance and the P&L is still
untouched, so the debits==credits invariant does not save us here. Two correct entries
can still be a wrong answer.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

# Banks rarely post both sides on the same day, but they don't take weeks either. Five
# days spans a weekend plus slack. Too wide invents matches between unrelated round
# numbers; too narrow misses real transfers. Deliberately conservative -- a missed match
# is a visible chore, an invented one is a silently wrong Balance Sheet.
DEFAULT_WINDOW_DAYS = 5


@dataclass(frozen=True)
class TransferMatch:
    staged_id: int
    counterpart_id: int
    days_apart: int


def find_counterpart(
    conn: sqlite3.Connection,
    staged_id: int,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> int | None:
    """The opposite side of this transaction, if it looks like one.

    Criteria: exactly opposite amount, a *different* statement account, within the date
    window, still pending, and not already matched. Amount must match exactly -- see
    ADR 0007 on why wire fees and FX break this.
    """
    row = conn.execute(
        """SELECT s.id, s.account_id, s.txn_date, s.amount_minor, s.status,
                  s.transfer_match_id
             FROM staged_transactions s WHERE s.id = ?""",
        (staged_id,),
    ).fetchone()
    if row is None or row["status"] != "pending" or row["transfer_match_id"] is not None:
        return None

    if not _is_statement_account(conn, row["account_id"]):
        return None

    low = (date.fromisoformat(row["txn_date"]) - timedelta(days=window_days)).isoformat()
    high = (date.fromisoformat(row["txn_date"]) + timedelta(days=window_days)).isoformat()

    candidates = conn.execute(
        """SELECT s.id, s.txn_date
             FROM staged_transactions s
             JOIN accounts a ON a.id = s.account_id
            WHERE s.amount_minor = ?
              AND s.account_id <> ?
              AND a.is_statement_account = 1
              AND s.status = 'pending'
              AND s.transfer_match_id IS NULL
              AND s.txn_date BETWEEN ? AND ?
              AND s.id <> ?""",
        (-row["amount_minor"], row["account_id"], low, high, staged_id),
    ).fetchall()

    if not candidates:
        return None

    # Closest date wins, then lowest id. Ties must resolve deterministically or the same
    # import could pair differently on a re-run.
    origin = date.fromisoformat(row["txn_date"])
    best = min(
        candidates,
        key=lambda c: (abs((date.fromisoformat(c["txn_date"]) - origin).days), c["id"]),
    )
    return best["id"]


def detect_in_batch(
    conn: sqlite3.Connection,
    batch_id: int,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> int:
    """Pair transfers involving this batch's rows. Returns the number of pairs found.

    Matches against *all* pending rows, not just this batch's: the two sides of a
    transfer almost always arrive in two separate CSVs, so a batch-local search would
    find nothing in exactly the case that matters.

    Only suggests. Nothing posts, and the user can unlink -- principle 8, and ADR 0007's
    reason for never auto-posting a guess about which rows belong together.
    """
    rows = conn.execute(
        """SELECT s.id FROM staged_transactions s
             JOIN accounts a ON a.id = s.account_id
            WHERE s.batch_id = ? AND s.status = 'pending'
              AND s.transfer_match_id IS NULL
              AND a.is_statement_account = 1
            ORDER BY s.txn_date, s.id""",
        (batch_id,),
    ).fetchall()

    pairs = 0
    for row in rows:
        counterpart = find_counterpart(conn, row["id"], window_days=window_days)
        if counterpart is None:
            continue
        link(conn, row["id"], counterpart)
        pairs += 1
    return pairs


def link(conn: sqlite3.Connection, staged_id: int, counterpart_id: int) -> None:
    """Mark two rows as the two sides of one transfer."""
    if staged_id == counterpart_id:
        raise ValueError("a transaction cannot be its own transfer counterpart")
    conn.execute(
        "UPDATE staged_transactions SET transfer_match_id = ? WHERE id = ?",
        (counterpart_id, staged_id),
    )
    conn.execute(
        "UPDATE staged_transactions SET transfer_match_id = ? WHERE id = ?",
        (staged_id, counterpart_id),
    )


def unlink(conn: sqlite3.Connection, staged_id: int) -> None:
    """Reject a suggested pairing. Both rows go back to being ordinary transactions."""
    row = conn.execute(
        "SELECT transfer_match_id FROM staged_transactions WHERE id = ?", (staged_id,)
    ).fetchone()
    if row is None or row["transfer_match_id"] is None:
        return
    conn.execute(
        "UPDATE staged_transactions SET transfer_match_id = NULL WHERE id IN (?, ?)",
        (staged_id, row["transfer_match_id"]),
    )


def _is_statement_account(conn: sqlite3.Connection, account_id: int) -> bool:
    row = conn.execute(
        "SELECT is_statement_account FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    return bool(row and row["is_statement_account"])
