"""Chart of accounts.

Numbering follows the convention accountants already expect (see
docs/research/gaap-notes.md), so the codes sort correctly and a CPA recognizes the
shape on sight.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

ASSET = "asset"
LIABILITY = "liability"
EQUITY = "equity"
REVENUE = "revenue"
EXPENSE = "expense"

DEBIT = "debit"
CREDIT = "credit"

# Which way each account type naturally leans. This table *is* the debit/credit rule
# from gaap-notes.md, encoded once so no other module has to remember it.
NORMAL_BALANCE = {
    ASSET: DEBIT,
    EXPENSE: DEBIT,
    LIABILITY: CREDIT,
    EQUITY: CREDIT,
    REVENUE: CREDIT,
}

# Account ranges by type, per the standard convention. Used to *validate* a code.
TYPE_RANGES = {
    ASSET: (1000, 1999),
    LIABILITY: (2000, 2999),
    EQUITY: (3000, 3999),
    REVENUE: (4000, 4999),
    EXPENSE: (5000, 6999),  # 5000s COGS, 6000s operating expenses
}

# Where a *new* account of each type should be numbered, which is not the same question.
#
# "expense" spans 5000-6999, but the P&L treats those halves differently: 5000s are cost
# of goods sold and sit above gross profit; 6000s are operating expenses and sit below
# it. Auto-numbering into the lowest free slot put a new "Studio rent" at 5010 -- i.e.
# into COGS -- which understates gross profit on every report thereafter.
#
# So new expenses default to the 6000s. Operating expense is overwhelmingly the common
# case, and COGS is a deliberate choice a user can still make by naming a 5xxx code
# explicitly. The type alone cannot tell us which they meant; the safer default can.
NEW_ACCOUNT_RANGES = {
    ASSET: (1000, 1999),
    LIABILITY: (2000, 2999),
    EQUITY: (3000, 3999),
    REVENUE: (4000, 4999),
    EXPENSE: (6000, 6999),
}


@dataclass(frozen=True)
class Account:
    id: int
    code: str
    name: str
    type: str
    normal_balance: str
    # True for accounts you can import a statement for and transfer between (ADR 0007).
    is_statement_account: bool = False
    # One plain sentence shown where the user picks a category. Stored per-account rather
    # than in a lookup table so a category the *user* invents can carry their own note.
    description: str | None = None


# The accounts money actually moves *through*, as opposed to the categories it moves
# *to*. Note this is not "all assets and liabilities": Accounts Receivable and Equipment
# are assets you cannot transfer to, and offering them as transfer targets would be
# offering nonsense. A loan is here because paying it down is a real transfer of money.
STATEMENT_ACCOUNT_CODES = frozenset({
    "1000",  # Business Checking
    "1010",  # Business Savings
    "2100",  # Credit Card Payable
    "2500",  # Loans Payable
})


# A default chart that is good enough to ignore on day one. A new user should never
# face an empty screen, but every line here is editable -- research is explicit that a
# flexible chart is what lets the software keep up with a growing business.
#
# The fourth field is guidance: one plain sentence, shown at the moment of choosing.
# Principle 2 says rigor underneath, plain language on top, and this is where that gets
# tested -- "what does a credit card payment go to?" is a fair question with a
# non-obvious answer, and a chart of accounts that only makes sense to an accountant has
# failed the person it is for.
#
# Written by a developer. Section 5 of docs/review/cpa-review-request.md asks a CPA to
# correct these, because being confidently wrong here is worse than saying nothing.
DEFAULT_CHART: list[tuple[str, str, str, str]] = [
    # Assets
    ("1000", "Business Checking", ASSET,
     "Your main account. Money in and out of the business day to day."),
    ("1010", "Business Savings", ASSET,
     "Money set aside. Moving money here isn't spending it — it's still yours."),
    ("1100", "Accounts Receivable", ASSET,
     "Work you've invoiced but haven't been paid for yet."),
    ("1200", "Undeposited Funds", ASSET,
     "Payments you've received but haven't banked yet, like cheques in a drawer."),
    ("1500", "Equipment", ASSET,
     "Things you bought to keep and use, not to resell — a laptop, a van, a machine. "
     "Big purchases go here rather than to an expense."),
    ("1510", "Accumulated Depreciation", ASSET,
     "How much value your equipment has lost over time. Your accountant usually sets this."),
    # Liabilities
    ("2000", "Accounts Payable", LIABILITY,
     "Bills you've received but haven't paid yet."),
    ("2100", "Credit Card Payable", LIABILITY,
     "What you owe on the card. Paying the card is NOT an expense — the purchases were "
     "already counted when you charged them. Choose this to record a payment."),
    ("2200", "Sales Tax Payable", LIABILITY,
     "Sales tax you've collected and owe to the state. It was never your money."),
    ("2500", "Loans Payable", LIABILITY,
     "What you still owe on a loan. A loan payment is part this and part Interest "
     "Expense — only the interest part is an expense."),
    # Equity
    ("3000", "Owner's Capital", EQUITY,
     "Your own money put into the business. It's not income — you didn't earn it, you "
     "invested it."),
    ("3100", "Owner's Draw", EQUITY,
     "Money you take out for yourself. NOT an expense and not wages — it's you taking "
     "back part of your stake, so it never touches your profit."),
    ("3900", "Retained Earnings", EQUITY,
     "Profit from previous years that stayed in the business. Usually your accountant's "
     "territory."),
    # Revenue
    ("4000", "Sales Revenue", REVENUE,
     "Money earned selling goods."),
    ("4100", "Service Revenue", REVENUE,
     "Money earned doing work for clients."),
    ("4900", "Other Income", REVENUE,
     "Money earned that isn't your main line of work — interest, a rebate, a one-off."),
    # Cost of goods sold
    ("5000", "Cost of Goods Sold", EXPENSE,
     "What the thing you sold actually cost you. Only for costs tied to a specific sale."),
    ("5100", "Materials & Supplies", EXPENSE,
     "Raw materials and parts that go into what you sell."),
    ("5200", "Subcontractors", EXPENSE,
     "People you paid to do work you were hired for."),
    # Operating expenses
    ("6000", "Advertising & Marketing", EXPENSE,
     "Ads, website, printing, anything to get customers."),
    ("6050", "Bank & Merchant Fees", EXPENSE,
     "Bank charges and card processing fees — Stripe, Square, monthly account fees."),
    ("6100", "Office Supplies", EXPENSE,
     "Small things you use up: paper, pens, coffee, printer ink, stationery."),
    ("6150", "Software & Subscriptions", EXPENSE,
     "Anything you pay for monthly or yearly to run the business."),
    ("6200", "Rent & Lease", EXPENSE,
     "Rent for your premises or leased equipment."),
    ("6250", "Utilities", EXPENSE,
     "Power, water, gas for your business premises."),
    ("6300", "Insurance", EXPENSE,
     "Business insurance premiums."),
    ("6350", "Professional Fees", EXPENSE,
     "Your accountant, lawyer, consultants."),
    ("6400", "Travel", EXPENSE,
     "Flights, hotels, taxis and trains for business trips."),
    ("6450", "Meals & Entertainment", EXPENSE,
     "Meals with a business purpose. Keep a note of who and why — the IRS asks."),
    ("6500", "Vehicle & Fuel", EXPENSE,
     "Gas, repairs and running costs for a business car, van or truck."),
    ("6550", "Repairs & Maintenance", EXPENSE,
     "Fixing things you already own. If it's an upgrade that lasts years, it's Equipment."),
    ("6600", "Shipping & Postage", EXPENSE,
     "Postage and delivery — USPS, FedEx, couriers."),
    ("6650", "Telephone & Internet", EXPENSE,
     "Phone and internet for the business."),
    ("6700", "Interest Expense", EXPENSE,
     "The interest part of a loan or card payment. This part IS an expense; the "
     "principal isn't."),
    ("6750", "Taxes & Licenses", EXPENSE,
     "Business licences, permits, and taxes that aren't income tax."),
    ("6900", "Uncategorized Expense", EXPENSE,
     "A holding pen for things you haven't sorted yet. Try to keep this empty — anything "
     "left here is a number you can't explain."),
]

# Where a transaction lands when no rule matches. Deliberately a real account rather
# than NULL: the books stay balanced and complete, and the P&L shows an honest
# "Uncategorized" line the owner is motivated to clear. Hiding unknowns outside the
# ledger would be the dishonest option.
UNCATEGORIZED_EXPENSE_CODE = "6900"
UNCATEGORIZED_REVENUE_CODE = "4900"


_SELECT = (
    "SELECT id, code, name, type, normal_balance, is_statement_account, description "
    "FROM accounts"
)


def _to_account(row: sqlite3.Row) -> Account:
    data = dict(row)
    data["is_statement_account"] = bool(data["is_statement_account"])
    return Account(**data)


def seed_default_chart(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT INTO accounts (code, name, type, normal_balance, description,
                                 is_statement_account)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (code, name, type_, NORMAL_BALANCE[type_], guidance,
             int(code in STATEMENT_ACCOUNT_CODES))
            for code, name, type_, guidance in DEFAULT_CHART
        ],
    )


def by_code(conn: sqlite3.Connection, code: str) -> Account:
    row = conn.execute(f"{_SELECT} WHERE code = ?", (code,)).fetchone()
    if row is None:
        raise KeyError(f"no account with code {code!r}")
    return _to_account(row)


def list_all(conn: sqlite3.Connection, *, active_only: bool = True) -> list[Account]:
    sql = _SELECT
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY code"
    return [_to_account(row) for row in conn.execute(sql)]


def list_statement_accounts(conn: sqlite3.Connection) -> list[Account]:
    """Accounts you can import a statement for, and transfer between (ADR 0007)."""
    return [
        _to_account(row)
        for row in conn.execute(
            f"{_SELECT} WHERE is_statement_account = 1 AND is_active = 1 ORDER BY code"
        )
    ]


def is_statement_account(conn: sqlite3.Connection, account_id: int) -> bool:
    row = conn.execute(
        "SELECT is_statement_account FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    return bool(row and row["is_statement_account"])


def create(
    conn: sqlite3.Connection,
    code: str,
    name: str,
    type_: str,
    description: str | None = None,
    *,
    is_statement_account: bool = False,
) -> Account:
    if type_ not in NORMAL_BALANCE:
        raise ValueError(f"unknown account type {type_!r}")

    low, high = TYPE_RANGES[type_]
    if not code.isdigit() or not (low <= int(code) <= high):
        raise ValueError(
            f"account code {code!r} is outside the {low}-{high} range for {type_} accounts"
        )
    if is_statement_account and type_ not in (ASSET, LIABILITY):
        # You cannot hold money in an expense account. Catching this here keeps a
        # nonsensical transfer target out of the UI rather than out of a bug report.
        raise ValueError("only asset or liability accounts can be statement accounts")

    cursor = conn.execute(
        """INSERT INTO accounts (code, name, type, normal_balance, description,
                                 is_statement_account)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (code, name, type_, NORMAL_BALANCE[type_], description, int(is_statement_account)),
    )
    return Account(
        id=cursor.lastrowid, code=code, name=name, type=type_,
        normal_balance=NORMAL_BALANCE[type_], is_statement_account=is_statement_account,
        description=description,
    )


class AccountInUseError(Exception):
    """This account has history, so it cannot be removed. See ADR 0010."""


def by_id(conn: sqlite3.Connection, account_id: int) -> Account:
    row = conn.execute(f"{_SELECT} WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise KeyError(f"no account with id {account_id}")
    return _to_account(row)


def usage(conn: sqlite3.Connection, account_id: int) -> dict[str, int]:
    """Everything that references this account.

    Drives both the refusal to delete and the explanation for it: "used by 14 posted
    transactions" is an answer, "you can't do that" is a wall.
    """
    return {
        "posted_lines": conn.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE account_id = ?", (account_id,)
        ).fetchone()["n"],
        "staged_transactions": conn.execute(
            """SELECT COUNT(*) AS n FROM staged_transactions
                WHERE account_id = ? OR suggested_account_id = ?""",
            (account_id, account_id),
        ).fetchone()["n"],
        "rules": conn.execute(
            "SELECT COUNT(*) AS n FROM rules WHERE account_id = ?", (account_id,)
        ).fetchone()["n"],
        "reconciliations": conn.execute(
            "SELECT COUNT(*) AS n FROM reconciliations WHERE account_id = ?", (account_id,)
        ).fetchone()["n"],
    }


def update(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> Account:
    """Rename, re-word, hide or unhide an account (ADR 0010).

    Deliberately cannot change `code` or `type`. A name is a label and changing it is
    safe -- every journal line references the id, so history is untouched. A *type*
    change is not cosmetic at all: flipping 6100 from expense to asset silently moves
    every historical transaction from the P&L to the Balance Sheet, retroactively,
    with nothing to warn anyone.
    """
    account = by_id(conn, account_id)  # raises if it doesn't exist

    if name is not None and not name.strip():
        raise ValueError("an account needs a name")

    if is_active is False and account.is_statement_account:
        # Hiding the account a statement imports into would strand the import screen.
        raise ValueError(
            f"{account.name} is an account you import statements into, so it can't be "
            f"hidden. Rename it if it's not what you thought."
        )

    fields: list[str] = []
    values: list[object] = []
    if name is not None:
        fields.append("name = ?")
        values.append(name.strip())
    if description is not None:
        fields.append("description = ?")
        values.append(description.strip() or None)
    if is_active is not None:
        fields.append("is_active = ?")
        values.append(int(is_active))

    if fields:
        values.append(account_id)
        conn.execute(f"UPDATE accounts SET {', '.join(fields)} WHERE id = ?", values)

    return by_id(conn, account_id)


def delete(conn: sqlite3.Connection, account_id: int) -> None:
    """Remove an account that has never been used.

    Refused the moment anything references it. ADR 0010: "hide" is the honest verb for
    what people usually mean, but an account with no history has nothing to protect, so
    deleting it is real rather than a euphemism.
    """
    account = by_id(conn, account_id)
    counts = usage(conn, account_id)

    if any(counts.values()):
        labels = {
            "posted_lines": ("posted transaction", "posted transactions"),
            "staged_transactions": ("imported transaction", "imported transactions"),
            "rules": ("categorization rule", "categorization rules"),
            "reconciliations": ("reconciliation", "reconciliations"),
        }
        used_for = ", ".join(
            f"{n} {labels[key][0] if n == 1 else labels[key][1]}"
            for key, n in counts.items()
            if n
        )
        raise AccountInUseError(
            f"{account.code} {account.name} is used by {used_for}. Deleting it would "
            f"leave a hole in your books — hide it instead and it will stop appearing "
            f"in the list."
        )

    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


def next_code(conn: sqlite3.Connection, type_: str) -> str:
    """A free code in the right range, so the user never has to pick a number.

    The range is what makes the type safe (ADR 0010), which means the number is our
    problem, not theirs. Someone adding "Studio rent" should not have to learn that
    expenses live in the 6000s.
    """
    if type_ not in NEW_ACCOUNT_RANGES:
        raise ValueError(f"unknown account type {type_!r}")
    # Not TYPE_RANGES: a new expense belongs in operating expenses, not COGS. See the
    # comment on NEW_ACCOUNT_RANGES -- getting this wrong misfiles it above gross profit.
    low, high = NEW_ACCOUNT_RANGES[type_]

    taken = {
        int(row["code"])
        # Four-digit codes only: int() on a non-numeric code would blow up here, and a
        # user-invented code is not guaranteed to look like ours.
        for row in conn.execute(
            "SELECT code FROM accounts WHERE code GLOB '[0-9][0-9][0-9][0-9]'"
        )
        if low <= int(row["code"]) <= high
    }
    # Step by 10 so there's room to insert related accounts later, the way the default
    # chart does. Fall back to every integer once the tens are exhausted.
    for candidate in range(low, high + 1, 10):
        if candidate not in taken:
            return str(candidate)
    for candidate in range(low, high + 1):
        if candidate not in taken:
            return str(candidate)
    raise ValueError(f"no free account codes left in the {low}-{high} range")
