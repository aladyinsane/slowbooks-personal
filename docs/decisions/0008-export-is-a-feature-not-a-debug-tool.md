# ADR 0008 — Export is a product feature, not a debug tool

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decided by:** Lauren (product owner)

## Context

[ADR 0001](0001-local-first-sqlite.md) stakes the entire product on one claim: **the books
are yours.** That claim is what makes us different from QuickBooks (forced migration off
Desktop, "an absolute nightmare") *and* from Xero (which cannot make local backups at all).

Until export exists, the claim is a slogan. This was flagged in review of PR #1 and moved
into v0.1 for that reason.

There's an obvious objection: the user already has the SQLite file. Isn't that the export?

No, and the gap is the whole design. The file serves *one* audience — someone technical
enough to open SQLite. Export has two real audiences, and neither is that person:

1. **Someone leaving SlowBooks.** They need their data in something another tool can read.
   If leaving is hard, every promise we've made about ownership is decoration.
2. **The accountant.** Per [our research](../research/quickbooks-pain-points.md), the CPA
   is the gatekeeper — *"my accountant can't open your file"* beats any amount of nicety.
   A CPA wants a general ledger, not a `.db`.

## Decision

**One button produces a ZIP that a human, a spreadsheet, and another program can all read.**

The archive contains three layers:

1. **Raw table dumps** (`tables/*.csv`) — every row of every table, verbatim, including
   `amount_minor` as integer cents. Lossless and complete: this is the layer that makes
   "you can rebuild your books elsewhere" true rather than aspirational.
2. **Human/accountant reports** (`general-ledger.csv`, `trial-balance.csv`,
   `transactions.csv`) — joined, denormalized, with money as ordinary decimal strings.
   This is the layer a CPA actually opens.
3. **`README.txt` and `manifest.json`** — what this is, what each file means, what the
   money convention is, row counts, schema version, and how to read it without us.

Also `GET /api/export/json` for a single structured document, and a plain
`GET /api/export/database` that streams the SQLite file itself.

## Rationale

**Two money representations on purpose, and this is the sharp bit.** The raw dumps keep
integer cents because that is the only lossless form ([ADR 0003](0003-money-as-integer-minor-units.md)).
The reports emit `1234.56` because an accountant opening a CSV of `123456` will conclude
our software is broken, and they will be right to. Serving both audiences honestly means
writing the number twice, and `README.txt` says which is which so neither is mistaken for
the other.

**Completeness is the point, not convenience.** An export that covers "the important
tables" is one we get to define, and the user finds the gap at the worst moment — when
they're already leaving. Dumping every table is less clever and actually keeps the promise.

**The README matters more than it looks.** An export the user can't interpret without us
is still lock-in, just politer. The archive has to explain itself to someone who no longer
has access to this application, because that is exactly the scenario it exists for.

**Streaming the raw `.db` is the honest backstop.** It's the one artifact guaranteed to be
complete, because it *is* the book. Also the foundation for one-click backup (v0.2), which
[ADR 0001](0001-local-first-sqlite.md) names as its biggest risk.

## Consequences

**Good**

- The product's central claim becomes testable. `test_export.py` asserts every table is
  present and every row is accounted for — if we add a table and forget the export, CI says
  so. **Our anti-lock-in promise now has a failing test behind it, not a paragraph.**
- The accountant gate gets its first real answer (a general ledger they can open) well
  before v0.4.
- The `.db` endpoint gives v0.2's backup feature its plumbing for free.

**Bad / accepted costs**

- **Two money formats in one archive** is a genuine footgun. Mitigated by README and by
  segregating raw dumps under `tables/`, but someone will still sum the wrong column.
- **The export is a schema-shaped snapshot.** Raw dumps mirror our internal tables, so a
  consumer who builds on them is coupled to our schema — and we migrate it (v1→v2→v3
  already). The reports layer is the stable surface; the raw layer is the honest one.
  They serve different purposes and we should not pretend the raw layer is an API.
- **Whole-archive-in-memory.** Fine at small-business scale, wrong at 500k rows. Streaming
  is a later problem; noting it so it isn't a surprise.
- **No re-import.** Export is one-directional. "Restore from export" is a different, harder
  feature (it would have to reconcile against an append-only ledger). The `.db` file is the
  restore path today, and the README says so plainly rather than leaving the user to
  discover the gap.

## Alternatives considered

**Just tell users to copy the `.db` file.** Zero work, and it's what a technical user does.
Rejected: it serves nobody who isn't technical, and the accountant — the actual gatekeeper —
cannot open it.

**Export only the reports.** Smaller and prettier, and enough for the CPA. Rejected: it
doesn't let anyone leave with their data intact, which is the more important audience and
the one our whole strategy rests on.

**Plain-text ledger format (Beancount/ledger-cli).** Still on the
[parking lot](../product/future-features.md) and genuinely the strongest anti-lock-in
stance available. Rejected for now on audience size — CSV reaches everyone, and this
reaches a small if enthusiastic group.

## Revisit when

- Someone actually tries to leave and tells us what was missing. That's the only real test
  of this ADR, and we should ask rather than assume we passed.
- Row counts get big enough that in-memory archive construction hurts.
