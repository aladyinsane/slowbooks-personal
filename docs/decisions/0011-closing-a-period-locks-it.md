# ADR 0011 — Closing a period locks it, and the lock is enforced by the database

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decided by:** Lauren (product owner)
- **Completes:** [ADR 0009](0009-reconciliation-is-an-assertion.md)'s biggest gap

## Context

[ADR 0009](0009-reconciliation-is-an-assertion.md) shipped reconciliation and admitted its
own hole:

> **Doesn't prevent backdating, only detects it.** Prevention is period locking (v0.2).
> Detection without prevention means the user finds out after the fact.

That gap is worse than it sounds. The demo in PR #7 is the whole argument: post a January
bank fee into an already-reconciled period and `ledger_balanced` is true, the trial balance
balances, the Balance Sheet balances — **and January is silently wrong.** We can see it, and
we can only tell the user afterwards.

Meanwhile [gaap-notes.md](../research/gaap-notes.md) is direct about what closing means:

> Closing a period must **lock** it: no edits to entries dated within a closed period. This
> is what makes prior-period reports reproducible. If a correction is needed after close,
> the answer is a **reversing entry in the current period**, never a silent edit to history.

A prior-period report that can change after you've shown it to a bank is not a report.

## Decision

**Closing the books through a date freezes everything on or before it.**

1. **A close is a date, and it's global.** "The books are closed through 2026-01-31" means
   no entry dated on or before that may be posted, ever. Not per-account — closing the books
   is an entity-wide act, and a January that's final for checking but open for savings is
   not a closed January.
2. **The database enforces it**, with a trigger, exactly like debits==credits. Application
   code cannot bypass it and neither can a future us with a migration script.
3. **Corrections after close go in the current period.** `void()` now dates the reversing
   entry forward into the first open period rather than matching the original. This is the
   ADR 0004 follow-up finally coming due.
4. **Closes are append-only.** Reopening is a new record that reverses a close, never a
   deletion. The line moves back to the previous close.
5. **We warn, but don't refuse, on unreconciled or uncategorized work.** Closing with
   unreconciled accounts is a decision the user is allowed to make; closing while blind to
   it is not.

## Rationale

**A trigger, because the alternative has already failed twice.** Every invariant we enforce
in the database has held; every one we planned to enforce in application code was quietly
skipped by a caller. The categorization grid posted on selection despite ADR 0004 saying
drafts stay editable — the ADR was right and the code didn't ask it. A lock that lives in
`ledger.post()` is a lock until someone writes a second writer.

**Global, not per-account, even though reconciliation is per-account.** These are different
questions that people run together. Reconciliation asks *"does this account match its
statement?"* — necessarily per-account. Closing asks *"is this period final?"* — necessarily
about the whole entity, because the P&L is about the whole entity. You reconcile every
account and *then* close.

They connect at the close screen: closing offers to tell you which accounts aren't
reconciled through that date. That's the useful relationship, and it's advisory. Auto-locking
on reconcile — floated in ADR 0009's "revisit when" — would conflate the two and surprise
someone who reconciled one account.

**Reversals must fall forward, and this is the subtle part.** ADR 0004 dates a reversal to
match its original so the original period's reports stay truthful. Once that period is
closed, that's exactly wrong: the reversal would *change a closed period*, which is what
closing exists to prevent. So the rule inverts at the lock line — in an open period, match
the original; in a closed one, land in the first open period. That's not a workaround, it's
what real accounting does, and it's why "closed" and "correctable" aren't in conflict.

**Warn, don't refuse.** A user might close a period knowing an account isn't reconciled —
maybe the statement hasn't arrived. Refusing would make us the boss of their books. Telling
them, loudly, and then doing what they asked is the respectful version. This is the same
posture as ADR 0006: our job is to make sure they know, not to decide for them.

## Consequences

**Good**

- Prior-period reports become reproducible. That's the property that makes a P&L you handed
  to a bank in February still mean the same thing in June.
- The backdating hole from ADR 0009 closes. Detection stays (for entries that predate a
  close) but the common case is now impossible rather than merely visible.
- Enforced where it can't be argued with. A future feature that posts entries gets the lock
  for free, without knowing it exists.

**Bad / accepted costs**

- **"Why can't I record this?" for anyone importing an old statement.** Real friction, and
  the answer — "you closed the books through January" — is correct but annoying at the
  moment they hit it. Mitigated by naming the close date and the reopen path in the error,
  and by flagging closed-period rows *at import time* rather than at the end of a long
  categorization session.
- **Reversal dates now differ from their originals**, which makes the audit trail slightly
  harder to read: the void of a January entry appears in March. That's correct accounting
  and it will still confuse someone.
- **Reopening is a loaded gun.** We allow it, because refusing would be worse — but a user
  who reopens, edits, and re-closes has changed a report someone may have already seen. We
  record every close and reopen so the history is at least legible.
- **A global lock means a single slow user blocks everything.** Not a real problem at
  single-user scale; would be if we ever went multi-user.
- **More schema, another migration.**

## Alternatives considered

**Per-account locking, mirroring reconciliation.** Superficially tidy, and wrong: it can't
express "January is final", which is the only thing closing is for. A period half-closed is
just a period.

**Auto-lock on reconcile.** ADR 0009 raised it. Rejected: reconciling one account is not a
statement about the period, and silently freezing the books as a side effect of a different
action is exactly the kind of surprise that makes people distrust software.

**Refuse to close with unreconciled accounts.** Tempting, and paternalistic. The statement
may not have arrived; the user may not care about that account. Warn and obey.

**Soft lock — warn on posting into a closed period but allow it.** This is what we already
have, and ADR 0009 named it as the gap. A warning nobody must act on is a warning most
people won't.

## Revisit when

- Someone reopens a period to fix something and finds the audit trail confusing. That's the
  first place this design will hurt.
- The CPA review comes back (§4.5 asks precisely whether detection was acceptable and what
  year-end should look like — their answer may reshape this).
- Year-end closing entries arrive, which is a bigger question than a lock and the one we
  flagged as our weakest area.
