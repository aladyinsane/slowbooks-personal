"""Where the book file lives.

The packaged app puts it next to the executable so program and books travel together;
development keeps it in home. An explicit SLOWBOOKS_DB overrides both (ADR 0013).
"""

from __future__ import annotations

import sys
from pathlib import Path

from slowbooks import deps


def test_the_env_override_always_wins(monkeypatch, tmp_path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("SLOWBOOKS_DB", str(target))
    # Even while looking packaged, an explicit path beats the default.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert deps.database_path() == target


def test_development_default_is_the_home_folder(monkeypatch):
    monkeypatch.delenv("SLOWBOOKS_DB", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert deps.database_path() == Path.home() / "slowbooks-personal.db"


def test_packaged_default_sits_next_to_the_executable(monkeypatch, tmp_path):
    monkeypatch.delenv("SLOWBOOKS_DB", raising=False)
    fake_exe = tmp_path / "SlowBooks Personal.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    result = deps.database_path()

    assert result == fake_exe.resolve().parent / "slowbooks-personal.db"
    assert result.parent == tmp_path.resolve()
