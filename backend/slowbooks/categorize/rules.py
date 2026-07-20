"""Deterministic categorization rules.

Rules, not a model. Every suggestion carries a human-readable reason, the same
transaction categorizes the same way in March as it did in July, and nothing leaves the
machine. See docs/decisions/0005-deterministic-rules-categorization.md.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from slowbooks import accounts

# Lower number = higher priority. Ties break by id (oldest wins) so ordering is total
# and stable -- a rule's behavior must never depend on row order in the table.
DEFAULT_PRIORITY = 100
BUILTIN_PRIORITY = 500  # user rules outrank the starter pack by default


@dataclass(frozen=True)
class Match:
    account_id: int
    account_code: str
    account_name: str
    rule_id: int
    reason: str
    # True when this came from the shipped starter pack rather than something the user
    # taught us. ADR 0006: the user is entitled to know how much a guess is worth.
    is_starter_rule: bool


# The starter pack. ADR 0005 accepts that rules have a worse cold start than a model
# would; this is the mitigation. These are common enough to be safe and are ordinary
# editable rules, not privileged ones -- a user correction simply outranks them.
#
# Order matters where one pattern is a substring of another (e.g. "UBER EATS" contains
# "UBER"): ties break by insertion order, so the more specific pattern must come first.
#
# (pattern, account_code, applies_to)
STARTER_RULES: list[tuple[str, str, str]] = [
    # Income -- credits only. The same merchant string means opposite things by
    # direction, which is exactly why applies_to exists: interest paid *to* you is
    # income, interest charged *by* a lender is an expense.
    ("PAYROLL", "4000", "credit"),
    ("DIRECT DEP", "4000", "credit"),
    ("INTEREST PAID", "4200", "credit"),
    ("DIVIDEND", "4200", "credit"),
    ("TAX REFUND", "4900", "credit"),
    ("VENMO", "4900", "credit"),
    ("ZELLE", "4900", "credit"),
    ("CASH APP", "4900", "credit"),
    ("REFUND", "4900", "credit"),
    ("DEPOSIT", "4900", "credit"),
    # Bank & card fees
    ("OVERDRAFT", "6700", "debit"),
    ("ATM FEE", "6700", "debit"),
    ("MONTHLY FEE", "6700", "debit"),
    ("MAINTENANCE FEE", "6700", "debit"),
    ("SERVICE CHARGE", "6700", "debit"),
    # Subscriptions & memberships -- specific plans before their parent brand
    ("AMAZON PRIME", "6500", "debit"),
    ("NETFLIX", "6500", "debit"),
    ("SPOTIFY", "6500", "debit"),
    ("HULU", "6500", "debit"),
    ("DISNEY+", "6500", "debit"),
    ("DISNEY PLUS", "6500", "debit"),
    ("YOUTUBE PREMIUM", "6500", "debit"),
    ("APPLE.COM/BILL", "6500", "debit"),
    ("ICLOUD", "6500", "debit"),
    ("ADOBE", "6500", "debit"),
    ("MICROSOFT", "6500", "debit"),
    ("DROPBOX", "6500", "debit"),
    ("AUDIBLE", "6500", "debit"),
    ("PATREON", "6500", "debit"),
    # Groceries
    ("KROGER", "6100", "debit"),
    ("SAFEWAY", "6100", "debit"),
    ("WHOLE FOODS", "6100", "debit"),
    ("TRADER JOE", "6100", "debit"),
    ("ALDI", "6100", "debit"),
    ("PUBLIX", "6100", "debit"),
    ("COSTCO", "6100", "debit"),
    ("WEGMANS", "6100", "debit"),
    ("GIANT FOOD", "6100", "debit"),
    ("STOP & SHOP", "6100", "debit"),
    ("HARRIS TEETER", "6100", "debit"),
    # Dining & takeout -- delivery apps before "UBER" alone
    ("UBER EATS", "6150", "debit"),
    ("DOORDASH", "6150", "debit"),
    ("GRUBHUB", "6150", "debit"),
    ("STARBUCKS", "6150", "debit"),
    ("MCDONALD", "6150", "debit"),
    ("CHIPOTLE", "6150", "debit"),
    ("CHICK-FIL-A", "6150", "debit"),
    ("DUNKIN", "6150", "debit"),
    ("PANERA", "6150", "debit"),
    # Transportation & fuel
    ("UBER", "6200", "debit"),
    ("LYFT", "6200", "debit"),
    ("SHELL", "6200", "debit"),
    ("CHEVRON", "6200", "debit"),
    ("EXXON", "6200", "debit"),
    ("BP ", "6200", "debit"),
    ("TEXACO", "6200", "debit"),
    ("SUNOCO", "6200", "debit"),
    ("PARKING", "6200", "debit"),
    ("TOLL", "6200", "debit"),
    # Auto maintenance & repairs
    ("JIFFY LUBE", "6250", "debit"),
    ("AUTOZONE", "6250", "debit"),
    ("MIDAS", "6250", "debit"),
    ("FIRESTONE", "6250", "debit"),
    # Insurance
    ("GEICO", "6300", "debit"),
    ("STATE FARM", "6300", "debit"),
    ("PROGRESSIVE", "6300", "debit"),
    ("ALLSTATE", "6300", "debit"),
    ("INSURANCE", "6300", "debit"),
    # Healthcare & medical
    ("CVS", "6350", "debit"),
    ("WALGREENS", "6350", "debit"),
    ("RITE AID", "6350", "debit"),
    # Personal care & fitness
    ("PLANET FITNESS", "6400", "debit"),
    ("LA FITNESS", "6400", "debit"),
    ("PELOTON", "6400", "debit"),
    # Entertainment
    ("AMC THEATRE", "6450", "debit"),
    ("STEAM GAMES", "6450", "debit"),
    ("PLAYSTATION", "6450", "debit"),
    ("XBOX", "6450", "debit"),
    ("TICKETMASTER", "6450", "debit"),
    # Shopping -- generic "AMAZON" after the specific subscription patterns above
    ("AMAZON", "6550", "debit"),
    ("TARGET", "6550", "debit"),
    ("WALMART", "6550", "debit"),
    ("BEST BUY", "6550", "debit"),
    ("HOME DEPOT", "6550", "debit"),
    ("LOWES", "6550", "debit"),
    ("TJ MAXX", "6550", "debit"),
    ("MARSHALLS", "6550", "debit"),
    # Travel
    ("DELTA AIR", "6600", "debit"),
    ("UNITED AIRLINES", "6600", "debit"),
    ("AMERICAN AIR", "6600", "debit"),
    ("SOUTHWEST AIR", "6600", "debit"),
    ("MARRIOTT", "6600", "debit"),
    ("HILTON", "6600", "debit"),
    ("AIRBNB", "6600", "debit"),
    ("EXPEDIA", "6600", "debit"),
    # Phone & internet
    ("VERIZON", "6650", "debit"),
    ("AT&T", "6650", "debit"),
    ("T-MOBILE", "6650", "debit"),
    ("COMCAST", "6650", "debit"),
    ("SPECTRUM", "6650", "debit"),
    ("XFINITY", "6650", "debit"),
    # Interest expense
    ("INTEREST CHARGE", "6750", "debit"),
    ("INTEREST CHARGED", "6750", "debit"),
    # Gifts & donations -- also where a P2P app lands when *you* sent the money; the
    # same app credited means someone paid *you*, which is Other Income above.
    ("GOFUNDME", "6800", "debit"),
    ("DONATION", "6800", "debit"),
    ("RED CROSS", "6800", "debit"),
    ("VENMO", "6800", "debit"),
    ("ZELLE", "6800", "debit"),
    ("CASH APP", "6800", "debit"),
    # Taxes
    ("IRS", "6850", "debit"),
    ("PROPERTY TAX", "6850", "debit"),
    # Utilities -- checked after the more specific patterns above
    ("ELECTRIC", "6050", "debit"),
    ("GAS COMPANY", "6050", "debit"),
    ("WATER DEPT", "6050", "debit"),
    ("WASTE MANAGEMENT", "6050", "debit"),
    # Rent & mortgage
    ("MORTGAGE", "6000", "debit"),
    ("RENT", "6000", "debit"),
]


def seed_starter_rules(conn: sqlite3.Connection) -> None:
    code_to_id = {
        account.code: account.id for account in accounts.list_all(conn, active_only=False)
    }
    conn.executemany(
        """INSERT INTO rules (priority, match_type, pattern, account_id, applies_to,
                              is_builtin)
           VALUES (?, 'contains', ?, ?, ?, 1)""",
        [
            (BUILTIN_PRIORITY, pattern, code_to_id[code], applies_to)
            for pattern, code, applies_to in STARTER_RULES
            if code in code_to_id
        ],
    )


def create_rule(
    conn: sqlite3.Connection,
    pattern: str,
    account_id: int,
    *,
    match_type: str = "contains",
    applies_to: str = "any",
    priority: int = DEFAULT_PRIORITY,
) -> int:
    """Create a user rule. This is how the system 'learns'.

    Learning here means writing down something the user can read, edit, and delete --
    not adjusting an opaque weight. That is the whole point of ADR 0005.
    """
    if match_type not in ("contains", "regex", "exact"):
        raise ValueError(f"unknown match_type {match_type!r}")
    if applies_to not in ("any", "debit", "credit"):
        raise ValueError(f"unknown applies_to {applies_to!r}")
    if not pattern.strip():
        raise ValueError("rule pattern must not be empty")
    if match_type == "regex":
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc

    cursor = conn.execute(
        """INSERT INTO rules (priority, match_type, pattern, account_id, applies_to,
                              is_builtin)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (priority, match_type, pattern, account_id, applies_to),
    )
    return cursor.lastrowid


def match_transaction(
    conn: sqlite3.Connection, description: str, amount_minor: int
) -> Match | None:
    """Find the highest-priority rule matching this transaction, or None.

    Reads all rules and scans in Python rather than pushing the match into SQL. At a
    few hundred rules this is microseconds -- far inside the <100ms budget -- and it
    keeps regex semantics identical to what the rule editor previews.
    """
    direction = "debit" if amount_minor < 0 else "credit"
    haystack = description.upper()

    rows = conn.execute(
        """SELECT r.id, r.match_type, r.pattern, r.account_id, r.applies_to, r.is_builtin,
                  a.code AS account_code, a.name AS account_name
             FROM rules r
             JOIN accounts a ON a.id = r.account_id
            WHERE r.applies_to IN ('any', ?)
            ORDER BY r.priority ASC, r.id ASC""",
        (direction,),
    ).fetchall()

    for row in rows:
        if _matches(row["match_type"], row["pattern"], haystack):
            return Match(
                account_id=row["account_id"],
                account_code=row["account_code"],
                account_name=row["account_name"],
                rule_id=row["id"],
                reason=(
                    f'description {row["match_type"]} "{row["pattern"]}" '
                    f'→ {row["account_code"]} {row["account_name"]}'
                ),
                is_starter_rule=bool(row["is_builtin"]),
            )
    return None


def _matches(match_type: str, pattern: str, haystack: str) -> bool:
    needle = pattern.upper()
    if match_type == "contains":
        return needle in haystack
    if match_type == "exact":
        return needle == haystack
    if match_type == "regex":
        try:
            return re.search(pattern, haystack, re.IGNORECASE) is not None
        except re.error:
            # A rule with a broken regex should not take down an entire import.
            return False
    return False


def apply_rules_to_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, int]:
    """Categorize a batch's pending rows.

    Returns {"matched": n, "from_starter_rules": n}. The split matters: starter-rule
    suggestions are guesses we shipped about a life we have never seen, and ADR 0006
    requires the caller be able to say so out loud.

    Only fills in *suggestions*. Nothing posts, and the user can override every one.
    """
    pending = conn.execute(
        """SELECT id, description, amount_minor FROM staged_transactions
            WHERE batch_id = ? AND status = 'pending'
              AND transfer_match_id IS NULL""",
        (batch_id,),
    ).fetchall()

    # Paired transfers are excluded on purpose: money between your own accounts is not
    # income or expense, so a category suggestion for one would be offering the user a
    # choice that is wrong by construction (ADR 0007). "TRANSFER TO SAVINGS" would
    # otherwise happily match a starter rule.
    matched = 0
    from_starter = 0
    for row in pending:
        match = match_transaction(conn, row["description"], row["amount_minor"])
        if match is None:
            continue
        conn.execute(
            """UPDATE staged_transactions
                  SET suggested_account_id = ?, suggested_reason = ?,
                      suggested_rule_id = ?
                WHERE id = ?""",
            (match.account_id, match.reason, match.rule_id, row["id"]),
        )
        matched += 1
        from_starter += match.is_starter_rule
    return {"matched": matched, "from_starter_rules": from_starter}
