"""Profit & Loss (Income Statement).

Revenue - COGS - Expenses over a period. The report the owner actually reads.

Derived live from journal_lines, never stored, so it cannot disagree with the ledger.
See docs/engineering/architecture.md.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slowbooks import money


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
        """SELECT a.code, a.name, a.type, COALESCE(SUM(l.amount_minor), 0) AS balance
             FROM accounts a
             JOIN journal_lines l   ON l.account_id = a.id
             JOIN journal_entries e ON e.id = l.entry_id
            WHERE a.type IN ('revenue', 'expense')
              AND e.posted_at IS NOT NULL
              AND e.entry_date BETWEEN ? AND ?
            GROUP BY a.id, a.code, a.name, a.type
           HAVING SUM(l.amount_minor) <> 0
            ORDER BY a.code""",
        (start_iso, end_iso),
    ).fetchall()

    revenue: list[dict[str, object]] = []
    cogs: list[dict[str, object]] = []
    expenses: list[dict[str, object]] = []

    for row in rows:
        if row["type"] == "revenue":
            # Credit balance is negative internally; revenue reads positive.
            revenue.append(_line(row["code"], row["name"], -row["balance"]))
        elif row["code"].startswith("5"):
            cogs.append(_line(row["code"], row["name"], row["balance"]))
        else:
            expenses.append(_line(row["code"], row["name"], row["balance"]))

    total_revenue = sum(int(item["amount_minor"]) for item in revenue)
    total_cogs = sum(int(item["amount_minor"]) for item in cogs)
    total_expenses = sum(int(item["amount_minor"]) for item in expenses)

    gross_profit = total_revenue - total_cogs
    net_income = gross_profit - total_expenses

    return {
        "report": "Profit and Loss",
        "basis": "accrual",
        "period": {"start": start_iso, "end": end_iso},
        "revenue": {
            "lines": revenue,
            "total_minor": total_revenue,
            "total": money.format(total_revenue),
        },
        "cost_of_goods_sold": {
            "lines": cogs,
            "total_minor": total_cogs,
            "total": money.format(total_cogs),
        },
        "gross_profit_minor": gross_profit,
        "gross_profit": money.format(gross_profit),
        "operating_expenses": {
            "lines": expenses,
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
