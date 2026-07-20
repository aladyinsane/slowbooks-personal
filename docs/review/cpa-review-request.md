# SlowBooks — request for professional review

**What this is:** a request for a CPA to check whether a piece of accounting software gets
the accounting right.

**What we need from you:** a judgement on whether the ledger and the financial statements
are correct, and a list of anything that would embarrass us in front of an auditor or the
IRS. We are not asking you to review code. Everything below can be checked from the
outputs.

**Why it matters:** nobody has used this for real books yet, and nobody will until someone
qualified has looked at it. We would rather find out now than after somebody files a
return.

---

## 1. What SlowBooks is

Small-business accounting software. One user — the business owner — doing their own books.

- Import CSV statements from a bank, credit card, or loan account.
- Categorize the transactions (with help; see §5).
- Produce a **Profit & Loss**, a **Balance Sheet**, and a **Trial Balance**.
- Reconcile each account against its bank statement.

It's local-first: the books live in a single file on the owner's own computer. Nothing is
sent anywhere. There is no cloud service.

**Scope, so you don't look for what isn't there.** Deliberately not built: payroll,
inventory/COGS costing methods, multi-currency, sales tax, invoicing/AR, bills/AP, fixed
asset depreciation schedules. Loan statements are only partially handled — see §6, and
we'd particularly value your view there.

## 2. How it works underneath, in one page

You don't need this to review the outputs, but you'll probably want it.

- **Strict double-entry.** Every transaction is a journal entry with two or more lines.
  Total debits always equal total credits — this is enforced by the database itself, not
  by application code, so it cannot be bypassed.
- **Accrual basis.** There is no cash-basis reporting yet. See §6.
- **Append-only.** Posted entries are never edited or deleted. A correction is a
  **reversing entry** that points back at the original. Both remain visible forever.
- **Money is stored as whole cents, as integers.** Never as a decimal or floating-point
  number, which cannot represent 0.1 exactly and would let a ledger drift.
- **Standard chart of accounts:** 1000s assets, 2000s liabilities, 3000s equity,
  4000s revenue, 5000s COGS, 6000s operating expenses. Customizable by the user.

## 3. How to check it — the practical part

You'll need about an hour and a computer. Two options:

**Option A — we send you a book file.** Simplest. We give you a `.zip` export containing
`general-ledger.csv`, `trial-balance.csv`, and `transactions.csv`, generated from a
realistic set of test books. You open them in Excel and tell us what's wrong. **No software
to install.** We recommend this.

**Option B — you drive it yourself.** We set it up on your machine or screen-share, you
import statements and poke at it. Better for judging the *workflow* (§5), which is where a
bookkeeper's instincts are worth more than ours.

Either way, we can send test statements that exercise the awkward cases, or you can use
real anonymised ones if that's easier.

## 4. What we specifically want you to check

Ordered by how badly we'd like to know.

### 4.1 Are the statements right?

- Does the **P&L** classify things correctly? Revenue, COGS, and operating expenses are
  separated; gross profit is revenue − COGS; net income is gross profit − operating
  expenses.
- Does the **Balance Sheet** balance, and is it laid out the way you'd expect?
- Is **`Assets = Liabilities + Equity`** actually holding, including the current-period
  earnings line?
- Does the **Trial Balance** look like a trial balance to you?
- **Do the two statements agree?** P&L net income should equal the Balance Sheet's current
  period earnings.

### 4.2 The equity treatment — we think this is our weakest area

We don't post **closing entries**. Instead, the Balance Sheet computes
"Current Period Earnings" as revenue − expenses to date, and shows it inside equity. There
is a Retained Earnings account in the chart, but nothing ever posts to it.

**Is that defensible?** It means any date produces a coherent Balance Sheet, including
mid-year, which is when an owner actually looks. But it also means we've never closed a
year, and we don't know what breaks when the owner hits December 31st.

**What should year-end look like?** This is the thing we're least sure about and most want
you to opine on.

### 4.3 Owner's draw vs. payroll vs. expense

The chart has **Owner's Draw (3100)** as equity, not an expense. We believe a draw reduces
equity and never touches the P&L — and that getting this wrong misstates both profit and
the tax return.

- Is our treatment right?
- For a sole proprietor vs. an S-corp, does the answer change in a way the software should
  know about?
- Is there a trap here we're walking into?

### 4.4 Transfers between the owner's own accounts

Moving $5,000 from checking to savings, or paying a credit card from checking, is **not**
income or an expense. We detect these, pair the two statement rows, and post **one** entry
that touches only the Balance Sheet.

- Is a credit card payment being treated as a transfer (checking down, liability down) the
  correct treatment? We believe booking it as an expense would double-count, since the
  purchases were already expensed when charged.
- Are there transfer-like transactions we're likely to mis-handle?

### 4.5 Reconciliation

The user types in the bank's closing balance; we compare it to ours; if they match, they
confirm and we record the assertion permanently, stamping every line it covered. Undo is a
reversal, not a deletion.

- Is that a reconciliation as you'd recognise it?
- **We don't yet lock a reconciled period.** We *detect* a transaction backdated into a
  reconciled period and warn about it, but we don't prevent it. How bad is that? Is
  detection acceptable, or is prevention mandatory?
- Bookkeepers usually tick off individual lines. We reconcile a whole account to a date,
  all-or-nothing. Is that a real problem in practice?

### 4.6 The audit trail

Nothing is ever deleted. "Deleting" a transaction posts a reversing entry; both show in the
general ledger, with the reversal marked `void` in the `source` column.

- Is this what an auditor would want to see?
- Is there anything we should be recording that we aren't — timestamps, who did what,
  reasons for changes?

### 4.7 The chart of accounts

Attached in the export as `tables/accounts.csv`.

- Is anything **missing** that a small business will hit in month one?
- Is anything **mis-typed** (in the wrong range, or the wrong normal balance)?
- Are the names ones a non-accountant would understand? We've favoured plain language over
  precision in a few places and would like to know where that's gone too far.

## 5. The part where your instincts matter more than ours

We're software people. We've made the software refuse to be internally inconsistent. What
we can't judge is whether it helps someone make the *right* decision.

- When an owner sees a $1,200 loan payment, they think "expense." It's really principal
  (Balance Sheet) plus interest (P&L). **How would you explain that to them in one
  sentence?** We'd like to put that sentence in the product.
- Same for: a credit card payment, an owner's draw, a refund, a customer deposit, a
  transfer.
- **What do self-prepared books get wrong most often?** If you tell us the top five, we
  will design against them specifically. This is probably the single most useful thing you
  could give us.

## 6. Known gaps — please tell us how much these matter

We already know about these. We want your ranking of what's disqualifying vs. what can wait.

| Gap | Our current position |
|---|---|
| **No cash-basis reporting** | Accrual only. Most of our users will likely file taxes on cash basis. We know the conversion touches A/R, A/P and prepaids and we haven't attempted it. |
| **No closing entries / year-end** | §4.2. |
| **Loan payments can't be split** | A $1,200 payment can only be booked to one account today, which overstates expenses and understates the loan balance. Split transactions are next on our roadmap. **Is this disqualifying for anyone with a loan?** |
| **No period locking** | §4.5. |
| **No A/P or A/R** | Which arguably makes "accrual" a bit of a claim. How much does this undermine the accrual basis in practice? |
| **Refunds** | A refund currently books as income unless the user recategorizes it. It should reduce the original expense. We know; it's queued. |
| **No 1099 tracking, no sales tax** | Deliberate. |

## 7. What we'd like back

Whatever's easiest for you — a marked-up spreadsheet, an email, or an hour on a call.
Ideally:

1. **Anything that's actually wrong.** Wrong numbers, wrong classification, wrong sign.
2. **Anything that would fail an audit** or that you'd refuse to sign off on.
3. **Your ranking of §6** — what's disqualifying, what's fine for now.
4. **The §5 answers**, if you have the patience. They'd shape the product more than
   anything else on this list.

Please be blunt. We would much rather hear "this is wrong and here's why" than have it be
polite and ship it to someone's real books.

---

## Appendix — reading the export

`general-ledger.csv` — one row per journal line.

| Column | Meaning |
|---|---|
| `date` | transaction date |
| `entry` | journal entry id; lines sharing an id are one transaction and always net to zero |
| `account_code`, `account_name`, `account_type` | the account |
| `description`, `memo` | as imported from the statement |
| `debit`, `credit` | ordinary decimal amounts; exactly one is populated per row |
| `source` | `import`, `manual`, `transfer`, or `void` |

`trial-balance.csv` — every account with a non-zero balance, plus a TOTAL row. The two
totals must match.

`transactions.csv` — one row per entry, for readability rather than rigour.

`tables/*.csv` — raw database dumps. **Money in these is integer cents:** `123456` means
`$1,234.56`. In `tables/journal_lines.csv`, `amount_minor` is signed — positive is a debit,
negative is a credit. The reports are the ones with normal decimals; the raw dumps are
lossless. The `README.txt` inside the export explains all of this too.
