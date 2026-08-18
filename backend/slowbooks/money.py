"""Money handling. Every cent in SlowBooks passes through here.

Money is an int of minor units (cents). Never a float. See
docs/decisions/0003-money-as-integer-minor-units.md for why this is not negotiable.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

Minor = int

_CURRENCY_JUNK = re.compile(r"[$£€\s]")
_PARENS_NEGATIVE = re.compile(r"^\((.*)\)$")
# A comma with no decimal point anywhere is ambiguous on its own -- "3,000" (thousands)
# vs "3,5" (European decimal). This distinguishes them: thousands grouping is always
# groups of exactly three digits.
_COMMA_THOUSANDS_ONLY = re.compile(r"^-?\d{1,3}(?:,\d{3})+$")


class MoneyParseError(ValueError):
    """A string could not be understood as an amount."""


def parse(value: str | int | Decimal) -> Minor:
    """Parse a human/CSV amount into integer cents.

    Handles the formats bank CSVs actually emit:
        "$1,234.56" -> 123456
        "1234.56"   -> 123456
        "(45.00)"   -> -4500      accounting-style negative
        "-45"       -> -4500
        "1.234,56"  -> 123456     European
        ""          -> raises

    Decimal is used transiently and never escapes this module.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return _decimal_to_minor(value)

    if value is None:
        raise MoneyParseError("cannot parse None as money")

    text = _CURRENCY_JUNK.sub("", str(value)).strip()
    if not text:
        raise MoneyParseError("cannot parse empty string as money")

    negative = False
    parens = _PARENS_NEGATIVE.match(text)
    if parens:
        negative = True
        text = parens.group(1)

    text = _normalize_separators(text)

    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyParseError(f"cannot parse {value!r} as money") from exc

    if negative:
        amount = -amount
    return _decimal_to_minor(amount)


def _normalize_separators(text: str) -> str:
    """Reduce thousands/decimal separators to a plain Decimal-parseable string.

    The ambiguous case is "1.234,56" (European) vs "1,234.56" (US). Whichever
    separator appears last is the decimal point.

    A lone comma with no dot at all is a second, distinct ambiguity: "3,000" (US
    thousands grouping, no cents) vs "3,5" (European decimal). A comma isn't a decimal
    point here unless it fails to look like thousands grouping -- see
    _COMMA_THOUSANDS_ONLY.
    """
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")

    if last_comma == -1 and last_dot == -1:
        return text
    if last_dot == -1:
        if _COMMA_THOUSANDS_ONLY.match(text):
            return text.replace(",", "")
        return text.replace(",", ".")
    if last_comma > last_dot:
        return text.replace(".", "").replace(",", ".")
    return text.replace(",", "")


def _decimal_to_minor(amount: Decimal) -> Minor:
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format(minor: Minor, *, symbol: str = "$") -> str:
    """Format cents for display: -123456 -> "-$1,234.56"."""
    sign = "-" if minor < 0 else ""
    whole, cents = divmod(abs(minor), 100)
    return f"{sign}{symbol}{whole:,}.{cents:02d}"


def format_accounting(minor: Minor, *, symbol: str = "$") -> str:
    """Accounting-style display, where negatives wear parentheses.

    -123456 -> "($1,234.56)". This is what accountants expect on a statement.
    """
    if minor < 0:
        whole, cents = divmod(abs(minor), 100)
        return f"({symbol}{whole:,}.{cents:02d})"
    return format(minor, symbol=symbol)


def allocate(total: Minor, weights: list[int]) -> list[Minor]:
    """Split `total` proportionally to `weights`, losing no cents.

    Splitting $10.00 three ways gives [334, 333, 333], not three lots of 333.33
    with a cent evaporating. The remainder is distributed one cent at a time to
    the largest fractional parts, so sum(result) == total exactly. This matters
    anywhere we split money -- loan principal/interest most immediately.
    """
    if not weights:
        raise ValueError("cannot allocate across zero weights")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be non-negative")

    total_weight = sum(weights)
    if total_weight == 0:
        raise ValueError("weights must not sum to zero")

    # Integer-only: floor each share, then hand out the remainder by largest
    # fractional part. No float, no drift.
    shares: list[int] = []
    remainders: list[tuple[int, int]] = []
    for index, weight in enumerate(weights):
        numerator = total * weight
        share = numerator // total_weight
        shares.append(share)
        remainders.append((numerator - share * total_weight, index))

    shortfall = total - sum(shares)
    remainders.sort(key=lambda pair: (-pair[0], pair[1]))
    step = 1 if shortfall > 0 else -1
    for offset in range(abs(shortfall)):
        shares[remainders[offset % len(remainders)][1]] += step

    return shares
