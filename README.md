# SlowBooks Personal

Simple personal finance software that doesn't suck to use.

Personal finance built around one idea: **the books belong to the person who keeps
them.** One SQLite file on your own disk, real double-entry underneath, plain language
on top, and no subscription that can hold your data hostage.

## Why

Mint shut down and took years of transaction history with it. YNAB and Monarch charge
a recurring fee to keep using data you entered yourself, and linking your bank through
a service like Plaid means a third party sits between you and your own numbers. None of
them let you just... have the file.

This is a fork of SlowBooks — small-business accounting software built on the same
premise — retargeted for a household instead of a business: no Accounts Receivable, no
cost of goods sold, no owner's draw. Just checking, savings, cards, loans, and where the
money actually goes.

The principles it was built on are in [docs/product/principles.md](docs/product/principles.md).

## Status

**v0.1 feature-complete.** Import → categorize → post → reconcile → report runs end to
end, driven through the real UI. Transfers are handled correctly (the error that quietly
inflates most self-prepared books), your books export in one click, and a reconciled
period is *proven* against the bank rather than merely balanced.

| | |
|---|---|
| ✅ Double-entry ledger, balance enforced by SQLite trigger | ✅ P&L, Balance Sheet, Trial Balance |
| ✅ CSV import (dialect sniffing, duplicate detection) | ✅ Deterministic rules + starter pack |
| ✅ Personal chart of accounts | ✅ Void-by-reversal audit trail |
| ✅ Transfers between your own accounts | ✅ React categorization grid |
| ✅ **Data export** — ZIP, general ledger, raw .db | ✅ **Bank reconciliation** |
| ✅ Visual design pass (light + dark) | ✅ **Period locking** — closes the books through a date |
| ✅ **Reports on screen** + register with drill-down | ✅ Transaction search (substring) |
| ✅ **Print stylesheet** — P&L and Balance Sheet as clean statements | ⬜ Refunds, backup, split transactions (v0.2+) |

Not production software. Don't rely on it as your only record.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"
pytest                           # 390 tests, ~13s
uvicorn slowbooks.main:app --reload
```

Then open <http://localhost:8000/docs> for the API, and try a sample statement:

```bash
curl -F "file=@sample-data/chase-checking-jan2026.csv" \
     "http://localhost:8000/api/imports?account_id=1"
```

Your books live at `~/slowbooks-personal.db` — named so it doesn't collide with the
original business SlowBooks' `slowbooks.db` if you have both installed. Copy it anywhere;
it's yours. Override with `SLOWBOOKS_DB`.

Frontend — run alongside the backend, which it proxies to:

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

## Layout

```
backend/        FastAPI + SQLite. The ledger, import, rules, reports.
frontend/       React + TypeScript (Vite). Stub for now.
docs/
  research/     Background from the original SlowBooks (small-business accounting)
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

SlowBooks Personal is free software under the [GNU Affero General Public License v3.0](LICENSE) — copyright © 2026 Lauren Chaplinski.

Use it, study it, change it, share it. The one obligation: if you distribute it — or run a modified version as a network service — you pass the same freedoms on, source included. That network clause is the point. Financial software has a habit of getting locked up and rented back to you; the AGPL is what keeps a hosted SlowBooks from becoming the thing it was built to replace.
