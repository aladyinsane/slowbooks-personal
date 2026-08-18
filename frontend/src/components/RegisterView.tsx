import { useEffect, useState } from "react";
import { api, type Account, type Register } from "../lib/api";

/**
 * The register: transactions, date order, running balance (ADR 0012).
 *
 * The shape of a bank statement, because that's the document our user has read their
 * whole life. Not a journal — two rows per transaction with debits and credits is
 * exactly the vocabulary ADR 0004 keeps off-screen.
 *
 * Two modes, and the difference is real rather than cosmetic:
 *
 *   - **One account** is a statement, so it carries a running balance.
 *   - **All accounts** is a list, so it doesn't. Summing checking, a credit card and an
 *     expense in one column produces a figure that means nothing — the same reason a
 *     filtered view drops the balance.
 *
 * This is also where every report number drills down to. Principle 8: "the computer says
 * $12,400" is worthless if the owner can't see what's in it.
 */

const ALL_ACCOUNTS = "all";

interface Props {
  accounts: Account[];
  /** Set when arriving from a report line, so the drill-down lands pre-filtered. */
  initial?: { accountId: number | null; start?: string; end?: string } | null;
  onClose: () => void;
}

export function RegisterView({ accounts, initial, onClose }: Props) {
  const [accountId, setAccountId] = useState<number | null>(initial?.accountId ?? null);
  const [start, setStart] = useState(initial?.start ?? "");
  const [end, setEnd] = useState(initial?.end ?? "");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Register | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!initial) return;
    setAccountId(initial.accountId);
    setStart(initial.start ?? "");
    setEnd(initial.end ?? "");
    setQuery("");
    setOffset(0);
  }, [initial]);

  // Any change to what we're looking at sends us back to page 1. Staying on page 7 of a
  // different result set would show a page that has nothing to do with the request.
  useEffect(() => {
    setOffset(0);
  }, [accountId, start, end, query]);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    api
      .register({
        accountId,
        start: start || undefined,
        end: end || undefined,
        q: query.trim() || undefined,
        offset,
      })
      .then((result) => {
        if (!cancelled) {
          setPage(result);
          setError(null);
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [accountId, start, end, query, offset]);

  const showBalance = page?.has_running_balance ?? false;
  const from = page && page.count > 0 ? page.offset + 1 : 0;
  const to = page ? page.offset + page.count : 0;

  return (
    <section className="register" aria-labelledby="register-heading">
      <div className="register-head">
        <h2 id="register-heading">
          {page?.account ? `${page.account.code} ${page.account.name}` : "All transactions"}
        </h2>
        <button className="link" onClick={onClose}>
          close
        </button>
      </div>

      {error && (
        <div className="bad-box" role="alert">
          {error}
        </div>
      )}

      <div className="register-filters">
        <label htmlFor="reg-account">Account</label>
        <select
          id="reg-account"
          value={accountId === null ? ALL_ACCOUNTS : accountId}
          onChange={(e) =>
            setAccountId(e.target.value === ALL_ACCOUNTS ? null : Number(e.target.value))
          }
        >
          <option value={ALL_ACCOUNTS}>All accounts</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.code} {account.name}
            </option>
          ))}
        </select>

        <label htmlFor="reg-start">From</label>
        <input id="reg-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        <label htmlFor="reg-end">to</label>
        <input id="reg-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />

        {/* "Can't search for keywords in transactions" is a named QuickBooks complaint. */}
        <input
          type="text"
          placeholder="Search descriptions…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search descriptions"
        />
      </div>

      {page === null ? (
        <p className="muted register-empty">{busy ? "Loading…" : ""}</p>
      ) : page.total_count === 0 ? (
        <p className="muted register-empty">
          {page.is_filtered
            ? `Nothing matches “${page.query}”.`
            : "No transactions here yet."}
        </p>
      ) : (
        <>
          <table className="grid register-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                {/* All-accounts needs to say which account each row is; a single-account
                    register already says it in the heading. */}
                <th>{accountId === null ? "Account" : "Category"}</th>
                <th className="num">Amount</th>
                <th className="num">{showBalance ? "Balance" : ""}</th>
              </tr>
            </thead>
            <tbody>
              {showBalance && page.offset === 0 && page.opening_balance && (
                <tr className="register-opening">
                  <td className="date">{page.start ?? ""}</td>
                  <td colSpan={2} className="muted">
                    Balance brought forward
                  </td>
                  <td />
                  <td className="num">{page.opening_balance}</td>
                </tr>
              )}
              {page.lines.map((line, i) => (
                <tr key={`${line.entry_id}-${line.account_code}-${i}`}>
                  <td className="date">{line.date}</td>
                  <td className="desc" title={line.memo ?? line.description}>
                    {line.description}
                    {line.is_reversal && <span className="badge badge-review">correction</span>}
                  </td>
                  {/* The register hides the debits and credits; it must not hide where
                      the money actually went. */}
                  <td className="muted register-other">
                    {accountId === null ? line.account : (line.other_side ?? "—")}
                  </td>
                  <td className={line.amount_minor < 0 ? "num amount out" : "num amount in"}>
                    {line.amount}
                  </td>
                  <td className="num register-balance">
                    {line.running_balance ?? ""}
                    {line.reconciled && (
                      <span className="tick" title="Reconciled against your statement">
                        {" "}
                        ✓
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3}>
                  {page.total_count > page.count
                    ? `${from}–${to} of ${page.total_count}`
                    : `${page.total_count} ${page.total_count === 1 ? "transaction" : "transactions"}`}
                  {page.is_filtered && " matched"}
                </td>
                {/* The whole set's total, not the page's: this is the number the user
                    clicked on the report, and it must survive pagination. Suppressed in
                    the all-accounts view, where it is always exactly $0.00 -- every
                    entry's lines sum to zero, so the "total" of everything is the
                    debits==credits invariant wearing a confusing hat. */}
                <td className="num">{page.account ? page.total : ""}</td>
                <td className="num">{page.closing_balance ?? ""}</td>
              </tr>
            </tfoot>
          </table>

          {(page.offset > 0 || page.has_more) && (
            <div className="pager">
              <button
                disabled={page.offset === 0 || busy}
                onClick={() => setOffset(Math.max(0, offset - page.limit))}
              >
                ← Newer
              </button>
              <span className="muted">
                {from}–{to} of {page.total_count}
              </span>
              <button disabled={!page.has_more || busy} onClick={() => setOffset(offset + page.limit)}>
                Older →
              </button>
              {/* A per-page subtotal only means something for a single account. In the
                  all-accounts view every page is whole entry-pairs, so it is always
                  exactly $0.00 -- the same debits==credits invariant the footer total
                  suppresses. Showing it here would just reintroduce the confusing hat. */}
              {page.account && <span className="muted">this page: {page.page_total}</span>}
            </div>
          )}

          {!showBalance && (
            // Saying why beats an unexplained empty column.
            <p className="muted register-note">
              {page.is_filtered
                ? "Showing what matched, so there’s no running balance — a filtered list isn’t a statement."
                : "Showing every account, so there’s no running balance — adding up different accounts in one column wouldn’t mean anything. Pick one account to see it."}
            </p>
          )}
        </>
      )}
    </section>
  );
}
