"""Gate for LAN access (see docs/decisions/0001-local-first-sqlite.md).

SlowBooks is local-first and single-user, with no accounts and no login. Binding the
server to the LAN (an opt-in setting, see settings.LAN_ACCESS_ENABLED and launch.py) is
the one case where that stops being true by default: anything else on the same Wi-Fi can
now reach the API. This module is the proportionate response -- a PIN, not a login
system. It exists to deter a curious housemate or neighbor, not to withstand an
attacker; that's why it's a stdlib hash and an in-memory session rather than a real auth
stack.

The owner's own computer is always exempt (is_loopback) -- they never see a PIN prompt,
LAN access on or off.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time

from fastapi import HTTPException, Request

from slowbooks import settings

COOKIE_NAME = "sb_session"

_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days -- a phone shouldn't re-enter a PIN daily
_LOCKOUT_WINDOW_SECONDS = 60
_LOCKOUT_THRESHOLD = 5

# Process-lifetime state. `_lan_enabled` mirrors the bind decision launch.py already made
# at startup (see settings.LAN_ACCESS_ENABLED) -- fixed until restart, same as the bind
# itself. `_pin_hash` is refreshed live on every set_pin(), since changing the PIN doesn't
# require rebinding the socket.
_lan_enabled = False
_pin_hash: str | None = None
_sessions: dict[str, float] = {}
_failed_attempts: dict[str, list[float]] = {}


def hash_pin(pin: str) -> str:
    """PBKDF2-HMAC-SHA256 with a random salt. Stdlib only -- proportionate for a home-Wi-Fi
    deterrent, not a hardened credential store."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return secrets.compare_digest(digest.hex(), digest_hex)


def is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1"}


def load(conn: sqlite3.Connection) -> None:
    """Read persisted state into the process-lifetime cache. Called once at startup."""
    global _lan_enabled, _pin_hash
    _lan_enabled = settings.get_bool(conn, settings.LAN_ACCESS_ENABLED)
    _pin_hash = settings.get(conn, settings.ACCESS_PIN_HASH)


def set_pin(conn: sqlite3.Connection, pin: str) -> None:
    global _pin_hash
    hashed = hash_pin(pin)
    settings.set_(conn, settings.ACCESS_PIN_HASH, hashed)
    _pin_hash = hashed
    # A changed PIN invalidates whatever anyone else on the network was already using.
    _sessions.clear()


def lan_access_enabled() -> bool:
    return _lan_enabled


def pin_configured() -> bool:
    return _pin_hash is not None


def check_pin(pin: str) -> bool:
    return _pin_hash is not None and verify_pin(pin, _pin_hash)


def issue_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.monotonic() + _SESSION_TTL_SECONDS
    return token


def session_is_valid(token: str) -> bool:
    expiry = _sessions.get(token)
    if expiry is None:
        return False
    if expiry < time.monotonic():
        del _sessions[token]
        return False
    return True


def record_failure(ip: str) -> None:
    now = time.monotonic()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < _LOCKOUT_WINDOW_SECONDS]
    attempts.append(now)
    _failed_attempts[ip] = attempts


def is_locked_out(ip: str) -> bool:
    now = time.monotonic()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < _LOCKOUT_WINDOW_SECONDS]
    _failed_attempts[ip] = attempts
    return len(attempts) >= _LOCKOUT_THRESHOLD


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def require_unlocked(request: Request) -> None:
    """Applied to the whole API router. A no-op unless LAN access is on, so every
    existing behavior (and every test written before this feature existed) is unchanged
    for anyone who never opts in."""
    if not _lan_enabled:
        return
    if is_loopback(_client_host(request)):
        return
    if not pin_configured():
        raise HTTPException(
            403,
            "Set an access PIN on this computer before using SlowBooks from another device.",
        )
    token = request.cookies.get(COOKIE_NAME)
    if token and session_is_valid(token):
        return
    raise HTTPException(401, detail={"locked": True, "pin_required": True})


def require_loopback(request: Request) -> None:
    """Only the computer's own owner may flip the LAN switch or change the PIN -- never
    a LAN peer, even an unlocked one."""
    if not is_loopback(_client_host(request)):
        raise HTTPException(403, "This can only be changed from this computer.")
