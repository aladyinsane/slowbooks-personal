"""Trial Balance.

Every account with its debit or credit balance, and proof the two columns agree.

The owner will never open this. The accountant opens it first -- and per
docs/research/quickbooks-pain-points.md, the accountant is the gatekeeper on whether
this product is usable at all. Cheap to build once the ledger exists.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slowbooks import money


def trial_balance(conn: sqlite3.Connection, as_of: date | str) -> dict[str, object]:
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

    lines = []
    total_debits = 0
    total_credits = 0

    for row in rows:
        balance = row["balance"]
        debit = balance if balance > 0 else 0
        credit = -balance if balance < 0 else 0
        total_debits += debit
        total_credits += credit
        lines.append(
            {
                "code": row["code"],
                "name": row["name"],
                "type": row["type"],
                "debit_minor": debit,
                "credit_minor": credit,
                "debit": money.format(debit) if debit else "",
                "credit": money.format(credit) if credit else "",
            }
        )

    return {
        "report": "Trial Balance",
        "as_of": as_of_iso,
        "lines": lines,
        "total_debits_minor": total_debits,
        "total_credits_minor": total_credits,
        "total_debits": money.format(total_debits),
        "total_credits": money.format(total_credits),
        "balanced": total_debits == total_credits,
    }
