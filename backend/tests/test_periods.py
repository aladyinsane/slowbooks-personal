"""Period locking tests (ADR 0011).

ADR 0009 shipped reconciliation with a named hole: it detects a backdated entry but
cannot prevent one. These prove the hole is closed, and closed in the database rather
than in application code — because every invariant we put in a trigger has held, and the
one we left to application discipline (ADR 0004's draft zone) was quietly skipped by the
first UI that touched it.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from slowbooks import accounts, ledger, periods, posting, reconciliation
from slowbooks.importing import csv_import


@pytest.fixture
def checking(conn):
    return accounts.by_code(conn, "1000").id


@pytest.fixture
def supplies(conn):
    return accounts.by_code(conn, "6100").id


@pytest.fixture
def books(conn, checking, supplies):
    ledger.post(conn, "2026-01-02", "Owner investment",
                [ledger.debit(checking, 10_000_00),
                 ledger.credit(accounts.by_code(conn, "3000").id, 10_000_00)])
    ledger.post(conn, "2026-01-15", "Staples",
                [ledger.debit(supplies, 450_00), ledger.credit(checking, 450_00)])
    return conn


class TestClosing:
    def test_nothing_is_closed_to_begin_with(self, conn):
        assert periods.closed_through(conn) is None
        assert not periods.is_closed(conn, "2020-01-01")

    def test_closing_sets_the_line(self, books):
        periods.close(books, "2026-01-31", "January")
        assert periods.closed_through(books) == "2026-01-31"
        assert periods.is_closed(books, "2026-01-15")
        assert periods.is_closed(books, "2026-01-31")  # inclusive
        assert not periods.is_closed(books, "2026-02-01")

    def test_closing_forward_moves_the_line(self, books):
        periods.close(books, "2026-01-31")
        periods.close(books, "2026-02-28")
        assert periods.closed_through(books) == "2026-02-28"

    def test_cannot_close_backwards(self, books):
        periods.close(books, "2026-02-28")
        with pytest.raises(periods.PeriodError, match="already closed through"):
            periods.close(books, "2026-01-31")

    def test_cannot_close_the_same_date_twice(self, books):
        periods.close(books, "2026-01-31")
        with pytest.raises(periods.PeriodError, match="already closed through"):
            periods.close(books, "2026-01-31")

    def test_a_non_date_is_refused(self, conn):
        with pytest.raises(periods.PeriodError, match="not a date"):
            periods.close(conn, "last tuesday")


class TestTheLock:
    def test_posting_into_a_closed_period_is_refused(self, books, checking, supplies):
        periods.close(books, "2026-01-31")

        with pytest.raises(ledger.LedgerError, match="books are closed through 2026-01-31"):
            ledger.post(books, "2026-01-20", "Forgotten fee",
                        [ledger.debit(supplies, 25_00), ledger.credit(checking, 25_00)])

    def test_the_error_says_how_to_get_past_it(self, books, checking, supplies):
        periods.close(books, "2026-01-31")
        with pytest.raises(ledger.LedgerError) as exc:
            ledger.post(books, "2026-01-20", "Fee",
                        [ledger.debit(supplies, 25_00), ledger.credit(checking, 25_00)])
        # Naming the date and the way out beats "operation not permitted".
        assert "Reopen that period" in str(exc.value)

    def test_posting_after_the_line_still_works(self, books, checking, supplies):
        periods.close(books, "2026-01-31")
        entry = ledger.post(books, "2026-02-01", "February supplies",
                            [ledger.debit(supplies, 25_00), ledger.credit(checking, 25_00)])
        assert entry > 0
        assert ledger.is_balanced(books)

    def test_the_database_refuses_even_via_raw_sql(self, books, checking, supplies):
        """The point of ADR 0011.

        A lock that lives in ledger.post() is a lock until someone writes a second
        writer. This one is in the database, so it holds against anything that speaks
        SQLite to the file.
        """
        periods.close(books, "2026-01-31")

        cursor = books.execute(
            """INSERT INTO journal_entries (entry_date, description, source, posted_at)
               VALUES ('2026-01-20', 'Sneaking in', 'manual', NULL)"""
        )
        entry_id = cursor.lastrowid
        books.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?,?,?)",
            (entry_id, supplies, 2500),
        )
        books.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?,?,?)",
            (entry_id, checking, -2500),
        )

        with pytest.raises(sqlite3.IntegrityError, match="books are closed"):
            books.execute(
                "UPDATE journal_entries SET posted_at = '2026-01-20' WHERE id = ?",
                (entry_id,),
            )

    def test_existing_entries_are_untouched_by_a_close(self, books):
        before = ledger.account_balance(books, accounts.by_code(books, "1000").id)
        periods.close(books, "2026-01-31")
        assert ledger.account_balance(books, accounts.by_code(books, "1000").id) == before
        assert ledger.is_balanced(books)

    def test_posting_a_staged_row_into_a_closed_period_is_refused(self, books, checking):
        periods.close(books, "2026-01-31")
        csv_import.import_csv(
            books, "Date,Description,Amount\n2026-01-20,STAPLES 00999,-30.00\n",
            "late.csv", checking,
        )
        staged_id = books.execute(
            "SELECT id FROM staged_transactions ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

        with pytest.raises(ledger.LedgerError, match="books are closed"):
            posting.post_staged(books, staged_id)


class TestReopening:
    def test_reopening_moves_the_line_back(self, books):
        close_id = periods.close(books, "2026-01-31")
        periods.reopen(books, close_id, "found a missing receipt")
        assert periods.closed_through(books) is None

    def test_reopening_falls_back_to_the_previous_close(self, books):
        periods.close(books, "2026-01-31")
        february = periods.close(books, "2026-02-28")
        periods.reopen(books, february)
        assert periods.closed_through(books) == "2026-01-31"

    def test_posting_works_again_after_a_reopen(self, books, checking, supplies):
        close_id = periods.close(books, "2026-01-31")
        periods.reopen(books, close_id)
        entry = ledger.post(books, "2026-01-20", "Forgotten fee",
                            [ledger.debit(supplies, 25_00), ledger.credit(checking, 25_00)])
        assert entry > 0

    def test_reopening_is_a_record_not_an_erasure(self, books):
        close_id = periods.close(books, "2026-01-31", "January")
        reopen_id = periods.reopen(books, close_id, "missing receipt")

        # Both survive: someone changed their mind and the history says so.
        assert periods.get(books, close_id) is not None
        assert periods.get(books, reopen_id).reopens_id == close_id
        assert len(periods.history(books)) == 2

    def test_cannot_reopen_twice(self, books):
        close_id = periods.close(books, "2026-01-31")
        periods.reopen(books, close_id)
        with pytest.raises(periods.PeriodError, match="already reopened"):
            periods.reopen(books, close_id)

    def test_cannot_reopen_a_reopening(self, books):
        close_id = periods.close(books, "2026-01-31")
        reopen_id = periods.reopen(books, close_id)
        with pytest.raises(periods.PeriodError, match="itself a reopening"):
            periods.reopen(books, reopen_id)

    def test_reopening_nothing_is_an_error(self, conn):
        with pytest.raises(periods.PeriodError, match="no period close"):
            periods.reopen(conn, 9999)


class TestVoidFallsForward:
    """ADR 0004 dated a reversal to match its original. In a closed period that is
    exactly wrong — it would change a closed period, which is what closing prevents.
    The rule inverts at the lock line (ADR 0011).
    """

    def test_void_in_an_open_period_matches_the_original(self, books, checking, supplies):
        entry = ledger.post(books, "2026-03-10", "Mistake",
                            [ledger.debit(supplies, 100_00), ledger.credit(checking, 100_00)])
        reversal = ledger.void(books, entry, "wrong")
        assert ledger.get(books, reversal).entry_date == "2026-03-10"

    def test_void_in_a_closed_period_falls_forward(self, books, checking, supplies):
        entry = ledger.post(books, "2026-01-15", "Mistake",
                            [ledger.debit(supplies, 100_00), ledger.credit(checking, 100_00)])
        periods.close(books, "2026-01-31")

        reversal_id = ledger.void(books, entry, "not a business expense")
        reversal = ledger.get(books, reversal_id)

        assert reversal.entry_date > "2026-01-31"
        assert reversal.entry_date == periods.first_open_date(books)
        # The original is untouched, so January's reports still say what they said.
        assert ledger.get(books, entry).entry_date == "2026-01-15"
        assert ledger.is_balanced(books)

    def test_the_reversal_says_why_its_date_moved(self, books, checking, supplies):
        entry = ledger.post(books, "2026-01-15", "Mistake",
                            [ledger.debit(supplies, 100_00), ledger.credit(checking, 100_00)])
        periods.close(books, "2026-01-31")
        reversal = ledger.get(books, ledger.void(books, entry))
        # The void of a January entry showing up in July will confuse someone. Say why.
        assert "closed period" in reversal.description
        assert "2026-01-15" in reversal.description

    def test_first_open_date_is_today_when_nothing_is_closed(self, conn):
        assert periods.first_open_date(conn) == date.today().isoformat()

    def test_first_open_date_clears_a_future_close(self, conn):
        far_future = (date.today() + timedelta(days=60)).isoformat()
        periods.close(conn, far_future)
        expected = (date.today() + timedelta(days=61)).isoformat()
        assert periods.first_open_date(conn) == expected


class TestReadiness:
    def test_a_tidy_period_says_so(self, books, checking):
        # Reconcile every statement account through the date, nothing left pending.
        for account in accounts.list_statement_accounts(books):
            balance = ledger.account_balance(books, account.id, as_of="2026-01-31")
            natural = -balance if account.type == "liability" else balance
            reconciliation.reconcile(books, account.id, "2026-01-31", natural)

        state = periods.readiness(books, "2026-01-31")
        assert state["is_tidy"]
        assert state["unreconciled_accounts"] == []

    def test_unreconciled_accounts_are_named(self, books):
        state = periods.readiness(books, "2026-01-31")
        assert not state["is_tidy"]
        names = {a["account"] for a in state["unreconciled_accounts"]}
        assert any("Business Checking" in n for n in names)

    def test_empty_accounts_are_not_warned_about(self, books):
        """Found by driving it: the panel listed all four statement accounts as
        unreconciled, but savings, the card and the loan had no transactions at all.
        Nothing to reconcile, so warning about them is a false alarm -- and four
        warnings where one is real dilutes the one that matters.
        """
        state = periods.readiness(books, "2026-01-31")
        names = {a["account"] for a in state["unreconciled_accounts"]}
        assert not any("Savings" in n for n in names)
        assert not any("Credit Card" in n for n in names)
        assert not any("Loans" in n for n in names)
        # Only the account that actually has money in it.
        assert len(state["unreconciled_accounts"]) == 1

    def test_an_account_with_activity_is_warned_about(self, books, checking):
        savings = accounts.by_code(books, "1010").id
        ledger.post(books, "2026-01-20", "To savings",
                    [ledger.debit(savings, 1_000_00), ledger.credit(checking, 1_000_00)])
        state = periods.readiness(books, "2026-01-31")
        names = {a["account"] for a in state["unreconciled_accounts"]}
        assert any("Savings" in n for n in names)

    def test_uncategorized_transactions_are_counted(self, books, checking):
        csv_import.import_csv(
            books, "Date,Description,Amount\n2026-01-20,ZZQQ MYSTERY,-30.00\n",
            "jan.csv", checking,
        )
        state = periods.readiness(books, "2026-01-31")
        assert state["uncategorized_transactions"] == 1

    def test_readiness_never_blocks(self, books):
        """Advisory, not a veto (ADR 0011).

        A user may close knowing an account isn't reconciled — the statement might not
        have arrived. Refusing would make us the boss of their books.
        """
        state = periods.readiness(books, "2026-01-31")
        assert not state["is_tidy"]
        assert periods.close(books, "2026-01-31") > 0  # allowed anyway


class TestWithReconciliation:
    def test_closing_closes_the_backdating_hole(self, books, checking, supplies):
        """The gap ADR 0009 admitted, closed.

        PR #7 demonstrated: post a January fee into a reconciled January and
        ledger_balanced is true, the trial balance balances, the Balance Sheet balances
        — and January is silently wrong. We could only tell the user afterwards.
        """
        balance = ledger.account_balance(books, checking, as_of="2026-01-31")
        reconciliation.reconcile(books, checking, "2026-01-31", balance)
        periods.close(books, "2026-01-31")

        with pytest.raises(ledger.LedgerError, match="books are closed"):
            ledger.post(books, "2026-01-20", "Forgotten fee",
                        [ledger.debit(supplies, 25_00), ledger.credit(checking, 25_00)])

        # Nothing to detect after the fact, because nothing got in.
        assert reconciliation.find_backdated_entries(books) == []

    def test_detection_still_covers_earlier_entries(self, books, checking, supplies):
        # Reconcile, backdate, *then* close. The lock can't retroactively prevent what
        # already happened, so detection still earns its place.
        balance = ledger.account_balance(books, checking, as_of="2026-01-31")
        reconciliation.reconcile(books, checking, "2026-01-31", balance)
        ledger.post(books, "2026-01-20", "Slipped in",
                    [ledger.debit(supplies, 25_00), ledger.credit(checking, 25_00)])

        assert len(reconciliation.find_backdated_entries(books)) == 1
