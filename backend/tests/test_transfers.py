"""Transfer tests (ADR 0007).

The headline test is test_both_sides_post_only_once. A transfer double-count leaves the
books *balanced* -- debits still equal credits -- so our strongest existing invariant
cannot catch it. Two correct entries can still be a wrong answer. These tests are the
only thing standing between that and a silently wrong Balance Sheet.
"""

from __future__ import annotations

import pytest

from slowbooks import accounts, ledger, posting, reports, transfers
from slowbooks.importing import csv_import

# The same $5,000 move, as the two banks report it. Note the dates differ by a day --
# banks rarely post both sides together, which is why the match window exists.
CHECKING_OUT = """Date,Description,Amount
2026-03-10,ONLINE TRANSFER TO SAVINGS,-5000.00
2026-03-12,KROGER 00123,-84.19
"""

SAVINGS_IN = """Date,Description,Amount
2026-03-11,ONLINE TRANSFER FROM CHECKING,5000.00
"""


@pytest.fixture
def checking(conn):
    return accounts.by_code(conn, "1000").id


@pytest.fixture
def savings(conn):
    return accounts.by_code(conn, "1010").id


@pytest.fixture
def imported(conn, checking, savings):
    """Both statements imported, transfer detected but nothing posted."""
    a = csv_import.import_csv(conn, CHECKING_OUT, "checking.csv", checking)
    b = csv_import.import_csv(conn, SAVINGS_IN, "savings.csv", savings)
    return a, b


class TestStatementAccounts:
    def test_default_chart_marks_the_right_accounts(self, conn):
        codes = {a.code for a in accounts.list_statement_accounts(conn)}
        assert codes == {"1000", "1010", "1020", "2100", "2500"}

    def test_receivables_and_equipment_are_not_transfer_targets(self, conn):
        # Assets you cannot move money into. Offering them would be offering nonsense --
        # the old code-prefix heuristic in the frontend got this wrong.
        assert not accounts.by_code(conn, "1100").is_statement_account  # A/R
        assert not accounts.by_code(conn, "1500").is_statement_account  # Equipment

    def test_expense_accounts_cannot_be_statement_accounts(self, conn):
        with pytest.raises(ValueError, match="asset or liability"):
            accounts.create(conn, "6800", "Nope", "expense", is_statement_account=True)

    def test_user_can_add_a_second_checking_account(self, conn):
        second = accounts.create(
            conn, "1030", "Second Checking", "asset", is_statement_account=True
        )
        assert second.is_statement_account
        assert second.id in {a.id for a in accounts.list_statement_accounts(conn)}


class TestDetection:
    def test_detects_the_pair_across_two_statements(self, conn, imported):
        _, savings_batch = imported
        rows = conn.execute(
            "SELECT id, description, transfer_match_id FROM staged_transactions"
        ).fetchall()
        transfer_rows = [r for r in rows if r["transfer_match_id"] is not None]
        assert len(transfer_rows) == 2
        # Pointing at each other, not at themselves.
        assert transfer_rows[0]["transfer_match_id"] == transfer_rows[1]["id"]
        assert transfer_rows[1]["transfer_match_id"] == transfer_rows[0]["id"]
        assert savings_batch["transfer_pairs_found"] == 1

    def test_ordinary_transactions_are_untouched(self, conn, imported):
        kroger = conn.execute(
            """SELECT transfer_match_id FROM staged_transactions
                WHERE description LIKE 'KROGER%'"""
        ).fetchone()
        assert kroger["transfer_match_id"] is None

    def test_transfers_get_no_category_suggestion(self, conn, imported):
        # A category for a transfer is wrong by construction, so we must not offer one.
        row = conn.execute(
            """SELECT suggested_account_id FROM staged_transactions
                WHERE transfer_match_id IS NOT NULL LIMIT 1"""
        ).fetchone()
        assert row["suggested_account_id"] is None

    def test_transfers_are_not_counted_as_review_work(self, conn, imported):
        _, savings_batch = imported
        # The savings statement is one row, and it's a resolved transfer. Nagging the
        # user to review it would be nagging about something already handled.
        assert savings_batch["needs_review"] == 0

    def test_no_match_outside_the_date_window(self, conn, checking, savings):
        csv_import.import_csv(conn, CHECKING_OUT, "checking.csv", checking)
        late = "Date,Description,Amount\n2026-04-20,TRANSFER FROM CHECKING,5000.00\n"
        result = csv_import.import_csv(conn, late, "savings.csv", savings)
        assert result["transfer_pairs_found"] == 0

    def test_no_match_on_a_different_amount(self, conn, checking, savings):
        csv_import.import_csv(conn, CHECKING_OUT, "checking.csv", checking)
        wrong = "Date,Description,Amount\n2026-03-11,TRANSFER FROM CHECKING,4999.00\n"
        result = csv_import.import_csv(conn, wrong, "savings.csv", wrong and savings)
        assert result["transfer_pairs_found"] == 0

    def test_no_match_within_the_same_account(self, conn, checking):
        # A -500 and +500 in one account is not a transfer; it is probably a refund.
        content = (
            "Date,Description,Amount\n"
            "2026-03-10,SOMETHING,-500.00\n"
            "2026-03-11,SOMETHING REFUNDED,500.00\n"
        )
        result = csv_import.import_csv(conn, content, "checking.csv", checking)
        assert result["transfer_pairs_found"] == 0

    def test_closest_date_wins_when_several_could_match(self, conn, checking, savings):
        csv_import.import_csv(conn, CHECKING_OUT, "checking.csv", checking)
        # Two candidates in range; the 03-11 one is nearer the 03-10 origin.
        content = (
            "Date,Description,Amount\n"
            "2026-03-14,TRANSFER FROM CHECKING,5000.00\n"
            "2026-03-11,TRANSFER FROM CHECKING,5000.00\n"
        )
        csv_import.import_csv(conn, content, "savings.csv", savings)

        checking_row = conn.execute(
            "SELECT transfer_match_id FROM staged_transactions WHERE amount_minor = -500000"
        ).fetchone()
        matched = conn.execute(
            "SELECT txn_date FROM staged_transactions WHERE id = ?",
            (checking_row["transfer_match_id"],),
        ).fetchone()
        assert matched["txn_date"] == "2026-03-11"

    def test_unlink_rejects_a_suggested_pair(self, conn, imported):
        row = conn.execute(
            """SELECT id, transfer_match_id FROM staged_transactions
                WHERE transfer_match_id IS NOT NULL"""
        ).fetchone()
        counterpart_id = row["transfer_match_id"]

        transfers.unlink(conn, row["id"])

        # Both sides unlink -- a one-sided pairing would be a corrupt state.
        for staged_id in (row["id"], counterpart_id):
            after = conn.execute(
                "SELECT transfer_match_id FROM staged_transactions WHERE id = ?", (staged_id,)
            ).fetchone()
            assert after["transfer_match_id"] is None


class TestPosting:
    def test_transfer_posts_one_entry_with_no_pnl_impact(self, conn, imported):
        row = conn.execute(
            """SELECT id FROM staged_transactions
                WHERE transfer_match_id IS NOT NULL AND amount_minor < 0"""
        ).fetchone()

        posting.post_staged(conn, row["id"])

        pnl = reports.profit_and_loss(conn, "2026-01-01", "2026-12-31")
        # The whole point: moving your own money is neither income nor expense.
        assert pnl["revenue"]["total_minor"] == 0
        assert pnl["operating_expenses"]["total_minor"] == 0
        assert pnl["net_income_minor"] == 0

        assert ledger.account_balance(conn, accounts.by_code(conn, "1000").id) == -500000
        assert ledger.account_balance(conn, accounts.by_code(conn, "1010").id) == 500000
        assert ledger.is_balanced(conn)

    def test_both_sides_post_only_once(self, conn, imported, checking, savings):
        """THE test. Posting both sides must move the money once, not twice.

        This is the failure that survives the debits==credits invariant: two
        independently-correct entries produce a balanced, wrong Balance Sheet.
        """
        rows = conn.execute(
            "SELECT id FROM staged_transactions WHERE transfer_match_id IS NOT NULL"
        ).fetchall()
        assert len(rows) == 2

        posting.post_staged(conn, rows[0]["id"])

        # The counterpart is settled by the same entry, so it can't be posted again.
        with pytest.raises(posting.PostingError, match="already posted"):
            posting.post_staged(conn, rows[1]["id"])

        entries = conn.execute(
            "SELECT COUNT(*) AS n FROM journal_entries WHERE source = 'transfer'"
        ).fetchone()
        assert entries["n"] == 1

        assert ledger.account_balance(conn, checking) == -500000
        assert ledger.account_balance(conn, savings) == 500000  # not 1,000,000

    def test_both_staged_rows_point_at_the_same_entry(self, conn, imported):
        rows = conn.execute(
            "SELECT id FROM staged_transactions WHERE transfer_match_id IS NOT NULL"
        ).fetchall()
        posting.post_staged(conn, rows[0]["id"])

        after = conn.execute(
            """SELECT status, posted_entry_id FROM staged_transactions
                WHERE transfer_match_id IS NOT NULL"""
        ).fetchall()
        assert all(r["status"] == "posted" for r in after)
        assert len({r["posted_entry_id"] for r in after}) == 1

    def test_posting_from_either_side_gives_the_same_result(self, conn, checking, savings):
        # Direction of travel must not depend on which statement the user opens first.
        csv_import.import_csv(conn, CHECKING_OUT, "checking.csv", checking)
        csv_import.import_csv(conn, SAVINGS_IN, "savings.csv", savings)

        incoming = conn.execute(
            """SELECT id FROM staged_transactions
                WHERE transfer_match_id IS NOT NULL AND amount_minor > 0"""
        ).fetchone()
        posting.post_staged(conn, incoming["id"])

        assert ledger.account_balance(conn, checking) == -500000
        assert ledger.account_balance(conn, savings) == 500000

    def test_manual_transfer_without_detection_still_cannot_double_count(
        self, conn, checking, savings
    ):
        """Belt and braces: the guard must not depend on detection having fired.

        A user whose transfer straddled the date window will categorize each side by
        hand. They are in exactly the same danger, so post_staged looks for the
        counterpart itself.
        """
        csv_import.import_csv(conn, CHECKING_OUT, "checking.csv", checking)
        csv_import.import_csv(conn, SAVINGS_IN, "savings.csv", savings)

        # Simulate detection never having run.
        conn.execute("UPDATE staged_transactions SET transfer_match_id = NULL")

        out_row = conn.execute(
            "SELECT id FROM staged_transactions WHERE amount_minor = -500000"
        ).fetchone()
        in_row = conn.execute(
            "SELECT id FROM staged_transactions WHERE amount_minor = 500000"
        ).fetchone()

        posting.post_staged(conn, out_row["id"], savings)  # user picks "transfer to savings"

        with pytest.raises(posting.PostingError, match="already posted"):
            posting.post_staged(conn, in_row["id"], checking)

        assert ledger.account_balance(conn, savings) == 500000

    def test_batch_post_handles_transfers_and_categories_together(self, conn, imported):
        checking_batch, _ = imported
        result = posting.post_batch(conn, checking_batch["batch_id"])

        # The transfer plus the Kroger row, both posted, no double count.
        assert result["posted"] == 2
        assert ledger.is_balanced(conn)
        assert reports.balance_sheet(conn, "2026-12-31")["balanced"]
        assert ledger.account_balance(conn, accounts.by_code(conn, "1010").id) == 500000

    def test_batch_post_of_second_statement_is_a_no_op_for_transfer(self, conn, imported):
        checking_batch, savings_batch = imported
        posting.post_batch(conn, checking_batch["batch_id"])

        # Savings side already settled; posting its batch must not move money again.
        result = posting.post_batch(conn, savings_batch["batch_id"])
        assert result["posted"] == 0
        assert ledger.account_balance(conn, accounts.by_code(conn, "1010").id) == 500000

    def test_credit_card_payment_is_a_transfer(self, conn, checking):
        """Paying a card is checking -> liability, not an expense.

        A classic error: booking the payment as an expense double-counts, because the
        purchases it settles were already expensed when they were charged.
        """
        card = accounts.by_code(conn, "2100").id
        card_csv = "Date,Description,Amount\n2026-03-15,PAYMENT THANK YOU,900.00\n"
        pay_csv = "Date,Description,Amount\n2026-03-15,CREDIT CARD PAYMENT,-900.00\n"

        csv_import.import_csv(conn, pay_csv, "checking.csv", checking)
        result = csv_import.import_csv(conn, card_csv, "card.csv", card)
        assert result["transfer_pairs_found"] == 1

        row = conn.execute(
            "SELECT id FROM staged_transactions WHERE transfer_match_id IS NOT NULL LIMIT 1"
        ).fetchone()
        posting.post_staged(conn, row["id"])

        pnl = reports.profit_and_loss(conn, "2026-01-01", "2026-12-31")
        assert pnl["operating_expenses"]["total_minor"] == 0  # paying a card is not an expense
        assert ledger.account_balance(conn, checking) == -90000
        # Liability is credit-normal: +90000 signed means the debt fell by $900.
        assert ledger.account_balance(conn, card) == 90000


class TestTheBugThisPrevents:
    def test_uncaught_double_count_would_still_balance(self, conn, checking, savings):
        """Documents *why* pairing is necessary rather than paranoid.

        Posting both sides as independent, individually-correct entries yields books
        that balance perfectly and a Balance Sheet that is wrong by $5,000. If our
        strongest invariant can't see the bug, only structure can prevent it.
        """
        csv_import.import_csv(conn, CHECKING_OUT, "checking.csv", checking)
        csv_import.import_csv(conn, SAVINGS_IN, "savings.csv", savings)
        conn.execute("UPDATE staged_transactions SET transfer_match_id = NULL")

        # Post both sides by hand, bypassing posting.py's guard entirely.
        ledger.post(conn, "2026-03-10", "side one",
                    [ledger.debit(savings, 500000), ledger.credit(checking, 500000)])
        ledger.post(conn, "2026-03-11", "side two",
                    [ledger.debit(savings, 500000), ledger.credit(checking, 500000)])

        assert ledger.is_balanced(conn)  # balanced...
        assert reports.balance_sheet(conn, "2026-12-31")["balanced"]  # ...and balanced...
        assert ledger.account_balance(conn, savings) == 1_000_000  # ...and wrong.
