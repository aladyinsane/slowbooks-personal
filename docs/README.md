# SlowBooks Documentation

The development process lives here: what we learned, what we decided, why, and what we
deliberately said no to.

## Start here

**[research/quickbooks-pain-points.md](research/quickbooks-pain-points.md)** — the most
important document in the repo. Everything else is downstream of it. QuickBooks is the
standard *despite* being disliked; understanding exactly why is the whole strategy.

Then **[product/principles.md](product/principles.md)** — the eight principles those
complaints produced. They exist to be used in arguments, and each one traces back to a
specific finding.

## Research

| Doc | What's in it |
|---|---|
| [quickbooks-pain-points.md](research/quickbooks-pain-points.md) | Why people dislike QuickBooks, grouped, with the design constraint each one implies — plus the honest counter-argument (the CPA is the gatekeeper) |
| [competitive-landscape.md](research/competitive-landscape.md) | Xero, Wave, FreshBooks, OneUp. What their gaps tell us — notably that Xero can't do local backups either, and that Wave proves free isn't enough |
| [core-features.md](research/core-features.md) | What a system like this needs beyond your original ask. Bank reconciliation, transfer detection, and why loan statements are harder than they look |
| [gaap-notes.md](research/gaap-notes.md) | Double-entry, debits/credits, cash vs. accrual, chart of accounts, period close. Engineering reference — items marked **[CPA REVIEW]** need a professional |

## Decisions (ADRs)

Numbered, immutable once accepted, superseded rather than edited. Every one has a real
**Consequences** section — an ADR with no downsides listed hasn't finished thinking.

| ADR | Decision | The interesting part |
|---|---|---|
| [0001](decisions/0001-local-first-sqlite.md) | Local-first, one SQLite file | Our strongest wedge — and its biggest risk is a user losing their only copy |
| [0002](decisions/0002-python-fastapi-react.md) | Python/FastAPI + React/TypeScript | Chose React for the one screen the product is about |
| [0003](decisions/0003-money-as-integer-minor-units.md) | Money is integer cents, never float | The most boring ADR and the one most likely to save the project |
| [0004](decisions/0004-double-entry-immutable-ledger.md) | Double-entry, append-only | How we keep a strict ledger *and* a bulk-delete button: void, don't delete |
| [0005](decisions/0005-deterministic-rules-categorization.md) | Rules, not a model | Explainability isn't negotiable — and the door we left open for ML |
| [0006](decisions/0006-starter-rules-announce-themselves.md) | Starter rules announce themselves | We can't make the guesses right, so we make them visibly guesses |
| [0007](decisions/0007-transfers-are-not-categories.md) | Transfers are not categories | Two individually-correct entries can still be a wrong answer |
| [0008](decisions/0008-export-is-a-feature-not-a-debug-tool.md) | Export is a product feature | The user already has the .db — that serves nobody who isn't technical |
| [0009](decisions/0009-reconciliation-is-an-assertion.md) | Reconciliation is an assertion | "The computer says it matches" is worth nothing; a human saying so is the artifact |
| [0010](decisions/0010-accounts-are-editable-but-never-deleted.md) | Accounts are editable, never deleted | "Hide" is the honest verb for what people actually mean |
| [0011](decisions/0011-closing-a-period-locks-it.md) | Closing a period locks it | Enforced by the database, because the invariant we left to discipline got skipped |
| [0012](decisions/0012-the-ledger-view-is-a-register.md) | The ledger view is a register | Every number is a door — principle 8's test, passed rather than aspired to |
| [0013](decisions/0013-ship-as-a-double-click-app.md) | Ship as one double-click app | Packaged the program, not the books — local-first survives the installer |

## Product

| Doc | What's in it |
|---|---|
| [principles.md](product/principles.md) | The eight principles, each traced to a complaint, each with a test — plus what we're deliberately *not* |
| [design.md](product/design.md) | The visual language: calm and document-like, and why. Colour means something or it isn't there |
| [roadmap.md](product/roadmap.md) | v0.1 through v0.5, sequenced by what proves the thesis |
| [future-features.md](product/future-features.md) | The parking lot, with reasons. Being on it is not a commitment — this is how we remember ideas instead of accreting them |

## Review

| Doc | What's in it |
|---|---|
| [cpa-review-request.md](review/cpa-review-request.md) | What we want a CPA to check and how they can check it. Blocks any real-user release |

## Engineering

| Doc | What's in it |
|---|---|
| [architecture.md](engineering/architecture.md) | Layers, data model, why reports are derived and never stored, performance budget |
| [contributing.md](engineering/contributing.md) | Branch/PR workflow, the rules that don't bend, setup |
| [packaging.md](engineering/packaging.md) | Building the double-click desktop app, and how to hand it to a non-technical tester |

## Conventions

- **ADRs are immutable.** Changed your mind? Write a new one that supersedes the old.
  Same reasoning as the ledger, for the same reason.
- **Research docs cite sources.** Claims about what users hate should be traceable to
  users saying so, not to our intuition.
- **Costs get written down.** Anywhere we chose a trade-off, the thing we gave up is on
  the page. A doc that only lists upsides is marketing.
