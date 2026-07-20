# Future Features / Parking Lot

Ideas worth remembering, with the reasoning attached. **Being on this list is not a
commitment.** Principle 4 says every feature must earn its place on the screen — this
document exists so ideas are *remembered* rather than *accreted*, which is precisely the
failure mode we diagnosed in QuickBooks.

Killing something is a valid outcome. Record it here when it happens.

Also see [Known risks in shipped features](#known-risks-in-shipped-features) near the
bottom — soft spots we shipped on purpose, recorded so we revisit them deliberately
instead of rediscovering them through a confused user.

---

**A note on this list:** it was written for the original small-business SlowBooks. Several
entries (invoicing, accounts payable, 1099s, payroll, sales tax, multi-entity, time
tracking, an accountant-collaboration mode) have no personal-finance analog and are
removed below rather than kept as dead weight. What's left is what's genuinely still a
candidate. New personal-finance-specific ideas belong here too — this list isn't
repopulated yet, just pruned.

## Strong candidates

### Receipt capture + attachments
Attach the receipt image to the transaction. Useful for returns, warranties,
reimbursement claims, and substantiating a tax deduction (medical expenses, charitable
donations) at filing time. OCR is a further step; attachments alone are most of the value
and much cheaper.

### Budgeting / forecasting
Budget vs. actual is a natural extension once the income/expense report exists, and cheap
by comparison. This is also where the three budgeting approaches noted in
[personal-finance-landscape.md](../research/personal-finance-landscape.md) (YNAB's
priority groups, Monarch's Fixed/Variable/Non-Monthly buckets, the 50/30/20 rule) would
actually get used — they're views over categorized transactions, not a reason to change
how we categorize.

---

## Deliberately deferred (with reasons)

### Multi-currency
FX revaluation touches every report and every balance. Most individuals track a single
currency; revisit if travel, expat, or foreign-account use turns out to be common among
our users.

### Bank feeds (Plaid et al.)
Tempting — CSV import is friction, and it's the one feature every mainstream competitor
(Mint, YNAB, Monarch, Copilot) leads with. **But:** requires an aggregator (per-connection
cost), credential handling, and a cloud component. That means a subscription and a
server, which undermines ADR 0001's whole position. Direct conflict with the product
thesis; would need a very good answer.

### Mobile app
Real need (photograph a receipt at the restaurant), but conflicts hard with local-first
single-user. Would need the sync layer from ADR 0001's "revisit when."

---

### Smarter category search
The picker matches whole words against an account's name and its guidance, with stopwords
dropped. Two known misses:

- **No stemming.** "paid the card" finds nothing; "pay the card" works, because *pay*
  happens to be a substring of *Paying*. A user who types the past tense gets told we
  have no such category.
- **No synonyms.** We mitigate this by *writing the guidance in the words people
  actually say* ("gas … car, van or truck" rather than "fuel … vehicles"), which is
  better writing regardless. But it only covers what we thought of.

Both are only worth solving if real users hit them. A stemmer is a dependency and a
synonym table is a maintenance burden; better guidance copy is free and helps anyway.

### Merge two accounts
Move all of B's history into A, then retire B. This is what people actually want when they
reach for Delete on an account that has history, and it's the honest version of the
request ([ADR 0010](../decisions/0010-accounts-are-editable-but-never-deleted.md)).

It's also a rewrite of posted history, which [ADR 0004](../decisions/0004-double-entry-immutable-ledger.md)
forbids — doing it properly means reversing and re-posting every affected entry, which is
real work and leaves a confusing audit trail. Worth doing when someone asks for it twice.

## Known risks in shipped features

Not feature ideas — things we shipped with a soft spot we chose to accept, recorded so
they're revisited deliberately rather than rediscovered by a confused user.

### Badge fatigue on the starter-rule warning
*From [ADR 0006](../decisions/0006-starter-rules-announce-themselves.md). Raised in review
of PR #3, 2026-07-16.*

Every starter-rule suggestion is badged `starter rule` so the user knows it's a guess. But
on **import #1 nearly every categorized row is a starter guess**, so the badge is on almost
every row — and a signal that fires everywhere isn't a signal. The exact scroll-past
behavior ADR 0006 exists to prevent could reassert itself against our own warning.

**Partly self-correcting.** User rules outrank builtins, so badges disappear as the user
teaches the system. Import #1 is badge-heavy; by month three it should be sparse and
meaningful. The mechanism is designed to fade.

**Why we shipped it anyway.** The alternative on day one is a silent wrong number. A noisy
warning beats no warning; we just shouldn't assume noisy is the finished state.

**If it becomes a real problem**, the honest fix is to let the *banner* carry the weight and
quiet the per-row badge — **not** to remove the distinction between a guess and a taught
rule. That distinction is the whole point; only its presentation is negotiable.

Other options if we get there:
- Badge only the *first* row per merchant, since the guess is per-merchant, not per-row.
- Sort starter guesses to the top on first import so review is a block of work with an end,
  rather than a scan of the whole file.
- Group the grid by merchant so one decision covers twenty rows (this is really the
  rule-suggestion feature from v0.3 wearing a different hat).

**What tells us it's happening:** the override rate on starter suggestions.

- High override rate → the pack is miscalibrated for real users. Fixable, and honestly the
  *better* outcome — it means people are reading the badges.
- **Near-zero override rate → more worrying**, not less. It probably means the badge is
  being ignored and guesses are being rubber-stamped. A number nobody checks is exactly the
  failure this was built to prevent, and it would look like success on every metric.

Needs real usage data. Blocked on having users.

---

## Speculative

### Local model for rule suggestion
The door left open in [ADR 0005](../decisions/0005-deterministic-rules-categorization.md).
The constraint that keeps it honest: the model proposes a **rule**, never categorizes a
transaction directly. Output stays deterministic, inspectable, editable.

### Sync layer (CRDT or hosted replica)
The unlock for multi-device, collaboration, and mobile — i.e. three of the biggest gaps at
once. Also genuinely hard, and the point where we'd risk becoming what we're competing
against. If we ever do this, "your local file remains authoritative and complete" is the
line we don't cross.

### Open file format / plain-text ledger export
An even stronger anti-lock-in stance: interop with Beancount/ledger-cli. Small audience,
but they're loud and aligned with our values, and it makes the ownership promise concrete
in a way even the SQLite file doesn't.

### Guided period-close checklist
Turn closing a period into a walkthrough — anything unreconciled or uncategorized,
surfaced before you lock the month. Turns "closing the books" from a bookkeeping ritual
into a plain end-of-month review.
