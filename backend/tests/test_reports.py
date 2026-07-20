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
            for code in ["1000", "2100", "2500", "3000", "4000", "5000",
                         "6100", "6200", "6700"]}


@pytest.fixture
def books(conn, chart):
    """A small but realistic set of books for one quarter."""
    # Owner funds the business
    ledger.post(conn, "2026-01-02", "Owner investment",
                [ledger.debit(chart["1000"], 5_000_00),
                 ledger.credit(chart["3000"], 5_000_00)])
    # Revenue
    ledger.post(conn, "2026-01-15", "Client payment",
                [ledger.debit(chart["1000"], 10_000_00),
                 ledger.credit(chart["4000"], 10_000_00)])
    ledger.post(conn, "2026-02-15", "Client payment",
                [ledger.debit(chart["1000"], 8_000_00),
                 ledger.credit(chart["4000"], 8_000_00)])
    # COGS
    ledger.post(conn, "2026-01-20", "Materials",
                [ledger.debit(chart["5000"], 3_000_00),
                 ledger.credit(chart["1000"], 3_000_00)])
    # Operating expenses
    ledger.post(conn, "2026-01-31", "Rent",
                [ledger.debit(chart["6200"], 2_000_00),
                 ledger.credit(chart["1000"], 2_000_00)])
    ledger.post(conn, "2026-02-28", "Rent",
                [ledger.debit(chart["6200"], 2_000_00),
                 ledger.credit(chart["1000"], 2_000_00)])
    ledger.post(conn, "2026-01-10", "Office supplies on card",
                [ledger.debit(chart["6100"], 450_00),
                 ledger.credit(chart["2100"], 450_00)])
    # Outside the reporting window on purpose.
    ledger.post(conn, "2026-04-05", "April rent",
                [ledger.debit(chart["6200"], 2_000_00),
                 ledger.credit(chart["1000"], 2_000_00)])
    return conn


class TestProfitAndLoss:
    def test_pnl_arithmetic(self, books):
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-03-31")

        assert pnl["revenue"]["total_minor"] == 18_000_00
        assert pnl["cost_of_goods_sold"]["total_minor"] == 3_000_00
        assert pnl["gross_profit_minor"] == 15_000_00
        assert pnl["operating_expenses"]["total_minor"] == 4_450_00  # rent x2 + supplies
        assert pnl["net_income_minor"] == 10_550_00
        assert pnl["net_income"] == "$10,550.00"

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
        # Checking: 5000 + 10000 + 8000 - 3000 - 2000 - 2000 = 16,000
        assert sheet["assets"]["total_minor"] == 16_000_00
        # Card balance from the supplies purchase
        assert sheet["liabilities"]["total_minor"] == 450_00
        # Capital 5,000 + earnings 10,550
        assert sheet["equity"]["total_minor"] == 15_550_00

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

        ledger.void(books, entry_id, "not a business expense")

        sheet = reports.balance_sheet(books, "2026-12-31")
        assert sheet["balanced"]
        # Voided in the same period, so the numbers return to where they were.
        assert sheet["liabilities"]["total_minor"] == 450_00
        assert ledger.is_balanced(books)


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
