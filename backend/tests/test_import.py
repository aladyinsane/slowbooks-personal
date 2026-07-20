"""CSV import and categorization tests.

Bank CSVs are hostile in specific, recurring ways. Each fixture here is a real format
shape we have to survive.
"""

from __future__ import annotations

import pytest

from slowbooks import accounts, categorize, ledger, posting, reports, settings
from slowbooks.importing import csv_import

CHASE = """Transaction Date,Post Date,Description,Category,Type,Amount
01/15/2026,01/16/2026,KROGER 00123 SEATTLE WA,Shopping,Sale,-450.00
01/20/2026,01/21/2026,SHELL OIL 5734,Gas,Sale,-62.50
01/25/2026,01/26/2026,PAYMENT THANK YOU,Payment,Payment,500.00
"""

SPLIT_COLUMNS = """Date,Description,Debit,Credit,Balance
2026-01-15,ADOBE CREATIVE CLOUD,54.99,,1945.01
2026-01-16,STRIPE TRANSFER,,2500.00,4445.01
2026-01-17,USPS SHIPPING,23.40,,4421.61
"""

SEMICOLON_EUROPEAN = """Date;Description;Amount
15/01/2026;OFFICE DEPOT;-1.234,56
16/01/2026;CLIENT PAYMENT;2.500,00
"""


@pytest.fixture
def checking(conn):
    return accounts.by_code(conn, "1000").id


class TestSniffing:
    def test_detects_chase_style_columns(self):
        mapping = csv_import.sniff_mapping(
            ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount"]
        )
        assert mapping.date == "Transaction Date"
        assert mapping.description == "Description"
        assert mapping.amount == "Amount"

    def test_detects_split_debit_credit_columns(self):
        mapping = csv_import.sniff_mapping(["Date", "Description", "Debit", "Credit"])
        assert mapping.amount is None
        assert mapping.debit == "Debit"
        assert mapping.credit == "Credit"

    def test_errors_name_the_missing_column(self):
        with pytest.raises(csv_import.ImportError_, match="date column"):
            csv_import.sniff_mapping(["Foo", "Bar"])
        with pytest.raises(csv_import.ImportError_, match="amount column"):
            csv_import.sniff_mapping(["Date", "Description", "Notes"])


class TestParsing:
    def test_reads_signed_amount_format(self, checking):
        _, rows = csv_import.read_rows(CHASE, checking)
        assert len(rows) == 3
        assert rows[0].txn_date == "2026-01-15"
        assert rows[0].amount_minor == -45000
        assert rows[2].amount_minor == 50000

    def test_reads_split_debit_credit_columns(self, checking):
        _, rows = csv_import.read_rows(SPLIT_COLUMNS, checking)
        # Debit column means money out, so it must come back negative.
        assert rows[0].amount_minor == -5499
        assert rows[1].amount_minor == 250000
        assert rows[2].amount_minor == -2340

    def test_reads_semicolon_delimited_european_numbers(self, checking):
        _, rows = csv_import.read_rows(SEMICOLON_EUROPEAN, checking)
        assert rows[0].amount_minor == -123456
        assert rows[1].amount_minor == 250000

    def test_invert_sign_for_card_statements(self, checking):
        # Card issuers often write purchases positive, from their own perspective.
        mapping = csv_import.ColumnMapping(
            date="Transaction Date", description="Description",
            amount="Amount", invert_sign=True,
        )
        _, rows = csv_import.read_rows(CHASE, checking, mapping)
        assert rows[0].amount_minor == 45000

    def test_skips_blank_and_zero_rows(self, checking):
        content = "Date,Description,Amount\n2026-01-15,REAL,-10.00\n\n2026-01-16,ZERO,0.00\n"
        _, rows = csv_import.read_rows(content, checking)
        assert len(rows) == 1

    def test_handles_excel_bom(self, checking):
        _, rows = csv_import.read_rows("﻿" + CHASE, checking)
        assert len(rows) == 3

    def test_error_messages_name_the_line_number(self, checking):
        bad = "Date,Description,Amount\n2026-01-15,OK,-10.00\nNOTADATE,BAD,-5.00\n"
        with pytest.raises(csv_import.ImportError_, match="line 3"):
            csv_import.read_rows(bad, checking)

    def test_rejects_empty_file(self, checking):
        with pytest.raises(csv_import.ImportError_, match="empty"):
            csv_import.read_rows("", checking)


class TestFingerprinting:
    def test_identical_transactions_fingerprint_alike(self, checking):
        a = csv_import.fingerprint(checking, "2026-01-15", -45000, "KROGER 00123")
        b = csv_import.fingerprint(checking, "2026-01-15", -45000, "kroger  00123 ")
        assert a == b

    def test_different_transactions_do_not_collide(self, checking):
        base = csv_import.fingerprint(checking, "2026-01-15", -45000, "KROGER")
        assert base != csv_import.fingerprint(checking, "2026-01-16", -45000, "KROGER")
        assert base != csv_import.fingerprint(checking, "2026-01-15", -45001, "KROGER")
        assert base != csv_import.fingerprint(checking, "2026-01-15", -45000, "SHELL")
        assert base != csv_import.fingerprint(checking + 1, "2026-01-15", -45000, "KROGER")


class TestImport:
    def test_import_stages_without_posting(self, conn, checking):
        result = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        assert result["rows_read"] == 3
        # Nothing may reach the ledger until the user says so.
        assert conn.execute("SELECT COUNT(*) AS n FROM journal_entries").fetchone()["n"] == 0

    def test_reimporting_the_same_file_flags_duplicates(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        second = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        # The top way to corrupt books, caught.
        assert second["duplicates_flagged"] == 3

    def test_duplicates_within_one_file_are_flagged(self, conn, checking):
        content = (
            "Date,Description,Amount\n"
            "2026-01-15,KROGER,-45.00\n"
            "2026-01-15,KROGER,-45.00\n"
        )
        result = csv_import.import_csv(conn, content, "dupe.csv", checking)
        assert result["duplicates_flagged"] == 1

    def test_import_reports_a_date_range(self, conn, checking):
        result = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        assert result["date_range"] == ["2026-01-15", "2026-01-25"]


class TestCategorization:
    def test_starter_rules_match_common_merchants(self, conn):
        match = categorize.match_transaction(conn, "KROGER 00123 SEATTLE WA", -45000)
        assert match is not None
        assert match.account_code == "6100"
        # Principle 8: the suggestion must explain itself.
        assert "KROGER" in match.reason

    def test_sign_disambiguates_the_same_merchant(self, conn):
        # A VENMO credit means someone paid you; a VENMO debit means you paid someone.
        income = categorize.match_transaction(conn, "VENMO PAYMENT FROM ALEX", 250000)
        sent = categorize.match_transaction(conn, "VENMO PAYMENT TO ALEX", -3000)
        assert income.account_code == "4900"
        assert sent.account_code == "6800"

    def test_unmatched_transaction_returns_none(self, conn):
        assert categorize.match_transaction(conn, "ZZQQ UNKNOWN VENDOR", -1000) is None

    def test_user_rules_outrank_builtins(self, conn):
        travel = accounts.by_code(conn, "6600").id
        categorize.create_rule(conn, "SHELL", travel)  # priority 100 beats builtin 500
        match = categorize.match_transaction(conn, "SHELL OIL 5734", -6250)
        assert match.account_code == "6600"

    def test_regex_rules(self, conn):
        supplies = accounts.by_code(conn, "6100").id
        categorize.create_rule(conn, r"ACME \d{4}", supplies, match_type="regex")
        assert categorize.match_transaction(conn, "ACME 1234 STORE", -1000) is not None
        assert categorize.match_transaction(conn, "ACME STORE", -1000) is None

    def test_invalid_regex_is_rejected_at_creation(self, conn):
        with pytest.raises(ValueError, match="invalid regex"):
            categorize.create_rule(conn, "[unclosed", 1, match_type="regex")

    def test_import_auto_categorizes(self, conn, checking):
        result = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        assert result["auto_categorized"] >= 2  # Kroger + Shell


class TestStarterRuleProvenance:
    """ADR 0006: a shipped guess must be distinguishable from a taught rule."""

    def test_starter_matches_are_marked(self, conn):
        match = categorize.match_transaction(conn, "KROGER 00123", -45000)
        assert match.is_starter_rule is True

    def test_user_rules_are_not_marked_as_starter(self, conn):
        entertainment = accounts.by_code(conn, "6450").id
        categorize.create_rule(conn, "ZZQQ MYSTERY", entertainment)
        match = categorize.match_transaction(conn, "ZZQQ MYSTERY VENDOR", -9900)
        assert match.is_starter_rule is False

    def test_a_user_override_retires_the_starter_badge(self, conn, checking):
        # The scaffolding is designed to come down: once the user teaches us, the
        # suggestion stops being a guess (user priority 100 beats builtin 500).
        assert categorize.match_transaction(conn, "SHELL OIL 5734", -6250).is_starter_rule
        categorize.create_rule(conn, "SHELL", accounts.by_code(conn, "6600").id)
        after = categorize.match_transaction(conn, "SHELL OIL 5734", -6250)
        assert after.is_starter_rule is False
        assert after.account_code == "6600"

    def test_batch_reports_starter_count_separately(self, conn, checking):
        result = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        # Kroger + Shell are starter guesses; the mystery vendor matches nothing.
        assert result["from_starter_rules"] == 2
        assert result["auto_categorized"] == 2

    def test_rule_id_is_recorded_on_the_staged_row(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        row = conn.execute(
            """SELECT suggested_rule_id FROM staged_transactions
                WHERE description LIKE 'KROGER%'"""
        ).fetchone()
        assert row["suggested_rule_id"] is not None

    def test_first_import_warns_then_stops_after_acknowledgement(self, conn, checking):
        first = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        assert first["warn_about_starter_rules"] is True

        settings.set_bool(conn, settings.STARTER_RULES_ACKNOWLEDGED, True)

        # A different month's rows -- re-importing CHASE would flag every row as a
        # duplicate, and duplicates are never categorized, so it would prove nothing.
        february = (
            "Date,Description,Amount\n"
            "2026-02-15,KROGER 00987,-120.00\n"
            "2026-02-20,SHELL OIL 1122,-48.00\n"
        )
        second = csv_import.import_csv(conn, february, "february.csv", checking)
        assert second["warn_about_starter_rules"] is False
        # Provenance itself never stops being reported -- only the first-run banner does.
        assert second["from_starter_rules"] == 2

    def test_no_warning_when_no_starter_rule_fires(self, conn, checking):
        content = "Date,Description,Amount\n2026-01-15,ZZQQ MYSTERY VENDOR,-99.00\n"
        result = csv_import.import_csv(conn, content, "mystery.csv", checking)
        assert result["from_starter_rules"] == 0
        assert result["warn_about_starter_rules"] is False

    def test_user_override_clears_starter_provenance_on_the_staged_row(self, conn, checking):
        """Regression, found by driving the real UI.

        Correcting a starter guess posted the right entry but left suggested_rule_id
        pointing at the builtin rule, so the row kept rendering a "starter rule" badge
        after the user had personally chosen the category. The badge is the whole
        mechanism of ADR 0006 -- one that lies is worse than none.
        """
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged = conn.execute(
            """SELECT id, suggested_rule_id FROM staged_transactions
                WHERE description LIKE 'SHELL%'"""
        ).fetchone()
        assert staged["suggested_rule_id"] is not None  # started as a starter guess

        # The user says this was actually a rebate, not fuel.
        income = accounts.by_code(conn, "4000").id
        posting.post_staged(conn, staged["id"], income)

        after = conn.execute(
            """SELECT suggested_rule_id, suggested_account_id, suggested_reason
                 FROM staged_transactions WHERE id = ?""",
            (staged["id"],),
        ).fetchone()
        assert after["suggested_rule_id"] is None
        assert after["suggested_account_id"] == income
        assert "you chose" in after["suggested_reason"]

    def test_accepting_a_guess_as_is_keeps_its_provenance(self, conn, checking):
        # Accepting a guess does not make it not a guess. "Accept all" must not quietly
        # relabel shipped guesses as the user's own decisions.
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged = conn.execute(
            """SELECT id, suggested_rule_id FROM staged_transactions
                WHERE description LIKE 'SHELL%'"""
        ).fetchone()

        posting.post_staged(conn, staged["id"])  # no explicit category

        after = conn.execute(
            "SELECT suggested_rule_id FROM staged_transactions WHERE id = ?", (staged["id"],)
        ).fetchone()
        assert after["suggested_rule_id"] == staged["suggested_rule_id"]

    def test_deleting_a_rule_keeps_the_suggestion_and_drops_provenance(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged = conn.execute(
            """SELECT id, suggested_rule_id, suggested_account_id
                 FROM staged_transactions WHERE description LIKE 'KROGER%'"""
        ).fetchone()

        conn.execute("DELETE FROM rules WHERE id = ?", (staged["suggested_rule_id"],))

        after = conn.execute(
            """SELECT suggested_rule_id, suggested_account_id
                 FROM staged_transactions WHERE id = ?""",
            (staged["id"],),
        ).fetchone()
        # ON DELETE SET NULL: the category survives, only the provenance is lost.
        assert after["suggested_rule_id"] is None
        assert after["suggested_account_id"] == staged["suggested_account_id"]


class TestDraftZone:
    """ADR 0004 always said imported rows stay editable until posted. The grid skipped
    that: it posted on selection, so a mis-click became an immutable journal entry that
    could only be undone with a reversal. These pin the behaviour the ADR described.
    """

    def test_choosing_a_category_posts_nothing(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged_id = conn.execute("SELECT id FROM staged_transactions LIMIT 1").fetchone()["id"]

        posting.choose_category(conn, staged_id, accounts.by_code(conn, "6100").id)

        assert conn.execute(
            "SELECT COUNT(*) AS n FROM journal_entries"
        ).fetchone()["n"] == 0
        row = conn.execute(
            "SELECT status, suggested_account_id FROM staged_transactions WHERE id = ?",
            (staged_id,),
        ).fetchone()
        assert row["status"] == "pending"
        assert row["suggested_account_id"] is not None

    def test_the_user_can_change_their_mind_freely(self, conn, checking):
        # The whole point. Before posting, a wrong choice costs nothing.
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged_id = conn.execute("SELECT id FROM staged_transactions LIMIT 1").fetchone()["id"]

        for code in ["6100", "6600", "6450", "6100"]:
            posting.choose_category(conn, staged_id, accounts.by_code(conn, code).id)

        assert conn.execute("SELECT COUNT(*) AS n FROM journal_entries").fetchone()["n"] == 0
        final = conn.execute(
            "SELECT suggested_account_id FROM staged_transactions WHERE id = ?", (staged_id,)
        ).fetchone()
        assert final["suggested_account_id"] == accounts.by_code(conn, "6100").id

    def test_choosing_overrides_a_starter_guess_and_retires_the_badge(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged = conn.execute(
            """SELECT id, suggested_rule_id FROM staged_transactions
                WHERE description LIKE 'SHELL%'"""
        ).fetchone()
        assert staged["suggested_rule_id"] is not None

        posting.choose_category(conn, staged["id"], accounts.by_code(conn, "4000").id)

        after = conn.execute(
            """SELECT suggested_rule_id, suggested_reason FROM staged_transactions
                WHERE id = ?""",
            (staged["id"],),
        ).fetchone()
        assert after["suggested_rule_id"] is None  # no longer our guess (ADR 0006)
        assert "you chose" in after["suggested_reason"]

    def test_a_category_can_be_cleared(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged = conn.execute(
            "SELECT id FROM staged_transactions WHERE description LIKE 'SHELL%'"
        ).fetchone()

        posting.choose_category(conn, staged["id"], None)

        row = conn.execute(
            """SELECT suggested_account_id, suggested_reason FROM staged_transactions
                WHERE id = ?""",
            (staged["id"],),
        ).fetchone()
        assert row["suggested_account_id"] is None
        assert row["suggested_reason"] is None

    def test_cannot_recategorize_a_posted_row(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged = conn.execute(
            "SELECT id FROM staged_transactions WHERE description LIKE 'KROGER%'"
        ).fetchone()
        posting.post_staged(conn, staged["id"])

        # Immutability starts at posting -- that boundary still holds.
        with pytest.raises(posting.PostingError, match="already posted"):
            posting.choose_category(conn, staged["id"], accounts.by_code(conn, "6600").id)

    def test_cannot_choose_the_rows_own_bank_account(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged_id = conn.execute("SELECT id FROM staged_transactions LIMIT 1").fetchone()["id"]
        with pytest.raises(posting.PostingError, match="own bank account"):
            posting.choose_category(conn, staged_id, checking)

    def test_cannot_choose_an_account_that_does_not_exist(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged_id = conn.execute("SELECT id FROM staged_transactions LIMIT 1").fetchone()["id"]
        with pytest.raises(posting.PostingError, match="no account"):
            posting.choose_category(conn, staged_id, 9999)

    def test_choose_then_post_the_batch(self, conn, checking):
        """The flow the user asked for: categorize everything, then commit once."""
        content = (
            "Date,Description,Amount\n"
            "2026-01-15,ZZQQ MYSTERY ONE,-10.00\n"
            "2026-01-16,ZZQQ MYSTERY TWO,-20.00\n"
        )
        batch = csv_import.import_csv(conn, content, "mystery.csv", checking)
        assert batch["needs_review"] == 2

        for row in conn.execute("SELECT id FROM staged_transactions").fetchall():
            posting.choose_category(conn, row["id"], accounts.by_code(conn, "6100").id)

        assert conn.execute("SELECT COUNT(*) AS n FROM journal_entries").fetchone()["n"] == 0

        result = posting.post_batch(conn, batch["batch_id"])
        assert result["posted"] == 2
        assert result["still_pending"] == 0
        assert ledger.is_balanced(conn)


class TestPostingStaged:
    def test_posting_produces_a_balanced_entry(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged = conn.execute(
            "SELECT id FROM staged_transactions WHERE description LIKE 'KROGER%'"
        ).fetchone()

        entry_id = posting.post_staged(conn, staged["id"])
        assert ledger.is_balanced(conn)
        # Money out of checking: expense debited, asset credited.
        assert ledger.account_balance(conn, accounts.by_code(conn, "6100").id) == 45000
        assert ledger.account_balance(conn, checking) == -45000
        assert ledger.get(conn, entry_id).source == "import"

    def test_cannot_post_twice(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged_id = conn.execute("SELECT id FROM staged_transactions LIMIT 1").fetchone()["id"]
        posting.post_staged(conn, staged_id)
        with pytest.raises(posting.PostingError, match="already posted"):
            posting.post_staged(conn, staged_id)

    def test_cannot_categorize_to_the_source_account(self, conn, checking):
        csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        staged_id = conn.execute("SELECT id FROM staged_transactions LIMIT 1").fetchone()["id"]
        with pytest.raises(posting.PostingError, match="own bank account"):
            posting.post_staged(conn, staged_id, checking)

    def test_batch_post_leaves_uncategorized_rows_pending(self, conn, checking):
        content = (
            "Date,Description,Amount\n"
            "2026-01-15,KROGER 00123,-45.00\n"
            "2026-01-16,ZZQQ MYSTERY VENDOR,-99.00\n"
        )
        result = csv_import.import_csv(conn, content, "mixed.csv", checking)
        outcome = posting.post_batch(conn, result["batch_id"])

        # Unknowns stay visible instead of being buried in Uncategorized.
        assert outcome["posted"] == 1
        assert outcome["still_pending"] == 1

    def test_full_loop_import_to_reports(self, conn, checking):
        """Import -> categorize -> post -> reports, the whole v0.1 thesis."""
        result = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
        posting.post_batch(conn, result["batch_id"])

        sheet = reports.balance_sheet(conn, "2026-12-31")
        assert sheet["balanced"]
        assert ledger.is_balanced(conn)

        pnl = reports.profit_and_loss(conn, "2026-01-01", "2026-12-31")
        # Kroger 450 + Shell 62.50 categorized as expenses.
        assert pnl["operating_expenses"]["total_minor"] == 51250
