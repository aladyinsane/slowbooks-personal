"""Build the double-click desktop app (ADR 0013).

    python scripts/build_desktop.py

Two steps: build the frontend so FastAPI has something to serve, then bundle the Python
backend + uvicorn + that frontend into a single executable with PyInstaller. The result
is one file the tester double-clicks -- no Python, no Node, no terminal.

Run it from a venv that has the build extras:  pip install -e "backend[build]"
Builds for the OS you run it on; a Windows .exe comes out of Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FRONTEND_DIST = FRONTEND / "dist"
ENTRY = ROOT / "backend" / "slowbooks" / "launch.py"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def run(cmd: list[str], cwd: Path) -> None:
    print(f"\n$ {' '.join(cmd)}  (in {cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def build_frontend() -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    run([npm, "install"], cwd=FRONTEND)
    run([npm, "run", "build"], cwd=FRONTEND)
    if not FRONTEND_DIST.is_dir():
        sys.exit("frontend build produced no dist/ -- aborting")


def build_executable() -> None:
    # PyInstaller wants "<source><os.pathsep><dest-inside-bundle>". The frontend lands at
    # <bundle>/frontend, which is exactly where main._frontend_dir looks when frozen.
    add_data = f"{FRONTEND_DIST}{os.pathsep}frontend"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "SlowBooks",
        "--onefile",          # one file to hand over
        "--console",          # the window is the off switch: close it, server stops
        "--noconfirm",
        "--clean",
        "--paths", str(ROOT / "backend"),
        "--add-data", add_data,
        # uvicorn loads its loop/protocol/lifespan implementations by string at runtime,
        # so static analysis misses them without this.
        "--collect-submodules", "uvicorn",
        # Belt and braces: pull in the whole app package regardless of import style.
        "--collect-submodules", "slowbooks",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        str(ENTRY),
    ]
    run(cmd, cwd=ROOT)


def main() -> None:
    build_frontend()
    build_executable()
    exe = DIST / ("SlowBooks.exe" if os.name == "nt" else "SlowBooks")
    print("\nDone.")
    print(f"  {exe}")
    print("  Hand this single file to the tester. First launch on Windows shows a")
    print("  SmartScreen warning -> More info -> Run anyway (it's unsigned).")


if __name__ == "__main__":
    main()
