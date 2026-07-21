"""Report tests.

The most valuable tests in the repo. The accounting identity holding after arbitrary
operations catches whole categories of bugs at once -- see
docs/engineering/architecture.md.
"""

from __future__ import annotations

import pytest

from slowbooks import accounts, ledger, reports


@pytest.fixture
def chart(conn):
    return {code: accounts.by_code(conn, code).id
            for code in ["1000", "2100", "2500", "3000", "4000",
                         "6000", "6100", "6700"]}


@pytest.fixture
def books(conn, chart):
    """A small but realistic set of books for one quarter."""
    # Where the books started
    ledger.post(conn, "2026-01-02", "Opening balance",
                [ledger.debit(chart["1000"], 5_000_00),
                 ledger.credit(chart["3000"], 5_000_00)])
    # Income
    ledger.post(conn, "2026-01-15", "Payroll",
                [ledger.debit(chart["1000"], 10_000_00),
                 ledger.credit(chart["4000"], 10_000_00)])
    ledger.post(conn, "2026-02-15", "Payroll",
                [ledger.debit(chart["1000"], 8_000_00),
                 ledger.credit(chart["4000"], 8_000_00)])
    # Expenses
    ledger.post(conn, "2026-01-31", "Rent",
                [ledger.debit(chart["6000"], 2_000_00),
                 ledger.credit(chart["1000"], 2_000_00)])
    ledger.post(conn, "2026-02-28", "Rent",
                [ledger.debit(chart["6000"], 2_000_00),
                 ledger.credit(chart["1000"], 2_000_00)])
    ledger.post(conn, "2026-01-10", "Groceries on card",
                [ledger.debit(chart["6100"], 450_00),
                 ledger.credit(chart["2100"], 450_00)])
    # Outside the reporting window on purpose.
    ledger.post(conn, "2026-04-05", "April rent",
                [ledger.debit(chart["6000"], 2_000_00),
                 ledger.credit(chart["1000"], 2_000_00)])
    return conn


class TestProfitAndLoss:
    def test_pnl_arithmetic(self, books):
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")

        assert pnl["revenue"]["total_minor"] == 18_000_00
        assert pnl["operating_expenses"]["total_minor"] == 4_450_00  # rent x2 + groceries
        assert pnl["net_income_minor"] == 13_550_00
        assert pnl["net_income"] == "$13,550.00"

    def test_period_boundaries_are_inclusive_and_exclude_outside(self, books):
        # April rent must not leak into Q1.
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")
        assert pnl["operating_expenses"]["total_minor"] == 4_450_00

        april = reports.profit_and_loss(books, "2026-04-01", "2026-04-30")
        assert april["operating_expenses"]["total_minor"] == 2_000_00
        assert april["net_income_minor"] == -2_000_00

    def test_revenue_reads_positive(self, books):
        # Revenue is credit-normal (negative internally). A P&L showing negative
        # revenue would be technically consistent and completely unreadable.
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")
        assert all(line["amount_minor"] > 0 for line in pnl["revenue"]["lines"])

    def test_empty_period_is_all_zeros(self, books):
        pnl = reports.profit_and_loss(books, "2025-01-01", "2025-12-31")
        assert pnl["net_income_minor"] == 0
        assert pnl["revenue"]["lines"] == []


class TestBalanceSheet:
    def test_balance_sheet_balances(self, books):
        sheet = reports.balance_sheet(books, "2026-03-31")
        assert sheet["balanced"]
        assert sheet["assets"]["total_minor"] == sheet["total_liabilities_and_equity_minor"]

    def test_balance_sheet_figures(self, books):
        sheet = reports.balance_sheet(books, "2026-03-31")
        # Checking: 5000 + 10000 + 8000 - 2000 - 2000 = 19,000
        assert sheet["assets"]["total_minor"] == 19_000_00
        # Card balance from the groceries purchase
        assert sheet["liabilities"]["total_minor"] == 450_00
        # Opening balance 5,000 + earnings 13,550
        assert sheet["equity"]["total_minor"] == 18_550_00

    def test_liabilities_read_positive(self, books):
        sheet = reports.balance_sheet(books, "2026-03-31")
        assert all(line["amount_minor"] > 0 for line in sheet["liabilities"]["lines"])

    def test_empty_book_balances_trivially(self, conn):
        sheet = reports.balance_sheet(conn, "2026-03-31")
        assert sheet["balanced"]
        assert sheet["assets"]["total_minor"] == 0


class TestReportsAgree:
    """The two reports must tell the same story. If they disagree, one is lying."""

    def test_pnl_net_income_equals_balance_sheet_earnings(self, books):
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")
        sheet = reports.balance_sheet(books, "2026-03-31")

        earnings_line = next(
            line for line in sheet["equity"]["lines"]
            if line["name"] == "Current Period Earnings"
        )
        assert earnings_line["amount_minor"] == pnl["net_income_minor"]

    def test_accounting_identity_holds(self, books):
        """Assets = Liabilities + Equity + (Revenue - Expenses).

        The single best correctness test we have.
        """
        sheet = reports.balance_sheet(books, "2026-12-31")
        assert (
            sheet["assets"]["total_minor"]
            == sheet["liabilities"]["total_minor"] + sheet["equity"]["total_minor"]
        )

    def test_identity_survives_a_void(self, books, chart):
        entry_id = ledger.post(
            books, "2026-03-01", "Mistaken charge",
            [ledger.debit(chart["6100"], 999_99), ledger.credit(chart["2100"], 999_99)],
        )
        assert reports.balance_sheet(books, "2026-12-31")["balanced"]

        ledger.void(books, entry_id, "miscoded")

        sheet = reports.balance_sheet(books, "2026-12-31")
        assert sheet["balanced"]
        # Voided in the same period, so the numbers return to where they were.
        assert sheet["liabilities"]["total_minor"] == 450_00
        assert ledger.is_balanced(books)


class TestGroupSubtotals:
    """ADR 0014's "revisit when": reports subtotal by account group, not just flat lines."""

    def test_expense_groups_have_correct_subtotals(self, books):
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")
        subtotals = {g["name"]: g["total_minor"] for g in pnl["operating_expenses"]["groups"]}
        assert subtotals["Housing"] == 4_000_00       # rent x2
        assert subtotals["Food & Dining"] == 450_00   # groceries

    def test_group_subtotals_sum_to_the_section_total(self, books):
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")
        groups = pnl["operating_expenses"]["groups"]
        assert sum(g["total_minor"] for g in groups) == pnl["operating_expenses"]["total_minor"]

    def test_grouped_lines_are_the_same_lines_as_the_flat_list(self, books):
        """The `groups` breakdown re-buckets the same data, not a second source of truth."""
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")
        flat_codes = {line["code"] for line in pnl["operating_expenses"]["lines"]}
        grouped_codes = {
            line["code"]
            for group in pnl["operating_expenses"]["groups"]
            for line in group["lines"]
        }
        assert flat_codes == grouped_codes

    def test_an_ungrouped_account_lands_under_other(self, conn):
        checking = accounts.by_code(conn, "1000").id
        loose = accounts.create(conn, "6975", "Loose Expense", accounts.EXPENSE)
        ledger.post(conn, "2026-01-15", "Something",
                    [ledger.debit(loose.id, 100_00), ledger.credit(checking, 100_00)])

        pnl = reports.profit_and_loss(conn, "2026-01-01", "2026-01-31")
        other = next(g for g in pnl["operating_expenses"]["groups"] if g["name"] is None)
        assert other["total_minor"] == 100_00

    def test_balance_sheet_assets_are_grouped(self, books):
        sheet = reports.balance_sheet(books, "2026-03-31")
        subtotals = {g["name"]: g["total_minor"] for g in sheet["assets"]["groups"]}
        # Checking is the only asset account touched in this fixture.
        assert subtotals["Cash & Investments"] == 19_000_00

    def test_current_period_earnings_has_no_group_of_its_own(self, books):
        """It isn't tied to any account, so it can't have a group -- it lands in "Other"
        (ADR 0014), same as a genuinely ungrouped equity account."""
        sheet = reports.balance_sheet(books, "2026-03-31")
        other = next(g for g in sheet["equity"]["groups"] if g["name"] is None)
        assert any(line["name"] == "Current Period Earnings" for line in other["lines"])


class TestTrialBalance:
    def test_debits_equal_credits(self, books):
        tb = reports.trial_balance(books, "2026-12-31")
        assert tb["balanced"]
        assert tb["total_debits_minor"] == tb["total_credits_minor"]

    def test_every_nonzero_account_appears_once(self, books):
        tb = reports.trial_balance(books, "2026-12-31")
        codes = [line["code"] for line in tb["lines"]]
        assert len(codes) == len(set(codes))
        assert "1000" in codes and "4000" in codes

    def test_each_line_is_debit_or_credit_not_both(self, books):
        tb = reports.trial_balance(books, "2026-12-31")
        for line in tb["lines"]:
            assert not (line["debit_minor"] and line["credit_minor"])
