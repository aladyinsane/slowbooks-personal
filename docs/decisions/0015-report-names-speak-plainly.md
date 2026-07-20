# ADR 0015 — Report names speak plainly

- **Status:** Accepted
- **Date:** 2026-07-20
- **Decided by:** Lauren (product owner)

## Context

`docs/research/personal-finance-landscape.md` found that no personal-finance app
surveyed (Mint, YNAB, Monarch, Copilot) uses "Profit and Loss," "Balance Sheet," or
"Trial Balance" anywhere in its UI. The consistent consumer translations: Balance Sheet
→ Net Worth, P&L/Income Statement → Spending/Cash Flow. Trial Balance has no consumer
equivalent at all — it's a pure bookkeeping/audit concept nobody outside accounting ever
needs to see.

This was flagged as an open question and is now decided: rename in the API and UI.

## Decision

- **"Profit and Loss" → "Income & Expenses."** Not "Spending" or "Cash Flow" (the two
  translations the research found in the wild) — see Rationale.
- **"Balance Sheet" → "Net Worth."** Unambiguous; every app surveyed agrees.
- **"Trial Balance" stays internal/export-only.** It remains an API endpoint and a CSV
  in the data export, but is removed as an on-screen tab — no consumer app surfaces its
  equivalent, and it's checked automatically wherever `is_balanced`/`balanced` flags are
  already used app-wide.

**Scope of the rename** — three layers, each a real choice:

| Layer | Changed | Not changed |
|---|---|---|
| URL path | `/reports/profit-and-loss` → `/reports/income-and-expenses`; `/reports/balance-sheet` → `/reports/net-worth` | `/reports/trial-balance` |
| The `"report"` field value in the JSON response | `pnl.py` → `"Income & Expenses"`; `balance_sheet.py` → `"Net Worth"` | `trial_balance.py`'s `"Trial Balance"` |
| Frontend labels and types | `ReportsPanel.tsx` tab buttons and print title; `api.ts`'s `ProfitAndLoss`/`BalanceSheet` interfaces and `profitAndLoss`/`balanceSheet` client functions | — |
| Python function/module names | — | `reports.profit_and_loss()`, `reports.balance_sheet()`, `pnl.py`, `balance_sheet.py` stay as they are |

## Rationale

**"Income & Expenses" over "Spending" or "Cash Flow."** "Spending" undersells the report
— it shows income too, not just where money went. "Cash Flow" is the more tempting pick
since two competitors use it, but it's a real accounting term for something we don't
build: a formal Statement of Cash Flows separates operating, investing, and financing
activity, which needs more structure than "revenue minus expenses over a period." Calling
this report "Cash Flow" would set an expectation for anyone accounting-literate that the
report doesn't meet. "Income & Expenses" says exactly what's on the screen, in the same
plain-language spirit as the chart of accounts itself (principle 2).

**Trial Balance is the one report principle 2 doesn't apply to, and that's fine.** Every
other report translates a real question a person actually asks ("what's my net worth,"
"what did I spend"). Nobody asks "are my debits equal to my credits" — that's a
correctness check the software already runs on every post (the balance trigger, ADR
0004) and reports via `ledger_balanced`/`balanced` flags throughout the app. Keeping it
as an export/API-only artifact serves the same audience export already serves (ADR
0008) without cluttering the screen with a question nobody has.

**Not renaming the Python internals.** The decision was to rename this "in the API and
UI" — the URL, the JSON contract, and the screen. `reports.profit_and_loss()` and
`reports.balance_sheet()` as function names are implementation detail nobody outside the
codebase sees; renaming them would touch roughly 30 additional test call sites for no
user-facing benefit. If that symmetry turns out to matter later, it's a mechanical
follow-up, not a design decision.

## Consequences

**Good**

- Every report name on screen now answers a question a person actually asks, with zero
  translation required.
- One fewer tab, one fewer thing competing for attention on the main screen (principle
  4) — Trial Balance was never something a household needed at a glance.

**Bad / accepted costs**

- **A URL rename is a breaking API change**, even if this app has no external consumers
  today. Anyone who scripted against `/api/reports/profit-and-loss` breaks.
- **"Income & Expenses" is a judgment call, not a research finding.** Unlike "Net Worth,"
  which every surveyed app agreed on, this name was chosen over two names actually seen
  in the wild (Spending, Cash Flow) because neither fit precisely. It may not be the
  final word.
- **Trial Balance disappearing from the screen is a real loss for the rare user who does
  want to eyeball it** — mitigated by it staying one export/API call away, not deleted.

## Alternatives considered

**"Spending."** Shorter, matches how people talk ("check my spending this month"). Not
chosen because it undersells the income side of the same report — someone whose main
question is "how much did I make this month" would not think to click a tab called
"Spending."

**"Cash Flow."** The more common competitor translation. Not chosen because it's a real,
narrower accounting term (a Statement of Cash Flows) we don't build, and using it would
imply more rigor than the report actually has.

**Keep Trial Balance as a visible tab, just relabeled.** Rejected — there's no
plain-language name for "prove debits equal credits" that a household would recognize as
useful, because the underlying question isn't one they ask. Hiding it from the screen
while keeping it in the API/export is more honest than inventing a friendlier name for a
report nobody asked to see.

## Revisit when

- A future report actually needs the Statement-of-Cash-Flows structure (operating/
  investing/financing) — at that point "Cash Flow" becomes available again as an
  accurate name for a different report, not a renamed P&L.
- Someone asks where Trial Balance went — the answer is "still in your data export,"
  and if that keeps coming up, it's a sign the removal from the screen was wrong.
