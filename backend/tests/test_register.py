"""Register tests (ADR 0012).

A running balance is the reason a register is readable and the reason it's easy to get
subtly wrong: it depends on order being stable, and on knowing what the account held
*before* the window opened. Both failures produce numbers that look authoritative and
are false, which is the dangerous kind.
"""

from __future__ import annotations

import pytest

from slowbooks import accounts, ledger, reports


@pytest.fixture
def checking(conn):
    return accounts.by_code(conn, "1000").id


@pytest.fixture
def books(conn, checking):
    opening_balance = accounts.by_code(conn, "3000").id
    supplies = accounts.by_code(conn, "6100").id
    rent = accounts.by_code(conn, "6000").id
    income = accounts.by_code(conn, "4100").id

    ledger.post(conn, "2026-01-02", "Opening balance",
                [ledger.debit(checking, 10_000_00), ledger.credit(opening_balance, 10_000_00)])
    ledger.post(conn, "2026-01-10", "Rent",
                [ledger.debit(rent, 1_000_00), ledger.credit(checking, 1_000_00)])
    ledger.post(conn, "2026-01-20", "KROGER 00123",
                [ledger.debit(supplies, 450_00), ledger.credit(checking, 450_00)])
    ledger.post(conn, "2026-02-05", "Freelance project",
                [ledger.debit(checking, 3_000_00), ledger.credit(income, 3_000_00)])
    return conn


class TestRunningBalance:
    def test_it_accumulates_in_date_order(self, books, checking):
        page = reports.register(books, checking)
        balances = [line["running_balance_minor"] for line in page["lines"]]
        assert balances == [10_000_00, 9_000_00, 8_550_00, 11_550_00]

    def test_the_last_running_balance_is_the_closing_balance(self, books, checking):
        page = reports.register(books, checking)
        assert page["closing_balance_minor"] == page["lines"][-1]["running_balance_minor"]
        assert page["closing_balance_minor"] == ledger.account_balance(books, checking)

    def test_a_window_opens_from_the_prior_balance_not_from_zero(self, books, checking):
        """The subtle one.

        Ask for February alone and the running balance must start where January left
        off. Starting at zero would make every figure on the page wrong -- plausibly
        wrong, which nobody catches.
        """
        page = reports.register(books, checking, start="2026-02-01", end="2026-02-28")

        assert page["opening_balance_minor"] == 8_550_00  # where January ended
        assert page["lines"][0]["running_balance_minor"] == 11_550_00
        assert page["closing_balance_minor"] == 11_550_00

    def test_an_unbounded_window_opens_at_zero(self, books, checking):
        page = reports.register(books, checking)
        assert page["opening_balance_minor"] == 0

    def test_order_is_deterministic_when_dates_tie(self, books, checking):
        # Two entries on one day must not reorder between calls, or the running balance
        # wobbles. (date, entry_id) is total; insertion order is not.
        supplies = accounts.by_code(books, "6100").id
        for i in range(3):
            ledger.post(books, "2026-03-01", f"Same day {i}",
                        [ledger.debit(supplies, 10_00), ledger.credit(checking, 10_00)])

        first = [line["entry_id"] for line in reports.register(books, checking)["lines"]]
        second = [line["entry_id"] for line in reports.register(books, checking)["lines"]]
        assert first == second == sorted(first)

    def test_a_backdated_entry_lands_in_date_order(self, books, checking):
        # Imported late, dated early. The register must place it by its date, not by
        # when we happened to hear about it.
        supplies = accounts.by_code(books, "6100").id
        ledger.post(books, "2026-01-05", "Forgotten fee",
                    [ledger.debit(supplies, 25_00), ledger.credit(checking, 25_00)])

        page = reports.register(books, checking)
        dates = [line["date"] for line in page["lines"]]
        assert dates == sorted(dates)
        assert dates[1] == "2026-01-05"
        # And the balance after it reflects it.
        assert page["lines"][1]["running_balance_minor"] == 10_000_00 - 25_00


class TestTheOtherSide:
    def test_each_line_names_where_the_money_went(self, books, checking):
        # A register hides the debits and credits; it must not hide the *story*.
        page = reports.register(books, checking)
        kroger = next(ln for ln in page["lines"] if "KROGER" in ln["description"])
        assert kroger["other_side"] == "6100 Groceries"

    def test_a_split_entry_lists_every_other_account(self, conn, checking):
        principal = accounts.by_code(conn, "2500").id
        interest = accounts.by_code(conn, "6750").id
        ledger.post(conn, "2026-01-31", "Loan payment",
                    [ledger.debit(principal, 900_00), ledger.debit(interest, 100_00),
                     ledger.credit(checking, 1_000_00)])

        page = reports.register(conn, checking)
        other = page["lines"][0]["other_side"]
        assert "2500 Loans Payable" in other
        assert "6750 Interest Expense" in other

    def test_signs_follow_the_account_not_the_reader(self, books, checking):
        page = reports.register(books, checking)
        # Checking is debit-normal: money in is positive, money out negative.
        assert page["lines"][0]["amount_minor"] > 0   # investment in
        assert page["lines"][1]["amount_minor"] < 0   # rent out


class TestFiltering:
    def test_a_date_window_excludes_the_rest(self, books, checking):
        page = reports.register(books, checking, start="2026-01-01", end="2026-01-31")
        assert page["count"] == 3
        assert all(line["date"] <= "2026-01-31" for line in page["lines"])

    def test_searching_by_description(self, books, checking):
        # "Can't search for keywords in transactions" is a named QuickBooks complaint.
        page = reports.register(books, checking, query="kroger")
        assert page["count"] == 1
        assert "KROGER" in page["lines"][0]["description"]

    def test_search_is_case_insensitive(self, books, checking):
        assert reports.register(books, checking, query="KrOgEr")["count"] == 1

    def test_a_filtered_register_has_no_running_balance(self, books, checking):
        """A search result is not a statement.

        Carrying a running balance through an arbitrary subset would produce numbers
        that look authoritative and mean nothing -- the exact failure this product keeps
        finding elsewhere.
        """
        page = reports.register(books, checking, query="kroger")
        assert page["is_filtered"] is True
        assert page["opening_balance"] is None
        assert page["opening_balance_minor"] is None
        assert page["closing_balance"] is None
        assert page["closing_balance_minor"] is None
        assert all(line["running_balance"] is None for line in page["lines"])
        assert all(line["running_balance_minor"] is None for line in page["lines"])
        # The total of what matched is still meaningful, and still shown.
        assert page["total_minor"] == -450_00

    def test_search_finds_nothing_gracefully(self, books, checking):
        page = reports.register(books, checking, query="zzqq nothing")
        assert page["count"] == 0
        assert page["lines"] == []


class TestWhatItShows:
    def test_drafts_are_excluded(self, conn, checking):
        supplies = accounts.by_code(conn, "6100").id
        cursor = conn.execute(
            """INSERT INTO journal_entries (entry_date, description, source, posted_at)
               VALUES ('2026-01-01', 'DRAFT', 'manual', NULL)"""
        )
        conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?,?,?)",
            (cursor.lastrowid, supplies, 100),
        )
        conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?,?,?)",
            (cursor.lastrowid, checking, -100),
        )
        page = reports.register(conn, checking)
        assert not any("DRAFT" in line["description"] for line in page["lines"])

    def test_a_void_shows_both_sides_of_the_correction(self, books, checking):
        supplies = accounts.by_code(books, "6100").id
        entry = ledger.post(books, "2026-03-01", "Mistake",
                            [ledger.debit(supplies, 100_00), ledger.credit(checking, 100_00)])
        ledger.void(books, entry, "wrong")

        page = reports.register(books, checking)
        # Append-only means the audit trail is visible, not tidied away (ADR 0004).
        assert any(line["description"] == "Mistake" for line in page["lines"])
        reversal = next(line for line in page["lines"] if line["is_reversal"])
        assert reversal["source"] == "void"
        # Net effect nil: the closing balance is what it was before the mistake.
        assert page["closing_balance_minor"] == 11_550_00

    def test_reconciled_lines_are_marked(self, books, checking):
        from slowbooks import reconciliation

        balance = ledger.account_balance(books, checking, as_of="2026-01-31")
        reconciliation.reconcile(books, checking, "2026-01-31", balance)

        page = reports.register(books, checking)
        january = [line for line in page["lines"] if line["date"] <= "2026-01-31"]
        february = [line for line in page["lines"] if line["date"] > "2026-01-31"]
        assert all(line["reconciled"] for line in january)
        assert not any(line["reconciled"] for line in february)

    def test_an_empty_account_is_not_an_error(self, conn):
        savings = accounts.by_code(conn, "1010").id
        page = reports.register(conn, savings)
        assert page["count"] == 0
        assert page["closing_balance_minor"] == 0

    def test_unknown_account_raises(self, conn):
        with pytest.raises(KeyError):
            reports.register(conn, 9999)


class TestAllAccounts:
    """Omitting the account lists everything — a list, not a statement (ADR 0012)."""

    def test_it_lists_every_account(self, books):
        page = reports.register(books, None)
        # Two lines per entry: four entries in the fixture.
        assert page["total_count"] == 8
        assert page["account"] is None
        accounts_seen = {line["account_code"] for line in page["lines"]}
        assert "1000" in accounts_seen and "6100" in accounts_seen

    def test_it_has_no_running_balance(self, books):
        """Summing checking, a credit card and an expense in one column produces a
        figure that means nothing. Same rule as a filtered view.
        """
        page = reports.register(books, None)
        assert page["has_running_balance"] is False
        assert page["opening_balance"] is None
        assert page["closing_balance"] is None
        assert all(line["running_balance"] is None for line in page["lines"])

    def test_every_line_names_its_own_account(self, books):
        # A single-account register says which account in its heading; this one can't.
        page = reports.register(books, None)
        assert all(line["account"] for line in page["lines"])

    def test_it_is_chronological(self, books):
        page = reports.register(books, None)
        dates = [line["date"] for line in page["lines"]]
        assert dates == sorted(dates)

    def test_filters_still_apply(self, books):
        page = reports.register(books, None, start="2026-02-01")
        assert all(line["date"] >= "2026-02-01" for line in page["lines"])

        searched = reports.register(books, None, query="kroger")
        assert searched["total_count"] == 2  # both sides of the one entry

    def test_a_single_account_still_gets_its_balance(self, books, checking):
        page = reports.register(books, checking)
        assert page["has_running_balance"] is True
        assert page["closing_balance_minor"] == 11_550_00


class TestPagination:
    @pytest.fixture
    def many(self, conn, checking):
        supplies = accounts.by_code(conn, "6100").id
        opening_balance = accounts.by_code(conn, "3000").id
        ledger.post(conn, "2026-01-01", "Opening",
                    [ledger.debit(checking, 1_000_00),
                     ledger.credit(opening_balance, 1_000_00)])
        for day in range(1, 26):
            ledger.post(conn, f"2026-02-{day:02d}", f"Purchase {day}",
                        [ledger.debit(supplies, 1_00), ledger.credit(checking, 1_00)])
        return conn

    def test_a_page_is_capped(self, many, checking):
        page = reports.register(many, checking, limit=10)
        assert page["count"] == 10
        assert page["total_count"] == 26
        assert page["has_more"] is True

    def test_paging_walks_the_whole_set_without_gaps_or_repeats(self, many, checking):
        seen = []
        offset = 0
        while True:
            page = reports.register(many, checking, limit=10, offset=offset)
            seen.extend(line["description"] for line in page["lines"])
            if not page["has_more"]:
                break
            offset += page["limit"]

        assert len(seen) == 26
        assert len(set(seen)) == 26  # nothing duplicated across a boundary

    def test_the_running_balance_continues_across_pages(self, many, checking):
        """The subtle one.

        Page 2 must not restart at the window's opening balance. If it did, every figure
        on every page after the first would be wrong -- plausibly wrong, which nobody
        catches.
        """
        first = reports.register(many, checking, limit=10)
        second = reports.register(many, checking, limit=10, offset=10)

        assert second["opening_balance_minor"] == first["lines"][-1]["running_balance_minor"]
        assert second["lines"][0]["running_balance_minor"] == (
            first["lines"][-1]["running_balance_minor"] + second["lines"][0]["amount_minor"]
        )

    def test_the_last_page_closes_at_the_account_balance(self, many, checking):
        last = reports.register(many, checking, limit=10, offset=20)
        assert last["has_more"] is False
        assert last["closing_balance_minor"] == ledger.account_balance(many, checking)

    def test_the_whole_set_total_survives_pagination(self, many, checking):
        """The drill-down contract under pagination.

        The user clicked a number on a report. However many pages the register takes,
        `total` must still be that number -- a footer that only summed the visible page
        would quietly contradict the figure they clicked (principle 8).
        """
        page2 = reports.register(many, checking, limit=10, offset=10)
        assert page2["total_minor"] == ledger.account_balance(many, checking)
        # And it's the same on every page, because it describes the set, not the page.
        page1 = reports.register(many, checking, limit=10)
        assert page1["total_minor"] == page2["total_minor"]

    def test_page_total_is_this_page_not_the_whole_set(self, many, checking):
        """Naming matters here: mistaking a page total for the set's would be an error
        nobody could see."""
        page = reports.register(many, checking, limit=10, offset=10)
        assert page["page_total_minor"] == sum(
            line["amount_minor"] for line in page["lines"]
        )
        assert page["page_total_minor"] != ledger.account_balance(many, checking)

    def test_limit_is_clamped(self, many, checking):
        assert reports.register(many, checking, limit=99_999)["limit"] == 500
        assert reports.register(many, checking, limit=0)["limit"] == 1
        assert reports.register(many, checking, offset=-5)["offset"] == 0

    def test_offset_past_the_end_is_empty_not_an_error(self, many, checking):
        page = reports.register(many, checking, offset=9999)
        assert page["count"] == 0
        assert page["has_more"] is False
        assert page["total_count"] == 26

    def test_the_count_matches_what_paging_yields(self, many, checking):
        # A count that filtered differently from the page would paginate over a set the
        # user never sees.
        page = reports.register(many, checking, start="2026-02-01", limit=5)
        assert page["total_count"] == 25


class TestAgreesWithTheReports:
    def test_the_closing_balance_matches_the_balance_sheet(self, books, checking):
        """The register and the Balance Sheet must tell the same story.

        Two views of one ledger that disagree would mean one of them is lying, and the
        user has no way to tell which.
        """
        page = reports.register(books, checking, end="2026-02-28")
        sheet = reports.balance_sheet(books, "2026-02-28")
        line = next(
            item for item in sheet["assets"]["lines"] if item["name"] == "Checking"
        )
        assert page["closing_balance_minor"] == line["amount_minor"]

    def test_an_expense_register_matches_its_pnl_line(self, books):
        supplies = accounts.by_code(books, "6100").id
        page = reports.register(books, supplies, start="2026-01-01", end="2026-12-31")
        pnl = reports.profit_and_loss(books, "2026-01-01", "2026-12-31")
        line = next(
            item for item in pnl["operating_expenses"]["lines"] if item["code"] == "6100"
        )
        # This is the drill-down contract: click the number, see these rows, and they
        # add up to the number you clicked (principle 8).
        assert page["total_minor"] == line["amount_minor"]
