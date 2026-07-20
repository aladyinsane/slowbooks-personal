"""Getting the user's books out.

ADR 0001 stakes the whole product on "your books are yours." This module is where that
stops being a slogan. See ADR 0008.

Two audiences, neither of whom can open a .db file:
  - Someone leaving SlowBooks, who needs data another tool can read.
  - Their accountant, who wants a general ledger and is the actual gatekeeper.

So the archive has a lossless layer (raw table dumps, integer cents) and a readable layer
(joined reports, decimal strings), plus a README explaining which is which -- an export
the user cannot interpret without us is still lock-in, just politer.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from datetime import datetime

from slowbooks import db

# Every table we own. Deliberately not a curated "important tables" list: a curated list
# is one we get to define, and the user discovers the gap at the worst possible moment --
# when they are already leaving.
TABLES = [
    "accounts",
    "journal_entries",
    "journal_lines",
    "import_batches",
    "staged_transactions",
    "rules",
    "reconciliations",
    "period_closes",
    "settings",
    "schema_meta",
]

README = """SlowBooks export
================

Generated {timestamp}
Schema version {schema_version}

These are your books. You do not need SlowBooks to read them, and you never will.


WHAT'S IN HERE
--------------

  general-ledger.csv    Every posted transaction line, with its account, date and
                        description. This is the file to give an accountant. Opens
                        straight into Excel.

  trial-balance.csv     Every account with its closing balance. Debits and credits
                        must total the same; if they don't, something is wrong.

  transactions.csv      A plainer, one-row-per-transaction view. Open this one if
                        you just want to see what happened.

  tables/*.csv          A complete, exact dump of every table in the database. This
                        is the layer to use if you are moving to another system.

  manifest.json         Row counts and schema version, so you can check nothing was
                        lost.

  slowbooks.db          Not included here -- download it separately from Settings, or
                        just copy the file. It is the complete book and the only thing
                        needed to restore.


ABOUT THE NUMBERS  (please read this bit)
-----------------------------------------

The reports (general-ledger.csv, trial-balance.csv, transactions.csv) show money the
normal way: 1234.56 means one thousand two hundred thirty-four dollars and fifty-six
cents.

The raw dumps in tables/ store money as WHOLE CENTS, as integers: 123456 means
$1,234.56. This is not us being difficult -- computers cannot represent 0.1 exactly in
binary, so storing dollars as decimals makes a ledger drift by fractions of a cent until
it no longer balances. Integers cannot drift.

So: if you are reading tables/journal_lines.csv, divide amount_minor by 100.

In tables/journal_lines.csv, amount_minor is SIGNED:
  positive = a debit    negative = a credit
Every journal entry's lines sum to exactly zero. That is what double-entry means, and
you can verify it yourself in a spreadsheet.


ABOUT THE TEXT ENCODING
-----------------------

Everything here is UTF-8.

The three report files start with a byte-order mark, which is how you tell Excel a file
is UTF-8. Without it Excel assumes Windows-1252 and turns any accented name or dash in
your bank descriptions into gibberish.

The dumps in tables/ have no byte-order mark, because those are meant for programs, and
a stray marker glued to the first column name causes more trouble there than it solves.
If you are reading them in Python, "utf-8" is correct; if you read the reports in Python,
use "utf-8-sig".


ACCOUNT TYPES
-------------

  asset      what you own      (increases with a debit)
  liability  what you owe      (increases with a credit)
  equity     the owner's stake (increases with a credit)
  revenue    money earned      (increases with a credit)
  expense    money spent       (increases with a debit)

Assets = Liabilities + Equity + (Revenue - Expenses). Always. If that doesn't hold in
this export, we have a bug and we would want to know.
"""


# Excel on Windows opens a BOM-less CSV as cp1252, not UTF-8. Without this, a bank
# description with an em-dash or an accented name reaches the accountant as mojibake --
# "Client A â€" January" -- in the file we specifically tell them to open in a
# spreadsheet. The BOM is how you say "this is UTF-8" to Excel.
#
# It goes on the *reports only*, and that split is deliberate. A BOM is not free: a
# consumer decoding plain UTF-8 rather than utf-8-sig gets a stray ﻿ glued to the
# first column name. That's a fine trade for the human layer, which is read by Excel, and
# a bad one for the raw layer, which is read by programs -- the same reasoning as the two
# money formats in this file. Both audiences are served honestly, and README.txt says
# which is which.
BOM = "﻿"


def _rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 - fixed list


def _write_csv(rows: list[sqlite3.Row], columns: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[column] for column in columns])
    return buffer.getvalue()


def _decimal(minor: int) -> str:
    """Cents to an ordinary decimal string for humans.

    Not money.format(): a CSV wants 1234.56, not "$1,234.56". A currency symbol and
    thousands separators are display, and they turn a number into text the moment a
    spreadsheet reads them.
    """
    sign = "-" if minor < 0 else ""
    whole, cents = divmod(abs(minor), 100)
    return f"{sign}{whole}.{cents:02d}"


def table_dump(conn: sqlite3.Connection, table: str) -> str:
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    return _write_csv(_rows(conn, table), columns)


def general_ledger_csv(conn: sqlite3.Connection) -> str:
    """Every posted line, with debits and credits in separate columns.

    The artifact an accountant asks for first. Our research is blunt about this: being
    pleasant to use does not beat "my CPA can't open your file."
    """
    rows = conn.execute(
        """SELECT e.entry_date, e.id AS entry_id, a.code, a.name, a.type,
                  e.description, l.memo, l.amount_minor, e.source
             FROM journal_lines l
             JOIN journal_entries e ON e.id = l.entry_id
             JOIN accounts a        ON a.id = l.account_id
            WHERE e.posted_at IS NOT NULL
            ORDER BY e.entry_date, e.id, a.code"""
    ).fetchall()

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["date", "entry", "account_code", "account_name", "account_type",
         "description", "memo", "debit", "credit", "source"]
    )
    for row in rows:
        amount = row["amount_minor"]
        writer.writerow([
            row["entry_date"], row["entry_id"], row["code"], row["name"], row["type"],
            row["description"], row["memo"] or "",
            _decimal(amount) if amount > 0 else "",
            _decimal(-amount) if amount < 0 else "",
            row["source"],
        ])
    return buffer.getvalue()


def trial_balance_csv(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """SELECT a.code, a.name, a.type, COALESCE(SUM(l.amount_minor), 0) AS balance
             FROM accounts a
             JOIN journal_lines l   ON l.account_id = a.id
             JOIN journal_entries e ON e.id = l.entry_id
            WHERE e.posted_at IS NOT NULL
            GROUP BY a.id, a.code, a.name, a.type
           HAVING SUM(l.amount_minor) <> 0
            ORDER BY a.code"""
    ).fetchall()

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["account_code", "account_name", "account_type", "debit", "credit"])

    total_debits = total_credits = 0
    for row in rows:
        balance = row["balance"]
        total_debits += balance if balance > 0 else 0
        total_credits += -balance if balance < 0 else 0
        writer.writerow([
            row["code"], row["name"], row["type"],
            _decimal(balance) if balance > 0 else "",
            _decimal(-balance) if balance < 0 else "",
        ])
    writer.writerow([])
    writer.writerow(["", "TOTAL", "", _decimal(total_debits), _decimal(total_credits)])
    return buffer.getvalue()


def transactions_csv(conn: sqlite3.Connection) -> str:
    """One row per posted entry: the plain view for someone who just wants to look.

    A general ledger is two lines per transaction, which is correct and confusing. This
    is principle 2 -- rigor underneath, plain language on top -- applied to an export.
    """
    rows = conn.execute(
        """SELECT e.id, e.entry_date, e.description, e.source,
                  (SELECT a.code || ' ' || a.name FROM journal_lines l
                     JOIN accounts a ON a.id = l.account_id
                    WHERE l.entry_id = e.id AND l.amount_minor > 0
                    ORDER BY l.amount_minor DESC LIMIT 1) AS debit_account,
                  (SELECT a.code || ' ' || a.name FROM journal_lines l
                     JOIN accounts a ON a.id = l.account_id
                    WHERE l.entry_id = e.id AND l.amount_minor < 0
                    ORDER BY l.amount_minor ASC LIMIT 1) AS credit_account,
                  (SELECT SUM(l.amount_minor) FROM journal_lines l
                    WHERE l.entry_id = e.id AND l.amount_minor > 0) AS total
             FROM journal_entries e
            WHERE e.posted_at IS NOT NULL
            ORDER BY e.entry_date, e.id"""
    ).fetchall()

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "entry", "description", "amount", "from_account",
                     "to_account", "source"])
    for row in rows:
        writer.writerow([
            row["entry_date"], row["id"], row["description"],
            _decimal(row["total"] or 0),
            row["credit_account"] or "", row["debit_account"] or "", row["source"],
        ])
    return buffer.getvalue()


def manifest(conn: sqlite3.Connection) -> dict[str, object]:
    version = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'version'"
    ).fetchone()
    return {
        "application": "SlowBooks",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "schema_version": int(version["value"]) if version else db.SCHEMA_VERSION,
        "money_format": {
            "tables/": "integer minor units (cents); 123456 means 1234.56",
            "reports": "decimal strings; 1234.56 means 1234.56",
            "journal_lines.amount_minor": "signed; positive = debit, negative = credit",
        },
        "row_counts": {
            table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]  # noqa: S608
            for table in TABLES
        },
    }


def export_json(conn: sqlite3.Connection) -> dict[str, object]:
    """Everything, as one structured document."""
    return {
        "manifest": manifest(conn),
        "tables": {
            table: [dict(row) for row in _rows(conn, table)] for table in TABLES
        },
    }


def export_zip(conn: sqlite3.Connection) -> bytes:
    """The whole archive: lossless dumps, readable reports, and instructions."""
    info = manifest(conn)
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.txt",
            README.format(
                timestamp=info["exported_at"], schema_version=info["schema_version"]
            ),
        )
        archive.writestr("manifest.json", json.dumps(info, indent=2))

        archive.writestr("general-ledger.csv", BOM + general_ledger_csv(conn))
        archive.writestr("trial-balance.csv", BOM + trial_balance_csv(conn))
        archive.writestr("transactions.csv", BOM + transactions_csv(conn))

        # No BOM here: this layer is for programs, and a stray BOM in the first column
        # name is a worse bug for them than mojibake would be for Excel.
        for table in TABLES:
            archive.writestr(f"tables/{table}.csv", table_dump(conn, table))

    return buffer.getvalue()
