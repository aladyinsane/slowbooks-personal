# Core Functionality a Small-Business Accounting System Needs

Research date: 2026-07-16. This answers "what else does such a system need?" beyond the
CSV import / categorization / P&L / Balance Sheet you named.

## Tier 1 — Not optional. Without these it isn't accounting software.

| Capability | Why it's mandatory | Status |
|---|---|---|
| **Double-entry ledger** | Required for GAAP and for a Balance Sheet to exist at all | v1 |
| **Chart of Accounts** | The vocabulary everything else is expressed in | v1 |
| **CSV import** | Your stated entry point; also the universal path — every institution exports CSV | v1 |
| **Transaction categorization** | The actual daily work of bookkeeping | v1 |
| **P&L / Income Statement** | The report owners actually read | v1 |
| **Balance Sheet** | Required by lenders and the IRS; proves the ledger is sound | v1 |
| **Bank reconciliation** | See below — this is the one you didn't ask for and most need | v1 |
| **Duplicate detection** | Re-importing an overlapping CSV is the #1 way to corrupt books | v1 |
| **Transfer detection** | See below — the most common categorization error | v1 |
| **Data export** | Our anti-lock-in promise; meaningless if unimplemented | v1 |
| **Period close / locking** | Makes prior reports reproducible | v1 |
| **Audit trail** | Append-only ledger; auditability | v1 (structural) |

### Bank reconciliation deserves special mention

You didn't list it, but it's the feature that makes the books *trustworthy*. Reconciliation
is the process of matching recorded transactions against the bank's records so the balances
agree. Businesses use CSV files precisely for this.

Without it, every report is "these are the numbers, probably." With it, a reconciled period
is *proven* to match the bank. It's also the thing an accountant asks about first. Strong
recommendation for v1.

### Transfer detection deserves special mention

When you move $5,000 from checking to savings, that's **two rows** in **two CSVs**: a
-$5,000 and a +$5,000. Naively categorized, this becomes $5,000 of expense and $5,000 of
income — inflating both sides of the P&L while the true P&L impact is zero.

This is the single most common way self-prepared books go wrong, and it's invisible: the
numbers look plausible. Research confirms good tools specifically "surface transfer-like
rows." Auto-detecting matched opposite pairs across accounts within a date window is high
value and not hard.

Likewise **refunds** (a credit that should reduce an expense, not create revenue) and
**owner's draws vs. payroll** (a draw is equity, not an expense — getting this wrong
misstates both the P&L and the tax return).

## Tier 2 — Strongly expected. Absence generates complaints.

- **Rule memory.** When the user recategorizes a merchant, remember it so future imports get
  faster. Research is explicit that good tools do this. This is what makes month two take a
  quarter as long as month one — the compounding-value feature.
- **Bulk operations.** Select many, act once. QuickBooks' inability to bulk-delete is a top
  complaint. Bookkeeping is inherently repetitive; anything that forces one-at-a-time is a
  tax on the user.
- **Real search across transactions.** Another explicit QuickBooks complaint — users cannot
  search keywords within transactions.
- **Description cleaning.** Turn `SQ *COFFEE #1234 SEATTLE WA 0x8823` into `Square —
  Coffee`. Research lists this as a core capability. Raw bank descriptors are hostile.
- **Recurring transaction detection.** Flag likely recurring items (rent, subscriptions).
- **Attachments.** Receipt images/PDFs on a transaction. This is where IRS substantiation
  actually lives.
- **Multi-account.** Batch uploads across multiple accounts and statements at once,
  organized by account. Even a one-person business has checking + a card + probably a loan.
- **General Ledger and Trial Balance reports.** The owner won't read these; the *accountant*
  will, and the accountant is the gatekeeper (see the counter-argument in
  [quickbooks-pain-points.md](quickbooks-pain-points.md)).
- **Cash Flow Statement.** The third of the big three financial statements. Owners
  frequently care about it more than the P&L — profitable businesses die of cash flow.
- **Undo.** Import 400 transactions, realize the mapping was wrong, undo the batch. Without
  this, an import mistake is a manual cleanup nightmare and users will fear the button.

## Tier 3 — Real, but deliberately deferred

Documented in [product/future-features.md](../product/future-features.md) so they're
remembered rather than accreted. Invoicing/AR, bills/AP, payroll, inventory/COGS,
multi-currency, fixed asset depreciation schedules, sales tax, budgeting, multi-entity,
bank feeds, mobile, receipt OCR, 1099 tracking.

## Loan statements — a note on your specific ask

You mentioned importing loan statements, which are *not* like bank or card statements and
are worth calling out.

A loan payment is a **split**: part principal (reduces the liability — Balance Sheet only,
does **not** touch the P&L) and part interest (an expense — hits the P&L). A single $1,200
payment might be $900 principal + $300 interest.

Treating the whole $1,200 as an expense is a classic error that **overstates expenses and
understates both profit and the remaining loan balance** — wrong on both statements at once.
Worse, most loan CSVs give you one row with one amount and no split.

So loan import needs either an amortization schedule or per-transaction split entry. This is
genuinely more complex than checking/card import and should be scoped as its own feature.

## Sources

- [Top Software For Bank Transaction Categorization — DocuClipper](https://www.docuclipper.com/features/transaction-categorization/)
- [Transaction Categorization Software — DocuClipper](https://www.docuclipper.com/solutions/transaction-categorization-software/)
- [Personal finance app with CSV import and categorization — Koody](https://koody.com/blog/personal-finance-app-csv-import)
- [Bank Statement CSV Import for Budgeting — Koody](https://koody.com/bank-statement-csv-import)
- [CSV Bank Statement Definition — DocuClipper](https://www.docuclipper.com/glossary/csv-bank-statement/)
- [Import a precoded bank statement in CSV format — Xero Central](https://central.xero.com/s/article/Import-a-precoded-CSV-bank-statement)
- [CSV Format Bank Statement: UK Data Mapping Guide (2026)](https://snyp.ai/blog/csv-format-bank-statement)
