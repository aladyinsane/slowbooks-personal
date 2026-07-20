# SlowBooks

Simple accounting software that doesn't suck to use.

Small-business accounting built around one idea: **the books belong to the person who
keeps them.** One SQLite file on your own disk, GAAP-correct double-entry underneath,
plain language on top, and no subscription that can hold your data hostage.

## Why

QuickBooks is the industry standard and is widely disliked — for its accreted UI, 3–10
second page loads, ~70% price increases, constant upselling, and forced migration off
Desktop. The alternatives don't fix the root problem: even Xero, the best-liked of them,
[cannot make local backups of your data](docs/research/competitive-landscape.md).

The full diagnosis is in [docs/research/quickbooks-pain-points.md](docs/research/quickbooks-pain-points.md),
and the principles it produced are in [docs/product/principles.md](docs/product/principles.md).

## Status

**v0.1 feature-complete.** Import → categorize → post → reconcile → report runs end to
end, driven through the real UI. Transfers are handled correctly (the error that quietly
inflates most self-prepared books), your books export in one click, and a reconciled
period is *proven* against the bank rather than merely balanced.

| | |
|---|---|
| ✅ Double-entry ledger, balance enforced by SQLite trigger | ✅ P&L, Balance Sheet, Trial Balance |
| ✅ CSV import (dialect sniffing, duplicate detection) | ✅ Deterministic rules + starter pack |
| ✅ Default GAAP-shaped chart of accounts | ✅ Void-by-reversal audit trail |
| ✅ Transfers between your own accounts | ✅ React categorization grid |
| ✅ **Data export** — ZIP, general ledger, raw .db | ✅ **Bank reconciliation** |
| ✅ Visual design pass (light + dark) | ✅ **Period locking** — closes the books through a date |
| ✅ **Reports on screen** + register with drill-down | ✅ Transaction search (substring) |
| ✅ **Print stylesheet** — P&L and Balance Sheet as clean statements | ⬜ Refunds, backup, split transactions (v0.2+) |

Not production software. It has not been reviewed by a CPA. Don't file taxes with it yet.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"
pytest                           # 110 tests, ~1s
uvicorn slowbooks.main:app --reload
```

Then open <http://localhost:8000/docs> for the API, and try a sample statement:

```bash
curl -F "file=@sample-data/chase-checking-jan2026.csv" \
     "http://localhost:8000/api/imports?account_id=1"
```

Your books live at `~/slowbooks.db`. Copy it anywhere; it's yours. Override with
`SLOWBOOKS_DB`.

Frontend — run alongside the backend, which it proxies to:

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

## Layout

```
backend/        FastAPI + SQLite. The ledger, import, rules, reports.
frontend/       React + TypeScript (Vite). Stub for now.
docs/
  research/     QuickBooks pain points, competitors, GAAP, core features
  decisions/    ADRs — why things are the way they are
  product/      Principles, roadmap, parking lot
  engineering/  Architecture, dev workflow
sample-data/    Fictional bank/card statements for testing
```

Start with [docs/README.md](docs/README.md).

## The rules that don't bend

1. **No `float` anywhere near money.** Integer cents, always ([ADR 0003](docs/decisions/0003-money-as-integer-minor-units.md)).
2. **Never edit a posted journal entry.** Reverse it ([ADR 0004](docs/decisions/0004-double-entry-immutable-ledger.md)).
3. **Never break `Assets = Liabilities + Equity`.**

See [docs/engineering/contributing.md](docs/engineering/contributing.md).

## License

SlowBooks is free software under the [GNU Affero General Public License v3.0](LICENSE) — copyright © 2026 Lauren Chaplinski.

Use it, study it, change it, share it. The one obligation: if you distribute it — or run a modified version as a network service — you pass the same freedoms on, source included. That network clause is the point. Accounting software has a habit of getting locked up and rented back to you; the AGPL is what keeps a hosted SlowBooks from becoming the thing it was built to replace.
