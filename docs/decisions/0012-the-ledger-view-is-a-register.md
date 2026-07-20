# ADR 0012 — The ledger view is a register, and every report number drills into it

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decided by:** Lauren (product owner)

## Context

Raised in review: *"I'd like to give the user a way to see their ledger other than just
downloading it."*

Checking that turned up something worse than the request implied. **The UI has never
called a report endpoint.** `profit-and-loss`, `balance-sheet` and `trial-balance` have
existed since PR #1 — tested, exported, correct — and were reachable only by `curl` or by
opening a ZIP.

The original brief asked for exactly two things by name: *"generate simple reports such as
a Profit and Loss statement and a Balance Statement."* We built them and never showed them.

And [principle 8](../product/principles.md) states a test we were failing outright:

> **Test:** can the user get from any number to the underlying transactions?

No. There was no "underlying transactions" screen at all.

So the question isn't just "add a ledger view". It's: what does *seeing your books* mean
for a small business owner?

## Decision

**Three things, one idea: every number is a door.**

1. **Reports on screen** — P&L, Balance Sheet, Trial Balance. The thing the brief asked
   for, finally visible.
2. **A register, not a journal.** The ledger view defaults to one account at a time, in
   date order, with a **running balance** — the shape of a checkbook or a bank statement.
   An "all accounts" mode exists for when you want the whole book.
3. **Every report line links to the transactions behind it**, filtered to that account and
   that period. That's principle 8's test, passed rather than aspired to.

Plus a description filter on the register, because *"can't search for keywords in
transactions"* is one of the two specific complaints our research catalogued, and here it's
nearly free.

## Rationale

**Register, because that's the shape people already know.** A general ledger — every line,
grouped by account — is what an accountant wants, and it's what our *export* already gives
them ([ADR 0008](0008-export-is-a-feature-not-a-debug-tool.md)). A journal — every entry in
date order, two lines each — is technically the truest view of a double-entry book and is
almost unreadable to a non-accountant.

A register is the third thing: one account, chronological, with a running balance. It looks
like a bank statement, which is the document our user has been reading their whole life.
This is principle 2 — rigor underneath, plain language on top — applied to the view rather
than to the ledger.

The accountant is still served: the general ledger lives in the export, where they can open
it in Excel. Different audiences, different artifacts, both honest.

**The running balance is the reason a register works, and it's also the reason it has to be
ordered carefully.** A running balance means nothing unless the order is stable and
deterministic, so it's computed over `(date, entry_id)` — never over insertion order, which
would silently reorder a page when an old transaction is imported late.

**Drill-down is not a nicety.** Principle 8 says trust is earned by being inspectable:
*"'the computer says $12,400' is worthless if the owner can't check it."* A P&L with a
$12,400 expense line and no way to see what's in it is exactly the thing we said we
wouldn't ship.

**Reports stay derived.** No caching, no materialization ([architecture.md](../engineering/architecture.md)).
The view is a view.

## Consequences

**Good**

- The original brief is finally satisfied. That should have happened in PR #1 and didn't.
- Principle 8's test passes for the first time.
- Search arrives early and cheaply against a named QuickBooks complaint.
- The register is where a lot of later work will hang: bulk operations (v0.3), attachments,
  and the "why is this number wrong" workflow all want this screen to exist.

**Bad / accepted costs**

- **A register hides the other side of every transaction.** Looking at Checking, you see
  "$450 Staples" and not the matching Office Supplies debit. That's the *point* — the
  double-entry is the part we're keeping out of the user's face — but it means the register
  is not the whole truth, and an accountant reading it would be misled about what we store.
  The export is where the whole truth lives, and this is a real seam.
- ~~**No pagination.**~~ **Amended 2026-07-17, same review cycle.** Review asked for an
  all-accounts view, which made the row count unbounded and forced the revisit
  immediately. Now: pages of 100, and an all-accounts mode. Three rules that carry the
  original decision through pagination:
  - **The running balance continues across pages** — page 2 opens where page 1 stopped,
    by summing the skipped rows in the same `(date, entry_id, line_id)` order. A page 2
    that restarted at the window's opening balance would be plausibly wrong on every row.
  - **The footer total describes the whole filtered set, not the page.** It's the number
    the user clicked on a report, and it must survive pagination or the drill-down
    contract quietly breaks.
  - **All-accounts has no running balance** — summing checking, a card and an expense in
    one column means nothing — **and no set total either**, because that total is always
    exactly $0.00: every entry's lines sum to zero, so the "total of everything" is the
    debits==credits invariant wearing a confusing hat. The API reports it honestly; the
    UI suppresses it.
- **Substring search, not full-text.** `LIKE '%staples%'` is not the "real search" v0.3
  promises. It's better than nothing and worse than the thing we said we'd build; calling
  it done would be the mistake.
- **More surface on a screen principle 4 says must earn its place.** Accepted: a product
  that generates reports nobody can look at has bigger problems than a busy page.

## Alternatives considered

**A journal view** (every entry, both lines, date order). Truest to the ledger, and the
right thing for an auditor. Rejected as the *default*: two rows per transaction with debits
and credits is the vocabulary ADR 0004 explicitly keeps off-screen. It's a good candidate
for a later "show me the accounting" toggle.

**A general ledger view** (every line, grouped by account). This is what the export already
serves to the audience that wants it. Building it into the UI too would duplicate the
export's job for the smaller of our two audiences.

**Reports as a printable page only**, letting export cover the rest. That's the next PR
(print stylesheet), and it isn't a substitute: a report you can only print is a report you
can't explore.

## Revisit when

- Someone's register gets slow. Pagination is the answer and we'll know the number.
- The substring search stops being enough — which is when v0.3's real search earns its
  place rather than being speculative.
- A CPA looks at the register and tells us the hidden other side is a problem.
