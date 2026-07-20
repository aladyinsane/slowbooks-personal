# ADR 0007 — Transfers are a distinct kind of transaction, not a category

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decided by:** Lauren (product owner)

## Context

Moving $5,000 from checking to savings is not income and not an expense. Nothing was
earned and nothing was spent — the money is still yours, in a different pocket. On the
P&L it must have **zero** impact; on the Balance Sheet one asset falls and another rises.

Our research called this out early as *the most common and most invisible error in
self-prepared books* ([core-features.md](../research/core-features.md)): a naively
categorized transfer becomes $5,000 of expense **and** $5,000 of income, inflating both
sides of the P&L. Net income still comes out right, which is exactly why nobody notices.

Building the categorization grid turned this from a known gap into an active defect:

- The category dropdown excludes bank accounts, because categorizing a transaction into
  the account it came from is nonsense.
- So for a transfer row, **there was no correct option in the list.** The user was forced
  to pick an expense or income account — i.e. forced to produce a wrong P&L.

That's worse than a missing feature. **We were making the correct answer unreachable**,
for anyone with two accounts, which is most businesses.

## Decision

A transfer is a **first-class kind of transaction**, not a category:

1. **Statement accounts are modeled explicitly.** `accounts.is_statement_account` marks
   the accounts you can import a statement for and move money between (checking, savings,
   credit card, loan). Previously the UI guessed at this with a code-prefix heuristic.
2. **Transferring to a statement account is a valid, offered choice**, presented as
   "Transfer to Business Savings" rather than as a category.
3. **A transfer posts exactly one journal entry**, regardless of how many statements it
   appears on: debit the destination, credit the source.
4. **Both sides are auto-detected and paired.** Opposite-sign, equal-amount rows in
   different accounts within a date window are matched and shown as a pair.
5. **Posting either side settles both.** The counterpart is marked posted against the
   *same* entry, never posted again.

## Rationale

**The double-count is the whole problem, and it's a trap.** A transfer between two
imported accounts produces two rows: `-5,000` in checking and `+5,000` in savings. Each,
categorized independently and correctly, produces the *same* journal entry — debit
savings, credit checking. Post both and you have moved $10,000. The books still balance,
the P&L is still untouched, and the Balance Sheet is silently wrong by $5,000.

This is the failure mode this ADR exists to prevent, and it is nastier than the naive
miscategorization it replaces, because it survives our best existing safety net: the
debits==credits invariant. **Two correct entries can still be a wrong answer.** Pairing
the rows is the only structural fix.

**Modeling statement accounts beats guessing.** The frontend was filtering with
`code.startsWith("10")`, which is a heuristic pretending to be a rule. It also wrongly
offered Accounts Receivable and Equipment as transfer targets. A user who adds a second
checking account should be able to say what it is rather than discover our prefix
convention.

**Detection is deliberately advisory.** Matched pairs are *suggested*, exactly like rule
suggestions, and the user can reject them (principle 8). Two genuinely unrelated $5,000
movements in the same week are rare but real, and we must not silently merge them.

## Consequences

**Good**

- The correct answer becomes reachable. That alone justifies the work.
- The most common invisible error in self-prepared books is now prevented structurally
  rather than warned about.
- One entry per transfer means the Balance Sheet is right no matter how many of your
  statements you import, or in what order.
- `is_statement_account` is the honest model, and it's reusable: it's the same list that
  bank reconciliation will need next.

**Bad / accepted costs**

- **False positives are possible.** Two unrelated $500 movements between two accounts in
  the same week will look like a transfer. Mitigated by suggesting rather than
  auto-posting, but a user who bulk-accepts could merge two real transactions into one.
  This is the sharpest edge here, and the reason detection never posts by itself.
- **False negatives too.** Banks post the two sides on different dates; a transfer that
  straddles our window won't match. The user can still categorize each side manually, but
  then must not post both — which is the trap again, so we guard it at post time as well
  as at detection time.
- **Amount must match exactly.** Wire fees, FX, or a bank that rounds will break the
  match. Fine for domestic transfers; wrong the moment multi-currency appears (already
  deferred).
- **More schema:** `is_statement_account`, `transfer_match_id`, another migration.
- **A concept the user must learn.** "Transfer" is a third thing alongside income and
  expense. Justified because it *is* a third thing — pretending otherwise is what
  produces wrong books.

## Alternatives considered

**A dedicated "Transfers" equity/clearing account.** Each side posts against a clearing
account that should net to zero. Simpler to implement and requires no pairing — but it
puts a fake account on the Balance Sheet, and a non-zero clearing balance (from exactly
the mismatches above) is a bug the user has to interpret. It converts a structural
problem into a reconciliation chore.

**Auto-post detected transfers.** Fastest path, and it's what the user "obviously" wants.
Rejected: it makes false positives silent and irreversible-ish, and it breaks principle 8.
Detection is a suggestion, always.

**Do nothing; document that users should categorize transfers to the other account.**
This was the status quo, and it was actively harmful: the UI didn't offer the option, and
if the user found it, posting both sides would double-count with no warning.

## Revisit when

- Users report missed matches, which would mean the date window or exact-amount rule is
  too strict.
- Multi-currency or wire fees arrive, both of which break exact-amount matching.
- Bank reconciliation lands — it needs the same `is_statement_account` concept and will
  independently surface any transfer we mispaired.
