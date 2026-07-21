# Packaging the desktop app

How SlowBooks Personal becomes one double-click file, and how to give it to someone. The
*why* is in [ADR 0013](../decisions/0013-ship-as-a-double-click-app.md).

## Building it

From a virtualenv with the build extras:

```bash
cd backend
pip install -e ".[build]"      # pulls in PyInstaller
cd ..
python scripts/build_desktop.py
```

That does two things: builds the frontend (`npm install && npm run build`), then bundles
Python + uvicorn + that frontend into a single executable. The result:

```
dist/SlowBooks Personal.exe        # Windows
dist/SlowBooks Personal             # macOS / Linux
```

**It builds for the OS you run it on.** A Windows `.exe` comes out of Windows; you can't
build a Mac app from Windows. For other platforms, run the same script on that OS (or on a
matching GitHub Actions runner).

`dist/` and `build/` are git-ignored — the executable is a build artifact, not source.

## Giving it to someone

Hand over the **single file** `dist/SlowBooks Personal.exe`. Everything the app needs is
inside it — they don't install Python, Node, or anything else.

Include these instructions, because the first-launch warning is alarming if unexpected:

> 1. Double-click **SlowBooks Personal.exe**.
> 2. Windows will likely say **"Windows protected your PC."** This is because the app
>    isn't code-signed yet, not because anything is wrong. Click **More info**, then
>    **Run anyway**.
> 3. A small black window opens and stays open — that's SlowBooks Personal running. Your
>    web browser opens automatically to the app. **Leave the black window open** while you
>    use it; closing it stops SlowBooks Personal.
> 4. Your books are saved as `slowbooks-personal.db` **in the same folder as SlowBooks
>    Personal.exe**. To back them up, copy that file somewhere safe. To move to a new
>    computer, copy the whole folder across — the program and your books stay together.

(On macOS the equivalent of step 2 is **right-click the app → Open** the first time, which
gets past Gatekeeper.)

## What's going on underneath

- **One server.** `slowbooks.main` serves both the API and the built frontend, so the app
  is a single origin. `main._frontend_dir` finds the frontend inside the PyInstaller
  bundle (`sys._MEIPASS/frontend`) or, from source, at `frontend/dist`.
- **A free port.** `slowbooks.launch` binds an OS-assigned free port rather than a fixed
  one, so it can never collide with something already running. Set `SLOWBOOKS_PORT` to pin
  it (used by tests).
- **Their data.** A plain SQLite file. In a packaged build it's `slowbooks-personal.db`
  next to the executable (`deps._default_database_path`), so program and books travel
  together; in development it's `~/slowbooks-personal.db`. The filename deliberately
  differs from the original business SlowBooks' `slowbooks.db`, so the two don't silently
  overwrite each other's books if both are installed on one machine. `SLOWBOOKS_DB`
  overrides either default. We packaged the program, not the books.

## Known rough edges

Tracked as accepted costs in [ADR 0013](../decisions/0013-ship-as-a-double-click-app.md):
the unsigned-binary warning, per-OS builds, the visible console window, and the fact that
the executable isn't built or smoke-tested in CI yet.
