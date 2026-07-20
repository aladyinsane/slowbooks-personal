# ADR 0009 — Reconciliation is an assertion the user makes, not a state we compute

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decided by:** Lauren (product owner)

## Context

Every report we produce today means *"these are the numbers, probably."* The ledger is
internally consistent — debits equal credits, enforced by a trigger — but internal
consistency says nothing about whether the books match reality. A perfectly balanced set
of books can be missing every transaction from March.

Reconciliation is the step that closes that gap: you take the bank's own closing balance,
compare it to what SlowBooks thinks the account holds, and account for the difference. A
reconciled period is *proven* to match the bank.

Our research put this near the top of the "things you didn't ask for but need" list, and
it's the first thing an accountant asks about. It was moved into v0.1 for that reason.

The design question is what reconciliation *is*, structurally. Two framings:

- **A computed state.** We calculate whether the account matches and display it.
- **An assertion.** The user states "on this date, the bank said I had $X," and we record
  that claim, permanently, alongside whether it held.

## Decision

**A reconciliation is a durable record of a claim the user made, plus the evidence.**

1. The user supplies a **statement date** and the **bank's closing balance**. Those are
   facts from outside our system, and we never invent them.
2. We compute our balance as of that date, and the **difference**.
3. If the difference is zero, they may **finalize** the reconciliation. It's stored: date,
   bank balance, our balance, when it was done, and which entries it covered.
4. Each reconciled line is stamped with its `reconciliation_id`.
5. **Reconciliations are append-only**, like the ledger. Undoing one is a new record that
   reverses it, not a deletion.
6. **We never auto-reconcile.** Not even when the numbers obviously agree.

## Rationale

**"The computer says it matches" is worth nothing.** Principle 8 (*show the work*) is the
whole point here. The value of reconciliation isn't the arithmetic — it's that **a human
looked at the bank's number and said "yes, that's right."** If we computed and displayed
match/no-match, we'd have built a status indicator, not an audit trail. The assertion is
the artifact.

**It's the only thing that makes our reports mean anything.** The trigger proves the books
are *consistent*. Reconciliation is the only mechanism that proves they're *complete*. They
answer different questions, and we currently only answer the easy one.

**Storing our balance alongside the bank's is not redundant.** Both numbers are recorded at
finalize time. Ours is derivable — but only from today's ledger, and the whole point of a
reconciliation is that it was true *then*. If a later entry is backdated into a reconciled
period, we can detect it precisely because we wrote down what we believed at the time. A
recomputed number could never reveal that.

**Append-only for the same reason as the ledger.** A reconciliation is a statement about a
moment. Deleting one rewrites history; reversing one records that you changed your mind.
Consistent with [ADR 0004](0004-double-entry-immutable-ledger.md), and the reasoning is
identical.

**Statement accounts, reused.** [ADR 0007](0007-transfers-are-not-categories.md) modeled
`is_statement_account` for transfers, and it's exactly the right list here: you reconcile
things that issue statements. Predicted in that ADR's "revisit when," which is mild evidence
the model was right.

## Consequences

**Good**

- Reports gain a provenance they've never had: *this period is proven*, not *this period is
  arithmetically consistent*.
- The accountant gate gets a real answer. "Which periods are reconciled?" is among the first
  questions asked, and we can now answer it from data.
- Backdating into a reconciled period becomes **detectable**, because we recorded what we
  believed at the time. That's a whole class of silent corruption we currently cannot see.
- Cheap to build on what exists: statement accounts (ADR 0007) and `account_balance(as_of)`
  (already in `ledger.py`) do most of the work.

**Bad / accepted costs**

- **We ask the user for a number they must go find.** That's real friction, at the exact
  moment they'd like to be finished. It's also unavoidable: the bank's closing balance
  cannot be derived from data we hold — if we could compute it, reconciliation would be
  meaningless.
- **A non-zero difference is a dead end today.** We say *what* the gap is, not *why*. The
  genuinely useful version suggests candidates: a missing transaction, a duplicate, a
  transposition (a difference divisible by 9 is the classic tell). That's real work and
  it's deferred, which means v0.1 reconciliation helps most when it succeeds and least when
  it fails — the wrong way round, and worth being honest about.
- **No partial reconciliation.** Real bookkeepers tick off individual lines as they go. We
  reconcile a whole account to a date, all or nothing. Simpler, and wrong for anyone with a
  long statement.
- **Doesn't prevent backdating, only detects it.** Prevention is period locking (v0.2).
  Detection without prevention means the user finds out after the fact.
- **More schema, another migration.**

## Alternatives considered

**Compute and display "reconciled" automatically when balances agree.** Zero friction, and
tempting. Rejected: it's a status indicator wearing an audit trail's clothes. Nobody
asserted anything, so nothing is proven, and the moment the numbers agree by coincidence
we'd be actively lying. It would also mean a period could silently *un*-reconcile itself
when a backdated entry lands — the exact event we most need to surface.

**Line-by-line ticking.** What desktop accounting software does, and what bookkeepers
expect. Deferred, not rejected — it's the natural next step, and the schema (a
`reconciliation_id` per line) is deliberately shaped to allow it without migration pain.

**Reconcile against an imported statement's own rows** rather than a typed balance. Elegant:
the CSV is already there. But it only proves our rows match the rows we imported from that
CSV — circular. The bank's *closing balance* is an independent fact, which is the only kind
worth checking against.

## Revisit when

- Someone hits a non-zero difference and can't work out why. That's the moment this feature
  either earns its place or doesn't, and it's the strongest argument for building the
  discrepancy helpers.
- Period locking lands (v0.2), at which point reconciliation should probably imply a lock.
- Statements get long enough that all-or-nothing reconciliation stops being usable.
