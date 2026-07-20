"""Groups: how the chart of accounts is organized for display.

A group sits between an account's type (asset/liability/equity/revenue/expense) and the
account itself -- "Food & Dining" containing Groceries and Dining & Takeout. Modeled as a
first-class table rather than a hardcoded map for the same reason the chart of accounts
itself is editable (ADR 0010): a user should be able to rename or reorganize groups, not
be stuck with ours. See ADR 0014.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from slowbooks.accounts import ASSET, EQUITY, EXPENSE, LIABILITY, REVENUE

# (name, type). Mirrors accounts.py's DEFAULT_CHART -- a good-enough-to-ignore default
# that's fully editable afterward. See accounts.py's DEFAULT_CHART for which account
# goes in which group.
DEFAULT_GROUPS: list[tuple[str, str]] = [
    ("Cash & Investments", ASSET),
    ("Other Assets", ASSET),
    ("Credit & Loans", LIABILITY),
    ("Net Worth", EQUITY),
    ("Income", REVENUE),
    ("Housing", EXPENSE),
    ("Food & Dining", EXPENSE),
    ("Transportation", EXPENSE),
    ("Insurance & Healthcare", EXPENSE),
    ("Personal & Lifestyle", EXPENSE),
    ("Travel & Giving", EXPENSE),
    ("Bills & Fees", EXPENSE),
    ("Uncategorized", EXPENSE),
]


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    type: str


_SELECT = "SELECT id, name, type FROM groups"


def _to_group(row: sqlite3.Row) -> Group:
    return Group(**dict(row))


def seed_default_groups(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO groups (name, type) VALUES (?, ?)",
        DEFAULT_GROUPS,
    )


def by_id(conn: sqlite3.Connection, group_id: int) -> Group:
    row = conn.execute(f"{_SELECT} WHERE id = ?", (group_id,)).fetchone()
    if row is None:
        raise KeyError(f"no group with id {group_id}")
    return _to_group(row)


def list_all(conn: sqlite3.Connection, *, type_: str | None = None) -> list[Group]:
    sql = _SELECT
    params: tuple[object, ...] = ()
    if type_ is not None:
        sql += " WHERE type = ?"
        params = (type_,)
    sql += " ORDER BY name"
    return [_to_group(row) for row in conn.execute(sql, params)]


def create(conn: sqlite3.Connection, name: str, type_: str) -> Group:
    if not name.strip():
        raise ValueError("a group needs a name")
    if type_ not in (ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE):
        raise ValueError(f"unknown group type {type_!r}")

    cursor = conn.execute(
        "INSERT INTO groups (name, type) VALUES (?, ?)", (name.strip(), type_)
    )
    return Group(id=cursor.lastrowid, name=name.strip(), type=type_)


class GroupInUseError(Exception):
    """This group has accounts filed under it, so it cannot be removed."""


def usage(conn: sqlite3.Connection, group_id: int) -> int:
    """How many accounts currently belong to this group."""
    return conn.execute(
        "SELECT COUNT(*) AS n FROM accounts WHERE group_id = ?", (group_id,)
    ).fetchone()["n"]


def update(conn: sqlite3.Connection, group_id: int, *, name: str) -> Group:
    """Rename a group.

    Deliberately no `type` parameter: changing a group's type would either strand its
    member accounts (which keep their own, now-mismatched type) or require silently
    reassigning every one of them -- the same reasoning ADR 0010 uses to refuse changing
    an account's type. Move accounts to a different group individually instead.
    """
    by_id(conn, group_id)  # raises if it doesn't exist

    if not name.strip():
        raise ValueError("a group needs a name")

    conn.execute("UPDATE groups SET name = ? WHERE id = ?", (name.strip(), group_id))
    return by_id(conn, group_id)


def delete(conn: sqlite3.Connection, group_id: int) -> None:
    """Remove a group that has no accounts filed under it.

    Refused the moment any account references it -- deleting out from under an assigned
    account would silently orphan it. Move those accounts to another group first.
    """
    group = by_id(conn, group_id)
    count = usage(conn, group_id)

    if count:
        raise GroupInUseError(
            f"{group.name!r} has {count} account{'s' if count != 1 else ''} filed under "
            f"it. Move them to another group first."
        )

    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
