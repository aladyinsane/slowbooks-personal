"""Migration tests.

ADR 0001 promises the user owns their file and it keeps working. An upgrade that forces
them to start over would break that promise more thoroughly than any outage, so
migrations get real tests.

Fixtures come from `schemas_historical.py` -- frozen literal copies of what we actually
shipped. They used to be built by string-patching the current schema, which drifted
silently: the "v1" fixture grew a v3 column and every test here kept passing while
proving nothing. Real user files in the wild don't change when we edit db.py, so the
fixtures mustn't either.
"""

from __future__ import annotations

import sqlite3

import pytest

from slowbooks import accounts, categorize, db, settings, transfers
from slowbooks.importing import csv_import
from tests.schemas_historical import SCHEMAS


def _make_old_database(path, version: int) -> None:
    """A database exactly as the given schema version shipped it."""
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMAS[version])
    conn.execute("INSERT INTO schema_meta (key, value) VALUES ('version', ?)", (str(version),))
    conn.commit()
    conn.close()


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


class TestFixturesAreHonest:
    """Guard the guards. If these fail, every other test in this file proves nothing."""

    def test_v1_lacks_everything_added_after_it(self, tmp_path):
        path = tmp_path / "v1.db"
        _make_old_database(path, 1)
        conn = sqlite3.connect(str(path))

        staged = _columns(conn, "staged_transactions")
        assert "suggested_rule_id" not in staged      # added in v2
        assert "transfer_match_id" not in staged      # added in v3
        assert "is_statement_account" not in _columns(conn, "accounts")  # v3
        tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "settings" not in tables               # added in v2
        conn.close()

    def test_v2_has_v2_things_but_not_v3_things(self, tmp_path):
        path = tmp_path / "v2.db"
        _make_old_database(path, 2)
        conn = sqlite3.connect(str(path))

        staged = _columns(conn, "staged_transactions")
        assert "suggested_rule_id" in staged
        assert "transfer_match_id" not in staged
        assert "is_statement_account" not in _columns(conn, "accounts")
        tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "settings" in tables
        conn.close()

    def test_v4_has_v4_things_but_not_v5_things(self, tmp_path):
        path = tmp_path / "v4.db"
        _make_old_database(path, 4)
        conn = sqlite3.connect(str(path))

        assert "reconciliation_id" in _columns(conn, "journal_lines")
        tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "reconciliations" in tables
        assert "period_closes" not in tables  # added in v5
        conn.close()

    def test_v3_has_v3_things_but_not_v4_things(self, tmp_path):
        path = tmp_path / "v3.db"
        _make_old_database(path, 3)
        conn = sqlite3.connect(str(path))

        assert "transfer_match_id" in _columns(conn, "staged_transactions")
        assert "is_statement_account" in _columns(conn, "accounts")
        assert "reconciliation_id" not in _columns(conn, "journal_lines")  # added in v4
        tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "reconciliations" not in tables
        conn.close()


class TestUpgrades:
    @pytest.mark.parametrize("from_version", [1, 2, 3, 4])
    def test_old_database_reaches_current_schema(self, tmp_path, from_version):
        path = tmp_path / f"v{from_version}.db"
        _make_old_database(path, from_version)

        conn = db.connect(path)
        db.initialize(conn)

        staged = _columns(conn, "staged_transactions")
        assert "suggested_rule_id" in staged
        assert "transfer_match_id" in staged
        assert "is_statement_account" in _columns(conn, "accounts")
        assert "reconciliation_id" in _columns(conn, "journal_lines")
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "period_closes" in tables
        assert conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()["value"] == str(db.SCHEMA_VERSION)
        conn.close()

    @pytest.mark.parametrize("from_version", [1, 2, 3, 4])
    def test_reconciliation_works_after_migrating(self, tmp_path, from_version):
        """An old book must get the new feature, not just the new columns.

        The v4 migration also has to refresh the journal_lines immutability trigger --
        the original froze whole rows, and reconciliation stamps posted lines. A
        migration that left the old trigger in place would give an upgraded book a
        feature that errors on use.
        """
        from slowbooks import reconciliation

        path = tmp_path / f"v{from_version}.db"
        _make_old_database(path, from_version)

        conn = db.connect(path)
        db.initialize(conn)

        checking = accounts.by_code(conn, "1000").id
        from slowbooks import ledger

        ledger.post(conn, "2026-01-02", "Opening",
                    [ledger.debit(checking, 100_00),
                     ledger.credit(accounts.by_code(conn, "3000").id, 100_00)])

        rec_id = reconciliation.reconcile(conn, checking, "2026-01-31", 100_00)
        assert reconciliation.latest(conn, checking).id == rec_id
        conn.close()

    @pytest.mark.parametrize("from_version", [1, 2, 3, 4])
    def test_migrated_database_is_fully_functional(self, tmp_path, from_version):
        """A migration that leaves the app broken is not a migration."""
        path = tmp_path / f"v{from_version}.db"
        _make_old_database(path, from_version)

        conn = db.connect(path)
        db.initialize(conn)

        checking = accounts.by_code(conn, "1000").id
        result = csv_import.import_csv(
            conn,
            "Date,Description,Amount\n2026-01-15,KROGER 00123,-45.00\n",
            "chase.csv",
            checking,
        )
        assert result["from_starter_rules"] == 1
        conn.close()

    @pytest.mark.parametrize("from_version", [1, 2, 3, 4])
    def test_migration_is_idempotent(self, tmp_path, from_version):
        path = tmp_path / f"v{from_version}.db"
        _make_old_database(path, from_version)

        for _ in range(3):
            conn = db.connect(path)
            db.initialize(conn)  # must not raise "duplicate column name"
            conn.close()

        conn = db.connect(path)
        columns = [r["name"] for r in conn.execute("PRAGMA table_info(staged_transactions)")]
        assert columns.count("transfer_match_id") == 1
        conn.close()

    def test_migration_preserves_existing_data(self, tmp_path):
        path = tmp_path / "v1.db"
        _make_old_database(path, 1)

        conn = sqlite3.connect(str(path))
        conn.executescript(
            """
            INSERT INTO accounts (code, name, type, normal_balance)
                 VALUES ('1000', 'Checking', 'asset', 'debit');
            INSERT INTO import_batches (id, filename, account_id, row_count)
                 VALUES (1, 'old.csv', 1, 1);
            INSERT INTO staged_transactions
                 (batch_id, account_id, txn_date, description, amount_minor, fingerprint)
                 VALUES (1, 1, '2026-01-15', 'PRE-EXISTING ROW', -1234, 'abc123');
            """
        )
        conn.commit()
        conn.close()

        conn = db.connect(path)
        db.initialize(conn)

        row = conn.execute(
            """SELECT description, amount_minor, suggested_rule_id, transfer_match_id
                 FROM staged_transactions"""
        ).fetchone()
        assert row["description"] == "PRE-EXISTING ROW"
        assert row["amount_minor"] == -1234
        assert row["suggested_rule_id"] is None
        assert row["transfer_match_id"] is None
        conn.close()

    def test_v3_backfills_statement_accounts_on_an_existing_chart(self, tmp_path):
        """The subtle one.

        An existing book already has a chart of accounts, so seeding is skipped. If the
        new is_statement_account flag stayed 0 for every row, the user would silently
        lose the ability to record a transfer at all -- a migration that quietly
        disables a feature is worse than one that fails loudly.
        """
        path = tmp_path / "v2.db"
        _make_old_database(path, 2)

        conn = sqlite3.connect(str(path))
        conn.executescript(
            """
            INSERT INTO accounts (code, name, type, normal_balance)
                 VALUES ('1000', 'Checking', 'asset', 'debit'),
                        ('1010', 'Savings', 'asset', 'debit'),
                        ('2100', 'Credit Card', 'liability', 'credit'),
                        ('6100', 'Groceries', 'expense', 'debit');
            """
        )
        conn.commit()
        conn.close()

        conn = db.connect(path)
        db.initialize(conn)

        codes = {a.code for a in accounts.list_statement_accounts(conn)}
        assert codes == {"1000", "1010", "2100"}
        assert not accounts.by_code(conn, "6100").is_statement_account
        conn.close()

    def test_transfers_work_after_migrating_a_v1_book(self, tmp_path):
        """End-to-end proof that a real old file gets the new feature, not just columns."""
        path = tmp_path / "v1.db"
        _make_old_database(path, 1)

        conn = db.connect(path)
        db.initialize(conn)

        checking = accounts.by_code(conn, "1000").id
        savings = accounts.by_code(conn, "1010").id
        csv_import.import_csv(
            conn, "Date,Description,Amount\n2026-03-10,TRANSFER TO SAVINGS,-5000.00\n",
            "checking.csv", checking,
        )
        result = csv_import.import_csv(
            conn, "Date,Description,Amount\n2026-03-11,TRANSFER FROM CHECKING,5000.00\n",
            "savings.csv", savings,
        )
        assert result["transfer_pairs_found"] == 1
        conn.close()


class TestVersionGuards:
    def test_fresh_database_is_created_at_current_version(self, tmp_path):
        conn = db.connect(tmp_path / "fresh.db")
        db.initialize(conn)
        assert conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()["value"] == str(db.SCHEMA_VERSION)
        conn.close()

    def test_refuses_to_write_to_a_newer_book(self, tmp_path):
        """Silently writing to a book from a newer build could corrupt it.

        Refusing is conservative and matches ADR 0004's instinct: never quietly damage a
        financial record.
        """
        path = tmp_path / "future.db"
        conn = db.connect(path)
        db.initialize(conn)
        conn.execute("UPDATE schema_meta SET value = '99' WHERE key = 'version'")
        conn.close()

        conn = db.connect(path)
        with pytest.raises(RuntimeError, match="newer SlowBooks"):
            db.initialize(conn)
        conn.close()


class TestSeedingAndSettings:
    def test_settings_survive_a_reopen(self, tmp_path):
        path = tmp_path / "book.db"
        conn = db.connect(path)
        db.initialize(conn)
        settings.set_bool(conn, settings.STARTER_RULES_ACKNOWLEDGED, True)
        conn.close()

        # Acknowledgement lives in the book, so it travels with the file (ADR 0006).
        conn = db.connect(path)
        db.initialize(conn)
        assert settings.get_bool(conn, settings.STARTER_RULES_ACKNOWLEDGED) is True
        conn.close()

    def test_reinitializing_does_not_duplicate_starter_rules(self, tmp_path):
        path = tmp_path / "book.db"
        conn = db.connect(path)
        db.initialize(conn)
        before = conn.execute("SELECT COUNT(*) AS n FROM rules").fetchone()["n"]
        conn.close()

        conn = db.connect(path)
        db.initialize(conn)
        after = conn.execute("SELECT COUNT(*) AS n FROM rules").fetchone()["n"]
        conn.close()

        assert before == after == len(categorize.rules.STARTER_RULES)


@pytest.mark.parametrize("from_version", [1, 2, 3, 4])
def test_period_locking_works_after_migrating(tmp_path, from_version):
    """An upgraded book must get the lock, not just the table.

    The trigger is created by SCHEMA on every open (triggers are code, not data), so an
    old file picks it up — but that is exactly the kind of thing worth proving rather
    than assuming, since a migrated book that silently *lacks* the lock would look fine
    and let backdated entries through.
    """
    from slowbooks import ledger, periods

    path = tmp_path / f"v{from_version}.db"
    _make_old_database(path, from_version)

    conn = db.connect(path)
    db.initialize(conn)

    checking = accounts.by_code(conn, "1000").id
    groceries = accounts.by_code(conn, "6100").id
    ledger.post(conn, "2026-01-15", "Groceries",
                [ledger.debit(groceries, 45000), ledger.credit(checking, 45000)])
    periods.close(conn, "2026-01-31")

    with pytest.raises(ledger.LedgerError, match="books are closed"):
        ledger.post(conn, "2026-01-20", "Late",
                    [ledger.debit(groceries, 2500), ledger.credit(checking, 2500)])
    conn.close()


def test_transfers_module_is_importable_after_migration(tmp_path):
    # Guards the circular-import risk: db.py's v3 migration imports from accounts.py.
    path = tmp_path / "v1.db"
    _make_old_database(path, 1)
    conn = db.connect(path)
    db.initialize(conn)
    assert transfers.DEFAULT_WINDOW_DAYS > 0
    conn.close()
