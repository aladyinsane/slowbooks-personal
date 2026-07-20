"""SQLite connection and schema.

One file, on the user's disk, that they own. See
docs/decisions/0001-local-first-sqlite.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 6

# The balance and immutability invariants live in the database itself rather than in
# application code. Principle 6: correct by construction, not by user diligence -- and
# not by remembering to call the right helper. Nothing that speaks SQLite to this file
# can post unbalanced books, including a future us with a migration script.
SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- User-facing app state, as opposed to schema_meta which is about the database itself.
-- Currently just tracks whether the starter-rule warning has been seen (ADR 0006).
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- A group is how accounts are organized for display: "Food & Dining" containing
-- Groceries and Dining & Takeout. A first-class table rather than a hardcoded map so a
-- user can rename/reorganize groups the same way ADR 0010 already lets them rename
-- accounts -- a hardcoded frontend grouping would be a second source of truth that
-- drifts from the first. See ADR 0014.
CREATE TABLE IF NOT EXISTS groups (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN
             ('asset','liability','equity','revenue','expense')),
    UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS accounts (
    id             INTEGER PRIMARY KEY,
    code           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL CHECK (type IN
                       ('asset','liability','equity','revenue','expense')),
    normal_balance TEXT NOT NULL CHECK (normal_balance IN ('debit','credit')),
    is_active      INTEGER NOT NULL DEFAULT 1,
    description    TEXT,
    -- An account you can import a statement for and move money between: checking,
    -- savings, a credit card, a loan. Modeled rather than inferred from the code
    -- prefix -- a user who adds a second checking account should be able to say so
    -- instead of discovering our numbering convention. See ADR 0007.
    is_statement_account INTEGER NOT NULL DEFAULT 0,
    -- Which group this account displays under. Nullable: a user-invented account may
    -- not have picked one yet, and an ungrouped account is a valid state ("Other"), not
    -- an error. See ADR 0014.
    group_id INTEGER REFERENCES groups(id)
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id                INTEGER PRIMARY KEY,
    entry_date        TEXT NOT NULL,          -- ISO-8601 YYYY-MM-DD
    description       TEXT NOT NULL,
    source            TEXT NOT NULL DEFAULT 'manual',
    reverses_entry_id INTEGER REFERENCES journal_entries(id),
    posted_at         TEXT,                   -- NULL = draft, still mutable
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entries_date ON journal_entries(entry_date);

-- amount_minor is signed integer cents: positive = debit, negative = credit.
-- One signed column beats two nullable ones, and it makes the balance check a
-- plain SUM(...) = 0. See ADR 0003.
CREATE TABLE IF NOT EXISTS journal_lines (
    id           INTEGER PRIMARY KEY,
    entry_id     INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    amount_minor INTEGER NOT NULL CHECK (amount_minor <> 0),
    memo         TEXT,
    -- Which reconciliation covered this line (ADR 0009). Nullable: unreconciled is the
    -- normal state. Shaped to allow line-by-line ticking later without a migration.
    reconciliation_id INTEGER REFERENCES reconciliations(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_lines_entry   ON journal_lines(entry_id);
CREATE INDEX IF NOT EXISTS idx_lines_account ON journal_lines(account_id);
CREATE INDEX IF NOT EXISTS idx_lines_recon   ON journal_lines(reconciliation_id);

CREATE TABLE IF NOT EXISTS import_batches (
    id          INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    row_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS staged_transactions (
    id                  INTEGER PRIMARY KEY,
    batch_id            INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    account_id          INTEGER NOT NULL REFERENCES accounts(id),
    txn_date            TEXT NOT NULL,
    description         TEXT NOT NULL,
    amount_minor        INTEGER NOT NULL,
    fingerprint         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','posted','duplicate','ignored')),
    suggested_account_id INTEGER REFERENCES accounts(id),
    suggested_reason    TEXT,
    -- Which rule produced the suggestion. Lets the UI distinguish a starter guess from
    -- something the user taught us, which ADR 0006 requires -- storing only the
    -- resulting account throws away exactly the fact that matters most.
    --
    -- ON DELETE SET NULL: deleting a rule must not be blocked by, or destroy, a staged
    -- row that happens to cite it. The suggestion survives; only its provenance is lost.
    suggested_rule_id   INTEGER REFERENCES rules(id) ON DELETE SET NULL,
    posted_entry_id     INTEGER REFERENCES journal_entries(id),
    -- The other side of a transfer: the matching row in a different account (ADR 0007).
    -- Set on both rows, pointing at each other. Both settle against ONE journal entry,
    -- because posting each side independently would move the money twice.
    transfer_match_id   INTEGER REFERENCES staged_transactions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_staged_fingerprint ON staged_transactions(fingerprint);
CREATE INDEX IF NOT EXISTS idx_staged_batch       ON staged_transactions(batch_id);

-- Closing the books through a date freezes everything on or before it (ADR 0011).
-- Global, not per-account: closing asks "is this period final?", which is a question
-- about the whole entity. Append-only, like the ledger -- reopening is a new record
-- that reverses a close, never a deletion.
CREATE TABLE IF NOT EXISTS period_closes (
    id             INTEGER PRIMARY KEY,
    closed_through TEXT NOT NULL,              -- ISO-8601; on or before this is frozen
    closed_at      TEXT NOT NULL DEFAULT (datetime('now')),
    note           TEXT,
    reopens_id     INTEGER REFERENCES period_closes(id)
);

CREATE INDEX IF NOT EXISTS idx_closes_through ON period_closes(closed_through);

-- A reconciliation is a durable record of a claim the user made: "on this date, the
-- bank said I had $X." Not a computed status -- the human assertion IS the artifact
-- (ADR 0009). Append-only, like the ledger, for the same reason.
CREATE TABLE IF NOT EXISTS reconciliations (
    id              INTEGER PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    statement_date  TEXT NOT NULL,                 -- ISO-8601, the bank's closing date
    -- The bank's number, typed in by the user. A fact from outside our system that we
    -- must never invent: if we could compute it, reconciling would prove nothing.
    statement_balance_minor INTEGER NOT NULL,
    -- What we believed at the time. Derivable from today's ledger, but only from
    -- *today's* -- recording it is what lets us later detect a backdated entry.
    book_balance_minor      INTEGER NOT NULL,
    reconciled_at   TEXT NOT NULL DEFAULT (datetime('now')),
    note            TEXT,
    -- Set when a later reconciliation reverses this one. Undo is a new record, never a
    -- deletion (ADR 0004's reasoning, applied here).
    reverses_id     INTEGER REFERENCES reconciliations(id)
);

CREATE INDEX IF NOT EXISTS idx_recon_account ON reconciliations(account_id, statement_date);

CREATE TABLE IF NOT EXISTS rules (
    id         INTEGER PRIMARY KEY,
    priority   INTEGER NOT NULL DEFAULT 100,
    match_type TEXT NOT NULL CHECK (match_type IN ('contains','regex','exact')),
    pattern    TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    -- Sign constraint lets one pattern mean different things by direction: a VENMO
    -- debit is a gift you sent, a VENMO credit is income. 'any' when direction is
    -- irrelevant.
    applies_to TEXT NOT NULL DEFAULT 'any' CHECK (applies_to IN ('any','debit','credit')),
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rules_priority ON rules(priority);

-- Posting is the moment a draft becomes a financial fact. That is exactly where the
-- balance check belongs: drafts may be lopsided while being built, posted entries
-- may never be.
DROP TRIGGER IF EXISTS trg_entry_must_balance_on_post;
CREATE TRIGGER trg_entry_must_balance_on_post
BEFORE UPDATE OF posted_at ON journal_entries
WHEN NEW.posted_at IS NOT NULL AND OLD.posted_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'unbalanced journal entry: debits must equal credits')
    WHERE (SELECT COALESCE(SUM(amount_minor), 0)
             FROM journal_lines WHERE entry_id = NEW.id) <> 0;

    SELECT RAISE(ABORT, 'journal entry must have at least two lines')
    WHERE (SELECT COUNT(*) FROM journal_lines WHERE entry_id = NEW.id) < 2;
END;

-- Nothing may be posted into a closed period (ADR 0011). Fires at posting, like the
-- balance check, because that is the moment a draft becomes a financial fact.
--
-- The subquery is the "currently in force" close: the latest one that is not itself a
-- reopen and has not been reopened. Same shape as reconciliation.latest().
DROP TRIGGER IF EXISTS trg_no_posting_into_closed_period;
CREATE TRIGGER trg_no_posting_into_closed_period
BEFORE UPDATE OF posted_at ON journal_entries
WHEN NEW.posted_at IS NOT NULL AND OLD.posted_at IS NULL
     AND NEW.entry_date <= COALESCE((
         SELECT MAX(p.closed_through) FROM period_closes p
          WHERE p.reopens_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM period_closes r WHERE r.reopens_id = p.id)
     ), '0000-00-00')
BEGIN
    SELECT RAISE(ABORT, 'the books are closed for this date; reopen the period first');
END;

-- Append-only. Corrections are reversing entries, never rewrites. See ADR 0004.
DROP TRIGGER IF EXISTS trg_posted_entries_immutable;
CREATE TRIGGER trg_posted_entries_immutable
BEFORE UPDATE ON journal_entries
WHEN OLD.posted_at IS NOT NULL
     AND (NEW.entry_date <> OLD.entry_date
          OR NEW.posted_at IS NOT OLD.posted_at
          OR NEW.id <> OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'posted journal entries are immutable; post a reversal instead');
END;

DROP TRIGGER IF EXISTS trg_posted_entries_no_delete;
CREATE TRIGGER trg_posted_entries_no_delete
BEFORE DELETE ON journal_entries
WHEN OLD.posted_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'posted journal entries cannot be deleted; post a reversal instead');
END;

-- ADR 0004 draws the line at *financial facts*: amounts, dates and accounts are
-- immutable once posted; annotations are not. Reconciliation (ADR 0009) stamps
-- reconciliation_id onto posted lines, which is a note about a line rather than a
-- change to what it says -- so this guards the three columns that matter instead of
-- freezing the whole row.
DROP TRIGGER IF EXISTS trg_posted_lines_immutable;
CREATE TRIGGER trg_posted_lines_immutable
BEFORE UPDATE ON journal_lines
WHEN (SELECT posted_at FROM journal_entries WHERE id = OLD.entry_id) IS NOT NULL
     AND (NEW.amount_minor <> OLD.amount_minor
          OR NEW.account_id <> OLD.account_id
          OR NEW.entry_id <> OLD.entry_id)
BEGIN
    SELECT RAISE(ABORT, 'lines of a posted entry are immutable; post a reversal instead');
END;

DROP TRIGGER IF EXISTS trg_posted_lines_no_insert;
CREATE TRIGGER trg_posted_lines_no_insert
BEFORE INSERT ON journal_lines
WHEN (SELECT posted_at FROM journal_entries WHERE id = NEW.entry_id) IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'cannot add lines to a posted entry');
END;

DROP TRIGGER IF EXISTS trg_posted_lines_no_delete;
CREATE TRIGGER trg_posted_lines_no_delete
BEFORE DELETE ON journal_lines
WHEN (SELECT posted_at FROM journal_entries WHERE id = OLD.entry_id) IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'cannot delete lines from a posted entry');
END;

-- A group and its accounts must be the same type -- otherwise "Food & Dining" could
-- silently acquire a revenue account. See ADR 0014.
DROP TRIGGER IF EXISTS trg_account_group_type_matches_insert;
CREATE TRIGGER trg_account_group_type_matches_insert
BEFORE INSERT ON accounts
WHEN NEW.group_id IS NOT NULL
     AND NEW.type <> (SELECT type FROM groups WHERE id = NEW.group_id)
BEGIN
    SELECT RAISE(ABORT, 'a group and its accounts must be the same type');
END;

DROP TRIGGER IF EXISTS trg_account_group_type_matches_update;
CREATE TRIGGER trg_account_group_type_matches_update
BEFORE UPDATE ON accounts
WHEN NEW.group_id IS NOT NULL
     AND NEW.type <> (SELECT type FROM groups WHERE id = NEW.group_id)
BEGIN
    SELECT RAISE(ABORT, 'a group and its accounts must be the same type');
END;
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) a SlowBooks database.

    check_same_thread=False because FastAPI hands a request to whichever threadpool
    worker is free. Connections are not shared *between* threads -- deps.py keeps one
    per thread, for reasons documented at length there -- but a single thread-local
    connection can still be created on one worker and used on another.
    """
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL: readers don't block the writer and vice versa. With a connection per thread
    # that is what keeps concurrent reads off the writer's back.
    conn.execute("PRAGMA journal_mode = WAL")
    # SQLite allows one writer at a time. Without this, a second writer fails instantly
    # with "database is locked"; with it, it waits its turn. Our writes are single-user
    # and sub-millisecond, so waiting is invisible and failing would not be.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    """Create the schema, migrate an older file if needed, and seed if empty.

    Order matters, and getting it wrong broke every upgrade path once already:

      1. _migrate ADDs columns to tables that already exist. CREATE TABLE IF NOT EXISTS
         will not touch them, so this is the only chance those columns get.
      2. SCHEMA then creates whatever is missing -- new tables, and the indexes and
         triggers that *reference* the columns step 1 just added.

    Run in the other order, SCHEMA tries to index journal_lines(reconciliation_id) on a
    book that doesn't have that column yet, and the user's file fails to open.
    """
    existing_version = _read_version(conn)

    _migrate(conn, existing_version)
    conn.executescript(SCHEMA)

    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),),
    )

    from slowbooks import accounts, categorize, groups

    if conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"] == 0:
        # Gated separately from accounts: a migrated-but-empty book (an old schema
        # version with no accounts yet -- unusual in practice, but exactly what the
        # migration test fixtures construct) may already have had groups seeded by the
        # v6 migration step above, and seeding them again would collide on the
        # (name, type) UNIQUE constraint.
        if conn.execute("SELECT COUNT(*) AS n FROM groups").fetchone()["n"] == 0:
            groups.seed_default_groups(conn)
        accounts.seed_default_chart(conn)
        categorize.seed_starter_rules(conn)


def _read_version(conn: sqlite3.Connection) -> int | None:
    """Schema version of an existing file, or None if this is a fresh database."""
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone()
    if table is None:
        return None
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
    return int(row["value"]) if row else None


def _migrate(conn: sqlite3.Connection, from_version: int | None) -> None:
    """Bring an existing database up to SCHEMA_VERSION.

    ADR 0001 promises the user owns their file and it keeps working. That promise only
    survives if upgrades never require them to start over -- so migrations are part of
    the product, not housekeeping. CREATE TABLE IF NOT EXISTS silently does nothing to
    an existing table, so new columns land here or not at all.
    """
    if from_version is None:
        return  # fresh database; SCHEMA is already current

    if from_version < 2:
        # ADR 0006: track which rule produced each suggestion.
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(staged_transactions)")
        }
        if "suggested_rule_id" not in columns:
            # SQLite's ALTER TABLE ADD COLUMN cannot express a REFERENCES clause with a
            # delete action, so older files carry the column without the FK. It is
            # advisory data, not an invariant -- unlike the balance rules, nothing
            # breaks if it is null.
            conn.execute("ALTER TABLE staged_transactions ADD COLUMN suggested_rule_id INTEGER")

    if from_version < 3:
        # ADR 0007: transfers are a distinct kind of transaction.
        staged_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(staged_transactions)")
        }
        if "transfer_match_id" not in staged_columns:
            conn.execute("ALTER TABLE staged_transactions ADD COLUMN transfer_match_id INTEGER")

        account_columns = {row["name"] for row in conn.execute("PRAGMA table_info(accounts)")}
        if "is_statement_account" not in account_columns:
            conn.execute(
                "ALTER TABLE accounts ADD COLUMN is_statement_account "
                "INTEGER NOT NULL DEFAULT 0"
            )
            # Backfill from the default chart. An existing book already has these
            # accounts, and leaving every flag at 0 would silently remove the user's
            # ability to record a transfer at all -- a migration that quietly disables a
            # feature is worse than one that fails loudly.
            from slowbooks.accounts import STATEMENT_ACCOUNT_CODES

            conn.executemany(
                "UPDATE accounts SET is_statement_account = 1 WHERE code = ?",
                [(code,) for code in STATEMENT_ACCOUNT_CODES],
            )

    if from_version < 4:
        # ADR 0009: reconciliation. The table is created by SCHEMA above; only the
        # journal_lines column needs an ALTER on an existing file.
        line_columns = {row["name"] for row in conn.execute("PRAGMA table_info(journal_lines)")}
        if "reconciliation_id" not in line_columns:
            conn.execute("ALTER TABLE journal_lines ADD COLUMN reconciliation_id INTEGER")

    if from_version < 5:
        # ADR 0011: period locking. The table and trigger come from SCHEMA above; there
        # is no column to add, so nothing to ALTER. Listed anyway so the version ladder
        # has no silent gaps.
        pass

    if from_version < 6:
        # ADR 0014: categories get a Group layer. Unlike period_closes/reconciliations
        # (new tables that start empty), groups needs to be pre-seeded even on an
        # existing book -- so, unusually, this block creates the table itself right here
        # rather than waiting for SCHEMA below. SCHEMA's own `CREATE TABLE IF NOT EXISTS`
        # then no-ops harmlessly once it runs.
        tables = {
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "groups" not in tables:
            conn.execute(
                """CREATE TABLE groups (
                    id   INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN
                             ('asset','liability','equity','revenue','expense')),
                    UNIQUE(name, type)
                )"""
            )
            from slowbooks import groups as groups_module

            groups_module.seed_default_groups(conn)

        account_columns = {row["name"] for row in conn.execute("PRAGMA table_info(accounts)")}
        if "group_id" not in account_columns:
            # No REFERENCES here either, for the same reason is_statement_account and
            # suggested_rule_id don't have one: ALTER TABLE ADD COLUMN can't express it.
            conn.execute("ALTER TABLE accounts ADD COLUMN group_id INTEGER")

            # Backfill from the default chart, the same shape as v3's
            # is_statement_account backfill. A user-invented account (unknown code)
            # stays ungrouped rather than guessed at -- the UI shows that as "Other",
            # not an error.
            from slowbooks.accounts import CODE_TO_GROUP

            conn.executemany(
                """UPDATE accounts SET group_id =
                       (SELECT id FROM groups WHERE name = ? AND type = accounts.type)
                     WHERE code = ?""",
                [(group_name, code) for code, group_name in CODE_TO_GROUP.items()],
            )

    if from_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"this book was written by a newer SlowBooks (schema v{from_version}; "
            f"this build understands v{SCHEMA_VERSION}). Upgrade rather than risk "
            f"writing to it."
        )
