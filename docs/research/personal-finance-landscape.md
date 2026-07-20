# Personal Finance App Landscape

Research date: 2026-07-20.

Plays the role `quickbooks-pain-points.md` and `competitive-landscape.md` played for the
original small-business SlowBooks: the reason principles.md's "Because:" lines say what
they say. Those two docs are kept as historical background (see docs/README.md) — this
one is their personal-finance replacement.

## The players

| Product | Model | Category shape | Notable |
|---|---|---|---|
| Mint | Free, shut down Mar 2024 | Flat categories, ~20 groups | Proof that "free forever" from a big vendor is not a guarantee — years of transaction history vanished with the product |
| YNAB | ~$109/yr | Priority-ordered groups (Immediate Obligations, True Expenses, Debt Payments, Quality of Life) | Zero-based: every dollar assigned a job before it's spent, not tracked after |
| Monarch Money | ~$100/yr | Type → Group → Category, 3 layers | Cash-flow budgeting (plan against expected income) instead of YNAB's strict envelope rule; also offers a simpler "Flex" view (Fixed / Non-Monthly / Flexible) |
| Copilot | ~$95/yr, Apple-only | Type → Group → Category, AI-assisted categorization | Positioned explicitly as "the Mint replacement" |

## What the gaps tell us

**Mint's shutdown is the personal-finance version of Xero's no-local-backup problem.**
The best-known free tool in the category simply disappeared, taking years of categorized
history with it. Our local-first, one-SQLite-file position is differentiation against
the entire cloud-subscription field, not just against one competitor.

**Every serious app treats a transfer as its own type, never a category.** Checking →
savings, or a credit card payment, shows up as a `Transfer`, distinct from `Income` and
`Expense`. This is exactly [ADR 0007](../decisions/0007-transfers-are-not-categories.md)
— we already got this right independent of this research, which is a good sign the
underlying engine is sound even where the vocabulary around it isn't.

**Categories are three layers deep, we're two.** The consistent shape across Mint,
Monarch, and Copilot is:

```
Type (fixed: Income / Expense / Transfer)
  └─ Group (customizable: Housing, Food & Dining, Transportation, ...)
       └─ Category (Groceries, Restaurants & Bars, Coffee Shops, ...)
```

Our chart of accounts has Type (asset/liability/equity/revenue/expense) and Category
(the ~30 accounts in `accounts.py`), numbered into ranges instead of grouped by name —
there's no Group layer a user browses by. A "Food & Dining" group containing Groceries,
Dining & Takeout, and a future "Coffee Shops" split doesn't exist as a concept; it would
need to be invented.

**No accounting vocabulary survives contact with the user.** None of these four products
say "chart of accounts," "debit," "credit," "trial balance," or "journal entry" anywhere
in their UI. The translations, consistently:

| Accounting term (what we say now) | Consumer term (what they say) |
|---|---|
| Chart of accounts | Categories |
| Balance Sheet | Net Worth |
| Profit & Loss / Income Statement | Spending / Cash Flow |
| Journal entry | Transaction |
| Debit / Credit | *(not shown — direction is implicit in the amount's sign and color)* |
| Trial Balance | *(not shown at all — a pure bookkeeping/audit concept with no consumer-facing equivalent)* |
| Reconciliation | *(usually just "match your bank balance," if surfaced at all)* |

**Budgeting is a view on top of categories, not a separate taxonomy.** YNAB's priority
groups, Monarch's Fixed/Variable/Non-Monthly buckets, and the 50/30/20 Needs/Wants/Savings
rule are three different *lenses* over the same underlying transactions — none of them
replace having Groceries and Rent as categories. Worth knowing about, not worth deciding
between right now: we don't have a budgeting feature yet, so there's nothing to attach a
lens to.

## What we already get right

- Transfers as a distinct kind of transaction, never offered as a category (ADR 0007).
- A single category picker per transaction — the user experiences one choice, even
  though double-entry runs underneath. No app in this survey exposes the second side of
  an entry to the user, and neither do we.
- Starter-rule guesses that announce themselves as guesses (ADR 0006) — none of the
  apps surveyed do this; it's a point of difference worth keeping, not something the
  research suggests changing.

## What's still business-shaped

- **No Group layer.** Every competitor groups categories (Housing, Food & Dining,
  Transportation); we have a flat list ordered by account code.
- **Report names.** We still call the income/expense report "Profit and Loss" and show
  a "Trial Balance" — neither term appears in any personal-finance app surveyed.
- **"Chart of accounts" as user-facing language** in the UI copy and docs, where every
  competitor just says "Categories."

These are implementation questions, not conclusions — noted here so a future ADR can
decide them deliberately rather than the terminology drifting by accident.

## Open questions for a future ADR

1. Do we add a Group layer between Type and Category (e.g. "Food & Dining" containing
   Groceries + Dining & Takeout), or keep the flat list and rely on account naming/order?
2. Do we rename "Profit and Loss" → something like "Spending" or "Cash Flow," and
   "Balance Sheet" → "Net Worth," in the API and UI? (Trial Balance can likely stay an
   internal/export-only report — no consumer app surfaces its equivalent at all.)
3. If we add a Group layer, does it live in the database (a new column/table) or purely
   as a UI-level grouping over the existing account codes?

None of these are decided by this document — they're flagged for whoever picks up the
next piece of implementation work.

## Sources

- [Intuit Mint — Wikipedia](https://en.wikipedia.org/wiki/Intuit_Mint)
- [How Many YNAB Categories Should I Have? — YNAB](https://www.ynab.com/blog/how-many-ynab-categories)
- [Zero-Based Budgeting: YNAB vs. Monarch Compared — Monarch](https://www.monarch.com/how-monarch-compares-to-ynabs-zero-based-budgeting)
- [Flex Budgeting: The One-Number Budget That Actually Sticks — Monarch](https://www.monarch.com/blog/flex-budgeting-simplify-your-spending-with-just-one-number)
- [23 Budget Categories You Need in Your Budget — Monarch](https://www.monarch.com/blog/the-23-budget-categories-you-need-in-your-budget)
- [Default Categories — Monarch Help Center](https://help.monarch.com/hc/en-us/articles/360048883851-Default-Categories)
- [Groups of Categories — Copilot Help Center](https://help.copilot.money/en/articles/3767655-groups-of-categories)
- [Personal Balance Sheet: How to Calculate Your Net Worth — Britannica Money](https://www.britannica.com/money/personal-balance-sheet)
