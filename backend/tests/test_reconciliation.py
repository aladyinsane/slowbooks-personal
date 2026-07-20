"""Reconciliation tests (ADR 0009).

The distinction under test throughout: the balance trigger proves the books are
*consistent*; reconciliation proves they're *complete*. A perfectly balanced set of books
can be missing every transaction in March, and only this feature can tell.
"""

from __future__ import annotations

import pytest

from slowbooks import accounts, ledger, money, reconciliation
from slowbooks.importing import csv_import


@pytest.fixture
def checking(conn):
    return accounts.by_code(conn, "1000").id


@pytest.fixture
def card(conn):
    return accounts.by_code(conn, "2100").id


@pytest.fixture
def books(conn, checking):
    """You put in $10,000, spend $1,500. Book balance: $8,500."""
    ledger.post(conn, "2026-01-02", "Opening balance",
                [ledger.debit(checking, 10_000_00),
                 ledger.credit(accounts.by_code(conn, "3000").id, 10_000_00)])
    ledger.post(conn, "2026-01-10", "Rent",
                [ledger.debit(accounts.by_code(conn, "6000").id, 1_000_00),
                 ledger.credit(checking, 1_000_00)])
    ledger.post(conn, "2026-01-20", "Groceries",
                [ledger.debit(accounts.by_code(conn, "6100").id, 500_00),
                 ledger.credit(checking, 500_00)])
    return conn


class TestPreview:
    def test_matching_balance_can_reconcile(self, books, checking):
        state = reconciliation.preview(books, checking, "2026-01-31", 8_500_00)
        assert state.book_balance_minor == 8_500_00
        assert state.difference_minor == 0
        assert state.can_reconcile
        assert state.hint is None

    def test_mismatch_reports_the_difference(self, books, checking):
        # Bank says $8,400 -- we're $100 heavy, e.g. a bank fee we haven't imported.
        state = reconciliation.preview(books, checking, "2026-01-31", 8_400_00)
        assert state.difference_minor == 100_00
        assert not state.can_reconcile
        assert "more than the bank" in state.hint

    def test_transposition_hint(self, books, checking):
        # 8500 vs 8500-450: a difference divisible by 9 is the classic swapped-digits
        # tell, and it's the first thing a bookkeeper checks.
        state = reconciliation.preview(books, checking, "2026-01-31", 8_500_00 - 450)
        assert state.difference_minor == 450
        assert "divides by 9" in state.hint

    def test_preview_changes_nothing(self, books, checking):
        reconciliation.preview(books, checking, "2026-01-31", 8_500_00)
        assert reconciliation.latest(books, checking) is None
        assert books.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE reconciliation_id IS NOT NULL"
        ).fetchone()["n"] == 0

    def test_date_scopes_the_book_balance(self, books, checking):
        # As of the 15th, only the investment and rent have happened.
        state = reconciliation.preview(books, checking, "2026-01-15", 9_000_00)
        assert state.book_balance_minor == 9_000_00
        assert state.can_reconcile

    def test_counts_unreconciled_lines(self, books, checking):
        state = reconciliation.preview(books, checking, "2026-01-31", 8_500_00)
        assert state.unreconciled_line_count == 3

    def test_only_statement_accounts_are_reconcilable(self, books):
        # You reconcile things that issue statements. Groceries does not.
        supplies = accounts.by_code(books, "6100").id
        with pytest.raises(
            reconciliation.ReconciliationError, match="does not issue statements"
        ):
            reconciliation.preview(books, supplies, "2026-01-31", 0)

    def test_unknown_account_is_rejected(self, conn):
        with pytest.raises(reconciliation.ReconciliationError, match="no account"):
            reconciliation.preview(conn, 9999, "2026-01-31", 0)


class TestCreditCards:
    def test_card_balance_reads_the_way_a_statement_does(self, conn, card, checking):
        # Charge $900 on the card. The statement says "you owe 900.00", not "-900".
        ledger.post(conn, "2026-01-05", "Office chair",
                    [ledger.debit(accounts.by_code(conn, "1500").id, 900_00),
                     ledger.credit(card, 900_00)])

        state = reconciliation.preview(conn, card, "2026-01-31", 900_00)
        assert state.book_balance_minor == 900_00
        assert state.can_reconcile

    def test_card_payment_reduces_what_you_owe(self, conn, card, checking):
        ledger.post(conn, "2026-01-05", "Office chair",
                    [ledger.debit(accounts.by_code(conn, "1500").id, 900_00),
                     ledger.credit(card, 900_00)])
        ledger.post(conn, "2026-01-25", "Card payment",
                    [ledger.debit(card, 400_00), ledger.credit(checking, 400_00)])

        state = reconciliation.preview(conn, card, "2026-01-31", 500_00)
        assert state.book_balance_minor == 500_00
        assert state.can_reconcile


class TestReconcile:
    def test_reconciling_records_the_assertion(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00, "January")
        record = reconciliation.get(books, rec_id)

        # Both numbers are stored. The book balance is derivable from *today's* ledger --
        # recording it is what lets us detect a backdated entry later (ADR 0009).
        assert record.statement_balance_minor == 8_500_00
        assert record.book_balance_minor == 8_500_00
        assert record.statement_date == "2026-01-31"
        assert record.note == "January"

    def test_reconciling_stamps_the_lines_it_covers(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        stamped = books.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE reconciliation_id = ?", (rec_id,)
        ).fetchone()["n"]
        assert stamped == 3
        # Only this account's lines -- the other side of each entry stays untouched.
        assert books.execute(
            """SELECT COUNT(*) AS n FROM journal_lines
                WHERE reconciliation_id = ? AND account_id <> ?""",
            (rec_id, checking),
        ).fetchone()["n"] == 0

    def test_refuses_when_the_numbers_disagree(self, books, checking):
        # The refusal IS the feature: a reconciliation that tolerated a gap would be
        # asserting something untrue.
        with pytest.raises(reconciliation.ReconciliationError, match="difference"):
            reconciliation.reconcile(books, checking, "2026-01-31", 8_400_00)
        assert reconciliation.latest(books, checking) is None

    def test_failed_reconcile_stamps_nothing(self, books, checking):
        with pytest.raises(reconciliation.ReconciliationError):
            reconciliation.reconcile(books, checking, "2026-01-31", 8_400_00)
        assert books.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE reconciliation_id IS NOT NULL"
        ).fetchone()["n"] == 0

    def test_cannot_reconcile_the_same_period_twice(self, books, checking):
        reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        with pytest.raises(reconciliation.ReconciliationError, match="already reconciled"):
            reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)

    def test_cannot_reconcile_backwards(self, books, checking):
        reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        with pytest.raises(reconciliation.ReconciliationError, match="already reconciled"):
            reconciliation.reconcile(books, checking, "2026-01-15", 9_000_00)

    def test_second_period_only_covers_new_lines(self, books, checking):
        first = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        ledger.post(books, "2026-02-10", "February rent",
                    [ledger.debit(accounts.by_code(books, "6000").id, 1_000_00),
                     ledger.credit(checking, 1_000_00)])

        state = reconciliation.preview(books, checking, "2026-02-28", 7_500_00)
        assert state.unreconciled_line_count == 1  # only February's line is open
        second = reconciliation.reconcile(books, checking, "2026-02-28", 7_500_00)

        assert books.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE reconciliation_id = ?", (first,)
        ).fetchone()["n"] == 3
        assert books.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE reconciliation_id = ?", (second,)
        ).fetchone()["n"] == 1

    def test_reconciling_does_not_disturb_the_ledger(self, books, checking):
        before = ledger.account_balance(books, checking)
        reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        assert ledger.account_balance(books, checking) == before
        assert ledger.is_balanced(books)


class TestImmutabilityBoundary:
    """ADR 0004 said immutability covers financial facts, not annotations. Prove it."""

    def test_stamping_a_posted_line_is_allowed(self, books, checking):
        reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)  # must not raise

    def test_the_financial_facts_are_still_frozen(self, books, checking):
        import sqlite3

        reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        line = books.execute(
            "SELECT id FROM journal_lines WHERE account_id = ? LIMIT 1", (checking,)
        ).fetchone()

        # Loosening the trigger for reconciliation_id must not have opened the door to
        # editing amounts -- that would gut ADR 0004.
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            books.execute(
                "UPDATE journal_lines SET amount_minor = 1 WHERE id = ?", (line["id"],)
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            books.execute(
                "UPDATE journal_lines SET account_id = 2 WHERE id = ?", (line["id"],)
            )


class TestUndo:
    def test_undo_reverses_rather_than_deletes(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        undo_id = reconciliation.undo(books, rec_id, "wrong statement")

        # The original survives: append-only, same reasoning as the ledger.
        assert reconciliation.get(books, rec_id) is not None
        assert reconciliation.get(books, undo_id).reverses_id == rec_id
        assert reconciliation.latest(books, checking) is None

    def test_undo_releases_the_lines(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        reconciliation.undo(books, rec_id)
        assert books.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE reconciliation_id IS NOT NULL"
        ).fetchone()["n"] == 0

    def test_can_reconcile_again_after_undo(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        reconciliation.undo(books, rec_id)
        assert reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00) > 0

    def test_cannot_undo_twice(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        reconciliation.undo(books, rec_id)
        with pytest.raises(reconciliation.ReconciliationError, match="already undone"):
            reconciliation.undo(books, rec_id)

    def test_undo_of_nothing_is_an_error(self, books):
        with pytest.raises(reconciliation.ReconciliationError, match="no reconciliation"):
            reconciliation.undo(books, 9999)

    def test_history_keeps_everything(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        reconciliation.undo(books, rec_id, "mistake")
        # Both the claim and the retraction are on the record.
        assert len(reconciliation.history(books, checking)) == 2


class TestBackdating:
    """The reason we store book_balance_minor instead of recomputing it."""

    def test_a_backdated_entry_is_detected(self, books, checking):
        reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        assert reconciliation.find_backdated_entries(books) == []

        # A January transaction discovered in March and posted late. The books still
        # balance perfectly -- nothing else in the system would notice.
        ledger.post(books, "2026-01-15", "Forgotten bank fee",
                    [ledger.debit(accounts.by_code(books, "6050").id, 25_00),
                     ledger.credit(checking, 25_00)])
        assert ledger.is_balanced(books)

        found = reconciliation.find_backdated_entries(books)
        assert len(found) == 1
        assert found[0]["description"] == "Forgotten bank fee"
        assert found[0]["statement_date"] == "2026-01-31"

    def test_entries_after_the_statement_are_not_flagged(self, books, checking):
        reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        ledger.post(books, "2026-02-05", "February rent",
                    [ledger.debit(accounts.by_code(books, "6000").id, 1_000_00),
                     ledger.credit(checking, 1_000_00)])
        assert reconciliation.find_backdated_entries(books) == []

    def test_undone_reconciliations_do_not_flag_anything(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        reconciliation.undo(books, rec_id)
        ledger.post(books, "2026-01-15", "Late entry",
                    [ledger.debit(accounts.by_code(books, "6050").id, 25_00),
                     ledger.credit(checking, 25_00)])
        assert reconciliation.find_backdated_entries(books) == []

    def test_the_stored_balance_is_what_reveals_it(self, books, checking):
        rec_id = reconciliation.reconcile(books, checking, "2026-01-31", 8_500_00)
        ledger.post(books, "2026-01-15", "Forgotten fee",
                    [ledger.debit(accounts.by_code(books, "6050").id, 25_00),
                     ledger.credit(checking, 25_00)])

        record = reconciliation.get(books, rec_id)
        recomputed = reconciliation._book_balance(books, checking, "2026-01-31")
        # The recorded claim and today's reality now disagree -- which is the signal. A
        # recomputed number would simply have moved and told us nothing.
        assert record.book_balance_minor == 8_500_00
        assert recomputed == 8_475_00
        assert record.book_balance_minor != recomputed


class TestRealisticFlow:
    def test_import_then_reconcile_a_month(self, conn, checking):
        statement = (
            "Date,Description,Amount\n"
            "2026-01-02,OPENING DEPOSIT,10000.00\n"
            "2026-01-10,RENT PAYMENT,-1000.00\n"
            "2026-01-20,KROGER 00123,-500.00\n"
        )
        from slowbooks import posting

        batch = csv_import.import_csv(conn, statement, "jan.csv", checking)
        posting.post_batch(conn, batch["batch_id"])

        state = reconciliation.preview(conn, checking, "2026-01-31", 8_500_00)
        assert state.can_reconcile, f"unexpected gap: {money.format(state.difference_minor)}"

        rec_id = reconciliation.reconcile(conn, checking, "2026-01-31", 8_500_00)
        assert reconciliation.latest(conn, checking).id == rec_id

    def test_a_missing_transaction_shows_up_as_a_gap(self, conn, checking):
        """The failure this whole feature exists to catch.

        The books balance. The reports are internally consistent. And they're missing a
        transaction, which nothing else we have could ever tell us.
        """
        from slowbooks import posting

        incomplete = (
            "Date,Description,Amount\n"
            "2026-01-02,OPENING DEPOSIT,10000.00\n"
            "2026-01-10,RENT PAYMENT,-1000.00\n"
        )
        batch = csv_import.import_csv(conn, incomplete, "jan.csv", checking)
        posting.post_batch(conn, batch["batch_id"])

        assert ledger.is_balanced(conn)  # consistent...

        state = reconciliation.preview(conn, checking, "2026-01-31", 8_500_00)
        assert not state.can_reconcile  # ...but not complete
        assert state.difference_minor == 500_00
