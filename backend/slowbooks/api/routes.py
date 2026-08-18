"""HTTP API.

Thin by design: shape, validate, serialize. No accounting rules live here -- they
belong to the domain modules (see docs/engineering/architecture.md).
"""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from slowbooks import (
    access,
    accounts,
    categorize,
    exporting,
    groups,
    ledger,
    money,
    periods,
    posting,
    reconciliation,
    reports,
    settings,
    transfers,
)
from slowbooks.deps import database_path, get_db
from slowbooks.importing import csv_import
from slowbooks.reports.register import DEFAULT_LIMIT as REGISTER_PAGE_SIZE

# Gated once here rather than per-endpoint: require_unlocked is a no-op unless LAN
# access is on (see access.py), so this is a no-op for the whole existing test suite and
# for anyone who never opts in.
router = APIRouter(dependencies=[Depends(access.require_unlocked)])

# The one endpoint that must be reachable while locked -- submitting the PIN itself.
public_router = APIRouter()


# ---------------------------------------------------------------- accounts


class AccountIn(BaseModel):
    # Optional: the caller can name a code, but the range is what makes the type safe
    # (ADR 0010), so picking the number is our job, not the user's.
    code: str | None = Field(None, pattern=r"^\d{4}$")
    name: str = Field(..., min_length=1)
    type: str
    description: str | None = None
    is_statement_account: bool = False
    group_id: int | None = None


class AccountUpdateIn(BaseModel):
    """Rename, re-word, hide, unhide, or regroup. No `code` or `type` (ADR 0010)."""

    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    group_id: int | None = None


def _account_json(account: accounts.Account) -> dict:
    return {
        "id": account.id,
        "code": account.code,
        "name": account.name,
        "type": account.type,
        "normal_balance": account.normal_balance,
        # Drives both the import target list and the transfer targets, replacing the
        # frontend's old code-prefix guess (ADR 0007).
        "is_statement_account": account.is_statement_account,
        # Shown where the category is chosen. "What does a card payment go to?" is a
        # fair question and the answer belongs next to the answer, not in a help page.
        "guidance": account.description,
        # Which group this displays under (ADR 0014) -- null for an ungrouped account,
        # shown as "Other" in the UI rather than treated as an error.
        "group_id": account.group_id,
        "group_name": account.group_name,
    }


@router.get("/accounts", tags=["accounts"])
def list_accounts(include_hidden: bool = False, conn=Depends(get_db)):
    return [
        _account_json(a) for a in accounts.list_all(conn, active_only=not include_hidden)
    ]


@router.get("/accounts/manage", tags=["accounts"])
def manage_accounts(conn=Depends(get_db)):
    """Every account, hidden ones included, with what each is used by.

    The usage counts are the point: they turn "you can't delete this" into "this is used
    by 14 posted transactions", which is an answer rather than a wall (ADR 0010).
    """
    result = []
    for account in accounts.list_all(conn, active_only=False):
        counts = accounts.usage(conn, account.id)
        row = _account_json(account)
        row["is_active"] = bool(
            conn.execute(
                "SELECT is_active FROM accounts WHERE id = ?", (account.id,)
            ).fetchone()["is_active"]
        )
        row["usage"] = counts
        row["can_delete"] = not any(counts.values())
        result.append(row)
    return result


@router.get("/accounts/next-code", tags=["accounts"])
def suggest_code(type: str, conn=Depends(get_db)):
    try:
        return {"code": accounts.next_code(conn, type)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/accounts/{account_id}", tags=["accounts"])
def update_account(account_id: int, payload: AccountUpdateIn, conn=Depends(get_db)):
    try:
        account = accounts.update(
            conn, account_id,
            name=payload.name, description=payload.description,
            is_active=payload.is_active, group_id=payload.group_id,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _account_json(account)


@router.delete("/accounts/{account_id}", tags=["accounts"], status_code=204)
def delete_account(account_id: int, conn=Depends(get_db)):
    """Delete an account that has never been used. Refused otherwise (ADR 0010)."""
    try:
        accounts.delete(conn, account_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except accounts.AccountInUseError as exc:
        # 409, not 400: the request is well-formed, the books just disagree with it.
        raise HTTPException(409, str(exc)) from exc


@router.post("/accounts", tags=["accounts"], status_code=201)
def create_account(payload: AccountIn, conn=Depends(get_db)):
    try:
        # No code given? Choose one in the right range. Someone adding "Studio rent"
        # shouldn't have to learn that expenses live in the 6000s.
        code = payload.code or accounts.next_code(conn, payload.type)
        account = accounts.create(
            conn, code, payload.name, payload.type, payload.description,
            is_statement_account=payload.is_statement_account, group_id=payload.group_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, f"account code {payload.code} is already taken") from exc
    return _account_json(account)


# ---------------------------------------------------------------- groups


class GroupIn(BaseModel):
    name: str = Field(..., min_length=1)
    type: str


class GroupUpdateIn(BaseModel):
    """Rename only -- changing a group's type is refused (see groups.update)."""

    name: str = Field(..., min_length=1)


def _group_json(group: groups.Group) -> dict:
    return {"id": group.id, "name": group.name, "type": group.type}


@router.get("/groups", tags=["groups"])
def list_groups(type: str | None = None, conn=Depends(get_db)):
    return [_group_json(g) for g in groups.list_all(conn, type_=type)]


@router.post("/groups", tags=["groups"], status_code=201)
def create_group(payload: GroupIn, conn=Depends(get_db)):
    try:
        group = groups.create(conn, payload.name, payload.type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            409, f"a {payload.type} group named {payload.name!r} already exists"
        ) from exc
    return _group_json(group)


@router.patch("/groups/{group_id}", tags=["groups"])
def update_group(group_id: int, payload: GroupUpdateIn, conn=Depends(get_db)):
    try:
        group = groups.update(conn, group_id, name=payload.name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _group_json(group)


@router.delete("/groups/{group_id}", tags=["groups"], status_code=204)
def delete_group(group_id: int, conn=Depends(get_db)):
    """Delete a group with no accounts filed under it. Refused otherwise."""
    try:
        groups.delete(conn, group_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except groups.GroupInUseError as exc:
        raise HTTPException(409, str(exc)) from exc


# ---------------------------------------------------------------- import


@router.post("/imports", tags=["import"])
async def import_statement(account_id: int, file: UploadFile, conn=Depends(get_db)):
    """Stage a CSV against an account.

    Staged, not posted: the user previews and confirms before anything reaches the
    ledger (principle 8).
    """
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Bank exports are frequently Windows-1252, and it never fails to decode --
        # so it is the right last resort rather than a first guess.
        content = raw.decode("cp1252", errors="replace")

    try:
        return csv_import.import_csv(
            conn, content, file.filename or "upload.csv", account_id
        )
    except csv_import.ImportError_ as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/imports/{batch_id}/transactions", tags=["import"])
def list_staged(batch_id: int, conn=Depends(get_db)):
    rows = conn.execute(
        """SELECT s.id, s.txn_date, s.description, s.amount_minor, s.status,
                  s.account_id, s.suggested_account_id, s.suggested_reason,
                  s.suggested_rule_id, s.transfer_match_id,
                  a.code AS suggested_code, a.name AS suggested_name,
                  r.is_builtin AS rule_is_builtin,
                  m.description AS match_description, m.txn_date AS match_date,
                  ma.code AS match_account_code, ma.name AS match_account_name
             FROM staged_transactions s
             LEFT JOIN accounts a ON a.id = s.suggested_account_id
             LEFT JOIN rules r    ON r.id = s.suggested_rule_id
             LEFT JOIN staged_transactions m ON m.id = s.transfer_match_id
             LEFT JOIN accounts ma ON ma.id = m.account_id
            WHERE s.batch_id = ?
            ORDER BY s.txn_date, s.id""",
        (batch_id,),
    ).fetchall()

    return [
        {
            "id": r["id"],
            "date": r["txn_date"],
            "description": r["description"],
            "amount_minor": r["amount_minor"],
            "amount": money.format(r["amount_minor"]),
            "status": r["status"],
            # The statement this row came from. The UI needs it to avoid offering
            # "transfer to" the very account the money is already in -- an option that
            # could only ever produce an error.
            "account_id": r["account_id"],
            "suggested_account_id": r["suggested_account_id"],
            "suggested_account": (
                f'{r["suggested_code"]} {r["suggested_name"]}' if r["suggested_code"] else None
            ),
            "reason": r["suggested_reason"],
            "rule_id": r["suggested_rule_id"],
            # ADR 0006: a shipped guess and a rule the user wrote carry very different
            # weight, and collapsing them is what lets a bad guess pass unexamined.
            "is_starter_rule": bool(r["rule_is_builtin"]),
            # ADR 0007: a transfer is not a category, so the UI must not offer one.
            "is_transfer": r["transfer_match_id"] is not None,
            "transfer_match_id": r["transfer_match_id"],
            "transfer_counterpart": (
                {
                    "account": f'{r["match_account_code"]} {r["match_account_name"]}',
                    "date": r["match_date"],
                    "description": r["match_description"],
                }
                if r["transfer_match_id"] is not None and r["match_account_code"]
                else None
            ),
        }
        for r in rows
    ]


@router.delete("/staged/{staged_id}/transfer-match", tags=["import"], status_code=204)
def unlink_transfer(staged_id: int, conn=Depends(get_db)):
    """Reject a suggested transfer pairing (ADR 0007).

    Detection is a suggestion, not a verdict: two unrelated $500 movements in the same
    week look exactly like a transfer, and the user is the one who knows.
    """
    transfers.unlink(conn, staged_id)


class CategorizeIn(BaseModel):
    # None clears the category: "actually, I don't know yet".
    account_id: int | None = None


@router.patch("/staged/{staged_id}", tags=["import"])
def categorize_staged(staged_id: int, payload: CategorizeIn, conn=Depends(get_db)):
    """Choose a category without posting anything (ADR 0004's draft zone).

    Separate from /post on purpose. Choosing is reversible; posting is not.
    """
    try:
        posting.choose_category(conn, staged_id, payload.account_id)
    except posting.PostingError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": staged_id, "account_id": payload.account_id}


class PostStagedIn(BaseModel):
    account_id: int | None = None


@router.post("/staged/{staged_id}/post", tags=["import"])
def post_staged_transaction(staged_id: int, payload: PostStagedIn, conn=Depends(get_db)):
    try:
        entry_id = posting.post_staged(conn, staged_id, payload.account_id)
    except (posting.PostingError, ledger.LedgerError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"entry_id": entry_id}


@router.post("/imports/{batch_id}/post", tags=["import"])
def post_batch(batch_id: int, conn=Depends(get_db)):
    try:
        return posting.post_batch(conn, batch_id)
    except (posting.PostingError, ledger.LedgerError) as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------- rules


class RuleIn(BaseModel):
    pattern: str = Field(..., min_length=1)
    account_id: int
    match_type: str = "contains"
    applies_to: str = "any"
    priority: int = categorize.rules.DEFAULT_PRIORITY


@router.get("/rules", tags=["rules"])
def list_rules(conn=Depends(get_db)):
    rows = conn.execute(
        """SELECT r.id, r.priority, r.match_type, r.pattern, r.applies_to, r.is_builtin,
                  a.code AS account_code, a.name AS account_name
             FROM rules r JOIN accounts a ON a.id = r.account_id
            ORDER BY r.priority, r.id"""
    ).fetchall()
    return [dict(row) for row in rows]


@router.post("/rules", tags=["rules"], status_code=201)
def create_rule(payload: RuleIn, conn=Depends(get_db)):
    try:
        rule_id = categorize.create_rule(
            conn, payload.pattern, payload.account_id,
            match_type=payload.match_type, applies_to=payload.applies_to,
            priority=payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": rule_id}


@router.delete("/rules/{rule_id}", tags=["rules"], status_code=204)
def delete_rule(rule_id: int, conn=Depends(get_db)):
    conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


# ---------------------------------------------------------------- ledger


class VoidIn(BaseModel):
    reason: str | None = None


@router.post("/entries/{entry_id}/void", tags=["ledger"])
def void_entry(entry_id: int, payload: VoidIn, conn=Depends(get_db)):
    """Void by reversal. Nothing is ever deleted (ADR 0004)."""
    try:
        reversal_id = ledger.void(conn, entry_id, payload.reason)
    except ledger.LedgerError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"reversing_entry_id": reversal_id}


# ---------------------------------------------------------------- reports


@router.get("/reports/income-and-expenses", tags=["reports"])
def get_pnl(start: date, end: date, conn=Depends(get_db)):
    if start > end:
        raise HTTPException(400, "start date must not be after end date")
    return reports.profit_and_loss(conn, start, end)


@router.get("/reports/net-worth", tags=["reports"])
def get_balance_sheet(as_of: date, conn=Depends(get_db)):
    return reports.balance_sheet(conn, as_of)


@router.get("/reports/register", tags=["reports"])
def get_register(
    account_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    q: str | None = None,
    limit: int = REGISTER_PAGE_SIZE,
    offset: int = 0,
    conn=Depends(get_db),
):
    """Transactions with a running balance, one page at a time (ADR 0012).

    Where every report number drills down to. Principle 8: "the computer says $12,400"
    is worthless if the owner can't see what's in it.

    Omit account_id to list every account. That view has no running balance -- summing
    checking and a credit card and an expense in one column produces a figure that means
    nothing.
    """
    try:
        return reports.register(
            conn, account_id, start=start, end=end, query=q, limit=limit, offset=offset
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/reports/trial-balance", tags=["reports"])
def get_trial_balance(as_of: date, conn=Depends(get_db)):
    return reports.trial_balance(conn, as_of)


# ---------------------------------------------------------------- reconciliation


class ReconcileIn(BaseModel):
    account_id: int
    statement_date: date
    # The bank's number, typed by the user. Integer cents, like every other amount
    # crossing this API (ADR 0003) -- never a float.
    statement_balance_minor: int
    note: str | None = None


def _reconciliation_json(record: reconciliation.Reconciliation) -> dict:
    return {
        "id": record.id,
        "account_id": record.account_id,
        "statement_date": record.statement_date,
        "statement_balance_minor": record.statement_balance_minor,
        "statement_balance": money.format(record.statement_balance_minor),
        "book_balance_minor": record.book_balance_minor,
        "book_balance": money.format(record.book_balance_minor),
        "reconciled_at": record.reconciled_at,
        "note": record.note,
        "reverses_id": record.reverses_id,
    }


@router.get("/reconciliation/preview", tags=["reconciliation"])
def preview_reconciliation(
    account_id: int,
    statement_date: date,
    statement_balance_minor: int,
    conn=Depends(get_db),
):
    """Compare the bank's closing balance to ours. Changes nothing (ADR 0009)."""
    try:
        state = reconciliation.preview(
            conn, account_id, statement_date, statement_balance_minor
        )
    except reconciliation.ReconciliationError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "account_id": state.account_id,
        "account": f"{state.account_code} {state.account_name}",
        "statement_date": state.statement_date,
        "statement_balance_minor": state.statement_balance_minor,
        "statement_balance": money.format(state.statement_balance_minor),
        "book_balance_minor": state.book_balance_minor,
        "book_balance": money.format(state.book_balance_minor),
        "difference_minor": state.difference_minor,
        "difference": money.format(state.difference_minor),
        "unreconciled_line_count": state.unreconciled_line_count,
        "can_reconcile": state.can_reconcile,
        "hint": state.hint,
    }


@router.post("/reconciliation", tags=["reconciliation"], status_code=201)
def create_reconciliation(payload: ReconcileIn, conn=Depends(get_db)):
    """Record the user's assertion that this account matches the bank."""
    try:
        rec_id = reconciliation.reconcile(
            conn, payload.account_id, payload.statement_date,
            payload.statement_balance_minor, payload.note,
        )
    except reconciliation.ReconciliationError as exc:
        # A refused reconciliation is a user-facing fact, not a server error: the gap is
        # the thing they need to go look at.
        raise HTTPException(400, str(exc)) from exc
    return _reconciliation_json(reconciliation.get(conn, rec_id))


@router.get("/reconciliation", tags=["reconciliation"])
def list_reconciliations(account_id: int | None = None, conn=Depends(get_db)):
    return [_reconciliation_json(r) for r in reconciliation.history(conn, account_id)]


@router.get("/reconciliation/status", tags=["reconciliation"])
def reconciliation_status(conn=Depends(get_db)):
    """Where each statement account stands.

    "Which periods are reconciled?" is among the first things an accountant asks, and
    until now we could not answer it from data.
    """
    result = []
    for account in accounts.list_statement_accounts(conn):
        latest = reconciliation.latest(conn, account.id)
        result.append({
            "account_id": account.id,
            "account": f"{account.code} {account.name}",
            "reconciled_through": latest.statement_date if latest else None,
            "reconciliation_id": latest.id if latest else None,
            "current_balance_minor": reconciliation._book_balance(
                conn, account.id, date.today().isoformat()
            ),
        })
    return result


class UndoReconciliationIn(BaseModel):
    reason: str | None = None


@router.post("/reconciliation/{reconciliation_id}/undo", tags=["reconciliation"])
def undo_reconciliation(
    reconciliation_id: int, payload: UndoReconciliationIn, conn=Depends(get_db)
):
    """Undo by reversal. Append-only, like the ledger (ADR 0009)."""
    try:
        undo_id = reconciliation.undo(conn, reconciliation_id, payload.reason)
    except reconciliation.ReconciliationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _reconciliation_json(reconciliation.get(conn, undo_id))


@router.get("/reconciliation/backdated", tags=["reconciliation"])
def backdated_entries(conn=Depends(get_db)):
    """Entries posted into an already-reconciled period.

    Detection, not prevention -- prevention is period locking (v0.2). These books still
    balance perfectly, which is exactly why this needs surfacing.
    """
    return reconciliation.find_backdated_entries(conn)


# ---------------------------------------------------------------- periods


class ClosePeriodIn(BaseModel):
    through: date
    note: str | None = None


def _close_json(record: periods.PeriodClose) -> dict:
    return {
        "id": record.id,
        "closed_through": record.closed_through,
        "closed_at": record.closed_at,
        "note": record.note,
        "reopens_id": record.reopens_id,
    }


@router.get("/periods", tags=["periods"])
def period_status(conn=Depends(get_db)):
    current = periods.current(conn)
    return {
        "closed_through": periods.closed_through(conn),
        "first_open_date": periods.first_open_date(conn),
        "current_close": _close_json(current) if current else None,
        "history": [_close_json(c) for c in periods.history(conn)],
    }


@router.get("/periods/readiness", tags=["periods"])
def period_readiness(through: date, conn=Depends(get_db)):
    """What to know before closing. Advisory -- none of it blocks (ADR 0011)."""
    return periods.readiness(conn, through)


@router.post("/periods/close", tags=["periods"], status_code=201)
def close_period(payload: ClosePeriodIn, conn=Depends(get_db)):
    try:
        close_id = periods.close(conn, payload.through, payload.note)
    except periods.PeriodError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _close_json(periods.get(conn, close_id))


class ReopenPeriodIn(BaseModel):
    reason: str | None = None


@router.post("/periods/{close_id}/reopen", tags=["periods"])
def reopen_period(close_id: int, payload: ReopenPeriodIn, conn=Depends(get_db)):
    try:
        reopen_id = periods.reopen(conn, close_id, payload.reason)
    except periods.PeriodError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _close_json(periods.get(conn, reopen_id))


# ---------------------------------------------------------------- settings


@router.get("/settings/starter-rules-acknowledged", tags=["settings"])
def get_starter_rules_ack(conn=Depends(get_db)):
    return {
        "acknowledged": settings.get_bool(conn, settings.STARTER_RULES_ACKNOWLEDGED)
    }


@router.post("/settings/starter-rules-acknowledged", tags=["settings"])
def acknowledge_starter_rules(conn=Depends(get_db)):
    """Record that the user has seen the first-run starter-rule warning (ADR 0006).

    Stored in the book file, not the browser: acknowledgement should travel with the
    books when the user copies them to another machine.
    """
    settings.set_bool(conn, settings.STARTER_RULES_ACKNOWLEDGED, True)
    return {"acknowledged": True}


class NetworkIn(BaseModel):
    enabled: bool


@router.get("/settings/network", tags=["settings"])
def get_network_settings():
    return {
        "lan_access_enabled": access.lan_access_enabled(),
        "pin_configured": access.pin_configured(),
    }


@router.post(
    "/settings/network",
    tags=["settings"],
    dependencies=[Depends(access.require_loopback)],
)
def set_network_settings(payload: NetworkIn, conn=Depends(get_db)):
    """Turn LAN access on or off. Loopback-only: a LAN peer, even an unlocked one, must
    never be able to grant itself broader access.

    uvicorn's bind host is fixed at process start (see launch.py), so this takes effect
    on the next launch, not immediately -- the response says so.
    """
    settings.set_bool(conn, settings.LAN_ACCESS_ENABLED, payload.enabled)
    return {"lan_access_enabled": payload.enabled, "restart_required": True}


class PinIn(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


@router.post("/access/pin", tags=["access"], dependencies=[Depends(access.require_loopback)])
def set_pin(payload: PinIn, conn=Depends(get_db)):
    access.set_pin(conn, payload.pin)
    return {"pin_configured": True}


class UnlockIn(BaseModel):
    pin: str


@public_router.post("/access/unlock", tags=["access"])
def unlock(payload: UnlockIn, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    if access.is_locked_out(ip):
        raise HTTPException(429, "Too many attempts. Try again in a minute.")
    if not access.check_pin(payload.pin):
        access.record_failure(ip)
        raise HTTPException(401, "That PIN doesn't match.")
    token = access.issue_session()
    response.set_cookie(
        access.COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"ok": True}


# ---------------------------------------------------------------- export


@router.get("/export/zip", tags=["export"])
def export_zip(conn=Depends(get_db)):
    """Download everything: lossless dumps, accountant-readable reports, instructions.

    ADR 0008. This endpoint is the difference between "your books are yours" being a
    claim and being true.
    """
    stamp = date.today().isoformat()
    return Response(
        content=exporting.export_zip(conn),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="slowbooks-export-{stamp}.zip"'
        },
    )


@router.get("/export/json", tags=["export"])
def export_json(conn=Depends(get_db)):
    return exporting.export_json(conn)


@router.get("/export/database", tags=["export"])
def export_database(conn=Depends(get_db)):
    """Stream the SQLite file itself.

    The only artifact guaranteed complete, because it *is* the book -- and the restore
    path, since export is one-directional (ADR 0008).

    Depends on get_db so the book is guaranteed to exist and be current: an empty book
    is a perfectly valid thing to download (it has your chart of accounts), and a user
    who exports before importing anything should get a file, not an error.
    """
    # Checkpoint first: in WAL mode recent writes live in the -wal sidecar, so copying
    # the .db alone can hand the user a book missing their last few transactions. A
    # backup that silently omits data is worse than no backup.
    conn.execute("PRAGMA wal_checkpoint(FULL)")

    return FileResponse(
        database_path(),
        media_type="application/vnd.sqlite3",
        filename=f"slowbooks-{date.today().isoformat()}.db",
    )


@router.get("/health", tags=["system"])
def health(conn=Depends(get_db)):
    return {"status": "ok", "ledger_balanced": ledger.is_balanced(conn)}


@router.get("/book-file", tags=["system"])
def book_file():
    """Where the user's book lives on disk, so they can find it and back it up.

    Read-only. The location follows how the app runs -- next to the executable when
    packaged, the home folder in development -- plus SLOWBOOKS_DB. Changing it is not a
    setting yet (a browser tab can't open a native folder picker); see ADR 0013 and
    deps.database_path.
    """
    path = database_path()
    resolved = path.resolve()
    exists = path.exists()
    return {
        "path": str(resolved),
        "directory": str(resolved.parent),
        "filename": resolved.name,
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
    }
