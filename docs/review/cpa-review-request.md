# SlowBooks — professional review request (retired for this fork)

**Status:** Retired 2026-07-20. Kept for history rather than deleted; not an active
request.

## Why this doesn't carry over

This document asked a CPA to check whether the original small-business SlowBooks got the
accounting right before real users touched it with real tax filings — in particular §4.2
(year-end closing entries), §4.3 (owner's draw vs. payroll vs. expense, and whether the
answer changes for a sole proprietor vs. an S-corp), and §4.7 (whether the chart of
accounts was missing anything a small business hits in month one).

None of that has a personal-finance equivalent. There's no owner's draw, no S-corp
election, and no CPA who reviews a household's checking account before they're allowed
to use it. The premise the whole request was built on — *"nobody will use this for real
books until someone qualified has looked at it"* — doesn't have an analogous gatekeeper
here.

## What actually still matters, and how it's covered

The *mechanics* §4.1–§4.6 asked about (does the P&L/Balance Sheet classify things
correctly, do the two statements agree, does reconciliation work, is the audit trail
sound, is a loan payment split correctly) aren't going unchecked — they're exactly what
[ADR 0004](../decisions/0004-double-entry-immutable-ledger.md)'s balance trigger,
`test_reports.py`'s accounting-identity test, and the reconciliation/period-locking test
suites verify continuously, on every change, rather than once via a point-in-time
professional sign-off. See [engineering/architecture.md](../engineering/architecture.md)
for how those invariants are enforced.

The one item from the original §6 gap table that's genuinely still open for personal use
is **loan payments can't be split** (a $1,200 payment booked as one line overstates
expenses and understates the remaining loan balance) — tracked as its own roadmap item
in [product/roadmap.md](../product/roadmap.md) under "Loan statements," not blocked on a
review that no longer applies.

## Revisit when

A different kind of professional-review gate turns out to matter for personal
finance — for example, if investment-account accuracy or tax-lot tracking ever gets
built and a financial advisor's or tax preparer's sign-off becomes the honest thing to
ask for. That would be a new document, not a revival of this one: the questions here
(owner's draw, S-corp treatment, month-one small-business chart gaps) would still have
no bearing on it.
