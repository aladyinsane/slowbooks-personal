# GAAP and Accounting Fundamentals — Implementation Notes

Research date: 2026-07-16, updated 2026-07-20 for the personal-finance fork.

> **Caveat.** This is an engineering reference for building the ledger correctly, not
> accounting or tax advice, and it was written by a developer rather than an accountant.
> Anything marked **[CPA REVIEW]** is a spot where a tax professional's judgment matters
> more than a developer's guess — check it before relying on this software for your own
> tax filing.

## The one rule that determines the architecture

**Only accrual-basis accounting is accepted under GAAP** (the rules set by FASB). Accrual
basis requires **double-entry bookkeeping**: every transaction is recorded in at least two
accounts using debits and credits.

This is why SlowBooks is a double-entry system underneath even though the user interface
will rarely say "debit" or "credit." Single-entry is simpler to build and simpler to
explain, but it cannot produce a Balance Sheet, cannot be audited, and is not GAAP. There
is no path from single-entry to GAAP later — it's a foundation decision. See
[decisions/0004-double-entry-immutable-ledger.md](../decisions/0004-double-entry-immutable-ledger.md).

## Cash vs. accrual, and why we need both

Individuals file taxes on a cash basis almost without exception — income is taxed when
you receive it, not when you're owed it. But "when did the money actually move" and
"what do I currently owe or have coming" are two different questions a household asks
just as often as a business does: a bill you've received but haven't paid yet (tracked
via the Bills Owed account) is a real accrual fact even though nothing has left your
checking account.

So the realistic situation is the same shape it was for the business version: **accrual
for a complete picture of where things stand, cash basis for "what actually moved this
month."** This means basis is a *reporting-time toggle*, not a storage decision. We store
accrual-truth journal entries and filter at report time — see the cash-basis toggle
tracked in [product/roadmap.md](../product/roadmap.md).

Implementation consequence: **never** store a transaction in a way that loses the accrual
information. You can derive cash from accrual; you cannot derive accrual from cash.

## The accounting equation

```
Assets = Liabilities + Equity
```

Extended for a period in progress:

```
Assets = Liabilities + Equity + (Revenue - Expenses)
```

The Balance Sheet is a statement of this equation at a point in time. The P&L is the
`(Revenue - Expenses)` term over a period. **These two reports must agree**, and that
agreement is the single best correctness test we have — see `test_reports.py`.

## Debits and credits

The part everyone finds confusing. The mechanical rule:

| Account type | Normal balance | Debit does | Credit does |
|---|---|---|---|
| Asset | Debit | Increase | Decrease |
| Expense | Debit | Increase | Decrease |
| Liability | Credit | Decrease | Increase |
| Equity | Credit | Decrease | Increase |
| Revenue | Credit | Decrease | Increase |

Mnemonic: **DEA** (Debits: Expenses, Assets) increase with debits; **CLER** (Credits:
Liabilities, Equity, Revenue) increase with credits.

The invariant: **in every journal entry, total debits must equal total credits.** We enforce
this in the database layer and it is the reason the books can never silently drift.

### Worked example — the user's mental model vs. ours

The user sees: *"$45 at Kroger on the credit card."*

We record:

| Account | Debit | Credit |
|---|---|---|
| 6100 Groceries (Expense) | $45.00 | |
| 2100 Credit Card (Liability) | | $45.00 |

Expense up (debit), liability up (credit). Balanced. The user never sees this table unless
they ask — but it's what makes the Balance Sheet work.

## Chart of Accounts

A numbering convention that accountants already expect, and that sorts correctly:

| Range | Type | Examples |
|---|---|---|
| 1000–1999 | Assets | Checking, Savings, Investments, Property |
| 2000–2999 | Liabilities | Credit Card, Bills Owed, Loans Payable |
| 3000–3999 | Equity | Opening Balance, Net Worth Carried Forward |
| 4000–4999 | Revenue | Salary & Wages, Freelance & Side Income, Interest & Dividends |
| 6000–6999 | Expenses | Rent, Utilities, Groceries, Subscriptions |

Note there's no 5000s range here. The original business version split expense into 5000s
(cost of goods sold) and 6000s (operating expenses) because a business needs gross profit
to mean something. A household has no goods it resells, so that split has no referent —
expense is just 6000–6999, one range (see [accounts.py](../../backend/slowbooks/accounts.py)'s
`TYPE_RANGES`).

The chart must be **customizable** — a flexible chart of accounts is repeatedly called out
as what lets the software keep up with a life that doesn't stay the same shape. But it
should ship with a sensible default so a new user isn't staring at an empty screen on day
one. Defaults that are good enough to ignore are the whole game here.

## Principles that constrain the software

- **Revenue recognition** — revenue is recognized when *earned*, not when cash arrives.
  (ASC 606 is the full standard and is far beyond scope here; for a household the naive
  version — a paycheck is income when it's paid, not when the pay period ended — is what
  matters.)
- **Matching principle** — expenses are recognized in the same period as the revenue they
  helped generate. This is what drives period-end adjusting entries.
- **Consistency** — methods stay the same period to period. If we ever let users change
  something method-like, we must record when and why.
- **Materiality** — small amounts don't need the same rigor. This is our license to keep the
  UI simple; not every edge case deserves a dialog box.
- **Conservatism** — when uncertain, don't overstate assets or revenue.

## Period close and adjusting entries

At the end of each period, journal entries adjust and reconcile balances for **accrued
expenses, deferred revenue**, and other items that span periods.

Closing a period must **lock** it: no edits to entries dated within a closed period. This is
what makes prior-period reports reproducible. If a correction is needed after close, the
answer is a **reversing entry in the current period**, never a silent edit to history.

This is a hard rule, and it's the reason our ledger is append-only.

## Audit trail

I could not find a crisp citable statement of audit-trail requirements for small business
GAAP in this pass, so the design below is reasoned from first principles rather than
sourced. **[CPA REVIEW]**

The defensible position: **the ledger is append-only.** Corrections are new entries that
reverse old ones. Nothing is ever destroyed. This is how real accounting has worked since
long before computers, it's what makes books auditable, and it costs us nothing to do from
day one — while retrofitting it later would be a rewrite.

Note the tension with a UX goal: users expect a delete button, and "cannot bulk-delete
transactions" is a top QuickBooks complaint. Resolution: **void, don't delete.** Voiding
posts a reversing entry, so the UI can offer bulk-void that *feels* like deletion while the
ledger stays honest. The complaint is really about tedium, not about destroying data.

## Sources

- [Cash-Basis vs. Accrual-Basis Accounting — NetSuite](https://www.netsuite.com/portal/resource/articles/financial-management/cash-basis-accrual-basis.shtml)
- [GAAP Accrual Accounting: a Comprehensive Guide — inDinero](https://www.indinero.com/blog/gaap-what-it-is-why-your-investors-expect-it/)
- [Cash vs. Accrual Accounting: What's Best for My Small Business? — Bank of America](https://business.bankofamerica.com/en/resources/cash-vs-accrual-accounting)
- [Cash Versus Accrual Basis of Accounting: An Introduction — Congressional Research Service](https://www.congress.gov/crs-product/R43811)
- [Accounting Methods: Accrual, Cash-basis, Modified Cash-basis — Patriot Software](https://www.patriotsoftware.com/blog/accounting/accounting-methods/)
- [Cash vs accrual accounting — Xero](https://www.xero.com/us/guides/cash-vs-accrual-accounting/)
