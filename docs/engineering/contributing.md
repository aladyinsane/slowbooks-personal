# Development Workflow

## Branch → PR → review

`main` is always working. No direct commits to `main`.

```bash
git checkout main && git pull
git checkout -b feat/short-description
# ... work, committing as you go ...
git push -u origin feat/short-description
gh pr create --fill
```

Branch naming:

| Prefix | For |
|---|---|
| `feat/` | new capability |
| `fix/` | bug fix |
| `docs/` | documentation only |
| `refactor/` | no behavior change |
| `test/` | tests only |

## PR expectations

- One reviewable idea per PR. If the description needs "and also," split it.
- Say **why**, not just what. The what is in the diff.
- New decisions of consequence get an ADR in `docs/decisions/`.
- Anything touching money gets tests.

## Continuous integration

Every push and PR runs [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml): the
backend job (`ruff` + `pytest` on Python 3.12, the declared floor) and the frontend job
(`tsc` + `vitest` + `build` on Node 24). Green is expected before merge. CI is a backstop,
not a substitute for the rule below — **load the page before you call it done.**

## ADRs

When a decision would make a future reader ask "why on earth is it like this," write it
down. Copy the format of an existing one in `docs/decisions/`. Numbered sequentially,
immutable once accepted — superseded by a *new* ADR that references the old one, never
edited into a lie. (Same principle as the ledger, for the same reason.)

The **Consequences** section must contain real costs. An ADR with no downsides listed hasn't
finished thinking.

## The rules that don't bend

1. **No `float` anywhere near money.** Integer minor units, always
   ([ADR 0003](../decisions/0003-money-as-integer-minor-units.md)).
2. **All money arithmetic goes through `money.py`.**
3. **Only `ledger.py` writes journal entries.**
4. **Never edit a posted journal entry.** Reverse it
   ([ADR 0004](../decisions/0004-double-entry-immutable-ledger.md)).
5. **Never break the accounting identity.** The tests will catch you; the reviewer should
   catch you first.

## Setup

**Backend** (works today):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
pytest                         # verify
uvicorn slowbooks.main:app --reload
```

### `WinError 10013` when the backend starts (Windows)

```
ERROR: [WinError 10013] An attempt was made to access a socket in a way forbidden by
its access permissions
```

Almost always means **something is already listening on port 8000** — usually an earlier
backend that never shut down. Windows binds sockets exclusively, so a second bind to a
held port fails with `WSAEACCES` (10013, "access forbidden") instead of the "address
already in use" you'd see on macOS or Linux. Same cause, unfamiliar code.

Free the port, then start again (PowerShell):

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

Look before you kill — confirm it's a stray backend and not something you want:

```powershell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess |
  Select-Object Id, ProcessName, Path
```

A `python.exe` under the project `.venv` is a leftover backend, safe to stop. The rarer
other cause of 10013 is port 8000 falling inside a Hyper-V/WSL reserved range — check with
`netsh interface ipv4 show excludedportrange protocol=tcp`, and if 8000 is listed, run the
backend on another port.

**Frontend** (Node 24.18.0 / npm 11.16.0 verified 2026-07-16):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to the backend on :8000
npm run typecheck
npm run test       # vitest — currently money.ts only
npm run build
```

The frontend test suite exists for one reason: `money.ts`. JavaScript is the worst
language in this stack for money — every number is a float64 and there's no int to fall
back on — so anything that turns a human's typing into cents gets tested. Rendering
doesn't have tests yet; money does.

Run the backend at the same time — the dev server proxies `/api` to `127.0.0.1:8000`.

## Verify in the real app, not just in tests

Both bugs found in this project so far were invisible to the test suite and obvious the
moment the actual app ran:

1. SQLite connections crossing FastAPI's threadpool (110 green tests, died on request #1).
2. Concurrent first requests racing on connection setup (green tests, 500 on first page
   load).

Both were concurrency at the process boundary, which unit tests structurally don't
exercise. **Load the page before you call it done.**

`gh` CLI is installed for PRs. If a command needs auth, run `gh auth login` yourself —
tooling should never be handed your credentials.
