"""Ledger tests: the invariants from ADR 0004.

The point of these is that the *database* refuses bad books, not that our Python
happens to be careful. So several go around the ledger API and talk to SQLite
directly -- an invariant that only holds when you use the front door isn't one.
"""

from __future__ import annotations

import sqlite3

import pytest

from slowbooks import accounts, ledger


@pytest.fixture
def chart(conn):
    return {
        "checking": accounts.by_code(conn, "1000").id,
        "card": accounts.by_code(conn, "2100").id,
        "supplies": accounts.by_code(conn, "6100").id,
        "sales": accounts.by_code(conn, "4000").id,
        "capital": accounts.by_code(conn, "3000").id,
    }


class TestPosting:
    def test_posts_a_balanced_entry(self, conn, chart):
        entry_id = ledger.post(
            conn, "2026-01-15", "Staples run",
            [ledger.debit(chart["supplies"], 45000),
             ledger.credit(chart["card"], 45000)],
        )
        assert entry_id > 0
        assert ledger.is_balanced(conn)

    def test_rejects_unbalanced_entry(self, conn, chart):
        with pytest.raises(ledger.LedgerError, match="does not balance"):
            ledger.post(
                conn, "2026-01-15", "Wrong",
                [ledger.debit(chart["supplies"], 45000),
                 ledger.credit(chart["card"], 40000)],
            )

    def test_rejects_single_line_entry(self, conn, chart):
        with pytest.raises(ledger.LedgerError, match="at least two lines"):
            ledger.post(conn, "2026-01-15", "Half", [ledger.debit(chart["supplies"], 100)])

    def test_failed_post_leaves_nothing_behind(self, conn, chart):
        with pytest.raises(ledger.LedgerError):
            ledger.post(
                conn, "2026-01-15", "Wrong",
                [ledger.debit(chart["supplies"], 45000),
                 ledger.credit(chart["card"], 40000)],
            )
        # The rollback must be complete -- a half-written draft would be a landmine.
        assert conn.execute("SELECT COUNT(*) AS n FROM journal_entries").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM journal_lines").fetchone()["n"] == 0

    def test_multi_line_split_entry(self, conn, chart):
        # A loan payment: principal + interest out of checking. The v0.5 shape.
        entry_id = ledger.post(
            conn, "2026-01-15", "Loan payment",
            [
                ledger.debit(accounts.by_code(conn, "2500").id, 90000),   # principal
                ledger.debit(accounts.by_code(conn, "6700").id, 30000),   # interest
                ledger.credit(chart["checking"], 120000),
            ],
        )
        assert entry_id > 0
        assert ledger.is_balanced(conn)

    def test_debit_and_credit_helpers_reject_negatives(self, chart):
        with pytest.raises(ValueError):
            ledger.debit(chart["supplies"], -100)
        with pytest.raises(ValueError):
            ledger.credit(chart["card"], -100)


class TestDatabaseEnforcement:
    """The triggers, tested by trying to go around the application code."""

    def test_trigger_blocks_unbalanced_post_even_via_raw_sql(self, conn, chart):
        cursor = conn.execute(
            """INSERT INTO journal_entries (entry_date, description, source, posted_at)
               VALUES ('2026-01-15', 'Sneaky', 'manual', NULL)"""
        )
        entry_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?, ?, ?)",
            (entry_id, chart["supplies"], 45000),
        )
        conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?, ?, ?)",
            (entry_id, chart["card"], -40000),
        )
        with pytest.raises(sqlite3.IntegrityError, match="unbalanced"):
            conn.execute(
                "UPDATE journal_entries SET posted_at = '2026-01-15' WHERE id = ?", (entry_id,)
            )

    def test_posted_entry_cannot_be_deleted(self, conn, chart):
        entry_id = ledger.post(
            conn, "2026-01-15", "Staples",
            [ledger.debit(chart["supplies"], 45000), ledger.credit(chart["card"], 45000)],
        )
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))

    def test_posted_entry_date_cannot_be_changed(self, conn, chart):
        entry_id = ledger.post(
            conn, "2026-01-15", "Staples",
            [ledger.debit(chart["supplies"], 45000), ledger.credit(chart["card"], 45000)],
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE journal_entries SET entry_date = '2026-02-01' WHERE id = ?", (entry_id,)
            )

    def test_posted_lines_cannot_be_amended(self, conn, chart):
        entry_id = ledger.post(
            conn, "2026-01-15", "Staples",
            [ledger.debit(chart["supplies"], 45000), ledger.credit(chart["card"], 45000)],
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE journal_lines SET amount_minor = 999 WHERE entry_id = ?", (entry_id,)
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot delete lines"):
            conn.execute("DELETE FROM journal_lines WHERE entry_id = ?", (entry_id,))
        with pytest.raises(sqlite3.IntegrityError, match="cannot add lines"):
            conn.execute(
                "INSERT INTO journal_lines (entry_id, account_id, amount_minor) "
                "VALUES (?, ?, ?)",
                (entry_id, chart["supplies"], 100),
            )

    def test_zero_amount_lines_are_rejected(self, conn, chart):
        cursor = conn.execute(
            """INSERT INTO journal_entries (entry_date, description, source, posted_at)
               VALUES ('2026-01-15', 'Zero', 'manual', NULL)"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO journal_lines (entry_id, account_id, amount_minor) "
                "VALUES (?, ?, 0)",
                (cursor.lastrowid, chart["supplies"]),
            )


class TestVoid:
    def test_void_reverses_rather_than_deletes(self, conn, chart):
        entry_id = ledger.post(
            conn, "2026-01-15", "Staples",
            [ledger.debit(chart["supplies"], 45000), ledger.credit(chart["card"], 45000)],
        )
        reversal_id = ledger.void(conn, entry_id, "wrong card")

        # Original survives -- that is the whole point of the audit trail.
        assert ledger.get(conn, entry_id) is not None
        assert ledger.get(conn, reversal_id).reverses_entry_id == entry_id
        # And the net effect is zero.
        assert ledger.account_balance(conn, chart["supplies"]) == 0
        assert ledger.account_balance(conn, chart["card"]) == 0
        assert ledger.is_balanced(conn)

    def test_cannot_void_twice(self, conn, chart):
        entry_id = ledger.post(
            conn, "2026-01-15", "Staples",
            [ledger.debit(chart["supplies"], 45000), ledger.credit(chart["card"], 45000)],
        )
        ledger.void(conn, entry_id)
        with pytest.raises(ledger.LedgerError, match="already voided"):
            ledger.void(conn, entry_id)

    def test_cannot_void_nonexistent_entry(self, conn):
        with pytest.raises(ledger.LedgerError, match="no entry"):
            ledger.void(conn, 9999)


class TestBalances:
    def test_account_balance_signs_follow_normal_balance(self, conn, chart):
        ledger.post(
            conn, "2026-01-15", "Sale",
            [ledger.debit(chart["checking"], 100000), ledger.credit(chart["sales"], 100000)],
        )
        # Asset: debit-normal, positive. Revenue: credit-normal, negative internally.
        assert ledger.account_balance(conn, chart["checking"]) == 100000
        assert ledger.account_balance(conn, chart["sales"]) == -100000

    def test_as_of_excludes_later_entries(self, conn, chart):
        ledger.post(
            conn, "2026-01-15", "Sale 1",
            [ledger.debit(chart["checking"], 100000), ledger.credit(chart["sales"], 100000)],
        )
        ledger.post(
            conn, "2026-02-15", "Sale 2",
            [ledger.debit(chart["checking"], 50000), ledger.credit(chart["sales"], 50000)],
        )
        assert ledger.account_balance(conn, chart["checking"], as_of="2026-01-31") == 100000
        assert ledger.account_balance(conn, chart["checking"], as_of="2026-02-28") == 150000
