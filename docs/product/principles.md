# Product Principles

These exist to be *used in arguments*. When a feature request arrives, it gets checked
against this list. A principle that never rejects anything isn't a principle, it's a slogan.

Each one traces to a specific finding in [../research/quickbooks-pain-points.md](../research/quickbooks-pain-points.md).

---

## 1. The books are the user's, not ours

One SQLite file. On their disk. Copyable to a thumb drive. Plus full export of every table
to CSV/JSON, and it works forever with no subscription check.

*Because:* forced migration and data lock-in generate more anger than any other complaint,
and the leading alternative (Xero) can't make local backups either. This is our wedge.

**Test:** if we shut down tomorrow, does the user still have working books? If no, we've
broken the core promise.

## 2. Accrual truth underneath, plain language on top

The ledger is strict double-entry, GAAP-shaped, append-only. The interface says
"$450 at Staples → Office Supplies," not "debit 6100, credit 2100."

*Because:* GAAP requires double-entry, but our user is a business owner, not a bookkeeper.
The rigor is for correctness; the vocabulary is for humans. These are not in conflict —
QuickBooks just leaks its internals.

**Test:** can a non-accountant complete the task without learning a new word?

## 3. Fast is a feature, and it's the cheapest one to win

Budget: **<100ms** for any categorization action, **<1s** for any report on a book of 50k
transactions. Regressions past budget are bugs, not tech debt.

*Because:* 3–10 second page loads on every transaction. Bookkeeping is bulk repetition —
per-action latency multiplies by 200. This is a straight win available to us for free
because we're local (no network round-trip at all).

**Test:** does it feel instant on the 200th repetition, not the first?

## 4. Every feature must earn its place on the screen

New features must say what they push out. Nested menus are forbidden. No feature is added
because a competitor has it.

*Because:* QuickBooks' UI is "a mish-mash of add-ons over time" — the predictable sum of 30
years of individually-reasonable additions with no removals. Accretion is the default
outcome, so resisting it must be deliberate.

**Test:** where does this live, and what leaves to make room?

## 5. Never make a human repeat themselves

Categorize a merchant once; we remember. Bulk-select and act once. Search actually
searches. Undo works on whole batches.

*Because:* "can't bulk-delete," "can't search transactions." These complaints carry outsized
heat because the workaround is manual repetition — the exact thing the software was bought
to eliminate.

**Test:** did the user do the same thing twice? That's our bug.

## 6. Correct by construction, not by user diligence

Debits must equal credits — enforced in the database, not asked of the user. Duplicate
imports are caught. Transfers are detected. Closed periods lock. Corrections reverse rather
than overwrite.

*Because:* the user is not an accountant and shouldn't need to be. Errors that require
accounting knowledge to *notice* are the dangerous ones — a transfer miscategorized as
income looks completely plausible on a P&L.

**Test:** can the user create an inconsistent state? If yes, that's our bug, not theirs.

## 7. Never upsell

No in-app ads, no locked features with an upgrade button, no adjacent-product promotion.

*Because:* users call the constant upselling "appalling," and Wave proves free alone doesn't
win. This is a *UI* principle as much as a business one: an upsell is a permanent tax on
every screen it occupies, and it makes the product about our revenue instead of their work.

**Test:** does this screen serve the user's task, or ours?

## 8. Show the work

Every number in a report drills down to the transactions that produced it. Every
auto-categorization says why. Every import says exactly what it did and offers undo.

*Because:* trust in accounting software is everything, and it's earned by being inspectable.
"The computer says $12,400" is worthless if the owner can't check it — and this is what
makes automation safe to accept rather than something to fear.

**Test:** can the user get from any number to the underlying transactions?

---

## Anti-principles: things we are deliberately not

- **Not the most featureful.** We lose that fight to Intuit by definition. See the
  deferred list in [future-features.md](future-features.md).
- **Not for accountants as primary users.** They're a *gate* we must pass (export
  fidelity), not the audience we optimize for.
- **Not for every business.** Multi-entity, multi-currency, inventory-heavy, payroll-heavy —
  those users should use Xero or QuickBooks, and we should tell them so honestly.
- **Not free-as-strategy.** Wave demonstrates free doesn't overcome cumbersome. Whatever the
  eventual model, it isn't "win on price."
