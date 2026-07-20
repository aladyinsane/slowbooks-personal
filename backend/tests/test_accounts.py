"""Chart of accounts tests (ADR 0010).

The default chart is a guess about a business we haven't met. It has to be editable, and
the editing has to be incapable of breaking posted history.
"""

from __future__ import annotations

import pytest

from slowbooks import accounts, ledger, posting
from slowbooks.importing import csv_import


@pytest.fixture
def checking(conn):
    return accounts.by_code(conn, "1000").id


class TestRename:
    def test_renaming_leaves_history_alone(self, conn, checking):
        """Safe because journal lines reference the id, never the name.

        Worth a test rather than an assumption: it's the property that makes "rename
        freely" defensible at all.
        """
        supplies = accounts.by_code(conn, "6100").id
        ledger.post(conn, "2026-01-15", "Staples",
                    [ledger.debit(supplies, 45000), ledger.credit(checking, 45000)])

        accounts.update(conn, supplies, name="Stationery & bits")

        assert accounts.by_id(conn, supplies).name == "Stationery & bits"
        assert ledger.account_balance(conn, supplies) == 45000
        assert ledger.is_balanced(conn)

    def test_guidance_is_the_users_to_rewrite(self, conn):
        # Ours is a guess written by a developer. Theirs beats ours.
        supplies = accounts.by_code(conn, "6100").id
        accounts.update(conn, supplies, description="Anything from the art shop.")
        assert accounts.by_id(conn, supplies).description == "Anything from the art shop."

    def test_blank_name_is_refused(self, conn):
        supplies = accounts.by_code(conn, "6100").id
        with pytest.raises(ValueError, match="needs a name"):
            accounts.update(conn, supplies, name="   ")

    def test_update_cannot_change_code_or_type(self, conn):
        # Not a runtime check -- update() has no such parameters. Flipping 6100 from
        # expense to asset would silently move every historical transaction from the P&L
        # to the Balance Sheet, so the operation simply doesn't exist (ADR 0010).
        import inspect

        params = set(inspect.signature(accounts.update).parameters)
        assert "code" not in params
        assert "type_" not in params and "type" not in params

    def test_unknown_account_raises(self, conn):
        with pytest.raises(KeyError):
            accounts.update(conn, 9999, name="Nope")


class TestHide:
    def test_hiding_removes_it_from_the_picker_but_not_the_books(self, conn, checking):
        supplies = accounts.by_code(conn, "6100").id
        ledger.post(conn, "2026-01-15", "Staples",
                    [ledger.debit(supplies, 45000), ledger.credit(checking, 45000)])

        accounts.update(conn, supplies, is_active=False)

        assert supplies not in {a.id for a in accounts.list_all(conn)}
        assert supplies in {a.id for a in accounts.list_all(conn, active_only=False)}
        # The balance is still real, and still on the P&L. Hiding is about the list.
        assert ledger.account_balance(conn, supplies) == 45000

    def test_hiding_is_reversible(self, conn):
        supplies = accounts.by_code(conn, "6100").id
        accounts.update(conn, supplies, is_active=False)
        accounts.update(conn, supplies, is_active=True)
        assert supplies in {a.id for a in accounts.list_all(conn)}

    def test_cannot_hide_an_account_you_import_statements_into(self, conn, checking):
        # Hiding checking would strand the import screen it feeds.
        with pytest.raises(ValueError, match="import statements into"):
            accounts.update(conn, checking, is_active=False)


class TestAdd:
    def test_the_number_range_enforces_the_type(self, conn):
        # The range *is* the type. This is what makes "add your own category" safe to
        # hand to someone who has never heard the word "equity".
        with pytest.raises(ValueError, match="range"):
            accounts.create(conn, "1200", "Wrong", "expense")
        with pytest.raises(ValueError, match="range"):
            accounts.create(conn, "6800", "Wrong", "asset")

    def test_next_code_picks_a_free_number_in_the_right_range(self, conn):
        code = accounts.next_code(conn, accounts.EXPENSE)
        low, high = accounts.TYPE_RANGES[accounts.EXPENSE]
        assert low <= int(code) <= high
        assert code not in {a.code for a in accounts.list_all(conn, active_only=False)}

    def test_a_new_expense_lands_in_operating_expenses_not_cogs(self, conn):
        """The expense range spans 5000-6999, but those halves are different sections
        of the P&L: 5000s are COGS (above gross profit), 6000s are operating expenses
        (below it). Auto-numbering into the lowest free slot put a new "Studio rent" at
        5010 -- misfiling it as cost of goods sold and understating gross profit on
        every report from then on.
        """
        code = accounts.next_code(conn, accounts.EXPENSE)
        assert 6000 <= int(code) <= 6999, f"{code} is a COGS code, not an operating expense"

    def test_cogs_is_still_reachable_by_naming_the_code(self, conn):
        # A deliberate choice stays available; only the default changed.
        materials = accounts.create(conn, "5300", "Timber", accounts.EXPENSE)
        assert materials.code == "5300"

    def test_next_code_leaves_room_between_accounts(self, conn):
        # Steps of 10, like the default chart, so related accounts can be inserted later.
        assert int(accounts.next_code(conn, accounts.REVENUE)) % 10 == 0

    def test_next_code_never_collides(self, conn):
        created = []
        for i in range(5):
            code = accounts.next_code(conn, accounts.EXPENSE)
            accounts.create(conn, code, f"Invented {i}", accounts.EXPENSE)
            created.append(code)
        assert len(set(created)) == 5

    def test_a_new_category_is_immediately_usable(self, conn, checking):
        studio = accounts.create(
            conn, accounts.next_code(conn, accounts.EXPENSE), "Studio rent",
            accounts.EXPENSE, "Rent for the studio space.",
        )
        csv_import.import_csv(
            conn, "Date,Description,Amount\n2026-01-05,STUDIO LANDLORD,-800.00\n",
            "jan.csv", checking,
        )
        staged_id = conn.execute("SELECT id FROM staged_transactions").fetchone()["id"]
        posting.post_staged(conn, staged_id, studio.id)

        assert ledger.account_balance(conn, studio.id) == 80000
        assert ledger.is_balanced(conn)

    def test_a_new_statement_account_can_be_transferred_to(self, conn):
        second = accounts.create(
            conn, "1020", "Second Checking", accounts.ASSET, is_statement_account=True
        )
        assert second.id in {a.id for a in accounts.list_statement_accounts(conn)}

    def test_only_asset_or_liability_can_hold_money(self, conn):
        with pytest.raises(ValueError, match="asset or liability"):
            accounts.create(conn, "6800", "Nope", accounts.EXPENSE, is_statement_account=True)


class TestDelete:
    def test_an_unused_account_can_be_deleted(self, conn):
        invented = accounts.create(conn, "6800", "Never used", accounts.EXPENSE)
        accounts.delete(conn, invented.id)
        assert invented.id not in {a.id for a in accounts.list_all(conn, active_only=False)}

    def test_an_account_with_posted_history_cannot(self, conn, checking):
        """The guard that protects the ledger.

        Deleting this would leave journal lines pointing at nothing -- a hole in
        append-only history that ADR 0004 says can never exist.
        """
        supplies = accounts.by_code(conn, "6100").id
        ledger.post(conn, "2026-01-15", "Staples",
                    [ledger.debit(supplies, 45000), ledger.credit(checking, 45000)])

        with pytest.raises(accounts.AccountInUseError, match="posted transaction"):
            accounts.delete(conn, supplies)
        assert accounts.by_id(conn, supplies) is not None

    def test_the_refusal_says_what_is_using_it(self, conn, checking):
        # "Used by 2 posted lines" is an answer; "you can't do that" is a wall.
        supplies = accounts.by_code(conn, "6100").id
        ledger.post(conn, "2026-01-15", "Staples",
                    [ledger.debit(supplies, 45000), ledger.credit(checking, 45000)])

        with pytest.raises(accounts.AccountInUseError) as exc:
            accounts.delete(conn, supplies)
        message = str(exc.value)
        assert "6100" in message and "Office Supplies" in message
        assert "hide it instead" in message
        # Counts are written for a human: "1 posted transaction", not "1 posted lines".
        assert "1 posted transaction," in message

    def test_a_rule_counts_as_usage(self, conn):
        # Starter rules reference accounts; deleting one out from under a rule would
        # break categorization silently.
        supplies = accounts.by_code(conn, "6100").id
        with pytest.raises(accounts.AccountInUseError, match="categorization rule"):
            accounts.delete(conn, supplies)

    def test_a_staged_row_counts_as_usage(self, conn, checking):
        invented = accounts.create(conn, "6800", "Invented", accounts.EXPENSE)
        csv_import.import_csv(
            conn, "Date,Description,Amount\n2026-01-05,ZZQQ THING,-10.00\n",
            "jan.csv", checking,
        )
        staged_id = conn.execute("SELECT id FROM staged_transactions").fetchone()["id"]
        posting.choose_category(conn, staged_id, invented.id)

        # Not posted yet, but the user has pointed at it. Deleting would strand the draft.
        with pytest.raises(accounts.AccountInUseError, match="imported transaction"):
            accounts.delete(conn, invented.id)

    def test_a_reconciliation_counts_as_usage(self, conn, checking):
        from slowbooks import reconciliation

        ledger.post(conn, "2026-01-02", "Opening",
                    [ledger.debit(checking, 100_00),
                     ledger.credit(accounts.by_code(conn, "3000").id, 100_00)])
        reconciliation.reconcile(conn, checking, "2026-01-31", 100_00)

        with pytest.raises(accounts.AccountInUseError):
            accounts.delete(conn, checking)

    def test_usage_reports_zero_for_a_fresh_account(self, conn):
        invented = accounts.create(conn, "6800", "Fresh", accounts.EXPENSE)
        assert accounts.usage(conn, invented.id) == {
            "posted_lines": 0, "staged_transactions": 0, "rules": 0, "reconciliations": 0
        }
