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
from slowbooks.reports.grouping import group_lines


def balance_sheet(conn: sqlite3.Connection, as_of: date | str) -> dict[str, object]:
    """Balance sheet as of end-of-day `as_of`.

    Undistributed earnings (revenue - expenses to date) appear in equity as a
    computed line rather than a stored one. We do not post closing entries yet, and
    deriving it keeps the statement honest at any date -- including mid-year, which is
    when an owner actually looks.
    """
    as_of_iso = as_of.isoformat() if isinstance(as_of, date) else as_of

    rows = conn.execute(
        """SELECT a.code, a.name, a.type, g.name AS group_name,
                  COALESCE(SUM(l.amount_minor), 0) AS balance
             FROM accounts a
             LEFT JOIN groups g     ON g.id = a.group_id
             JOIN journal_lines l   ON l.account_id = a.id
             JOIN journal_entries e ON e.id = l.entry_id
            WHERE e.posted_at IS NOT NULL
              AND e.entry_date <= ?
            GROUP BY a.id, a.code, a.name, a.type, g.name
           HAVING SUM(l.amount_minor) <> 0
            ORDER BY a.code""",
        (as_of_iso,),
    ).fetchall()

    # Each entry pairs the line with its account's group name (ADR 0014) -- see
    # group_lines() and pnl.py's identical pattern.
    assets: list[tuple[dict[str, object], str | None]] = []
    liabilities: list[tuple[dict[str, object], str | None]] = []
    equity: list[tuple[dict[str, object], str | None]] = []
    earnings_minor = 0

    for row in rows:
        if row["type"] == "asset":
            # Assets are debit-normal: positive internally is already positive here.
            assets.append((_line(row["code"], row["name"], row["balance"]), row["group_name"]))
        elif row["type"] == "liability":
            liabilities.append(
                (_line(row["code"], row["name"], -row["balance"]), row["group_name"])
            )
        elif row["type"] == "equity":
            equity.append((_line(row["code"], row["name"], -row["balance"]), row["group_name"]))
        else:
            # Revenue and expense roll up into a single equity line.
            earnings_minor -= row["balance"]

    asset_lines = [line for line, _ in assets]
    liability_lines = [line for line, _ in liabilities]

    total_assets = sum(int(item["amount_minor"]) for item in asset_lines)
    total_liabilities = sum(int(item["amount_minor"]) for item in liability_lines)

    equity_entries = list(equity)
    if earnings_minor != 0:
        # Not tied to any account, so it can't have a group -- group_lines() files it
        # under "Other" alongside any genuinely ungrouped equity account, same as an
        # account with no group_id.
        equity_entries.append((_line("", "Current Period Earnings", earnings_minor), None))

    equity_lines = [line for line, _ in equity_entries]
    total_equity = sum(int(item["amount_minor"]) for item in equity_lines)

    return {
        "report": "Net Worth",
        "basis": "accrual",
        "as_of": as_of_iso,
        "assets": {
            "lines": asset_lines,
            "groups": group_lines(assets),
            "total_minor": total_assets,
            "total": money.format(total_assets),
        },
        "liabilities": {
            "lines": liability_lines,
            "groups": group_lines(liabilities),
            "total_minor": total_liabilities,
            "total": money.format(total_liabilities),
        },
        "equity": {
            "lines": equity_lines,
            "groups": group_lines(equity_entries),
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
