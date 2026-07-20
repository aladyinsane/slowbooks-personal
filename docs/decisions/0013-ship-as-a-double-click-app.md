# ADR 0013 — The app ships as one double-click executable

- **Status:** Accepted
- **Date:** 2026-07-17
- **Decided by:** Lauren (product owner)

## Context

The first real user is about to try SlowBooks — and they are not technical. The
development setup is a non-starter for them: two servers (FastAPI on :8000, Vite on
:5173), a Python virtualenv, a Node install, `pip`, `npm`, and a terminal to run it all.
None of that can be put in front of someone whose job is running a small business.

The [roadmap](../product/roadmap.md)'s cross-cutting list already named this: *"Packaging:
a thing a non-technical owner can double-click"* — an [ADR 0002](0002-python-fastapi-react.md)
follow-up that has now come due for a concrete reason rather than a speculative one.

The hard constraint is [ADR 0001](0001-local-first-sqlite.md): local-first, one SQLite
file, no cloud. Whatever we ship must keep the books on the user's own machine. That rules
out the easy answer (host it somewhere and send a link).

## Decision

**One double-click file. No install, no Python, no Node, no terminal.**

Three parts:

1. **One server, not two.** The frontend builds to static files, and FastAPI serves them
   itself (`main._frontend_dir`). The whole product becomes a single origin — UI and
   `/api` on the same port. In development the two-server split stays; only the packaged
   build collapses it.
2. **A launcher that opens the browser.** `slowbooks/launch.py` picks a *free* port,
   waits until the server actually answers, then opens the default browser to it. The
   console window it runs in is the off switch: close it, the server stops.
3. **PyInstaller bundles it into one executable.** `scripts/build_desktop.py` builds the
   frontend, then bundles Python + uvicorn + that frontend into a single `SlowBooks.exe`.
   The tester double-clicks it; their books are saved as `slowbooks.db` **next to the
   executable** — so the program and the books travel together (see
   `deps._default_database_path`). In development the default stays `~/slowbooks.db`, and
   `SLOWBOOKS_DB` overrides either.

The UX for now is a browser tab. A native app window (pywebview) is a deliberate *later*
step, not a rejected one — this is the smallest thing that gets the app into a tester's
hands.

## Rationale

**One server removes the whole class of "did you also start the backend?" failure**, which
no non-technical user could diagnose.

**A free port sidesteps the port-collision problem** ([the `WinError 10013` snag](../engineering/contributing.md))
by never touching a fixed port at all. The tester never learns what a port is.

**One file is the simplest possible hand-off.** "Double-click this" is the entire
instruction. A folder of files invites someone to double-click the wrong one.

**Local-first is untouched, and made literal.** The data is still a SQLite file on their
disk — now sitting right beside the executable, so the whole thing is a folder you can put
on a USB stick or copy to a new machine and it just works. We packaged the *program*, not
the *books* — the promise of ADR 0001 holds, and is easier to see.

## Consequences

**Good**

- A non-technical user can run SlowBooks. That was previously impossible.
- Verified first-run works: a fresh machine with an empty database gets the default chart
  of accounts seeded and lands on a working, empty book ready to import into.
- The free-port launcher makes the app immune to the port collisions that bit development
  twice.

**Bad / accepted costs**

- **Unsigned binary.** Windows SmartScreen will warn (*"Windows protected your PC" → More
  info → Run anyway*); macOS Gatekeeper would need a right-click → Open. For one tester,
  coaching them through it is fine; a wider release needs code signing (Apple $99/yr, a
  Windows cert $100–400/yr). This is the single biggest rough edge for a non-technical
  user and we are choosing to eat it for now.
- **Per-OS builds.** PyInstaller builds for the OS it runs on. Windows is covered because
  that's where we build; a macOS or Linux tester needs a build on that platform (a macOS
  GitHub Actions runner is the clean path now that CI exists).
- **The console window is the off switch** — functional, but a stray black terminal is not
  elegant. pywebview removes it later.
- **~18 MB, and a one-file build extracts to a temp dir on each launch** (a second or two
  on first run). Acceptable; a one-folder build trades the single-file hand-off for a
  faster start if that ever matters.
- **The executable is not built in CI.** It's a manual `scripts/build_desktop.py` run, so
  there's no automated proof the bundle still runs. A release workflow that builds and
  smoke-tests the exe is the eventual fix.

## Alternatives considered

**A native window now (pywebview / Tauri / Electron).** pywebview is the right *next* step
and shares this entire backend; deferred only to get something testable sooner. Tauri
would still run the Python backend as a sidecar (more moving parts). Electron ships a
second runtime on top of the Python one — heaviest of all.

**Docker.** A non-technical user installing Docker Desktop and running a CLI is further
from "double-click" than where we started. Rejected outright.

**Host it and send a link.** The easiest thing to build and a direct violation of
ADR 0001. The moment the books live on our server, the product is the thing it exists to
replace.

**Ship the source with a start script.** Still needs Python and Node installed. Fine for a
developer, useless for the actual tester.

## Revisit when

- We hand it to more than a handful of people — code signing stops being optional.
- A tester turns up on macOS or Linux — add a CI build for that platform.
- The console window confuses someone — do the pywebview native-window pass.
- We want confidence the bundle keeps working — add a release workflow that builds and
  smoke-tests the exe.
