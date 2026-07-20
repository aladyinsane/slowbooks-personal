import { useEffect, useState } from "react";
import {
  api,
  type BackdatedEntry,
  type ReconciliationPreview,
  type ReconciliationStatus,
} from "../lib/api";
import { parseInput } from "../lib/money";

/**
 * Bank reconciliation (ADR 0009).
 *
 * The screen is shaped around one idea: the user is *asserting* that their books match
 * the bank, not asking us whether they do. So the bank's closing balance is something
 * they type in — we never invent it, because a number we could compute would prove
 * nothing.
 *
 * Everything else we show means "these are the numbers, probably." A reconciled period
 * is the only thing here that means "this is proven."
 */
export function ReconcilePanel() {
  const [statuses, setStatuses] = useState<ReconciliationStatus[]>([]);
  const [backdated, setBackdated] = useState<BackdatedEntry[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [statementDate, setStatementDate] = useState("");
  const [balanceText, setBalanceText] = useState("");
  const [preview, setPreview] = useState<ReconciliationPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const refresh = async () => {
    const [status, flagged] = await Promise.all([
      api.reconciliationStatus(),
      api.backdatedEntries(),
    ]);
    setStatuses(status);
    setBackdated(flagged);
    if (accountId === null && status.length > 0) setAccountId(status[0].account_id);
  };

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const balanceMinor = parseInput(balanceText);
  const ready = accountId !== null && statementDate !== "" && balanceMinor !== null;

  async function check() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      setPreview(await api.previewReconciliation(accountId!, statementDate, balanceMinor!));
    } catch (err) {
      setError((err as Error).message);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!preview?.can_reconcile || accountId === null || balanceMinor === null) return;
    setBusy(true);
    try {
      await api.reconcile(accountId, statementDate, balanceMinor);
      setDone(`${preview.account} is reconciled through ${statementDate}.`);
      setPreview(null);
      setBalanceText("");
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function undo(id: number) {
    setBusy(true);
    try {
      await api.undoReconciliation(id);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="reconcile" aria-labelledby="reconcile-heading">
      <h2 id="reconcile-heading">Check against your bank</h2>
      <p className="lede">
        Your books add up — but adding up isn&rsquo;t the same as being complete. Comparing
        them to your bank&rsquo;s closing balance is the only way to know nothing is
        missing.
      </p>

      {backdated.length > 0 && (
        // The books still balance perfectly here, which is exactly why this needs saying
        // out loud. Nothing else in the system can see it.
        <div className="warn-box" role="alert">
          <strong>
            {backdated.length}{" "}
            {backdated.length === 1 ? "transaction was" : "transactions were"} added to a
            period you already reconciled.
          </strong>
          <ul>
            {backdated.map((entry) => (
              <li key={entry.entry_id}>
                {entry.entry_date} · {entry.description} · {entry.account_code}{" "}
                {entry.account_name}
              </li>
            ))}
          </ul>
          <p>
            That period no longer matches what you confirmed. Reconcile it again to check.
          </p>
        </div>
      )}

      <table className="status-table">
        <thead>
          <tr>
            <th>Account</th>
            <th>Reconciled through</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {statuses.map((status) => (
            <tr key={status.account_id}>
              <td>{status.account}</td>
              <td>
                {status.reconciled_through ? (
                  <span className="ok">{status.reconciled_through}</span>
                ) : (
                  <span className="muted">never</span>
                )}
              </td>
              <td>
                {status.reconciliation_id !== null && (
                  <button
                    className="link"
                    disabled={busy}
                    onClick={() => undo(status.reconciliation_id!)}
                  >
                    undo
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="reconcile-form">
        <label htmlFor="recon-account">Account</label>
        <select
          id="recon-account"
          value={accountId ?? ""}
          onChange={(e) => {
            setAccountId(Number(e.target.value));
            setPreview(null);
          }}
        >
          {statuses.map((status) => (
            <option key={status.account_id} value={status.account_id}>
              {status.account}
            </option>
          ))}
        </select>

        <label htmlFor="recon-date">Statement closing date</label>
        <input
          id="recon-date"
          type="date"
          value={statementDate}
          onChange={(e) => {
            setStatementDate(e.target.value);
            setPreview(null);
          }}
        />

        <label htmlFor="recon-balance">Closing balance on the statement</label>
        <input
          id="recon-balance"
          type="text"
          inputMode="decimal"
          placeholder="8,500.00"
          value={balanceText}
          onChange={(e) => {
            setBalanceText(e.target.value);
            setPreview(null);
          }}
        />
        {balanceText !== "" && balanceMinor === null && (
          <span className="field-error">That doesn&rsquo;t look like an amount.</span>
        )}

        <button className="primary" disabled={!ready || busy} onClick={check}>
          {busy ? "Checking…" : "Check"}
        </button>
      </div>

      {error && <p className="bad">{error}</p>}
      {done && <p className="posted">{done}</p>}

      {preview && (
        <div className={preview.can_reconcile ? "result match" : "result gap"}>
          <dl>
            <div>
              <dt>Your bank says</dt>
              <dd>{preview.statement_balance}</dd>
            </div>
            <div>
              <dt>SlowBooks says</dt>
              <dd>{preview.book_balance}</dd>
            </div>
            <div>
              <dt>Difference</dt>
              <dd className={preview.can_reconcile ? "ok" : "bad"}>{preview.difference}</dd>
            </div>
          </dl>

          {preview.can_reconcile ? (
            <>
              <p>
                These match. Confirming records that you checked{" "}
                {preview.unreconciled_line_count}{" "}
                {preview.unreconciled_line_count === 1 ? "transaction" : "transactions"}{" "}
                against your statement on this date.
              </p>
              <button className="primary" disabled={busy} onClick={confirm}>
                Confirm this matches
              </button>
            </>
          ) : (
            <p className="hint">{preview.hint}</p>
          )}
        </div>
      )}
    </section>
  );
}
