"""Tests for the LAN-access PIN gate (access.py).

Two layers: pure unit tests against access.py's functions with no HTTP involved, and a
few HTTP-level tests against the real app via TestClient, mirroring test_api.py's
pattern. TestClient's default reported client host is "testclient" -- not loopback --
which is exactly what's needed to simulate a LAN peer without extra configuration; the
`client=("127.0.0.1", ...)` constructor argument simulates the owner's own computer.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from slowbooks import access, deps, settings
from slowbooks.main import app


class TestPinHashing:
    def test_round_trips(self):
        hashed = access.hash_pin("1234")
        assert access.verify_pin("1234", hashed)

    def test_rejects_wrong_pin(self):
        hashed = access.hash_pin("1234")
        assert not access.verify_pin("9999", hashed)

    def test_hashes_are_salted_differently(self):
        # Same PIN, different salt each time -- so two users with "1234" don't share a
        # stored hash.
        assert access.hash_pin("1234") != access.hash_pin("1234")


class TestLoopback:
    @pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
    def test_recognizes_loopback(self, host):
        assert access.is_loopback(host)

    @pytest.mark.parametrize("host", ["192.168.1.50", "10.0.0.5", "testclient", ""])
    def test_rejects_non_loopback(self, host):
        assert not access.is_loopback(host)


class TestLockout:
    def setup_method(self):
        access._failed_attempts.clear()

    def test_not_locked_out_below_threshold(self):
        for _ in range(access._LOCKOUT_THRESHOLD - 1):
            access.record_failure("1.2.3.4")
        assert not access.is_locked_out("1.2.3.4")

    def test_locked_out_at_threshold(self):
        for _ in range(access._LOCKOUT_THRESHOLD):
            access.record_failure("1.2.3.4")
        assert access.is_locked_out("1.2.3.4")

    def test_old_attempts_expire(self):
        # Simulate attempts from outside the lockout window.
        access._failed_attempts["1.2.3.4"] = [
            time.monotonic() - access._LOCKOUT_WINDOW_SECONDS - 1
        ] * access._LOCKOUT_THRESHOLD
        assert not access.is_locked_out("1.2.3.4")

    def test_lockout_is_per_ip(self):
        for _ in range(access._LOCKOUT_THRESHOLD):
            access.record_failure("1.2.3.4")
        assert not access.is_locked_out("5.6.7.8")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOWBOOKS_DB", str(tmp_path / "test.db"))
    deps.reset_connection()
    # access.py's state is process-global (it mirrors the host-bind decision, which is
    # itself process-lifetime), so it must be reset around every test that touches it --
    # otherwise one test's enabled LAN access or configured PIN would leak into the next.
    access._lan_enabled = False
    access._pin_hash = None
    access._sessions.clear()
    access._failed_attempts.clear()
    yield TestClient(app)
    access._lan_enabled = False
    access._pin_hash = None
    access._sessions.clear()
    access._failed_attempts.clear()
    deps.reset_connection()


def test_lan_access_off_by_default_every_endpoint_still_works(client):
    """The regression guard: with LAN_ACCESS_ENABLED at its default (off), the gate is a
    no-op and behaves exactly as it did before this feature existed, for a client that
    isn't loopback either."""
    assert client.get("/api/accounts").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_loopback_never_gated_even_with_lan_access_on(client):
    conn = deps.get_db()
    settings.set_bool(conn, settings.LAN_ACCESS_ENABLED, True)
    access.load(conn)
    access.set_pin(conn, "1234")

    loopback_client = TestClient(app, client=("127.0.0.1", 12345))
    assert loopback_client.get("/api/accounts").status_code == 200


def test_lan_peer_is_gated_once_enabled(client):
    conn = deps.get_db()
    settings.set_bool(conn, settings.LAN_ACCESS_ENABLED, True)
    access.load(conn)
    access.set_pin(conn, "1234")

    response = client.get("/api/accounts")
    assert response.status_code == 401
    assert response.json()["detail"]["locked"] is True


def test_lan_peer_without_pin_configured_gets_a_clear_403(client):
    conn = deps.get_db()
    settings.set_bool(conn, settings.LAN_ACCESS_ENABLED, True)
    access.load(conn)

    response = client.get("/api/accounts")
    assert response.status_code == 403


def test_unlock_with_correct_pin_grants_access(client):
    conn = deps.get_db()
    settings.set_bool(conn, settings.LAN_ACCESS_ENABLED, True)
    access.load(conn)
    access.set_pin(conn, "1234")

    unlock = client.post("/api/access/unlock", json={"pin": "1234"})
    assert unlock.status_code == 200
    assert "sb_session" in unlock.cookies

    # The cookie set above rides along on the same TestClient's subsequent requests.
    assert client.get("/api/accounts").status_code == 200


def test_unlock_with_wrong_pin_is_rejected(client):
    conn = deps.get_db()
    settings.set_bool(conn, settings.LAN_ACCESS_ENABLED, True)
    access.load(conn)
    access.set_pin(conn, "1234")

    response = client.post("/api/access/unlock", json={"pin": "0000"})
    assert response.status_code == 401
    assert client.get("/api/accounts").status_code == 401


def test_repeated_wrong_pins_trip_the_lockout(client):
    conn = deps.get_db()
    settings.set_bool(conn, settings.LAN_ACCESS_ENABLED, True)
    access.load(conn)
    access.set_pin(conn, "1234")

    for _ in range(access._LOCKOUT_THRESHOLD):
        client.post("/api/access/unlock", json={"pin": "0000"})

    response = client.post("/api/access/unlock", json={"pin": "1234"})
    assert response.status_code == 429


def test_network_toggle_is_loopback_only(client):
    # A LAN peer (the default TestClient host) must not be able to grant itself access,
    # even before LAN access is turned on.
    response = client.post("/api/settings/network", json={"enabled": True})
    assert response.status_code == 403


def test_network_toggle_works_from_loopback(client):
    loopback_client = TestClient(app, client=("127.0.0.1", 12345))
    response = loopback_client.post("/api/settings/network", json={"enabled": True})
    assert response.status_code == 200
    assert settings.get_bool(deps.get_db(), settings.LAN_ACCESS_ENABLED) is True


def test_pin_can_only_be_set_from_loopback(client):
    response = client.post("/api/access/pin", json={"pin": "1234"})
    assert response.status_code == 403

    loopback_client = TestClient(app, client=("127.0.0.1", 12345))
    response = loopback_client.post("/api/access/pin", json={"pin": "1234"})
    assert response.status_code == 200
