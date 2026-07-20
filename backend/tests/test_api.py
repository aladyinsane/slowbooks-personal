"""API tests.

These exercise the real HTTP stack. That matters more than it sounds: FastAPI runs
sync endpoints in a worker threadpool, and the first version of db.connect() worked
perfectly in every unit test and fell over on the first real request
(sqlite3.ProgrammingError: objects created in a thread can only be used in that same
thread). Only a test that goes through the actual app catches that class of bug.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from slowbooks import deps
from slowbooks.main import app

CHASE = """Transaction Date,Post Date,Description,Category,Type,Amount
01/15/2026,01/16/2026,KROGER 00123 SEATTLE WA,Shopping,Sale,-450.00
01/22/2026,01/23/2026,PAYROLL DEPOSIT,Income,Deposit,2500.00
01/28/2026,01/29/2026,ZZQQ MYSTERY VENDOR,Other,Sale,-99.00
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOWBOOKS_DB", str(tmp_path / "test.db"))
    deps.reset_connection()
    yield TestClient(app)
    deps.reset_connection()


@pytest.fixture
def checking_id(client):
    accounts = client.get("/api/accounts").json()
    return next(a for a in accounts if a["code"] == "1000")["id"]


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ledger_balanced": True}


def test_book_file_reports_where_the_book_lives(client, tmp_path):
    # A request has to touch the db first, so the file actually exists on disk.
    client.get("/api/health")

    body = client.get("/api/book-file").json()

    resolved = (tmp_path / "test.db").resolve()
    assert body["path"] == str(resolved)
    assert body["directory"] == str(resolved.parent)
    assert body["filename"] == "test.db"
    assert body["exists"] is True
    assert body["size_bytes"] > 0


@pytest.mark.parametrize("attempt", range(10))
def test_concurrent_requests_are_safe(tmp_path, monkeypatch, attempt):
    """Regression for two separate concurrency bugs, both found by loading the real page.

    1. The frontend opens with Promise.all([health, accounts]). Two simultaneous
       requests hit a cold backend; both threads found the connection cache empty and
       each built one, and the loser died on `PRAGMA journal_mode = WAL` with
       "database is locked".

    2. Deeper, and the reason a shared connection had to go entirely: two threads
       running the *same SQL* shared one entry in sqlite3's statement cache. Thread B's
       execute() reset the prepared statement out from under thread A, so A's
       fetchone() returned None -- a COUNT(*) with no row -- and /api/health died
       subscripting it. sqlite3.threadsafety is 3, so nothing raised; the data was
       just quietly wrong. In an accounting system that is the worst possible shape
       for a bug.

    Repeated because races are probabilistic: the original reproduced ~25% of runs, so
    a single attempt would have shipped green three times out of four.
    """
    monkeypatch.setenv("SLOWBOOKS_DB", str(tmp_path / f"race-{attempt}.db"))
    deps.reset_connection()

    client = TestClient(app)
    results: list[int] = []
    errors: list[str] = []

    def hammer(path: str) -> None:
        try:
            response = client.get(path)
            results.append(response.status_code)
            if response.status_code != 200:
                errors.append(f"{path} -> {response.status_code}: {response.text[:200]}")
        except Exception as exc:
            errors.append(f"{path} raised {type(exc).__name__}: {exc}")

    # Repeating the same path matters: identical SQL is what collides in the statement
    # cache. Varied paths alone would not have caught bug 2.
    paths = ["/api/health", "/api/accounts"] * 6
    threads = [threading.Thread(target=hammer, args=(path,)) for path in paths]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    deps.reset_connection()
    assert not errors, f"concurrent requests failed: {errors[:3]}"
    assert results == [200] * len(paths)


def test_concurrent_writes_do_not_corrupt_the_ledger(tmp_path, monkeypatch):
    """Concurrent posting must leave the books balanced.

    Single-user does not mean single-threaded, and the ledger's invariants are worth
    proving under the concurrency FastAPI actually creates.
    """
    monkeypatch.setenv("SLOWBOOKS_DB", str(tmp_path / "writes.db"))
    deps.reset_connection()

    client = TestClient(app)
    checking = next(
        a for a in client.get("/api/accounts").json() if a["code"] == "1000"
    )["id"]

    rows = "\n".join(
        f"2026-01-{day:02d},KROGER {day:05d},-{day}.00" for day in range(1, 13)
    )
    batch = client.post(
        f"/api/imports?account_id={checking}",
        files={"file": ("chase.csv", f"Date,Description,Amount\n{rows}\n", "text/csv")},
    ).json()["batch_id"]

    staged = client.get(f"/api/imports/{batch}/transactions").json()
    errors: list[str] = []

    def post_one(staged_id: int) -> None:
        try:
            response = client.post(f"/api/staged/{staged_id}/post", json={})
            if response.status_code != 200:
                errors.append(f"{staged_id}: {response.status_code} {response.text[:150]}")
        except Exception as exc:
            errors.append(f"{staged_id} raised {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=post_one, args=(row["id"],)) for row in staged]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"concurrent posts failed: {errors[:3]}"
    assert client.get("/api/health").json()["ledger_balanced"]
    trial = client.get("/api/reports/trial-balance?as_of=2026-12-31").json()
    assert trial["balanced"]
    deps.reset_connection()


def test_default_chart_is_seeded(client):
    accounts = client.get("/api/accounts").json()
    assert len(accounts) > 30
    assert {a["type"] for a in accounts} == {
        "asset", "liability", "equity", "revenue", "expense"
    }


def test_new_account_must_fit_its_type_range(client):
    ok = client.post("/api/accounts", json={"code": "6975", "name": "Dues", "type": "expense"})
    assert ok.status_code == 201

    # 1200 is an asset code; asking for an expense there is a mistake worth blocking.
    bad = client.post("/api/accounts", json={"code": "1200", "name": "Nope", "type": "expense"})
    assert bad.status_code == 400
    assert "range" in bad.json()["detail"]


def test_full_import_to_report_flow(client, checking_id):
    upload = client.post(
        f"/api/imports?account_id={checking_id}",
        files={"file": ("chase.csv", CHASE, "text/csv")},
    )
    assert upload.status_code == 200
    summary = upload.json()
    assert summary["rows_read"] == 3
    assert summary["auto_categorized"] == 2
    assert summary["needs_review"] == 1

    staged = client.get(f"/api/imports/{summary['batch_id']}/transactions").json()
    assert len(staged) == 3
    # Principle 8: every suggestion explains itself.
    assert all(row["reason"] for row in staged if row["suggested_account_id"])

    posted = client.post(f"/api/imports/{summary['batch_id']}/post").json()
    assert posted == {"posted": 2, "still_pending": 1}

    pnl = client.get("/api/reports/profit-and-loss?start=2026-01-01&end=2026-12-31").json()
    assert pnl["revenue"]["total_minor"] == 250000
    assert pnl["net_income_minor"] == 205000

    sheet = client.get("/api/reports/balance-sheet?as_of=2026-12-31").json()
    assert sheet["balanced"]

    trial = client.get("/api/reports/trial-balance?as_of=2026-12-31").json()
    assert trial["balanced"]


def test_bad_csv_returns_400_not_500(client, checking_id):
    response = client.post(
        f"/api/imports?account_id={checking_id}",
        files={"file": ("junk.csv", "some,random,columns\n1,2,3\n", "text/csv")},
    )
    assert response.status_code == 400
    assert "date column" in response.json()["detail"]


def test_pnl_rejects_backwards_period(client):
    response = client.get("/api/reports/profit-and-loss?start=2026-12-31&end=2026-01-01")
    assert response.status_code == 400


def test_void_via_api(client, checking_id):
    upload = client.post(
        f"/api/imports?account_id={checking_id}",
        files={"file": ("chase.csv", CHASE, "text/csv")},
    )
    batch_id = upload.json()["batch_id"]
    staged = client.get(f"/api/imports/{batch_id}/transactions").json()
    target = next(row for row in staged if row["suggested_account_id"])

    entry_id = client.post(f"/api/staged/{target['id']}/post", json={}).json()["entry_id"]

    voided = client.post(f"/api/entries/{entry_id}/void", json={"reason": "personal"})
    assert voided.status_code == 200
    assert voided.json()["reversing_entry_id"] != entry_id

    # Voiding twice is a user error, not a server error.
    again = client.post(f"/api/entries/{entry_id}/void", json={})
    assert again.status_code == 400
    assert client.get("/api/health").json()["ledger_balanced"]


def test_user_rule_created_via_api_is_applied_on_import(client, checking_id):
    accounts = client.get("/api/accounts").json()
    meals = next(a for a in accounts if a["code"] == "6450")["id"]

    created = client.post(
        "/api/rules", json={"pattern": "ZZQQ MYSTERY", "account_id": meals}
    )
    assert created.status_code == 201

    # The rule the user just wrote should pick up the row that needed review.
    upload = client.post(
        f"/api/imports?account_id={checking_id}",
        files={"file": ("chase.csv", CHASE, "text/csv")},
    )
    assert upload.json()["needs_review"] == 0


def test_invalid_regex_rule_returns_400(client, checking_id):
    response = client.post(
        "/api/rules",
        json={"pattern": "[unclosed", "account_id": 1, "match_type": "regex"},
    )
    assert response.status_code == 400


def test_staged_rows_expose_their_own_account(client, checking_id):
    """The UI needs this to avoid offering "transfer to" the account money is already in.

    Found by driving the grid: the transfer dropdown listed the row's own source
    account, an option that could only ever return 400.
    """
    upload = client.post(
        f"/api/imports?account_id={checking_id}",
        files={"file": ("chase.csv", CHASE, "text/csv")},
    )
    staged = client.get(f"/api/imports/{upload.json()['batch_id']}/transactions").json()
    assert all(row["account_id"] == checking_id for row in staged)


def test_transfer_to_own_account_is_rejected(client, checking_id):
    upload = client.post(
        f"/api/imports?account_id={checking_id}",
        files={"file": ("chase.csv", CHASE, "text/csv")},
    )
    staged = client.get(f"/api/imports/{upload.json()['batch_id']}/transactions").json()

    response = client.post(
        f"/api/staged/{staged[0]['id']}/post", json={"account_id": checking_id}
    )
    assert response.status_code == 400
    assert "own bank account" in response.json()["detail"]


def test_transfer_flow_via_api(client):
    """Both statements, both batches posted, money moves exactly once (ADR 0007)."""
    accts = client.get("/api/accounts").json()
    checking = next(a for a in accts if a["code"] == "1000")["id"]
    savings = next(a for a in accts if a["code"] == "1010")["id"]

    out = client.post(
        f"/api/imports?account_id={checking}",
        files={"file": ("c.csv", "Date,Description,Amount\n2026-03-10,TO SAVINGS,-5000.00\n",
                        "text/csv")},
    ).json()
    into = client.post(
        f"/api/imports?account_id={savings}",
        files={"file": ("s.csv", "Date,Description,Amount\n2026-03-11,FROM CHECKING,5000.00\n",
                        "text/csv")},
    ).json()
    assert into["transfer_pairs_found"] == 1

    client.post(f"/api/imports/{out['batch_id']}/post")
    # Posting the second statement must not move the money again.
    assert client.post(f"/api/imports/{into['batch_id']}/post").json()["posted"] == 0

    pnl = client.get("/api/reports/profit-and-loss?start=2026-01-01&end=2026-12-31").json()
    assert pnl["net_income_minor"] == 0  # moving your own money is not income or expense

    sheet = client.get("/api/reports/balance-sheet?as_of=2026-12-31").json()
    savings_line = next(
        line for line in sheet["assets"]["lines"] if line["name"] == "Savings"
    )
    assert savings_line["amount_minor"] == 500000  # not 1,000,000
    assert sheet["balanced"]


def test_unlinking_a_transfer_restores_a_normal_row(client):
    accts = client.get("/api/accounts").json()
    checking = next(a for a in accts if a["code"] == "1000")["id"]
    savings = next(a for a in accts if a["code"] == "1010")["id"]

    client.post(
        f"/api/imports?account_id={checking}",
        files={"file": ("c.csv", "Date,Description,Amount\n2026-03-10,PAID VENDOR,-500.00\n",
                        "text/csv")},
    )
    batch = client.post(
        f"/api/imports?account_id={savings}",
        files={"file": ("s.csv", "Date,Description,Amount\n2026-03-11,REFUND,500.00\n",
                        "text/csv")},
    ).json()["batch_id"]

    staged = client.get(f"/api/imports/{batch}/transactions").json()
    assert staged[0]["is_transfer"]  # a plausible false positive

    assert client.delete(f"/api/staged/{staged[0]['id']}/transfer-match").status_code == 204

    after = client.get(f"/api/imports/{batch}/transactions").json()
    assert not after[0]["is_transfer"]


class TestExportEndpoints:
    def test_zip_download_has_sensible_headers(self, client, checking_id):
        client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("chase.csv", CHASE, "text/csv")},
        )
        response = client.get("/api/export/zip")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        assert ".zip" in response.headers["content-disposition"]

    def test_downloaded_zip_actually_opens(self, client, checking_id):
        import io
        import zipfile

        client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("chase.csv", CHASE, "text/csv")},
        )
        response = client.get("/api/export/zip")
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        # testzip() returns the first corrupt member, or None if the archive is sound.
        assert archive.testzip() is None
        assert "README.txt" in archive.namelist()

    def test_json_export_endpoint(self, client):
        data = client.get("/api/export/json").json()
        assert "manifest" in data and "tables" in data
        assert len(data["tables"]["accounts"]) > 30

    def test_database_download_is_a_real_sqlite_file(self, client, tmp_path):
        response = client.get("/api/export/database")
        assert response.status_code == 200
        # Every SQLite file starts with this magic string. If it doesn't, we handed the
        # user something that isn't their book.
        assert response.content[:16] == b"SQLite format 3\x00"

    def test_downloaded_database_is_usable_and_current(self, client, checking_id, tmp_path):
        """The restore path has to actually restore.

        WAL mode keeps recent writes in a sidecar file, so copying the .db without a
        checkpoint can hand back a book missing its latest transactions -- a backup
        that silently omits data is worse than no backup.
        """
        import sqlite3

        upload = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("chase.csv", CHASE, "text/csv")},
        )
        client.post(f"/api/imports/{upload.json()['batch_id']}/post")

        copy = tmp_path / "restored.db"
        copy.write_bytes(client.get("/api/export/database").content)

        restored = sqlite3.connect(str(copy))
        restored.row_factory = sqlite3.Row
        entries = restored.execute(
            "SELECT COUNT(*) AS n FROM journal_entries WHERE posted_at IS NOT NULL"
        ).fetchone()["n"]
        restored.close()
        assert entries == 2  # the writes we just made survived the copy


def test_database_download_works_on_a_fresh_book(client):
    """A user who exports before importing anything should get a file, not a 404.

    The route originally checked the file's existence before anything had created it,
    so a brand-new install would refuse to hand over its own book.
    """
    response = client.get("/api/export/database")
    assert response.status_code == 200
    assert response.content[:16] == b"SQLite format 3\x00"


class TestReconciliationEndpoints:
    """ADR 0009 over the real HTTP stack."""

    STATEMENT = (
        "Date,Description,Amount\n"
        "2026-01-02,OPENING DEPOSIT,10000.00\n"
        "2026-01-10,RENT PAYMENT,-1000.00\n"
        "2026-01-20,KROGER 00123,-500.00\n"
    )

    def _book(self, client, checking_id):
        batch = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("jan.csv", self.STATEMENT, "text/csv")},
        ).json()
        client.post(f"/api/imports/{batch['batch_id']}/post")

    def test_status_starts_empty(self, client):
        status = client.get("/api/reconciliation/status").json()
        # Only statement accounts, and nothing reconciled yet.
        codes = {s["account"].split()[0] for s in status}
        assert codes == {"1000", "1010", "1020", "2100", "2500"}
        assert all(s["reconciled_through"] is None for s in status)

    def test_preview_reports_a_match(self, client, checking_id):
        self._book(client, checking_id)
        preview = client.get(
            "/api/reconciliation/preview"
            f"?account_id={checking_id}&statement_date=2026-01-31"
            "&statement_balance_minor=850000"
        ).json()
        assert preview["can_reconcile"]
        assert preview["difference_minor"] == 0
        assert preview["book_balance"] == "$8,500.00"
        assert preview["hint"] is None

    def test_preview_reports_a_gap_in_plain_language(self, client, checking_id):
        self._book(client, checking_id)
        preview = client.get(
            "/api/reconciliation/preview"
            f"?account_id={checking_id}&statement_date=2026-01-31"
            "&statement_balance_minor=840000"
        ).json()
        assert not preview["can_reconcile"]
        # 850000 - 840000 cents = $100.00. Bank is $100 lighter than the book, e.g. a
        # fee we haven't imported.
        assert preview["difference"] == "$100.00"
        assert "more than the bank" in preview["hint"]

    def test_preview_does_not_reconcile(self, client, checking_id):
        self._book(client, checking_id)
        client.get(
            "/api/reconciliation/preview"
            f"?account_id={checking_id}&statement_date=2026-01-31"
            "&statement_balance_minor=850000"
        )
        assert client.get("/api/reconciliation").json() == []

    def test_reconcile_records_the_assertion(self, client, checking_id):
        self._book(client, checking_id)
        response = client.post(
            "/api/reconciliation",
            json={
                "account_id": checking_id,
                "statement_date": "2026-01-31",
                "statement_balance_minor": 850000,
                "note": "January",
            },
        )
        assert response.status_code == 201
        record = response.json()
        assert record["statement_balance"] == "$8,500.00"
        assert record["book_balance"] == "$8,500.00"

        status = client.get("/api/reconciliation/status").json()
        checking = next(s for s in status if s["account_id"] == checking_id)
        assert checking["reconciled_through"] == "2026-01-31"

    def test_a_gap_is_a_400_not_a_500(self, client, checking_id):
        self._book(client, checking_id)
        response = client.post(
            "/api/reconciliation",
            json={
                "account_id": checking_id,
                "statement_date": "2026-01-31",
                "statement_balance_minor": 840000,
            },
        )
        # A refused reconciliation is a user-facing fact, not a server error.
        assert response.status_code == 400
        assert "difference" in response.json()["detail"]

    def test_non_statement_account_is_rejected(self, client):
        supplies = next(
            a for a in client.get("/api/accounts").json() if a["code"] == "6100"
        )["id"]
        response = client.get(
            "/api/reconciliation/preview"
            f"?account_id={supplies}&statement_date=2026-01-31&statement_balance_minor=0"
        )
        assert response.status_code == 400
        assert "does not issue statements" in response.json()["detail"]

    def test_undo_and_reconcile_again(self, client, checking_id):
        self._book(client, checking_id)
        created = client.post(
            "/api/reconciliation",
            json={
                "account_id": checking_id,
                "statement_date": "2026-01-31",
                "statement_balance_minor": 850000,
            },
        ).json()

        undone = client.post(f"/api/reconciliation/{created['id']}/undo", json={})
        assert undone.status_code == 200
        assert undone.json()["reverses_id"] == created["id"]

        status = client.get("/api/reconciliation/status").json()
        assert next(
            s for s in status if s["account_id"] == checking_id
        )["reconciled_through"] is None

        # History keeps both: the claim and the retraction.
        assert len(client.get(f"/api/reconciliation?account_id={checking_id}").json()) == 2

        again = client.post(
            "/api/reconciliation",
            json={
                "account_id": checking_id,
                "statement_date": "2026-01-31",
                "statement_balance_minor": 850000,
            },
        )
        assert again.status_code == 201

    def test_backdated_entries_are_surfaced(self, client, checking_id):
        self._book(client, checking_id)
        client.post(
            "/api/reconciliation",
            json={
                "account_id": checking_id,
                "statement_date": "2026-01-31",
                "statement_balance_minor": 850000,
            },
        )
        assert client.get("/api/reconciliation/backdated").json() == []

        # A January transaction imported in March. The books still balance.
        late = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("late.csv",
                            "Date,Description,Amount\n2026-01-15,FORGOTTEN FEE,-25.00\n",
                            "text/csv")},
        ).json()
        staged = client.get(f"/api/imports/{late['batch_id']}/transactions").json()
        fees = next(a for a in client.get("/api/accounts").json() if a["code"] == "6050")
        client.post(f"/api/staged/{staged[0]['id']}/post", json={"account_id": fees["id"]})

        assert client.get("/api/health").json()["ledger_balanced"]  # still balanced...

        flagged = client.get("/api/reconciliation/backdated").json()  # ...but not right
        assert len(flagged) == 1
        assert flagged[0]["description"] == "FORGOTTEN FEE"


class TestAccountManagement:
    """ADR 0010 over the real HTTP stack."""

    def test_manage_lists_everything_with_usage(self, client):
        rows = client.get("/api/accounts/manage").json()
        assert len(rows) > 30
        supplies = next(r for r in rows if r["code"] == "6100")
        # Starter rules reference it, so it isn't deletable even on a fresh book.
        assert supplies["usage"]["rules"] > 0
        assert supplies["can_delete"] is False

    def test_rename_and_reword(self, client):
        supplies = next(a for a in client.get("/api/accounts").json() if a["code"] == "6100")
        response = client.patch(
            f"/api/accounts/{supplies['id']}",
            json={"name": "Stationery", "description": "Art shop stuff."},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Stationery"
        assert response.json()["guidance"] == "Art shop stuff."

    def test_hidden_accounts_leave_the_picker_but_stay_in_manage(self, client):
        travel = next(a for a in client.get("/api/accounts").json() if a["code"] == "6400")
        client.patch(f"/api/accounts/{travel['id']}", json={"is_active": False})

        assert travel["id"] not in {a["id"] for a in client.get("/api/accounts").json()}
        assert travel["id"] in {
            a["id"] for a in client.get("/api/accounts?include_hidden=true").json()
        }
        managed = next(
            r for r in client.get("/api/accounts/manage").json() if r["id"] == travel["id"]
        )
        assert managed["is_active"] is False

    def test_cannot_hide_a_statement_account(self, client, checking_id):
        response = client.patch(f"/api/accounts/{checking_id}", json={"is_active": False})
        assert response.status_code == 400
        assert "import statements into" in response.json()["detail"]

    def test_add_a_category_without_naming_a_number(self, client):
        response = client.post(
            "/api/accounts",
            json={"name": "Studio rent", "type": "expense",
                  "description": "Rent for the studio."},
        )
        assert response.status_code == 201
        created = response.json()
        # We picked the number, in the range that makes it an expense.
        assert 6000 <= int(created["code"]) <= 6999
        assert created["guidance"] == "Rent for the studio."
        assert created["id"] in {a["id"] for a in client.get("/api/accounts").json()}

    def test_next_code_endpoint(self, client):
        code = client.get("/api/accounts/next-code?type=revenue").json()["code"]
        assert 4000 <= int(code) <= 4999

    def test_a_code_outside_the_type_range_is_refused(self, client):
        response = client.post(
            "/api/accounts", json={"code": "1200", "name": "Nope", "type": "expense"}
        )
        assert response.status_code == 400
        assert "range" in response.json()["detail"]

    def test_a_duplicate_code_is_a_conflict_not_a_crash(self, client):
        response = client.post(
            "/api/accounts", json={"code": "6100", "name": "Clash", "type": "expense"}
        )
        assert response.status_code == 409

    def test_deleting_an_unused_account(self, client):
        created = client.post(
            "/api/accounts", json={"name": "Temporary", "type": "expense"}
        ).json()
        assert client.delete(f"/api/accounts/{created['id']}").status_code == 204
        assert created["id"] not in {a["id"] for a in client.get("/api/accounts").json()}

    def test_deleting_a_used_account_is_refused_with_a_reason(self, client, checking_id):
        upload = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("chase.csv", CHASE, "text/csv")},
        ).json()
        client.post(f"/api/imports/{upload['batch_id']}/post")

        supplies = next(a for a in client.get("/api/accounts").json() if a["code"] == "6100")
        response = client.delete(f"/api/accounts/{supplies['id']}")

        # 409: the request is fine, the books disagree with it.
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "posted transaction" in detail
        assert "hide it instead" in detail
        # And the books are untouched.
        assert client.get("/api/health").json()["ledger_balanced"]

    def test_renaming_does_not_disturb_the_reports(self, client, checking_id):
        upload = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("chase.csv", CHASE, "text/csv")},
        ).json()
        client.post(f"/api/imports/{upload['batch_id']}/post")
        pnl_url = "/api/reports/profit-and-loss?start=2026-01-01&end=2026-12-31"
        before = client.get(pnl_url).json()

        supplies = next(a for a in client.get("/api/accounts").json() if a["code"] == "6100")
        client.patch(f"/api/accounts/{supplies['id']}", json={"name": "Stationery"})

        after = client.get(pnl_url).json()
        # Same money, new label. Journal lines reference the id, never the name.
        assert after["net_income_minor"] == before["net_income_minor"]
        assert any(
            line["name"] == "Stationery" for line in after["operating_expenses"]["lines"]
        )


class TestRegisterEndpoint:
    """ADR 0012's register over the real HTTP stack, including the two fixes from
    review: all-accounts mode and pagination."""

    def _book(self, client, checking_id):
        upload = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("chase.csv", CHASE, "text/csv")},
        ).json()
        client.post(f"/api/imports/{upload['batch_id']}/post")

    def test_single_account_has_a_running_balance(self, client, checking_id):
        self._book(client, checking_id)
        page = client.get(f"/api/reports/register?account_id={checking_id}").json()
        assert page["has_running_balance"] is True
        assert page["account"]["code"] == "1000"
        assert page["closing_balance_minor"] is not None

    def test_omitting_the_account_lists_everything(self, client, checking_id):
        self._book(client, checking_id)
        page = client.get("/api/reports/register").json()
        assert page["account"] is None
        assert page["has_running_balance"] is False
        # Both sides of both posted entries.
        assert page["total_count"] == 4
        assert all(line["account"] for line in page["lines"])

    def test_all_accounts_total_is_zero_by_double_entry(self, client, checking_id):
        # Not a bug: summing every line of every entry is the debits==credits
        # invariant. The UI suppresses it; the API reports it honestly.
        self._book(client, checking_id)
        page = client.get("/api/reports/register").json()
        assert page["total_minor"] == 0

    def test_pagination_over_http(self, client, checking_id):
        self._book(client, checking_id)
        page = client.get(
            f"/api/reports/register?account_id={checking_id}&limit=1"
        ).json()
        assert page["count"] == 1
        assert page["total_count"] == 2
        assert page["has_more"] is True

        page2 = client.get(
            f"/api/reports/register?account_id={checking_id}&limit=1&offset=1"
        ).json()
        assert page2["has_more"] is False
        # The whole-set total is identical on every page: it describes the set.
        assert page2["total_minor"] == page["total_minor"]

    def test_unknown_account_is_a_404(self, client):
        assert client.get("/api/reports/register?account_id=9999").status_code == 404


class TestPeriodEndpoints:
    """ADR 0011 over the real HTTP stack."""

    def _book(self, client, checking_id):
        upload = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("chase.csv", CHASE, "text/csv")},
        ).json()
        client.post(f"/api/imports/{upload['batch_id']}/post")

    def test_nothing_closed_initially(self, client):
        state = client.get("/api/periods").json()
        assert state["closed_through"] is None
        assert state["current_close"] is None
        assert state["history"] == []

    def test_close_then_status(self, client, checking_id):
        self._book(client, checking_id)
        response = client.post(
            "/api/periods/close", json={"through": "2026-01-31", "note": "January"}
        )
        assert response.status_code == 201
        assert response.json()["closed_through"] == "2026-01-31"

        state = client.get("/api/periods").json()
        assert state["closed_through"] == "2026-01-31"
        assert state["current_close"]["note"] == "January"

    def test_posting_into_a_closed_period_is_a_400_with_a_reason(self, client, checking_id):
        self._book(client, checking_id)
        client.post("/api/periods/close", json={"through": "2026-01-31"})

        late = client.post(
            f"/api/imports?account_id={checking_id}",
            files={"file": ("late.csv",
                            "Date,Description,Amount\n2026-01-20,KROGER 00999,-30.00\n",
                            "text/csv")},
        ).json()
        staged = client.get(f"/api/imports/{late['batch_id']}/transactions").json()
        response = client.post(f"/api/staged/{staged[0]['id']}/post", json={})

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "closed through 2026-01-31" in detail
        assert "Reopen that period" in detail
        # And the books are untouched by the attempt.
        assert client.get("/api/health").json()["ledger_balanced"]

    def test_closing_backwards_is_refused(self, client):
        client.post("/api/periods/close", json={"through": "2026-02-28"})
        response = client.post("/api/periods/close", json={"through": "2026-01-31"})
        assert response.status_code == 400
        assert "already closed through" in response.json()["detail"]

    def test_readiness_names_what_is_untidy(self, client, checking_id):
        self._book(client, checking_id)
        state = client.get("/api/periods/readiness?through=2026-01-31").json()
        assert state["is_tidy"] is False
        assert len(state["unreconciled_accounts"]) > 0
        assert state["uncategorized_transactions"] == 1  # the mystery vendor

    def test_readiness_does_not_block_closing(self, client, checking_id):
        # Advisory, never a veto (ADR 0011).
        self._book(client, checking_id)
        readiness = client.get("/api/periods/readiness?through=2026-01-31").json()
        assert readiness["is_tidy"] is False
        closed = client.post("/api/periods/close", json={"through": "2026-01-31"})
        assert closed.status_code == 201

    def test_reopen_restores_posting(self, client, checking_id):
        self._book(client, checking_id)
        close = client.post("/api/periods/close", json={"through": "2026-01-31"}).json()

        reopened = client.post(f"/api/periods/{close['id']}/reopen", json={"reason": "oops"})
        assert reopened.status_code == 200
        assert reopened.json()["reopens_id"] == close["id"]
        assert client.get("/api/periods").json()["closed_through"] is None

        # History keeps both the close and the reopen.
        assert len(client.get("/api/periods").json()["history"]) == 2

    def test_void_of_a_closed_entry_falls_forward(self, client, checking_id):
        self._book(client, checking_id)
        entries = client.get("/api/export/json").json()["tables"]["journal_entries"]
        january = next(e for e in entries if e["entry_date"] == "2026-01-15")

        client.post("/api/periods/close", json={"through": "2026-01-31"})

        voided = client.post(f"/api/entries/{january['id']}/void", json={"reason": "personal"})
        assert voided.status_code == 200

        after = client.get("/api/export/json").json()["tables"]["journal_entries"]
        reversal = next(e for e in after if e["reverses_entry_id"] == january["id"])
        # Lands in the first open period, not back inside closed January.
        assert reversal["entry_date"] > "2026-01-31"
        assert client.get("/api/health").json()["ledger_balanced"]

    def test_period_closes_are_exported(self, client):
        client.post("/api/periods/close", json={"through": "2026-01-31", "note": "January"})
        tables = client.get("/api/export/json").json()["tables"]
        assert len(tables["period_closes"]) == 1
        assert tables["period_closes"][0]["closed_through"] == "2026-01-31"
