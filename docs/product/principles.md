# Product Principles

These exist to be *used in arguments*. When a feature request arrives, it gets checked
against this list. A principle that never rejects anything isn't a principle, it's a slogan.

Each one traces to a specific finding in
[../research/personal-finance-landscape.md](../research/personal-finance-landscape.md).

---

## 1. The books are the user's, not ours

One SQLite file. On their disk. Copyable to a thumb drive. Plus full export of every table
to CSV/JSON, and it works forever with no subscription check.

*Because:* Mint was free, ubiquitous, and shut down anyway — years of categorized history
gone with it. YNAB, Monarch, and Copilot all require an active subscription just to keep
seeing data the user typed in themselves. This is our wedge, and it doesn't depend on any
one competitor's pricing choices: it's a structural difference, not a cheaper plan.

**Test:** if we shut down tomorrow, does the user still have working books? If no, we've
broken the core promise.

## 2. Real double-entry underneath, plain language on top

The ledger is strict double-entry, append-only, and always balances. The interface says
"$45 at Kroger → Groceries," not "debit 6100, credit 2100."

*Because:* nothing in the personal-finance category — Mint, YNAB, Monarch, Copilot —
exposes debit/credit language or a chart of accounts to the user, and our user isn't a
bookkeeper either. The rigor is for correctness (Assets = Liabilities + Equity, always);
the vocabulary is for a person checking their own numbers on a Sunday night.

**Test:** can someone with zero accounting background complete the task without learning
a new word?

## 3. Fast is a feature, and it's the cheapest one to win

Budget: **<100ms** for any categorization action, **<1s** for any report on a book of 50k
transactions. Regressions past budget are bugs, not tech debt.

*Because:* categorizing a year of your own statements, or a decade of them if you're
finally getting organized, is bulk repetition — per-action latency multiplies by however
many transactions you have. This is a straight win available to us for free because we're
local: no network round-trip, no server to be slow.

**Test:** does it feel instant on the 200th repetition, not the first?

## 4. Every feature must earn its place on the screen

New features must say what they push out. Nested menus are forbidden. No feature is added
because a competitor has it.

*Because:* the products in this category accrete fast — investment tracking, credit-score
monitoring, budgeting gamification, bill-negotiation upsells, ads for financial products
based on your own spending data. Every one of those was individually reasonable to whoever
added it. Accretion is the default outcome, so resisting it must be deliberate.

**Test:** where does this live, and what leaves to make room?

## 5. Never make a human repeat themselves

Categorize a merchant once; we remember. Bulk-select and act once. Search actually
searches. Undo works on whole batches.

*Because:* managing your own money is bulk repetition too — the same grocery store, the
same streaming subscription, month after month. Making someone recategorize "Trader Joe's"
every single time it shows up is asking them to do the computer's job for it.

**Test:** did the user do the same thing twice? That's our bug.

## 6. Correct by construction, not by user diligence

Debits must equal credits — enforced in the database, not asked of the user. Duplicate
imports are caught. Transfers are detected. Closed periods lock. Corrections reverse rather
than overwrite.

*Because:* the user is not an accountant and shouldn't need to be. Errors that require
financial-literacy to *notice* are the dangerous ones — a transfer to savings
miscategorized as income looks completely plausible on a spending report, and the person
least likely to catch it is the one who isn't looking for it.

**Test:** can the user create an inconsistent state? If yes, that's our bug, not theirs.

## 7. Never upsell

No in-app ads, no locked features with an upgrade button, no adjacent-product promotion.

*Because:* Mint's business model was showing ads for credit cards and loans built from the
user's own transaction data — the thing that made it "free" is the same thing that made it
untrustworthy. An upsell is a permanent tax on every screen it occupies, and it makes the
product about our revenue instead of the user's own finances.

**Test:** does this screen serve the user's task, or ours?

## 8. Show the work

Every number in a report drills down to the transactions that produced it. Every
auto-categorization says why. Every import says exactly what it did and offers undo.

*Because:* trust in something that touches your own money is everything, and it's earned
by being inspectable. "You spent $1,200 on dining this month" is worthless if the user
can't check it — and this is what makes automated categorization safe to accept rather
than something to second-guess.

**Test:** can the user get from any number to the underlying transactions?

---

## Anti-principles: things we are deliberately not

- **Not the most featureful.** Monarch and Copilot will always have more integrations,
  investment tracking, and budgeting gamification than we will. See the deferred list in
  [future-features.md](future-features.md).
- **Not a budgeting methodology.** We don't enforce zero-based budgeting the way YNAB
  does, or ship a Fixed/Variable/Non-Monthly view the way Monarch does. Categorizing
  transactions correctly is the job; how someone budgets against that data is theirs to
  decide.
- **Not built for running a business.** If you need invoicing, 1099 tracking, sales tax,
  or payroll, that's real small-business accounting software's job (including the
  original SlowBooks this is forked from), not ours.
- **Not free-as-strategy.** Mint was free and it still went away — free doesn't fix an
  app being someone else's to shut down. Whatever the eventual model, "free" isn't the
  point; owning the file is.
