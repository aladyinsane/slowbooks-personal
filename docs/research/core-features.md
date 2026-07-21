# Core Functionality a Personal Ledger Needs

Research date: 2026-07-16, updated 2026-07-20 for the personal-finance fork. Answers
"what else does such a system need?" beyond the CSV import / categorization / P&L /
Balance Sheet originally named — the engineering scope below turned out to be
audience-independent even though this doc was first written for the small-business
version. See [personal-finance-landscape.md](personal-finance-landscape.md) for what's
specific to a household rather than a business.

## Tier 1 — Not optional. Without these it isn't accounting software.

| Capability | Why it's mandatory | Status |
|---|---|---|
| **Double-entry ledger** | Required for GAAP and for a Balance Sheet to exist at all | v1 |
| **Chart of Accounts** | The vocabulary everything else is expressed in | v1 |
| **CSV import** | Your stated entry point; also the universal path — every institution exports CSV | v1 |
| **Transaction categorization** | The actual daily work of bookkeeping | v1 |
| **P&L / Income Statement** | The report people actually read | v1 |
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
agree. Personal and business books alike use CSV files precisely for this.

Without it, every report is "these are the numbers, probably." With it, a reconciled
period is *proven* to match the bank. Strong recommendation for v1.

### Transfer detection deserves special mention

When you move $5,000 from checking to savings, that's **two rows** in **two CSVs**: a
-$5,000 and a +$5,000. Naively categorized, this becomes $5,000 of expense and $5,000 of
income — inflating both sides of the P&L while the true P&L impact is zero.

This is the single most common way self-prepared books go wrong, and it's invisible: the
numbers look plausible. Research confirms good tools specifically "surface transfer-like
rows." Auto-detecting matched opposite pairs across accounts within a date window is high
value and not hard.

Likewise **refunds** (a credit that should reduce an expense, not create revenue).

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
  organized by account. Even one person usually has checking + a card + probably a loan.
- **General Ledger and Trial Balance.** Shipped as export/API-only, not an on-screen
  report (ADR 0015) — no personal-finance app surfaces either, since "are my debits equal
  to my credits" isn't a question a household asks. Kept for whoever does want to look,
  and for the export's own completeness (ADR 0008).
- **Undo.** Import 400 transactions, realize the mapping was wrong, undo the batch. Without
  this, an import mistake is a manual cleanup nightmare and users will fear the button.

## Tier 3 — Real, but deliberately deferred

Documented in [product/future-features.md](../product/future-features.md) so they're
remembered rather than accreted: multi-currency, bank feeds, a mobile app, receipt
capture, budgeting/forecasting. (The original version of this list also had invoicing/AR,
bills/AP, payroll, inventory/COGS, sales tax, multi-entity, and 1099 tracking — all
business-only, all removed when future-features.md was pruned for this fork.)

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
