"""CSV import.

Bank CSVs are a swamp: every institution invents its own column names, date formats,
and sign conventions, and several use two columns (Debit/Credit) instead of one signed
Amount. This module turns that into staged transactions -- editable rows that have not
touched the ledger yet.

Nothing here posts to the ledger. Staging is the mutable zone (ADR 0004); posting is a
separate, deliberate act.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from slowbooks import money
from slowbooks.money import Minor

# Ordered by specificity: unambiguous ISO first, then US, then European. A bare
# "01/02/2026" is genuinely ambiguous and we resolve it US-first; the import preview
# exists so a human can catch that before anything is posted.
DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d",
    "%m/%d/%Y", "%m/%d/%y",
    "%d/%m/%Y", "%d/%m/%y",
    "%m-%d-%Y", "%d-%m-%Y",
    "%b %d, %Y", "%d %b %Y", "%B %d, %Y",
]

# Candidate header names, lowercased. Banks are not creative in consistent ways.
DATE_COLUMNS = ["date", "transaction date", "posted date", "post date", "trans date",
                "posting date", "date posted", "effective date"]
DESCRIPTION_COLUMNS = ["description", "payee", "name", "memo", "details", "narrative",
                       "transaction description", "merchant", "reference"]
AMOUNT_COLUMNS = ["amount", "transaction amount", "value"]
DEBIT_COLUMNS = ["debit", "withdrawal", "withdrawals", "money out", "paid out", "charge"]
CREDIT_COLUMNS = ["credit", "deposit", "deposits", "money in", "paid in", "payment"]

_WHITESPACE = re.compile(r"\s+")


class ImportError_(Exception):
    """The CSV could not be understood."""


@dataclass
class ColumnMapping:
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    # Card statements often report a purchase as a positive number, because they are
    # written from the bank's perspective rather than yours. Flipping at import keeps
    # one convention inside the ledger: positive = money in.
    invert_sign: bool = False


@dataclass
class StagedRow:
    txn_date: str
    description: str
    amount_minor: Minor
    fingerprint: str
    raw: dict[str, str]


def sniff_mapping(header: list[str]) -> ColumnMapping:
    """Guess which columns mean what.

    A guess, always shown to the user for confirmation before import -- principle 8,
    show the work. Silent guessing about money is how books get quietly wrong.
    """
    lookup = {h.strip().lower(): h for h in header if h and h.strip()}

    def find(candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate in lookup:
                return lookup[candidate]
        # Fall back to substring matching for headers like "Transaction Date (UTC)".
        for key, original in lookup.items():
            if any(candidate in key for candidate in candidates):
                return original
        return None

    date_col = find(DATE_COLUMNS)
    desc_col = find(DESCRIPTION_COLUMNS)
    if date_col is None:
        raise ImportError_(f"could not find a date column in: {', '.join(header)}")
    if desc_col is None:
        raise ImportError_(f"could not find a description column in: {', '.join(header)}")

    amount_col = find(AMOUNT_COLUMNS)
    if amount_col:
        return ColumnMapping(date=date_col, description=desc_col, amount=amount_col)

    debit_col, credit_col = find(DEBIT_COLUMNS), find(CREDIT_COLUMNS)
    if debit_col or credit_col:
        return ColumnMapping(
            date=date_col, description=desc_col, debit=debit_col, credit=credit_col
        )

    raise ImportError_(
        f"could not find an amount column (or debit/credit pair) in: {', '.join(header)}"
    )


def parse_date(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ImportError_("empty date")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    raise ImportError_(f"unrecognized date format: {text!r}")


def normalize_description(text: str) -> str:
    """Collapse whitespace and case for fingerprinting.

    Deliberately conservative: this feeds duplicate detection, so it must not merge
    genuinely different transactions. Cosmetic cleanup for *display* ("SQ *COFFEE
    #1234" -> "Square - Coffee") is a separate, richer job -- roadmap v0.3.
    """
    return _WHITESPACE.sub(" ", text.strip()).upper()


def fingerprint(account_id: int, txn_date: str, amount_minor: Minor, description: str) -> str:
    """Stable identity for duplicate detection.

    Re-importing an overlapping CSV is the top way to corrupt a set of books, and the
    damage is invisible: the numbers still look plausible.

    Known limitation: two genuinely distinct identical transactions (two $5.00 coffees,
    same shop, same day) fingerprint identically. Flagging as 'duplicate' rather than
    dropping is what makes that safe -- the user decides, and false positives cost a
    click while false negatives cost correctness.
    """
    payload = f"{account_id}|{txn_date}|{amount_minor}|{normalize_description(description)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def read_rows(content: str, account_id: int, mapping: ColumnMapping | None = None,
              ) -> tuple[ColumnMapping, list[StagedRow]]:
    """Parse CSV text into staged rows. Does not touch the database."""
    if not content.strip():
        raise ImportError_("file is empty")

    # Strip a BOM: Excel-exported CSVs routinely carry one, and it corrupts the first
    # header name into something no mapping will ever match.
    content = content.lstrip("﻿")

    try:
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # Sniffer gives up on single-column or odd files.

    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    if not reader.fieldnames:
        raise ImportError_("file has no header row")

    mapping = mapping or sniff_mapping(list(reader.fieldnames))

    rows: list[StagedRow] = []
    for line_number, raw in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw.values()):
            continue  # blank line; banks love a trailing one

        try:
            txn_date = parse_date(raw.get(mapping.date) or "")
            amount = _row_amount(raw, mapping)
        except (ImportError_, money.MoneyParseError) as exc:
            raise ImportError_(f"line {line_number}: {exc}") from exc

        if amount == 0:
            continue  # zero-value rows are noise, not transactions

        description = (raw.get(mapping.description) or "").strip() or "(no description)"
        rows.append(
            StagedRow(
                txn_date=txn_date,
                description=description,
                amount_minor=amount,
                fingerprint=fingerprint(account_id, txn_date, amount, description),
                raw=dict(raw),
            )
        )

    if not rows:
        raise ImportError_("no usable transaction rows found")
    return mapping, rows


def _row_amount(raw: dict[str, str], mapping: ColumnMapping) -> Minor:
    """Resolve one row's signed amount. Positive = money in, negative = money out."""
    if mapping.amount:
        amount = money.parse(raw.get(mapping.amount) or "0")
        return -amount if mapping.invert_sign else amount

    # Split debit/credit columns: exactly one is populated per row.
    debit = _optional_amount(raw, mapping.debit)
    credit = _optional_amount(raw, mapping.credit)

    if debit and credit:
        raise ImportError_("row has both a debit and a credit value")
    # Money out is a positive number in a "Withdrawal" column; negate it to reach our
    # single signed convention.
    return -abs(debit) if debit else abs(credit)


def _optional_amount(raw: dict[str, str], column: str | None) -> Minor:
    if not column:
        return 0
    text = (raw.get(column) or "").strip()
    return money.parse(text) if text else 0


def import_csv(
    conn: sqlite3.Connection,
    content: str,
    filename: str,
    account_id: int,
    mapping: ColumnMapping | None = None,
) -> dict[str, object]:
    """Stage a CSV against an account. Returns a summary of what happened.

    Staged rows are pending until explicitly posted, so an import is always previewable
    and always reversible.
    """
    mapping, rows = read_rows(content, account_id, mapping)

    existing = {
        row["fingerprint"]
        for row in conn.execute(
            "SELECT fingerprint FROM staged_transactions WHERE account_id = ?", (account_id,)
        )
    }

    try:
        conn.execute("BEGIN")
        cursor = conn.execute(
            "INSERT INTO import_batches (filename, account_id, row_count) VALUES (?, ?, ?)",
            (filename, account_id, len(rows)),
        )
        batch_id = cursor.lastrowid

        seen: set[str] = set()
        duplicates = 0
        for row in rows:
            # Catch duplicates within this file as well as against prior imports.
            is_duplicate = row.fingerprint in existing or row.fingerprint in seen
            duplicates += is_duplicate
            seen.add(row.fingerprint)
            conn.execute(
                """INSERT INTO staged_transactions
                       (batch_id, account_id, txn_date, description, amount_minor,
                        fingerprint, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, account_id, row.txn_date, row.description, row.amount_minor,
                 row.fingerprint, "duplicate" if is_duplicate else "pending"),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    from slowbooks import categorize, settings, transfers

    # Transfers first: a row that is the other side of a transfer must not also wear a
    # category suggestion, or the UI would offer the user a choice that is simply wrong
    # (ADR 0007). Money between your own accounts is neither income nor expense.
    transfer_pairs = transfers.detect_in_batch(conn, batch_id)

    categorized = categorize.apply_rules_to_batch(conn, batch_id)
    starter_count = categorized["from_starter_rules"]

    # ADR 0006: the first time shipped guesses touch this user's books, say so. The flag
    # is only set once they acknowledge it, so an abandoned first import still warns.
    warn_about_starter_rules = starter_count > 0 and not settings.get_bool(
        conn, settings.STARTER_RULES_ACKNOWLEDGED
    )

    return {
        "batch_id": batch_id,
        "filename": filename,
        "rows_read": len(rows),
        "duplicates_flagged": duplicates,
        "auto_categorized": categorized["matched"],
        "from_starter_rules": starter_count,
        "warn_about_starter_rules": warn_about_starter_rules,
        "transfer_pairs_found": transfer_pairs,
        # Paired transfers need no category, so they are not "review" work. Counting
        # them as such would nag the user about rows that are already resolved.
        "needs_review": len(rows) - duplicates - categorized["matched"] - transfer_pairs,
        "mapping": {
            "date": mapping.date,
            "description": mapping.description,
            "amount": mapping.amount,
            "debit": mapping.debit,
            "credit": mapping.credit,
        },
        "date_range": (
            [min(r.txn_date for r in rows), max(r.txn_date for r in rows)] if rows else []
        ),
    }
