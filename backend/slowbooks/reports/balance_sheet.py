"""Balance Sheet.

Assets = Liabilities + Equity at a point in time.

This report is the reason the ledger is double-entry (ADR 0004): it is not derivable
from single-entry data at all. If it balances, the books are internally sound; the
`balanced` flag it returns is our loudest correctness signal.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slowbooks import money


def balance_sheet(conn: sqlite3.Connection, as_of: date | str) -> dict[str, object]:
    """Balance sheet as of end-of-day `as_of`.

    Undistributed earnings (revenue - expenses to date) appear in equity as a
    computed line rather than a stored one. We do not post closing entries yet, and
    deriving it keeps the statement honest at any date -- including mid-year, which is
    when an owner actually looks.
    """
    as_of_iso = as_of.isoformat() if isinstance(as_of, date) else as_of

    rows = conn.execute(
        """SELECT a.code, a.name, a.type, COALESCE(SUM(l.amount_minor), 0) AS balance
             FROM accounts a
             JOIN journal_lines l   ON l.account_id = a.id
             JOIN journal_entries e ON e.id = l.entry_id
            WHERE e.posted_at IS NOT NULL
              AND e.entry_date <= ?
            GROUP BY a.id, a.code, a.name, a.type
           HAVING SUM(l.amount_minor) <> 0
            ORDER BY a.code""",
        (as_of_iso,),
    ).fetchall()

    assets: list[dict[str, object]] = []
    liabilities: list[dict[str, object]] = []
    equity: list[dict[str, object]] = []
    earnings_minor = 0

    for row in rows:
        if row["type"] == "asset":
            # Assets are debit-normal: positive internally is already positive here.
            assets.append(_line(row["code"], row["name"], row["balance"]))
        elif row["type"] == "liability":
            liabilities.append(_line(row["code"], row["name"], -row["balance"]))
        elif row["type"] == "equity":
            equity.append(_line(row["code"], row["name"], -row["balance"]))
        else:
            # Revenue and expense roll up into a single equity line.
            earnings_minor -= row["balance"]

    total_assets = sum(int(item["amount_minor"]) for item in assets)
    total_liabilities = sum(int(item["amount_minor"]) for item in liabilities)

    equity_lines = list(equity)
    if earnings_minor != 0:
        equity_lines.append(_line("", "Current Period Earnings", earnings_minor))

    total_equity = sum(int(item["amount_minor"]) for item in equity_lines)

    return {
        "report": "Net Worth",
        "basis": "accrual",
        "as_of": as_of_iso,
        "assets": {
            "lines": assets,
            "total_minor": total_assets,
            "total": money.format(total_assets),
        },
        "liabilities": {
            "lines": liabilities,
            "total_minor": total_liabilities,
            "total": money.format(total_liabilities),
        },
        "equity": {
            "lines": equity_lines,
            "total_minor": total_equity,
            "total": money.format(total_equity),
        },
        "total_liabilities_and_equity_minor": total_liabilities + total_equity,
        "total_liabilities_and_equity": money.format(total_liabilities + total_equity),
        # Guaranteed true by the balance trigger, surfaced anyway: a balance sheet that
        # cannot state whether it balances is not worth much.
        "balanced": total_assets == total_liabilities + total_equity,
    }


def _line(code: str, name: str, amount_minor: int) -> dict[str, object]:
    return {
        "code": code,
        "name": name,
        "amount_minor": amount_minor,
        "amount": money.format(amount_minor),
    }
