"""Group tests (ADR 0014).

Groups organize the chart of accounts for display -- "Food & Dining" containing
Groceries and Dining & Takeout. Modeled as a table for the same reason accounts are
(ADR 0010): a default that's good enough to ignore on day one, but never a bet the user
is stuck with.
"""

from __future__ import annotations

import sqlite3

import pytest

from slowbooks import accounts, groups, ledger


class TestDefaults:
    def test_default_groups_are_seeded(self, conn):
        all_groups = groups.list_all(conn)
        assert len(all_groups) == len(groups.DEFAULT_GROUPS)

    def test_every_default_account_has_a_group(self, conn):
        # A gap here means a chart account was added without a matching CODE_TO_GROUP
        # entry -- easy to miss by hand, so worth a blanket check.
        ungrouped = [a for a in accounts.list_all(conn) if a.group_id is None]
        assert ungrouped == []

    def test_groups_are_scoped_to_a_type(self, conn):
        expense_groups = groups.list_all(conn, type_=accounts.EXPENSE)
        assert all(g.type == accounts.EXPENSE for g in expense_groups)
        assert len(expense_groups) < len(groups.DEFAULT_GROUPS)


class TestRename:
    def test_renaming_leaves_member_accounts_alone(self, conn):
        food = next(g for g in groups.list_all(conn) if g.name == "Food & Dining")
        groups.update(conn, food.id, name="Eating")

        assert accounts.by_code(conn, "6100").group_name == "Eating"

    def test_blank_name_is_refused(self, conn):
        food = next(g for g in groups.list_all(conn) if g.name == "Food & Dining")
        with pytest.raises(ValueError, match="needs a name"):
            groups.update(conn, food.id, name="   ")

    def test_unknown_group_raises(self, conn):
        with pytest.raises(KeyError):
            groups.update(conn, 9999, name="Nope")

    def test_update_cannot_change_type(self):
        import inspect

        params = set(inspect.signature(groups.update).parameters)
        assert "type_" not in params and "type" not in params


class TestCreateAndDelete:
    def test_a_new_group_can_be_created(self, conn):
        new_group = groups.create(conn, "Hobbies", accounts.EXPENSE)
        assert new_group.id in {g.id for g in groups.list_all(conn)}

    def test_duplicate_name_and_type_is_refused(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            groups.create(conn, "Food & Dining", accounts.EXPENSE)

    def test_same_name_different_type_is_allowed(self, conn):
        # "Other" as an expense group already exists in some charts; a same-named group
        # under a different type is a different row, not a collision.
        created = groups.create(conn, "Food & Dining", accounts.ASSET)
        assert created.type == accounts.ASSET

    def test_an_empty_group_can_be_deleted(self, conn):
        empty = groups.create(conn, "Temporary", accounts.EXPENSE)
        groups.delete(conn, empty.id)
        assert empty.id not in {g.id for g in groups.list_all(conn)}

    def test_a_group_with_accounts_cannot_be_deleted(self, conn):
        food = next(g for g in groups.list_all(conn) if g.name == "Food & Dining")
        with pytest.raises(groups.GroupInUseError, match="account"):
            groups.delete(conn, food.id)
        # And the refusal doesn't touch anything.
        assert accounts.by_code(conn, "6100").group_id == food.id

    def test_usage_counts_member_accounts(self, conn):
        food = next(g for g in groups.list_all(conn) if g.name == "Food & Dining")
        # Groceries + Dining & Takeout, per the default chart.
        assert groups.usage(conn, food.id) == 2


class TestAccountAssignment:
    def test_a_new_account_can_join_an_existing_group(self, conn):
        food = next(g for g in groups.list_all(conn) if g.name == "Food & Dining")
        snacks = accounts.create(
            conn, "6975", "Snacks", accounts.EXPENSE, group_id=food.id
        )
        assert snacks.group_name == "Food & Dining"

    def test_mismatched_type_is_refused_on_create(self, conn):
        food = next(g for g in groups.list_all(conn) if g.name == "Food & Dining")
        with pytest.raises(ValueError, match="can't go in it"):
            accounts.create(conn, "1200", "Wrong", accounts.ASSET, group_id=food.id)

    def test_an_account_can_move_to_a_different_group(self, conn):
        transportation = next(
            g for g in groups.list_all(conn) if g.name == "Transportation"
        )
        moved = accounts.update(
            conn, accounts.by_code(conn, "6600").id, group_id=transportation.id
        )
        assert moved.group_name == "Transportation"

    def test_mismatched_type_is_refused_on_update(self, conn):
        income = next(g for g in groups.list_all(conn) if g.name == "Income")
        with pytest.raises(ValueError, match="can't go in it"):
            accounts.update(conn, accounts.by_code(conn, "6100").id, group_id=income.id)

    def test_the_database_refuses_a_mismatch_even_via_raw_sql(self, conn):
        """The trigger is the real guarantee; the Python check above is just a nicer
        error message on top of it."""
        income = next(g for g in groups.list_all(conn) if g.name == "Income")
        groceries_id = accounts.by_code(conn, "6100").id
        with pytest.raises(sqlite3.IntegrityError, match="same type"):
            conn.execute(
                "UPDATE accounts SET group_id = ? WHERE id = ?",
                (income.id, groceries_id),
            )


class TestUngroupedAccounts:
    def test_an_account_can_be_created_without_a_group(self, conn):
        loose = accounts.create(conn, "6975", "Loose", accounts.EXPENSE)
        assert loose.group_id is None
        assert loose.group_name is None

    def test_posting_to_an_ungrouped_account_still_works(self, conn):
        loose = accounts.create(conn, "6975", "Loose", accounts.EXPENSE)
        checking = accounts.by_code(conn, "1000").id
        ledger.post(conn, "2026-01-15", "Something",
                    [ledger.debit(loose.id, 1000), ledger.credit(checking, 1000)])
        assert ledger.is_balanced(conn)
