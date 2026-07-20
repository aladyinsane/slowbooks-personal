import { useEffect, useState } from "react";
import { api, type PeriodReadiness, type PeriodStatus } from "../lib/api";

/**
 * Closing the books through a date (ADR 0011).
 *
 * Two things this screen has to get right:
 *
 * 1. **It warns, it doesn't refuse.** Unreconciled accounts and uncategorized rows are
 *    worth knowing before you close. They are not our decision — the statement might not
 *    have arrived. Tell them, loudly, then obey.
 * 2. **Closing sounds final, because it is.** Nothing dated on or before the line can be
 *    recorded afterwards. Reopening exists, but it should feel like a decision rather
 *    than a shrug.
 */
export function ClosePanel() {
  const [status, setStatus] = useState<PeriodStatus | null>(null);
  const [through, setThrough] = useState("");
  const [note, setNote] = useState("");
  const [readiness, setReadiness] = useState<PeriodReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const refresh = () =>
    api.periodStatus().then(setStatus).catch((e: Error) => setError(e.message));

  useEffect(() => {
    void refresh();
  }, []);

  async function check() {
    if (!through) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      setReadiness(await api.periodReadiness(through));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await api.closePeriod(through, note.trim() || undefined);
      setDone(`The books are closed through ${through}.`);
      setReadiness(null);
      setNote("");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function reopen(closeId: number) {
    setBusy(true);
    setError(null);
    try {
      await api.reopenPeriod(closeId);
      setDone(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="close-period" aria-labelledby="close-heading">
      <h2 id="close-heading">Close the books</h2>
      <p className="lede">
        Closing a period makes it final: nothing dated on or before that day can be
        recorded afterwards. It&rsquo;s what keeps a report you gave someone in February
        saying the same thing in June.
      </p>

      {error && (
        <div className="bad-box" role="alert">
          {error}
        </div>
      )}
      {done && <p className="posted">{done}</p>}

      <p className="close-state">
        {status?.closed_through ? (
          <>
            Closed through <strong>{status.closed_through}</strong>
            {status.current_close?.note && <span className="muted"> · {status.current_close.note}</span>}
            <button
              className="link"
              disabled={busy}
              onClick={() => reopen(status.current_close!.id)}
            >
              reopen
            </button>
          </>
        ) : (
          <span className="muted">Nothing is closed yet — every date is still open.</span>
        )}
      </p>

      <div className="close-form">
        <label htmlFor="close-through">Close everything through</label>
        <input
          id="close-through"
          type="date"
          value={through}
          onChange={(e) => {
            setThrough(e.target.value);
            setReadiness(null);
          }}
        />
        <input
          type="text"
          className="wide"
          placeholder="Note (optional), e.g. January"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          aria-label="Note"
        />
        <button className="primary" disabled={!through || busy} onClick={check}>
          {busy ? "Checking…" : "Check"}
        </button>
      </div>

      {readiness && (
        <div className={readiness.is_tidy ? "result match" : "result gap"}>
          {readiness.is_tidy ? (
            <p>
              Everything through {readiness.through} is reconciled and categorized. Good
              time to close.
            </p>
          ) : (
            <>
              {/* Worth knowing, not a veto. */}
              <p className="hint">
                <strong>Before you close, so you know:</strong>
              </p>
              <ul className="close-warnings">
                {readiness.unreconciled_accounts.map((a) => (
                  <li key={a.account}>
                    <strong>{a.account}</strong> isn&rsquo;t reconciled through this date
                    {a.reconciled_through ? (
                      <span className="muted"> — reconciled through {a.reconciled_through}</span>
                    ) : (
                      <span className="muted"> — never reconciled</span>
                    )}
                  </li>
                ))}
                {readiness.uncategorized_transactions > 0 && (
                  <li>
                    <strong>
                      {readiness.uncategorized_transactions} imported{" "}
                      {readiness.uncategorized_transactions === 1
                        ? "transaction"
                        : "transactions"}
                    </strong>{" "}
                    in this period still{" "}
                    {readiness.uncategorized_transactions === 1 ? "needs" : "need"} a
                    category.{" "}
                    {readiness.uncategorized_transactions === 1 ? "It won" : "They won"}
                    &rsquo;t be recordable once it&rsquo;s closed.
                  </li>
                )}
              </ul>
              <p>You can close anyway — this is your call, not ours.</p>
            </>
          )}
          <button className="primary" disabled={busy} onClick={confirm}>
            Close through {readiness.through}
          </button>
        </div>
      )}

      {status && status.history.length > 0 && (
        <details className="close-history">
          <summary>History</summary>
          <ul>
            {status.history.map((record) => (
              <li key={record.id}>
                <span className="picker-code">{record.closed_at.slice(0, 10)}</span>{" "}
                {record.reopens_id ? "reopened" : "closed through"}{" "}
                <strong>{record.closed_through}</strong>
                {record.note && <span className="muted"> · {record.note}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
