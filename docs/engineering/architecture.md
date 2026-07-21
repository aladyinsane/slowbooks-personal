# Architecture

## Shape

```
┌─────────────────────────────────────────┐
│  React + TypeScript (Vite)              │   frontend/
│  localhost:5173 (dev)                   │
└────────────────┬────────────────────────┘
                 │  JSON over HTTP (localhost only)
┌────────────────▼────────────────────────┐
│  FastAPI            localhost:8000      │   backend/slowbooks/api/
├─────────────────────────────────────────┤
│  Domain                                 │
│   ledger  · importing · categorize      │   backend/slowbooks/
│   reports · accounts   · money          │
├─────────────────────────────────────────┤
│  SQLite — one file, user-owned          │   ~/slowbooks-personal.db
│  debits==credits enforced by trigger    │
└─────────────────────────────────────────┘
```

Everything binds to `127.0.0.1`. There is no remote anything. See
[ADR 0001](../decisions/0001-local-first-sqlite.md).

## Layers

| Layer | Responsibility | Must not |
|---|---|---|
| `api/` | HTTP shape, validation, serialization | contain accounting rules |
| `ledger.py` | Post entries, void by reversal, enforce balance | know about HTTP or CSV |
| `importing/` | Parse CSVs into staged transactions | post to the ledger directly |
| `categorize/` | Match rules → suggest accounts | mutate the ledger |
| `reports/` | Read-only aggregation | write anything |
| `money.py` | All money arithmetic, parsing, formatting | be bypassed, ever |
| `db.py` | Connection, schema, migrations | contain business logic |

The rule that matters: **money arithmetic happens only in `money.py`, and the ledger is the
only writer of journal entries.** Both are enforced by review.

## Data model

```
accounts          code, name, type(asset|liability|equity|revenue|expense), normal_balance
journal_entries   date, description, source, reverses_entry_id, created_at
journal_lines     entry_id → account_id, amount_minor (signed), memo
import_batches    filename, account_id, imported_at, row_count
staged_transactions  batch_id, date, description, amount_minor, status, fingerprint
rules             priority, match_type, pattern, account_id, reason
```

Key points:

- **`amount_minor` is a signed integer of cents** ([ADR 0003](../decisions/0003-money-as-integer-minor-units.md)).
  Positive = debit, negative = credit. One signed column is simpler than
  two nullable columns and makes the balance check a plain `SUM(...) = 0`.
- **`SUM(amount_minor) = 0` per entry is enforced by a SQLite trigger.** The database itself
  refuses unbalanced entries. This is principle 6 made structural — application code cannot
  bypass it, so the invariant is real rather than aspirational.
- **`journal_entries` are append-only** ([ADR 0004](../decisions/0004-double-entry-immutable-ledger.md)).
  Corrections are new entries pointing back via `reverses_entry_id`.
- **Staged transactions are the mutable zone.** Imported rows are freely editable until
  posted. Immutability begins at posting — which is also where import-undo lives.
- **`fingerprint`** = hash of (account, date, amount, normalized description). Drives
  duplicate detection, since re-importing an overlapping CSV is the top way to corrupt books.

## Reports are derived, never stored

P&L, Balance Sheet, and Trial Balance are all `SUM(amount_minor)` over `journal_lines`
filtered by account type and date. Nothing is cached or denormalized.

This means reports **cannot** disagree with the ledger — a whole class of bugs that doesn't
exist for us. At small-business scale (tens of thousands of rows) SQLite aggregates this in
milliseconds, so the usual reason to denormalize doesn't apply. If we ever outgrow it,
materialized period balances are the escape hatch — but not before measuring.

## Performance budget

From principle 3, because bookkeeping is bulk repetition and per-action latency multiplies
by 200:

| Action | Budget |
|---|---|
| Categorize a transaction | < 100 ms |
| Any report @ 50k transactions | < 1 s |
| Import a 1,000-row CSV | < 5 s |

Being local, we start with a large head start — there's no network round-trip at all.
Exceeding budget is a bug.

## Testing strategy

The tests that matter most:

1. **The accounting identity.** `Assets = Liabilities + Equity + (Revenue − Expenses)` must
   hold after any sequence of operations. This is the single best correctness test we have —
   it catches whole categories of bugs at once.
2. **P&L net income must equal the Balance Sheet's period earnings.** The two reports have to
   agree; if they don't, one of them is lying.
3. **Money edge cases.** The classic float traps, allocation/rounding, parsing formats.
4. **The balance trigger actually fires.** Verify the database rejects unbalanced entries —
   an untested invariant isn't an invariant.
