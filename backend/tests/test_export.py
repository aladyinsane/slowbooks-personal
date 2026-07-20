"""Export tests (ADR 0008).

The most valuable test here is test_every_table_is_exported. ADR 0001 stakes the whole
product on "your books are yours"; an export that quietly misses a table breaks that
promise at the worst possible moment -- when the user is already leaving. This makes the
promise fail CI instead of failing a person.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest

from slowbooks import accounts, db, exporting, ledger, posting
from slowbooks.importing import csv_import

CHASE = """Transaction Date,Post Date,Description,Category,Type,Amount
01/15/2026,01/16/2026,KROGER 00123 SEATTLE WA,Shopping,Sale,-450.00
01/22/2026,01/23/2026,PAYROLL DEPOSIT,Income,Deposit,2500.00
"""


@pytest.fixture
def books(conn):
    """A book with posted entries, a transfer, and an unposted row."""
    checking = accounts.by_code(conn, "1000").id
    savings = accounts.by_code(conn, "1010").id

    batch = csv_import.import_csv(conn, CHASE, "chase.csv", checking)
    posting.post_batch(conn, batch["batch_id"])

    csv_import.import_csv(
        conn, "Date,Description,Amount\n2026-03-10,TO SAVINGS,-1000.00\n",
        "c2.csv", checking,
    )
    savings_batch = csv_import.import_csv(
        conn, "Date,Description,Amount\n2026-03-11,FROM CHECKING,1000.00\n",
        "s2.csv", savings,
    )
    posting.post_batch(conn, savings_batch["batch_id"])
    return conn


def _archive(conn) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(exporting.export_zip(conn)))


def _read_csv(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8"))))


class TestCompleteness:
    def test_every_table_is_exported(self, books):
        """If we add a table and forget the export, this fails.

        The anti-lock-in promise gets a failing test rather than a paragraph.
        """
        real_tables = {
            row["name"]
            for row in books.execute(
                """SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"""
            )
        }
        assert real_tables == set(exporting.TABLES), (
            "a table exists that the export doesn't know about -- add it to "
            "exporting.TABLES or the user loses it when they leave"
        )

    def test_archive_contains_every_layer(self, books):
        names = set(_archive(books).namelist())
        assert "README.txt" in names
        assert "manifest.json" in names
        assert {"general-ledger.csv", "trial-balance.csv", "transactions.csv"} <= names
        assert all(f"tables/{table}.csv" in names for table in exporting.TABLES)

    def test_row_counts_match_the_database(self, books):
        archive = _archive(books)
        info = json.loads(archive.read("manifest.json"))

        for table in exporting.TABLES:
            actual = books.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            exported = len(_read_csv(archive, f"tables/{table}.csv"))
            assert info["row_counts"][table] == actual, f"{table} manifest count wrong"
            assert exported == actual, f"{table} dump is missing rows"

    def test_raw_dumps_include_every_column(self, books):
        """Read the header line directly: an empty table still has a header, and a
        DictReader over zero rows would silently prove nothing."""
        archive = _archive(books)
        for table in exporting.TABLES:
            columns = [r["name"] for r in books.execute(f"PRAGMA table_info({table})")]
            text = archive.read(f"tables/{table}.csv").decode("utf-8")
            header = next(csv.reader(io.StringIO(text)))
            assert header == columns, f"{table} dump dropped or reordered columns"

    def test_empty_tables_still_get_a_header(self, books):
        # A file with no header is not a CSV, it's an empty file -- and the user can't
        # tell "no data" from "we forgot this table".
        text = _archive(books).read("tables/settings.csv").decode("utf-8")
        assert text.strip() == "key,value"

    def test_unposted_rows_are_exported_too(self, conn):
        # The user's staged, un-reviewed work is still their data, even though it isn't
        # in the ledger yet.
        checking = accounts.by_code(conn, "1000").id
        csv_import.import_csv(
            conn, "Date,Description,Amount\n2026-02-01,ZZQQ MYSTERY,-99.00\n",
            "pending.csv", checking,
        )
        rows = _read_csv(_archive(conn), "tables/staged_transactions.csv")
        assert any(r["status"] == "pending" for r in rows)
        assert any("ZZQQ MYSTERY" in r["description"] for r in rows)


class TestEncoding:
    """Excel is the accountant's tool, and Excel needs to be told a file is UTF-8.

    Found by generating the review book for a real CPA: an em-dash in a description came
    out as "Client A â€" January" in the one file we tell them to open in a spreadsheet.
    """

    @pytest.fixture
    def accented(self, conn):
        checking = accounts.by_code(conn, "1000").id
        supplies = accounts.by_code(conn, "6100").id
        ledger.post(
            conn, "2026-01-15", "Café Ubuntu — supplies · £5 fee",
            [ledger.debit(supplies, 5000), ledger.credit(checking, 5000)],
        )
        return conn

    def test_reports_carry_a_bom_so_excel_reads_them_as_utf8(self, accented):
        archive = _archive(accented)
        for name in ("general-ledger.csv", "trial-balance.csv", "transactions.csv"):
            assert archive.read(name).startswith(b"\xef\xbb\xbf"), f"{name} lost its BOM"

    def test_raw_dumps_have_no_bom_because_programs_read_them(self, accented):
        # A BOM here would glue an invisible character to the first column name for
        # anyone decoding plain UTF-8 -- worse for this audience than mojibake is for Excel.
        archive = _archive(accented)
        for table in exporting.TABLES:
            assert not archive.read(f"tables/{table}.csv").startswith(b"\xef\xbb\xbf")

    def test_accented_descriptions_survive_the_round_trip(self, accented):
        text = _archive(accented).read("general-ledger.csv").decode("utf-8-sig")
        assert "Café Ubuntu — supplies · £5 fee" in text

    def test_the_exact_mojibake_that_started_this(self, accented):
        """Decoding the report as cp1252 -- what Excel does without a BOM -- must not
        silently produce plausible-looking garbage."""
        raw = _archive(accented).read("general-ledger.csv")
        # With the BOM, Excel switches to UTF-8 and never reaches the cp1252 path.
        assert raw[:3] == b"\xef\xbb\xbf"
        # Prove the hazard is real: an em-dash is \xe2\x80\x94 in UTF-8, which cp1252
        # renders as a-circumflex, euro, right-quote. This is what the CPA would have got.
        mojibake = "â€”"
        assert mojibake in raw[3:].decode("cp1252")

    def test_reports_are_still_valid_csv_after_the_bom(self, accented):
        # utf-8-sig strips the marker; the first column must be `date`, not `﻿date`.
        text = _archive(accented).read("general-ledger.csv").decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        assert "date" in rows[0]
        assert not any(key.startswith("﻿") for key in rows[0])


class TestMoneyRepresentation:
    def test_raw_dumps_keep_integer_cents(self, books):
        rows = _read_csv(_archive(books), "tables/journal_lines.csv")
        # Lossless, exactly as stored (ADR 0003). Never a decimal here.
        assert all("." not in r["amount_minor"] for r in rows)
        assert any(r["amount_minor"] == "45000" for r in rows)

    def test_reports_use_plain_decimals(self, books):
        rows = _read_csv(_archive(books), "general-ledger.csv")
        kroger = next(r for r in rows if "KROGER" in r["description"] and r["debit"])
        # An accountant opening 123456 would conclude we're broken, and be right.
        assert kroger["debit"] == "450.00"
        assert "$" not in kroger["debit"] and "," not in kroger["debit"]

    def test_decimal_formatting_edges(self):
        assert exporting._decimal(0) == "0.00"
        assert exporting._decimal(1) == "0.01"
        assert exporting._decimal(-1) == "-0.01"
        assert exporting._decimal(100) == "1.00"
        assert exporting._decimal(123456) == "1234.56"
        assert exporting._decimal(-123456) == "-1234.56"
        # No thousands separators: a comma would break the CSV column it lives in.
        assert exporting._decimal(100000000) == "1000000.00"

    def test_readme_explains_the_two_formats(self, books):
        readme = _archive(books).read("README.txt").decode("utf-8")
        # An export the user can't interpret without us is still lock-in, just politer.
        assert "amount_minor" in readme
        assert "divide" in readme.lower()
        assert "positive = a debit" in readme


class TestAccountantReports:
    def test_general_ledger_balances(self, books):
        rows = _read_csv(_archive(books), "general-ledger.csv")
        debits = sum(round(float(r["debit"]) * 100) for r in rows if r["debit"])
        credits = sum(round(float(r["credit"]) * 100) for r in rows if r["credit"])
        assert debits == credits

    def test_general_ledger_never_has_both_columns_on_a_line(self, books):
        for row in _read_csv(_archive(books), "general-ledger.csv"):
            assert not (row["debit"] and row["credit"])

    def test_trial_balance_totals_agree(self, books):
        rows = _read_csv(_archive(books), "trial-balance.csv")
        total = next(r for r in rows if r["account_name"] == "TOTAL")
        assert total["debit"] == total["credit"]

    def test_transactions_view_is_one_row_per_entry(self, books):
        rows = _read_csv(_archive(books), "transactions.csv")
        entries = books.execute(
            "SELECT COUNT(*) AS n FROM journal_entries WHERE posted_at IS NOT NULL"
        ).fetchone()["n"]
        assert len(rows) == entries

    def test_drafts_are_excluded_from_reports(self, conn):
        # An unposted draft is not a financial fact and must not appear in a ledger
        # handed to an accountant.
        checking = accounts.by_code(conn, "1000").id
        supplies = accounts.by_code(conn, "6100").id
        cursor = conn.execute(
            """INSERT INTO journal_entries (entry_date, description, source, posted_at)
               VALUES ('2026-01-01', 'DRAFT ONLY', 'manual', NULL)"""
        )
        conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?,?,?)",
            (cursor.lastrowid, supplies, 100),
        )
        conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, amount_minor) VALUES (?,?,?)",
            (cursor.lastrowid, checking, -100),
        )
        ledger_csv = exporting.general_ledger_csv(conn)
        assert "DRAFT ONLY" not in ledger_csv


class TestJsonExport:
    def test_json_has_every_table(self, books):
        data = exporting.export_json(books)
        assert set(data["tables"]) == set(exporting.TABLES)

    def test_json_row_counts_match(self, books):
        data = exporting.export_json(books)
        for table in exporting.TABLES:
            actual = books.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            assert len(data["tables"][table]) == actual

    def test_json_is_serializable(self, books):
        # sqlite3.Row isn't JSON-serializable; a dict() slip here would 500 at runtime.
        text = json.dumps(exporting.export_json(books))
        assert "accounts" in text


class TestEmptyBook:
    def test_export_of_a_fresh_book_still_works(self, conn):
        """A user who exports before doing anything must not hit a crash."""
        archive = _archive(conn)
        assert "README.txt" in archive.namelist()
        rows = _read_csv(archive, "tables/accounts.csv")
        assert len(rows) == len(accounts.list_all(conn, active_only=False))
        # No transactions yet, so the ledger is just a header.
        assert _read_csv(archive, "general-ledger.csv") == []


class TestVoidsAreVisible:
    def test_a_voided_entry_and_its_reversal_both_export(self, conn):
        """Append-only means history survives; the export must show it, not hide it."""
        checking = accounts.by_code(conn, "1000").id
        supplies = accounts.by_code(conn, "6100").id
        entry_id = ledger.post(
            conn, "2026-01-15", "Mistaken charge",
            [ledger.debit(supplies, 5000), ledger.credit(checking, 5000)],
        )
        ledger.void(conn, entry_id, "personal expense")

        rows = _read_csv(_archive(conn), "general-ledger.csv")
        assert any("Mistaken charge" == r["description"] for r in rows)
        assert any(r["source"] == "void" for r in rows)
        # And the net effect is nil, which the accountant can see for themselves.
        debits = sum(round(float(r["debit"]) * 100) for r in rows if r["debit"])
        credits = sum(round(float(r["credit"]) * 100) for r in rows if r["credit"])
        assert debits == credits


def test_manifest_records_schema_version(books):
    info = json.loads(_archive(books).read("manifest.json"))
    assert info["schema_version"] == db.SCHEMA_VERSION
