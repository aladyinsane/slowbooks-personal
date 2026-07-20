# Competitive Landscape

Research date: 2026-07-16.

## The players

| Product | Entry price | Strength | Notable weakness |
|---|---|---|---|
| QuickBooks Online | $38–$275/mo | Ubiquity; CPA compatibility | Complexity, performance, lock-in, upselling |
| Xero | $15/mo | Clean UI; unlimited users on every plan; 1,000+ integrations; strong inventory and multi-currency | **No local backup of your data**; cannot track partial payments on invoices |
| Wave | Free | Genuinely free, no caps on invoices or users | Reviewers call core functions "ridiculously cumbersome"; no inventory, project accounting, or multi-currency |
| FreshBooks | $21/mo | Time tracking and project-based invoicing; timer feeds billable time into invoice lines | Weaker as a general ledger; aimed at billable-hours businesses |
| OneUp | $9/mo | Price | Small ecosystem |

## What the gaps tell us

**Xero cannot create local backups.** This is the most interesting finding in the whole
scan. The best-liked QuickBooks alternative has the *same* structural problem as
QuickBooks — your books live somewhere you can't reach. Our local-first position isn't just
differentiation against Intuit; it's differentiation against the entire field.

**Wave proves free isn't enough.** Wave is free with no caps and people still describe it as
cumbersome. Price is not the binding constraint on this market; usability is. This is
evidence for our thesis and a warning: if we ship a clumsy free tool, being free won't save
it.

**Xero has unlimited users on every plan** while QuickBooks meters seats. Seat-metering is a
form of the upsell problem. Since we're local-first single-user for now, this is moot at
v1 — but if we ever go cloud, per-seat pricing would reintroduce the dynamic we're
criticizing.

**FreshBooks shows the value of picking a user.** It's unapologetically for people who bill
by the hour, and it wins that segment by being shaped for it. We've picked the small
business owner doing their own books; we should be equally unapologetic.

## Where we deliberately do not compete (v1)

Being honest about this up front prevents the accretion problem we're criticizing:

- **Payroll.** Tax tables are a per-jurisdiction, continuously-updating compliance burden.
  This is a company, not a feature.
- **Inventory / COGS.** Real inventory accounting (FIFO/LIFO/weighted average) is deep. Xero
  already does it well.
- **Multi-currency.** FX revaluation touches every report. Big surface area.
- **Time tracking / project accounting.** FreshBooks owns this.
- **Invoicing and A/R.** Defensible to add later and a common request, but it's a whole
  sub-application (templates, delivery, payment collection, dunning). Not v1.
- **Bank feeds / direct bank connections.** Requires an aggregator (Plaid et al.), which
  means per-connection cost, credential handling, and a cloud component. CSV import is the
  lowest-common-denominator path and every institution supports it. Revisit later.

## The market position, in one line

*The books are yours, on your machine, in a file you can open — and categorizing a month of
transactions takes fifteen minutes, not an afternoon.*

## Sources

- [8 QuickBooks Alternatives for Small Business Accounting 2026 — Lovable](https://lovable.dev/guides/quickbooks-alternatives-small-business-accounting)
- [Best Bookkeeping Software 2026: QuickBooks vs Xero vs Wave — SD CPA](https://www.sdocpa.com/bookkeeping-software-comparison/)
- [QuickBooks vs Xero vs FreshBooks vs Wave: Full Comparison 2026 — Hustler's Library](https://hustlerslibrary.com/quickbooks-vs-xero-vs-freshbooks-vs-wave-full-comparison-2026/)
- [QuickBooks Alternatives: 10 Best Accounting Software Options — Beancount.io](https://beancount.io/blog/2026/04/05/quickbooks-alternatives-best-accounting-software-for-small-business)
- [Best QuickBooks Alternatives in 2026: Compared by Use Case — Xenett](https://www.xenett.com/blog/quickbooks-alternatives-2026)
