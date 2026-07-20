# ADR 0004 — Double-entry, append-only ledger

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

GAAP accepts only accrual-basis accounting, and accrual requires double-entry bookkeeping.
A Balance Sheet — which you named as a required report — is not derivable from single-entry
data at all.

Separately, period close requires that prior periods be reproducible, and auditability
requires that history not be rewritten.

## Decision

Two structural commitments:

**1. Strict double-entry.** Every economic event is a `journal_entry` with two or more
`journal_lines`. Total debits equal total credits, enforced by a database trigger — not by
application code that someone might bypass, and not by asking the user to be careful.

**2. Append-only.** Journal entries are never updated or deleted after posting. Corrections
are *new* entries that reverse the original (`reverses_entry_id`). Nothing is destroyed.

Both are foundation decisions: there is no cheap path to either one later.

## Consequences

**Good**

- GAAP-correct by construction. A Balance Sheet is possible and always balances.
- The `Assets = Liabilities + Equity + (Revenue − Expenses)` identity becomes a continuously
  verifiable invariant — our single best correctness test.
- Complete audit trail for free. Every number's history is intact.
- Closed periods stay reproducible, because history is immutable by construction rather than
  by policy.

**Bad / accepted costs**

- **More rows.** A 400-row CSV becomes 400 entries and 800+ lines. SQLite doesn't care at
  our scale.
- **The reversal concept is unfamiliar** to non-accountants. Users expect Edit and Delete.
- **Cannot fix a typo in place.** A misspelled memo requires a reversal + re-post. This
  feels absurd for cosmetic fields.
- **Correction UX is genuinely harder** than `UPDATE`.

## Resolving the UX tension

The costs above are real, and "can't bulk-delete transactions" is already a top QuickBooks
complaint (see [research](../research/quickbooks-pain-points.md)). Being rigid here risks
recreating a problem we're trying to solve. The resolution:

- **Void, don't delete.** Voiding posts a reversing entry. The UI can offer *bulk void* that
  feels exactly like bulk delete. The complaint is about tedium, not about destroying data —
  so we can satisfy it fully without compromising the ledger.
- **Immutability applies to posted, financial facts only.** Non-financial metadata (memo,
  attachments, category *labels* that don't move money) may be mutable. **Amounts, dates,
  and accounts may not.**
- **Draft state before posting.** Imported transactions sit unposted and freely editable
  until the user commits them. Immutability starts at posting, which is where it matters —
  and this is where import-undo lives.
- **Unposted rows are the escape hatch.** The strictness only bites after the user has said
  "yes, this is real."

## Alternatives considered

**Single-entry with derived reports.** Rejected: cannot produce a Balance Sheet, isn't GAAP,
and has no migration path. This is the decision that separates accounting software from a
spreadsheet.

**Double-entry with mutable entries.** Rejected: much easier UX, but breaks period-close
reproducibility and audit trail. Retrofitting immutability later means migrating live
financial data — the worst possible time.

**Event-sourced ledger.** Considered and deferred. Append-only *is* the valuable 80% of
event sourcing; full event sourcing adds projection/replay machinery we don't need at
single-user scale.
