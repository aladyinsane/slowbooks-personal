# ADR 0003 — Money is stored as integer minor units (cents)

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

This is the most boring ADR and the one most likely to save the project.

Floating point cannot represent most decimal fractions exactly. `0.1 + 0.2 == 0.30000000000000004`
in every IEEE-754 language, including Python and JavaScript. In an accounting system this is
not a rounding curiosity — it is fatal:

- Debits and credits must be *exactly* equal. A float ledger drifts, and the balance check
  that's supposed to be our safety net starts producing false failures at $0.0000001.
- A Balance Sheet that's off by a penny is, to an accountant, simply broken. There's no
  "close enough."
- Errors accumulate. Over 50,000 transactions, drift compounds silently.

We also have a stack-specific hazard: SQLite has no native decimal type, and JavaScript has
no integer type distinct from double — everything is float64.

## Decision

**Money is a Python `int` of minor units (cents). Always. Everywhere.**

- Storage: SQLite `INTEGER`.
- API: JSON integer (`45000` = $450.00), plus a preformatted display string.
- Frontend: treated as an opaque integer; **never** used in float arithmetic in JS.
- `Decimal` is permitted *only* transiently inside `money.py` when parsing user/CSV input,
  and is converted to `int` before it escapes.
- **`float` is banned in any code path touching money.** No exceptions.

JS numbers are float64, which represent integers exactly up to 2^53 — about
$90,071,992,547,409. Our user is a small business. Integers are safe; decimals are not.

## Consequences

**Good**

- Arithmetic is exact. `1 + 2 == 3`, forever. The debits==credits invariant becomes a real
  guarantee rather than an approximation with a tolerance.
- Fast and trivially comparable/indexable in SQLite.
- Language-independent — the same integer means the same thing in Python, SQLite, and JS.

**Bad / accepted costs**

- Every display needs formatting (`45000` → `"$450.00"`). Centralized in `money.py` and
  mirrored in the frontend's `lib/money.ts`.
- Every input needs parsing. `"$1,234.56"`, `"1234.56"`, `"(45.00)"` (accounting negative),
  `"1.234,56"` (European) all must land on the same integer. Centralized in `money.py`.
- **Division needs an explicit rounding policy.** Splitting $10.00 three ways is 333 + 333 +
  334, not 333.33 × 3. Rounding must never lose or invent a cent. Handled by
  `money.allocate()`, which distributes remainders deterministically.
- Non-2-decimal currencies (JPY has 0, KWD has 3) would break a hardcoded `/100`. Out of
  scope now (USD only), but `money.py` is the one place that would need to change.

## Enforcement

This is a discipline that decays silently, so it needs teeth:

- All money arithmetic goes through `slowbooks/money.py`.
- The debits==credits invariant is enforced by a SQLite trigger — the database itself
  refuses an unbalanced entry (principle 6: correct by construction).
- `tests/test_money.py` covers the classic float traps explicitly.
- Code review rejects any `float` near money.
