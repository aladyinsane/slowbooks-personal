"""The register: transactions, in date order, with a running balance.

The shape of a bank statement, because that is the document our user has been reading
their whole life. See ADR 0012.

Two modes, and the difference is not cosmetic:

  - **One account.** A statement: it carries a running balance, because "what did this
    account hold after each transaction" is a question with an answer.
  - **All accounts.** A list: no running balance, because summing checking and a credit
    card and an expense in one column produces a figure that means nothing. Same rule as
    a filtered view -- a running balance over an arbitrary set looks authoritative and
    isn't.

Not a journal (every entry, both sides, debits and credits) -- that vocabulary is exactly
what ADR 0004 keeps off-screen. Not a general ledger either; the export already serves
that to the audience that wants it (ADR 0008).
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slowbooks import money
from slowbooks.money import Minor

# A page. Big enough that most months fit in one, small enough that an account with
# years of history doesn't hand the browser 50k rows -- the cost ADR 0012 accepted and
# said we'd revisit. All-accounts made the row count unbounded, so the revisit is now.
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _filters(
    account_id: int | None, start: str | None, end: str | None, query: str | None
) -> tuple[str, list[object]]:
    """The WHERE shared by the count, the page, and the running-balance offset sum.

    Built once because the three must agree exactly: a count that filters differently
    from the page would paginate over a set the user never sees.
    """
    sql = " WHERE e.posted_at IS NOT NULL"
    params: list[object] = []

    if account_id is not None:
        sql += " AND l.account_id = ?"
        params.append(account_id)
    if start:
        sql += " AND e.entry_date >= ?"
        params.append(start)
    if end:
        sql += " AND e.entry_date <= ?"
        params.append(end)
    if query:
        sql += " AND (e.description LIKE ? OR l.memo LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like])

    return sql, params


def _opening_balance(
    conn: sqlite3.Connection, account_id: int, start: str | None
) -> Minor:
    """What the account held before the window opens.

    Without this the running balance would start at zero mid-year and every figure on
    the page would be wrong -- plausibly wrong, which is the dangerous kind.
    """
    if start is None:
        return 0
    row = conn.execute(
        """SELECT COALESCE(SUM(l.amount_minor), 0) AS balance
             FROM journal_lines l
             JOIN journal_entries e ON e.id = l.entry_id
            WHERE l.account_id = ? AND e.posted_at IS NOT NULL
              AND e.entry_date < ?""",
        (account_id, start),
    ).fetchone()
    return row["balance"]


def _balance_before_page(
    conn: sqlite3.Connection, where: str, params: list[object], offset: int
) -> Minor:
    """Sum of the rows this page skipped.

    Page 2 of a register cannot start its running balance over. Summing the first
    `offset` rows in the *same* order gives the balance the page opens at -- so page 2
    continues where page 1 stopped, which is the only way a paginated running balance
    is worth showing at all.
    """
    if offset == 0:
        return 0
    row = conn.execute(
        f"""SELECT COALESCE(SUM(amount_minor), 0) AS balance FROM (
                SELECT l.amount_minor
                  FROM journal_lines l
                  JOIN journal_entries e ON e.id = l.entry_id
                  {where}
                 ORDER BY e.entry_date, e.id, l.id
                 LIMIT ?
            )""",  # noqa: S608 - `where` is built from fixed fragments, values bound
        [*params, offset],
    ).fetchone()
    return row["balance"]


def register(
    conn: sqlite3.Connection,
    account_id: int | None = None,
    *,
    start: date | str | None = None,
    end: date | str | None = None,
    query: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, object]:
    """Transactions with a running balance, one page at a time.

    `account_id=None` lists every account, which is a list rather than a statement --
    see the module docstring. `query` filters description and memo (substring, not
    full-text; ADR 0012).
    """
    from slowbooks import accounts

    account = accounts.by_id(conn, account_id) if account_id is not None else None
    start_iso = start.isoformat() if isinstance(start, date) else start
    end_iso = end.isoformat() if isinstance(end, date) else end

    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)

    where, params = _filters(account_id, start_iso, end_iso, query)

    # Both totals are over the *whole* filtered set, not the page.
    #
    # The money one is the drill-down contract: the user clicked $404.19 on a report and
    # must find $404.19 here, even if it takes three pages to list. A footer showing only
    # the page's sum would answer a question nobody asked and quietly contradict the
    # number they clicked (principle 8).
    totals = conn.execute(
        f"""SELECT COUNT(*) AS n, COALESCE(SUM(l.amount_minor), 0) AS amount
              FROM journal_lines l
              JOIN journal_entries e ON e.id = l.entry_id
              {where}""",  # noqa: S608
        params,
    ).fetchone()
    total_count = totals["n"]
    total_amount = totals["amount"]

    # A running balance needs one account (so the column means something) and no query
    # (a search result is not a statement).
    with_balance = account_id is not None and not query

    rows = conn.execute(
        f"""SELECT e.id AS entry_id, e.entry_date, e.description, e.source,
                   l.amount_minor, l.memo, l.reconciliation_id, e.reverses_entry_id,
                   a.code AS account_code, a.name AS account_name,
                   (SELECT GROUP_CONCAT(a2.code || ' ' || a2.name, ', ')
                      FROM journal_lines l2
                      JOIN accounts a2 ON a2.id = l2.account_id
                     WHERE l2.entry_id = e.id AND l2.account_id <> l.account_id
                   ) AS other_side
              FROM journal_lines l
              JOIN journal_entries e ON e.id = l.entry_id
              JOIN accounts a        ON a.id = l.account_id
              {where}
             ORDER BY e.entry_date, e.id, l.id
             LIMIT ? OFFSET ?""",  # noqa: S608
        [*params, limit, offset],
    ).fetchall()

    # l.id in the sort is not decoration: an entry has several lines, and without it two
    # lines of the same entry could swap between pages and the running balance would
    # wobble depending on where the page boundary fell.
    opening = 0
    running = 0
    if with_balance:
        opening = _opening_balance(conn, account_id, start_iso) + _balance_before_page(
            conn, where, params, offset
        )
        running = opening

    lines = []
    for row in rows:
        if with_balance:
            running += row["amount_minor"]
        lines.append({
            "entry_id": row["entry_id"],
            "date": row["entry_date"],
            "description": row["description"],
            "memo": row["memo"],
            "account": f'{row["account_code"]} {row["account_name"]}',
            "account_code": row["account_code"],
            "other_side": row["other_side"],
            "amount_minor": row["amount_minor"],
            "amount": money.format(row["amount_minor"]),
            "running_balance_minor": running if with_balance else None,
            "running_balance": money.format(running) if with_balance else None,
            "source": row["source"],
            "is_reversal": row["reverses_entry_id"] is not None,
            "reconciled": row["reconciliation_id"] is not None,
        })

    page_total = sum(int(line["amount_minor"]) for line in lines)

    return {
        "account": (
            {"id": account.id, "code": account.code, "name": account.name,
             "type": account.type}
            if account
            else None
        ),
        "start": start_iso,
        "end": end_iso,
        "query": query,
        "is_filtered": bool(query),
        "has_running_balance": with_balance,
        "opening_balance_minor": opening if with_balance else None,
        "opening_balance": money.format(opening) if with_balance else None,
        "closing_balance_minor": running if with_balance else None,
        "closing_balance": money.format(running) if with_balance else None,
        # The whole filtered set, across every page. This is the figure that has to match
        # the report line the user clicked.
        "total_minor": total_amount,
        "total": money.format(total_amount),
        "total_count": total_count,
        # Just this page. Named apart from `total` because confusing the two would be an
        # error nobody could see -- and because `total` already meant money in the first
        # version of this endpoint, so reusing it for a row count was asking for trouble.
        "page_total_minor": page_total,
        "page_total": money.format(page_total),
        "count": len(lines),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(lines) < total_count,
        "lines": lines,
    }
