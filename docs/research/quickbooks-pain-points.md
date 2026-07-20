# Why People Dislike QuickBooks

Research date: 2026-07-16. Sources at the bottom.

This is the most important document in the repo. SlowBooks exists because QuickBooks is
the industry standard *despite* being widely disliked. Every complaint below is a design
constraint for us, not just a competitor's problem.

## The complaints, grouped

### 1. Interface complexity and non-intuitiveness (the headline problem)

Users describe the UI as cumbersome and inefficient, with nested menus that read as "a
mish-mash of add-ons over time that make no sense." The recurring theme is that the
software accreted features for 30 years without anyone removing anything. Simple tasks are
either buried several menus deep or turn out to be impossible.

**What this means for us:** the menu structure must be designed once, deliberately, and
defended. Every new feature must answer "where does this live, and what does it push out?"
An accreted UI is not a bug that appears at the end; it's the sum of many individually
reasonable additions. See [product/principles.md](../product/principles.md).

### 2. Product-line confusion

Online, Desktop Pro/Premier/Enterprise, Self-Employed, and Payroll add-ons have
overlapping and inconsistent feature sets. Choosing the "right" product is itself a
research project, and features present in one edition are silently missing in another.

**What this means for us:** one product. One edition. No feature gating as a sales tactic.

### 3. Data lock-in and forced migration

This is the complaint with the most anger behind it. Intuit discontinued QuickBooks
Desktop — 2024 was the last version, with new subscription sales stopping September 30,
2024. Desktop 2023 loses all support May 31, 2026; Desktop 2024 on September 30, 2027.
After the cutoff, payroll tax tables freeze, bank feeds disconnect, and security patches
stop — so the software you "own" degrades on a schedule you don't control.

Commentators openly name data lock-in as the business rationale: once the data is in the
vendor's cloud, switching gets hard. Users forced onto QuickBooks Online describe the
migration as "an absolute nightmare" with loss of access to prior information.

**What this means for us:** this is our single strongest wedge. Local-first, one SQLite
file the owner can copy to a thumb drive, plus a full CSV/JSON export of every table. Our
answer to "what if SlowBooks disappears?" must be "you still have your books." See
[decisions/0001-local-first-sqlite.md](../decisions/0001-local-first-sqlite.md).

### 4. Pricing and upselling

Reported increases of ~70% — from $589 to nearly $1,000/year for the same basic feature
set — with another increase in February 2026 for existing subscribers. Users call the
constant upselling of adjacent services "appalling." QuickBooks Online lists at $38–$275
per month, against Wave (free), OneUp ($9/mo), Xero ($15/mo), FreshBooks ($21/mo).

**What this means for us:** no in-app upsells, ever. Not a monetization decision so much as
a UI one: an upsell is a permanent tax on every screen it lives on.

### 5. Performance

Pages reportedly take 3–10 seconds to load *on every transaction*. Users also report
increasing bugginess over time.

**What this means for us:** performance is a first-class feature, and it's the easiest one
to win. Bookkeeping is a bulk-entry activity — the user is doing the same action 200 times
in a row. At 5s per action that's a miserable afternoon; at 50ms it's fifteen minutes. We
should set an explicit budget and hold it. See
[engineering/architecture.md](../engineering/architecture.md).

### 6. Specific missing features that make people irrationally angry

These come up over and over and are individually small:

- Cannot bulk-delete multiple transactions in expenses.
- Cannot search for keywords within transactions.

**What this means for us:** bulk operations and real search are table stakes, not v2. The
reason these complaints have such heat is that the workaround is *manual repetition* — the
exact thing the software was bought to eliminate.

## The synthesis

The complaints are not independent. They share a root cause: **QuickBooks optimizes for the
buyer, not the user.** Feature-list breadth wins the purchase decision; the person
categorizing 200 transactions on a Sunday night pays the cost. Lock-in means that cost never
converts into churn, so it never converts into a fix.

Our whole strategy follows from inverting that. We can't out-feature Intuit and shouldn't
try. We can be dramatically better for the person actually doing the work, and we can make
leaving easy — which is the only credible signal that we intend to keep earning the stay.

## The uncomfortable counter-argument

We should be honest that people stay with QuickBooks for a real reason: **their accountant
expects it.** Xero and QBO are described as the two most CPA-compatible platforms in 2026.
Being pleasant to use does not overcome "my CPA can't open your file." This is a genuine
risk to the whole thesis, and it argues that accountant-facing export fidelity (clean
trial balance, general ledger export, journal entry export) is a survival feature rather
than a nice-to-have. Tracked in [product/roadmap.md](../product/roadmap.md).

## Sources

- [I HATE QUICKBOOKS COMPLAINTS — QuickBooks Community](https://quickbooks.intuit.com/learn-support/en-us/reports-and-accounting/i-hate-quickbooks-complaints/00/1219480)
- [Does anyone else think QuickBooks is terrible? — QuickBooks Community](https://quickbooks.intuit.com/learn-support/en-us/employees-and-payroll/does-anyone-else-think-quickbooks-is-terrible/00/1044704)
- [Why do so many people hate QuickBooks? — Quora](https://www.quora.com/Why-do-so-many-people-hate-QuickBooks)
- [QuickBooks is the worst — The Picture Framers Grumble](https://www.thegrumble.com/threads/quickbooks-is-the-worst.101064/)
- [Intuit Reviews — Trustpilot](https://www.trustpilot.com/review/quickbooks.com)
- [Longtime Customer Deeply Disappointed by QuickBooks Pricing and Forced Migration](https://quickbooks.intuit.com/learn-support/en-us/other-questions/longtime-customer-deeply-disappointed-by-quickbooks-pricing-and/00/1559617)
- [QuickBooks Desktop Discontinued: The Last Version and What Intuit Isn't Telling You — BizBooks Pro](https://www.bizbooks.pro/blog/quickbooks-desktop-discontinued.html)
- [QuickBooks Desktop service discontinuation policy — Intuit](https://quickbooks.intuit.com/learn-support/en-us/help-article/feature-preferences/quickbooks-desktop-service-discontinuation-policy/L17cXxlie_US_en_US)
- [QuickBooks Desktop Discontinued 2026: Dates, Options & Migration Guide — SD CPA](https://www.sdocpa.com/quickbooks-desktop-discontinued/)
