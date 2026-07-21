"""Shared helper for report-line subtotals by group (ADR 0014).

Both the Income & Expenses and Net Worth reports show account balances organized by
type (revenue/expense, assets/liabilities/equity); this adds the next layer down,
subtotaling within each type by the account's group -- "Food & Dining: $412" above the
individual Groceries and Dining & Takeout lines.
"""

from __future__ import annotations

from slowbooks import money


def group_lines(lines_with_group: list[tuple[dict, str | None]]) -> list[dict]:
    """Bucket already-computed report lines by their account's group, each with its own
    subtotal.

    Named groups come first, in the order their first line was encountered (which is
    account-code order, since callers build `lines_with_group` from a query already
    sorted that way). Ungrouped lines -- an account with no group, or a synthetic line
    like Balance Sheet's "Current Period Earnings" that isn't tied to any account --
    land in one final bucket under `name: None`, shown as "Other" in the UI rather than
    as an error, the same way AccountsPanel treats an ungrouped account.
    """
    named: dict[str, list[dict]] = {}
    named_order: list[str] = []
    ungrouped: list[dict] = []

    for line, group_name in lines_with_group:
        if group_name is None:
            ungrouped.append(line)
            continue
        if group_name not in named:
            named[group_name] = []
            named_order.append(group_name)
        named[group_name].append(line)

    result = [_subtotal(name, named[name]) for name in named_order]
    if ungrouped:
        result.append(_subtotal(None, ungrouped))
    return result


def _subtotal(name: str | None, lines: list[dict]) -> dict:
    total = sum(int(line["amount_minor"]) for line in lines)
    return {"name": name, "lines": lines, "total_minor": total, "total": money.format(total)}
