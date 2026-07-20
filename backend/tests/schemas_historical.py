"""Frozen copies of schemas we actually shipped.

**Never derive these from `db.SCHEMA`.** They were originally built by string-patching
the current schema, and they drifted the moment a column moved: the "v1" fixture quietly
grew a v3 column and the migration tests kept passing while proving nothing.

A migration test is a claim about *real user files that exist in the wild*. Those files
do not change when we edit db.py, so neither may these. Copy the schema verbatim when you
bump SCHEMA_VERSION, then leave it alone forever.

Anything here is history. Editing it is falsifying the record.
"""

# Shipped in PR #1. No settings table, no suggestion provenance, no transfers.
V1 = """
PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE accounts (
    id             INTEGER PRIMARY KEY,
    code           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL CHECK (type IN
                       ('asset','liability','equity','revenue','expense')),
    normal_balance TEXT NOT NULL CHECK (normal_balance IN ('debit','credit')),
    is_active      INTEGER NOT NULL DEFAULT 1,
    description    TEXT
);

CREATE TABLE journal_entries (
    id                INTEGER PRIMARY KEY,
    entry_date        TEXT NOT NULL,
    description       TEXT NOT NULL,
    source            TEXT NOT NULL DEFAULT 'manual',
    reverses_entry_id INTEGER REFERENCES journal_entries(id),
    posted_at         TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE journal_lines (
    id           INTEGER PRIMARY KEY,
    entry_id     INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    amount_minor INTEGER NOT NULL CHECK (amount_minor <> 0),
    memo         TEXT
);

CREATE TABLE import_batches (
    id          INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    row_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE staged_transactions (
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
    posted_entry_id     INTEGER REFERENCES journal_entries(id)
);

CREATE TABLE rules (
    id         INTEGER PRIMARY KEY,
    priority   INTEGER NOT NULL DEFAULT 100,
    match_type TEXT NOT NULL CHECK (match_type IN ('contains','regex','exact')),
    pattern    TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    applies_to TEXT NOT NULL DEFAULT 'any' CHECK (applies_to IN ('any','debit','credit')),
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Shipped in PR #3 (ADR 0006): adds the settings table and suggestion provenance.
V2 = V1.replace(
    """    suggested_reason    TEXT,
    posted_entry_id     INTEGER REFERENCES journal_entries(id)
);""",
    """    suggested_reason    TEXT,
    suggested_rule_id   INTEGER REFERENCES rules(id) ON DELETE SET NULL,
    posted_entry_id     INTEGER REFERENCES journal_entries(id)
);""",
) + """
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Shipped in PR #5 (ADR 0007): statement accounts and transfer pairing.
#
# Deriving V3 from V2 is safe in a way that deriving from db.SCHEMA was not: V1 and V2
# are frozen literals that will never move again, so this chain is deterministic. The
# rule the file header states is "never derive from current code", not "never derive".
V3 = V2.replace(
    """    is_active      INTEGER NOT NULL DEFAULT 1,
    description    TEXT
);""",
    """    is_active      INTEGER NOT NULL DEFAULT 1,
    description    TEXT,
    is_statement_account INTEGER NOT NULL DEFAULT 0
);""",
).replace(
    """    suggested_rule_id   INTEGER REFERENCES rules(id) ON DELETE SET NULL,
    posted_entry_id     INTEGER REFERENCES journal_entries(id)
);""",
    """    suggested_rule_id   INTEGER REFERENCES rules(id) ON DELETE SET NULL,
    posted_entry_id     INTEGER REFERENCES journal_entries(id),
    transfer_match_id   INTEGER REFERENCES staged_transactions(id) ON DELETE SET NULL
);""",
)

# Shipped in PR #7 (ADR 0009): reconciliation.
V4 = V3.replace(
    """    amount_minor INTEGER NOT NULL CHECK (amount_minor <> 0),
    memo         TEXT
);""",
    """    amount_minor INTEGER NOT NULL CHECK (amount_minor <> 0),
    memo         TEXT,
    reconciliation_id INTEGER REFERENCES reconciliations(id) ON DELETE SET NULL
);""",
) + """
CREATE TABLE reconciliations (
    id              INTEGER PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    statement_date  TEXT NOT NULL,
    statement_balance_minor INTEGER NOT NULL,
    book_balance_minor      INTEGER NOT NULL,
    reconciled_at   TEXT NOT NULL DEFAULT (datetime('now')),
    note            TEXT,
    reverses_id     INTEGER REFERENCES reconciliations(id)
);
"""

# Shipped for ADR 0011: period locking. No column changes, just a new table.
V5 = V4 + """
CREATE TABLE period_closes (
    id             INTEGER PRIMARY KEY,
    closed_through TEXT NOT NULL,
    closed_at      TEXT NOT NULL DEFAULT (datetime('now')),
    note           TEXT,
    reopens_id     INTEGER REFERENCES period_closes(id)
);
"""

SCHEMAS = {1: V1, 2: V2, 3: V3, 4: V4, 5: V5}
