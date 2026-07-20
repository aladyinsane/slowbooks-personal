# ADR 0002 — Python + FastAPI backend, React + TypeScript frontend

- **Status:** Accepted
- **Date:** 2026-07-16
- **Decided by:** Lauren (product owner)

## Context

We need a stack for a local-first desktop-ish app (see [ADR 0001](0001-local-first-sqlite.md)).
The dev machine has Python 3.14.6 and **no Node.js installed**.

## Decision

- **Backend:** Python 3.12+ / FastAPI / SQLite via the stdlib `sqlite3` module.
- **Frontend:** React + TypeScript, built with Vite.
- **Boundary:** a JSON HTTP API on localhost.

## Rationale

**Python for the ledger.** The accounting core benefits from Python's `decimal` and
`datetime`, its excellent stdlib `csv` module (bank CSVs are a swamp of encodings and
dialects), and `sqlite3` in the standard library. It's also the language already on the
machine.

**React/TypeScript for the UI.** The central screen is a transaction-categorization grid —
hundreds of rows, keyboard-driven, bulk-select, inline edit, optimistic updates. That is a
genuinely stateful, interaction-dense UI, and it's precisely where a component framework
earns its complexity. TypeScript's type checking is worth having in a money app.

**Why not server-rendered HTMX** (the alternative offered): simpler, no build step, and
would have worked — but the categorization grid with bulk-select and optimistic update is
the one screen where HTMX gets awkward, and it happens to be the screen the entire product
is about. Chose the tool that fits the hardest screen.

## Consequences

**Good**

- Right tool for each half: Python's data handling for the ledger, React's state management
  for the grid.
- FastAPI gives us OpenAPI docs for free, which makes the API self-documenting and gives us
  a path to typed client generation.
- The HTTP boundary keeps ADR 0001's "cloud later is a port, not a rewrite" honest.
- TypeScript catches a real class of bugs at the money/report boundary.

**Bad / accepted costs**

- **Two languages, two toolchains, two dependency trees.** More setup, more CI, more to keep
  current.
- **Two processes to run and eventually to package.** Shipping this as something a
  non-technical owner double-clicks is real work — likely PyInstaller for the backend with
  the built frontend as static assets. Deferred, but not free.
- **JS float risk at the boundary.** Mitigated by ADR 0003: money crosses the API as integer
  minor units and formatted strings, never as a float to be arithmetic'd in JS.
- **The two-process split has a real cost we've now paid once.** See below.

## Verified 2026-07-16

Node 24.18.0 installed; `tsc --noEmit` clean, `vite build` succeeds, and the app renders
against the live backend.

Worth recording, because it's the first evidence about this ADR's actual cost: the very
first real page load hit a **500**. The frontend opens with
`Promise.all([health, accounts])`, and two simultaneous requests against a cold backend
raced on lazy connection setup — both threads found the cache empty, both opened a
connection, and the loser died on `PRAGMA journal_mode = WAL` with "database is locked."
Fixed with double-checked locking in `deps.py`; regression test in `test_api.py`.

The lesson isn't "locking is hard." It's that **the client/server split creates
concurrency the domain code never sees**, and neither 110 unit tests nor the API tests
caught it — only loading the actual page did. That's a recurring tax of this decision,
not a one-off bug. Anything stateful in the backend now needs to assume concurrent
callers, despite ADR 0001 making this a single-*user* app. Single-user is not
single-threaded.

## Follow-ups

- [x] ~~Install Node.js LTS~~ — done 2026-07-16 (Node 24.18.0, npm 11.16.0).
- [ ] Decide packaging/distribution story before any public release.
- [ ] Consider generating a typed TS client from the FastAPI OpenAPI schema.
- [ ] `npm install` warns that esbuild's postinstall was blocked by npm's allow-scripts
      policy. Builds work regardless, so it isn't urgent — but it should be understood
      rather than ignored, since a half-installed native binary is the kind of thing that
      fails on someone else's machine and not ours.
