import { useCallback, useEffect, useState } from "react";
import { AccountsPanel } from "./components/AccountsPanel";
import { ClosePanel } from "./components/ClosePanel";
import { ExportPanel } from "./components/ExportPanel";
import { RegisterView } from "./components/RegisterView";
import { ReportsPanel } from "./components/ReportsPanel";
import { ReconcilePanel } from "./components/ReconcilePanel";
import { StarterRuleBanner } from "./components/StarterRuleBanner";
import { TransactionGrid } from "./components/TransactionGrid";
import { api, type Account, type ImportSummary, type StagedTransaction } from "./lib/api";

/**
 * Import → review → post.
 *
 * The v0.1 slice, and the screen the whole product is about. The design commitment that
 * shapes it is ADR 0006: a category we guessed and a category the user taught us must
 * never look the same, because the dangerous failure is plausible-but-wrong rather than
 * obviously-wrong.
 */
export function App() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [balanced, setBalanced] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [accountId, setAccountId] = useState<number | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [rows, setRows] = useState<StagedTransaction[]>([]);
  const [showBanner, setShowBanner] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<number>>(new Set());
  const [posted, setPosted] = useState<string | null>(null);
  // Set when a report line is clicked, which is the whole point of principle 8.
  const [drill, setDrill] = useState<{
    accountId: number | null;
    start?: string;
    end?: string;
  } | null>(null);
  // Whether the register is on screen at all. This has to live here rather than in
  // RegisterView: "close" originally cleared `drill` and nothing else, so the section
  // stayed exactly where it was. A button that does something invisible is worse than
  // one that's missing.
  const [registerOpen, setRegisterOpen] = useState(false);

  const refreshHealth = useCallback(async () => {
    const health = await api.health();
    setBalanced(health.ledger_balanced);
  }, []);

  useEffect(() => {
    Promise.all([api.health(), api.listAccounts()])
      .then(([health, list]) => {
        setBalanced(health.ledger_balanced);
        setAccounts(list);
        const checking = list.find((a) => a.code === "1000");
        if (checking) setAccountId(checking.id);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  async function handleFile(file: File) {
    if (accountId === null) return;
    setBusy(true);
    setError(null);
    setPosted(null);
    try {
      const result = await api.importStatement(accountId, file);
      setSummary(result);
      setRows(await api.listStaged(result.batch_id));
      setShowBanner(result.warn_about_starter_rules);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function openRegister(next: { accountId: number | null; start?: string; end?: string }) {
    setDrill(next);
    setRegisterOpen(true);
    // The register renders below the reports, so bring it into view rather than
    // silently changing something off-screen.
    requestAnimationFrame(() =>
      document.getElementById("register-heading")?.scrollIntoView({ block: "center" }),
    );
  }

  function drillDown(accountCode: string, start?: string, end?: string) {
    const account = accounts.find((a) => a.code === accountCode);
    if (!account) return;
    openRegister({ accountId: account.id, start, end });
  }

  async function unlinkTransfer(stagedId: number) {
    try {
      await api.unlinkTransfer(stagedId);
      if (summary) setRows(await api.listStaged(summary.batch_id));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function categorize(stagedId: number, newAccountId: number | null) {
    // A draft, not a posting. Optimistic because principle 3 is about the 200th row
    // feeling instant; reverted below if the server disagrees.
    const previous = rows;
    setRows((current) =>
      current.map((row) =>
        row.id === stagedId
          ? {
              ...row,
              suggested_account_id: newAccountId,
              // The user just made this call, so it is no longer our guess (ADR 0006).
              is_starter_rule: false,
              reason: newAccountId ? "you chose this category" : null,
            }
          : row,
      ),
    );
    setPendingIds((ids) => new Set(ids).add(stagedId));
    setPosted(null);

    try {
      await api.categorize(stagedId, newAccountId);
    } catch (err) {
      setRows(previous);
      setError((err as Error).message);
    } finally {
      setPendingIds((ids) => {
        const next = new Set(ids);
        next.delete(stagedId);
        return next;
      });
    }
  }

  async function commit() {
    if (!summary) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.postBatch(summary.batch_id);
      setPosted(
        result.still_pending === 0
          ? `Recorded ${result.posted} transaction${result.posted === 1 ? "" : "s"}.`
          : `Recorded ${result.posted}. ${result.still_pending} still need a category.`,
      );
      setRows(await api.listStaged(summary.batch_id));
      await refreshHealth();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function acceptAll() {
    if (!summary) return;
    setBusy(true);
    try {
      // Acknowledge first: if posting fails the user has still seen the warning, and
      // re-warning them about rules they just accepted would be noise.
      await api.acknowledgeStarterRules();
      const result = await api.postBatch(summary.batch_id);
      setPosted(`Recorded ${result.posted}. ${result.still_pending} still need a category.`);
      setRows(await api.listStaged(summary.batch_id));
      setShowBanner(false);
      await refreshHealth();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function reviewInstead() {
    setBusy(true);
    try {
      await api.acknowledgeStarterRules();
      setShowBanner(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // A row is ready when it has a category (or is a matched transfer, which needs none)
  // and hasn't been recorded yet. Duplicates are excluded: they're flagged for a reason.
  const draftRows = rows.filter((r) => r.status === "pending");
  const readyToRecord = draftRows.filter(
    (r) => r.suggested_account_id !== null || r.is_transfer,
  ).length;
  const stillNeeded = draftRows.length - readyToRecord;

  return (
    <main>
      <header>
        <div>
          <h1>SlowBooks</h1>
          <p className="tagline">Simple accounting software that doesn&rsquo;t suck to use.</p>
        </div>
        {/* The ledger's health belongs at the top, not buried in a footer: it's the one
            fact that qualifies everything else on the page. */}
        <p className="ledger-state">
          <span className={balanced ? "ok" : "bad"}>
            {balanced === null ? "checking…" : balanced ? "Ledger balanced" : "LEDGER OUT OF BALANCE"}
          </span>
          <span className="muted"> · {accounts.length} accounts</span>
        </p>
      </header>

      {error && (
        <div className="bad-box" role="alert">
          <strong>Something went wrong:</strong> {error}
        </div>
      )}

      <section className="import-section" aria-labelledby="import-heading">
        <h2 id="import-heading">Import a statement</h2>
        <p className="lede">
          A CSV from your bank, card or loan account. Nothing is recorded until you say so.
        </p>
        <div className="import">
        <label htmlFor="account">Into</label>
        <select
          id="account"
          value={accountId ?? ""}
          onChange={(event) => setAccountId(Number(event.target.value))}
        >
          {accounts
            .filter((a) => a.is_statement_account)
            .map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} {account.name}
              </option>
            ))}
        </select>
        <input
          type="file"
          accept=".csv,text/csv"
          disabled={busy || accountId === null}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
            event.target.value = ""; // let the same file be re-picked after a fix
          }}
        />
        </div>
      </section>

      {summary && (
        <p className="summary">
          <strong>{summary.filename}</strong>: {summary.rows_read} rows,{" "}
          {summary.auto_categorized} categorized ({summary.from_starter_rules} by starter
          rules), {summary.needs_review} need review
          {summary.transfer_pairs_found > 0 &&
            `, ${summary.transfer_pairs_found} transfer${
              summary.transfer_pairs_found === 1 ? "" : "s"
            } matched`}
          {summary.duplicates_flagged > 0 &&
            `, ${summary.duplicates_flagged} possible duplicates`}
          .
        </p>
      )}

      {showBanner && summary && (
        <StarterRuleBanner
          count={summary.from_starter_rules}
          onAcceptAll={acceptAll}
          onReview={reviewInstead}
          busy={busy}
        />
      )}

      {posted && <p className="posted">{posted}</p>}

      {rows.length > 0 && (
        <>
          <TransactionGrid
            rows={rows}
            accounts={accounts}
            onCategorize={categorize}
            onUnlinkTransfer={unlinkTransfer}
            pendingIds={pendingIds}
          />

          {/* The commit step. Nothing above this line has touched the ledger, so the
              user can change anything until they press it (ADR 0004). */}
          {readyToRecord > 0 || stillNeeded > 0 ? (
            <div className="commit-bar">
              <p>
                <strong>
                  {readyToRecord} ready to record
                  {stillNeeded > 0 && `, ${stillNeeded} still need a category`}
                </strong>
                <span className="note">
                  {" "}
                  · nothing is recorded until you press the button
                </span>
              </p>
              <button className="primary" disabled={busy || readyToRecord === 0} onClick={commit}>
                {busy
                  ? "Recording…"
                  : `Record ${readyToRecord} transaction${readyToRecord === 1 ? "" : "s"}`}
              </button>
            </div>
          ) : null}
        </>
      )}

      <ReportsPanel onDrillDown={drillDown} />

      {registerOpen ? (
        <RegisterView
          accounts={accounts}
          initial={drill}
          onClose={() => {
            setRegisterOpen(false);
            setDrill(null);
          }}
        />
      ) : (
        // Closing has to leave a way back in, or "close" becomes "hide forever".
        <section className="register-closed">
          <button className="link plain" onClick={() => openRegister({ accountId: null })}>
            See your transactions
          </button>
        </section>
      )}

      <AccountsPanel />

      <ReconcilePanel />

      <ClosePanel />

      <ExportPanel />

      <footer>
        Your books live in a file on this computer. Nothing here is sent anywhere.
      </footer>
    </main>
  );
}
