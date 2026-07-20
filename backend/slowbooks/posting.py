"""Turning staged transactions into journal entries.

This is the boundary between the mutable zone (staged rows the user can freely edit)
and the permanent record (posted, immutable, append-only entries). See ADR 0004.
"""

from __future__ import annotations

import sqlite3

from slowbooks import accounts, ledger


class PostingError(Exception):
    pass


def _settle_transfer_counterpart(
    conn: sqlite3.Connection, row: sqlite3.Row, entry_id: int, destination_id: int
) -> None:
    """Mark the other side of a transfer as settled by the same entry (ADR 0007).

    The single most important guard against double-counting. One transfer is one journal
    entry, however many statements it appears on. Post both sides independently and you
    have moved the money twice -- while the books still balance, so nothing else in the
    system notices.

    Deliberately does *not* rely on detection having run. A user who hand-picks
    "Transfer to Savings" on both rows is in exactly the same danger as one who accepted
    a suggested pair, so when no pairing exists we look for the counterpart here. Belt
    and braces, because the failure is silent and lands on the Balance Sheet.
    """
    counterpart_id = row["transfer_match_id"]

    if counterpart_id is None:
        # Not paired: find the unposted mirror image sitting in the destination account.
        from datetime import date, timedelta

        from slowbooks.transfers import DEFAULT_WINDOW_DAYS

        origin = date.fromisoformat(row["txn_date"])
        low = (origin - timedelta(days=DEFAULT_WINDOW_DAYS)).isoformat()
        high = (origin + timedelta(days=DEFAULT_WINDOW_DAYS)).isoformat()
        candidate = conn.execute(
            """SELECT id FROM staged_transactions
                WHERE account_id = ? AND amount_minor = ? AND status = 'pending'
                  AND transfer_match_id IS NULL AND txn_date BETWEEN ? AND ?
                ORDER BY ABS(JULIANDAY(txn_date) - JULIANDAY(?)), id
                LIMIT 1""",
            (destination_id, -row["amount_minor"], low, high, row["txn_date"]),
        ).fetchone()
        if candidate is None:
            return
        counterpart_id = candidate["id"]

    counterpart = conn.execute(
        "SELECT id, status FROM staged_transactions WHERE id = ?", (counterpart_id,)
    ).fetchone()
    if counterpart is None or counterpart["status"] == "posted":
        return

    conn.execute(
        """UPDATE staged_transactions
              SET status = 'posted', posted_entry_id = ?, transfer_match_id = ?,
                  suggested_account_id = ?,
                  suggested_reason = 'recorded as the other side of a transfer'
            WHERE id = ?""",
        (entry_id, row["id"], row["account_id"], counterpart_id),
    )


def choose_category(
    conn: sqlite3.Connection, staged_id: int, account_id: int | None
) -> None:
    """Set (or clear) a staged row's category without touching the ledger.

    This is the draft zone ADR 0004 designed and the UI originally skipped: the grid
    posted on selection, so a mis-click became an immutable journal entry that could
    only be undone by a reversal. Nothing here is a financial fact yet, so the user can
    change their mind as often as they like -- immutability starts at posting, which is
    where it means something.

    Passing None clears the category, which is how someone says "actually I don't know."
    """
    row = conn.execute(
        "SELECT id, account_id, status FROM staged_transactions WHERE id = ?", (staged_id,)
    ).fetchone()
    if row is None:
        raise PostingError(f"no staged transaction with id {staged_id}")
    if row["status"] == "posted":
        raise PostingError(
            "this transaction is already posted; void it if it needs to change"
        )
    if account_id is not None and account_id == row["account_id"]:
        raise PostingError("a transaction cannot be categorized to its own bank account")
    if account_id is not None:
        exists = conn.execute(
            "SELECT 1 FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if exists is None:
            raise PostingError(f"no account with id {account_id}")

    conn.execute(
        """UPDATE staged_transactions
              SET suggested_account_id = ?, suggested_rule_id = NULL,
                  suggested_reason = ?
            WHERE id = ?""",
        (account_id, "you chose this category" if account_id else None, staged_id),
    )


def post_staged(
    conn: sqlite3.Connection,
    staged_id: int,
    account_id: int | None = None,
) -> int:
    """Post one staged transaction. Returns the journal entry id.

    `account_id` is the *category* -- the other side of the entry. The bank account
    side is implied by which statement the row came from. Falls back to the rule
    suggestion, then to Uncategorized.

    The two-sided entry is built here so the user never has to think in debits and
    credits (principle 2): they pick "Office Supplies" and the second line follows.
    """
    row = conn.execute(
        """SELECT id, account_id, txn_date, description, amount_minor, status,
                  suggested_account_id, transfer_match_id
             FROM staged_transactions WHERE id = ?""",
        (staged_id,),
    ).fetchone()

    if row is None:
        raise PostingError(f"no staged transaction with id {staged_id}")
    if row["status"] == "posted":
        raise PostingError(f"staged transaction {staged_id} is already posted")
    if row["status"] == "ignored":
        raise PostingError(f"staged transaction {staged_id} is ignored")

    amount = row["amount_minor"]
    bank_account_id = row["account_id"]

    # A paired transfer has its counterpart's account as the implicit other side, so the
    # user never has to name a category for it -- there isn't one (ADR 0007).
    if account_id is None and row["transfer_match_id"] is not None:
        counterpart = conn.execute(
            "SELECT account_id FROM staged_transactions WHERE id = ?",
            (row["transfer_match_id"],),
        ).fetchone()
        if counterpart is None:
            raise PostingError("transfer counterpart no longer exists")
        category_id = counterpart["account_id"]
    else:
        category_id = (
            account_id or row["suggested_account_id"] or _fallback_category(conn, amount)
        )

    if category_id == bank_account_id:
        raise PostingError("a transaction cannot be categorized to its own bank account")

    # Money in: debit the bank account (asset up), credit the category (revenue up).
    # Money out: credit the bank account (asset down), debit the category (expense up).
    # For a credit-card account the bank side is a liability, and the same signed
    # arithmetic gives the right answer -- a charge credits the liability, i.e. raises
    # what you owe. This is why the ledger stores signed amounts rather than a
    # debit/credit enum: one code path, no special cases per account type.
    if amount > 0:
        lines = [
            ledger.debit(bank_account_id, amount, row["description"]),
            ledger.credit(category_id, amount, row["description"]),
        ]
    else:
        lines = [
            ledger.debit(category_id, -amount, row["description"]),
            ledger.credit(bank_account_id, -amount, row["description"]),
        ]

    # Both sides being statement accounts is what makes this a transfer rather than a
    # categorization: money left one pocket you own and landed in another.
    is_transfer = accounts.is_statement_account(
        conn, category_id
    ) and accounts.is_statement_account(conn, bank_account_id)

    entry_id = ledger.post(
        conn,
        row["txn_date"],
        row["description"],
        lines,
        source="transfer" if is_transfer else "import",
    )

    # Money moving between two of your own accounts is one event, not two. Settle the
    # counterpart against this same entry so posting the other side later cannot move
    # the money a second time (ADR 0007). Runs for any transfer -- detected or chosen by
    # hand -- because the double-count risk is identical either way.
    if is_transfer:
        _settle_transfer_counterpart(conn, row, entry_id, category_id)

    if account_id is not None:
        # The user named this category themselves, so it is no longer our guess. Leaving
        # the old provenance would make a corrected row keep claiming "starter rule" --
        # which is precisely the lie ADR 0006 exists to prevent, and worse than saying
        # nothing, because the badge is what the user relies on to know what to check.
        conn.execute(
            """UPDATE staged_transactions
                  SET status = 'posted', posted_entry_id = ?,
                      suggested_account_id = ?, suggested_rule_id = NULL,
                      suggested_reason = 'you chose this category'
                WHERE id = ?""",
            (entry_id, category_id, staged_id),
        )
    else:
        # Accepted as-is (e.g. "accept all"). The suggestion stands, and so does the
        # record of where it came from -- accepting a guess does not make it not a guess.
        conn.execute(
            """UPDATE staged_transactions SET status = 'posted', posted_entry_id = ?
                WHERE id = ?""",
            (entry_id, staged_id),
        )
    return entry_id


def post_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, int]:
    """Post every pending row in a batch that has a category or is a paired transfer.

    Rows with no suggestion are deliberately left pending rather than dumped into
    Uncategorized: silently burying unknowns in a catch-all account is how books rot.
    Surfacing them is the honest move, and the user can bulk-assign.

    Paired transfers are included -- they need no category, and the user clicking
    "accept all" is exactly the acceptance ADR 0007 requires before a suggested pairing
    becomes real.
    """
    pending = conn.execute(
        """SELECT id FROM staged_transactions
            WHERE batch_id = ? AND status = 'pending'
              AND (suggested_account_id IS NOT NULL OR transfer_match_id IS NOT NULL)
            ORDER BY txn_date, id""",
        (batch_id,),
    ).fetchall()

    posted = 0
    for row in pending:
        # Re-check: posting one side of a transfer settles the other, which may be a row
        # this loop is about to reach. Trusting the snapshot would double-post it.
        current = conn.execute(
            "SELECT status FROM staged_transactions WHERE id = ?", (row["id"],)
        ).fetchone()
        if current["status"] != "pending":
            continue
        post_staged(conn, row["id"])
        posted += 1

    remaining = conn.execute(
        """SELECT COUNT(*) AS n FROM staged_transactions
            WHERE batch_id = ? AND status = 'pending'""",
        (batch_id,),
    ).fetchone()["n"]

    return {"posted": posted, "still_pending": remaining}


def _fallback_category(conn: sqlite3.Connection, amount_minor: int) -> int:
    code = (
        accounts.UNCATEGORIZED_REVENUE_CODE
        if amount_minor > 0
        else accounts.UNCATEGORIZED_EXPENSE_CODE
    )
    return accounts.by_code(conn, code).id
