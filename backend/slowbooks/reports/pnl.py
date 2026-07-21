"""Profit & Loss (Income Statement).

Income - Expenses over a period. The report you actually read.

Derived live from journal_lines, never stored, so it cannot disagree with the ledger.
See docs/engineering/architecture.md.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slowbooks import money
from slowbooks.reports.grouping import group_lines


def profit_and_loss(
    conn: sqlite3.Connection,
    start: date | str,
    end: date | str,
) -> dict[str, object]:
    """P&L for [start, end] inclusive.

    Sign convention: revenue accounts carry credit balances, which are negative in our
    signed representation. We flip them at the boundary so the report reads the way a
    human expects -- revenue positive, expenses positive, net = revenue - expenses.
    """
    start_iso = start.isoformat() if isinstance(start, date) else start
    end_iso = end.isoformat() if isinstance(end, date) else end

    rows = conn.execute(
        """SELECT a.code, a.name, a.type, g.name AS group_name,
                  COALESCE(SUM(l.amount_minor), 0) AS balance
             FROM accounts a
             LEFT JOIN groups g     ON g.id = a.group_id
             JOIN journal_lines l   ON l.account_id = a.id
             JOIN journal_entries e ON e.id = l.entry_id
            WHERE a.type IN ('revenue', 'expense')
              AND e.posted_at IS NOT NULL
              AND e.entry_date BETWEEN ? AND ?
            GROUP BY a.id, a.code, a.name, a.type, g.name
           HAVING SUM(l.amount_minor) <> 0
            ORDER BY a.code""",
        (start_iso, end_iso),
    ).fetchall()

    # No cost-of-goods-sold section: that split exists in business accounting to make
    # gross profit mean something for a business reselling goods. A household has no
    # goods it resells, so every expense account is just an expense.
    #
    # Each entry pairs the line with its account's group name (ADR 0014), so callers get
    # both a flat list (unchanged shape) and a group-subtotaled breakdown from the same
    # data -- see group_lines().
    revenue: list[tuple[dict[str, object], str | None]] = []
    expenses: list[tuple[dict[str, object], str | None]] = []

    for row in rows:
        group_name = row["group_name"]
        if row["type"] == "revenue":
            # Credit balance is negative internally; revenue reads positive.
            revenue.append((_line(row["code"], row["name"], -row["balance"]), group_name))
        else:
            expenses.append((_line(row["code"], row["name"], row["balance"]), group_name))

    revenue_lines = [line for line, _ in revenue]
    expense_lines = [line for line, _ in expenses]

    total_revenue = sum(int(item["amount_minor"]) for item in revenue_lines)
    total_expenses = sum(int(item["amount_minor"]) for item in expense_lines)

    net_income = total_revenue - total_expenses

    return {
        "report": "Income & Expenses",
        "basis": "accrual",
        "period": {"start": start_iso, "end": end_iso},
        "revenue": {
            "lines": revenue_lines,
            "groups": group_lines(revenue),
            "total_minor": total_revenue,
            "total": money.format(total_revenue),
        },
        "operating_expenses": {
            "lines": expense_lines,
            "groups": group_lines(expenses),
            "total_minor": total_expenses,
            "total": money.format(total_expenses),
        },
        "net_income_minor": net_income,
        "net_income": money.format(net_income),
    }


def _line(code: str, name: str, amount_minor: int) -> dict[str, object]:
    return {
        "code": code,
        "name": name,
        "amount_minor": amount_minor,
        "amount": money.format(amount_minor),
    }
