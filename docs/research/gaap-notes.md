# GAAP and Accounting Fundamentals — Implementation Notes

Research date: 2026-07-16.

> **Caveat.** This is an engineering reference for building the ledger correctly, not
> accounting advice, and it was written by a developer rather than a CPA. Anything marked
> **[CPA REVIEW]** should be checked by an accountant before we ship it to real users
> making real tax filings.

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

Many small businesses can use the **cash method for federal income tax purposes**:
corporations or partnerships with average annual gross receipts of **$31 million or less**
(inflation-adjusted) over the three prior tax years generally qualify.

So the realistic situation for our user is: **accrual for GAAP-correct books, cash basis for
the tax return.** This means basis is a *reporting-time toggle*, not a storage decision. We
store accrual-truth journal entries and filter at report time.

**[CPA REVIEW]** The exact cash-basis conversion rules (particularly around A/R, A/P, and
prepaid expenses) need professional review before we advertise a cash-basis report as
tax-ready.

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

The owner sees: *"$450 at Staples on the business card."*

We record:

| Account | Debit | Credit |
|---|---|---|
| 6100 Office Supplies (Expense) | $450.00 | |
| 2100 Credit Card Payable (Liability) | | $450.00 |

Expense up (debit), liability up (credit). Balanced. The user never sees this table unless
they ask — but it's what makes the Balance Sheet work.

## Chart of Accounts

A numbering convention that accountants already expect, and that sorts correctly:

| Range | Type | Examples |
|---|---|---|
| 1000–1999 | Assets | Checking, Savings, A/R, Fixed Assets |
| 2000–2999 | Liabilities | Credit Cards, A/P, Loans Payable |
| 3000–3999 | Equity | Owner's Capital, Owner's Draw, Retained Earnings |
| 4000–4999 | Revenue | Sales, Service Income |
| 5000–5999 | COGS | Materials, Direct Labor |
| 6000–6999 | Expenses | Rent, Utilities, Office Supplies, Software |

The chart must be **customizable** — a flexible chart of accounts is repeatedly called out
as what lets the software keep up with a growing business. But it should ship with a
sensible default so a new user isn't staring at an empty screen on day one. Defaults that
are good enough to ignore are the whole game here.

## Principles that constrain the software

- **Revenue recognition** — revenue is recognized when *earned*, not when cash arrives.
  (ASC 606 is the full standard and is far beyond v1 scope; the naive version is what
  matters for a small service business.)
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
