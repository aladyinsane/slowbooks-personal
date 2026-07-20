import { useEffect, useState } from "react";
import { api, type ManagedAccount } from "../lib/api";

/**
 * Managing the chart of accounts (ADR 0010).
 *
 * The default chart is a guess about a life we haven't seen — the same objection
 * ADR 0006 raised about starter rules, one level up. So it has to be editable, and the
 * editing has to be incapable of breaking posted history.
 *
 * Rename, add and hide. Delete only when nothing references it, and when it does, the
 * refusal *says what is using it* — "used by 14 posted transactions" is an answer;
 * a greyed-out button is a wall.
 */

const TYPE_LABELS: Record<string, string> = {
  asset: "Things you own",
  liability: "Things you owe",
  equity: "Your stake",
  revenue: "Money coming in",
  expense: "Money going out",
};

const TYPE_ORDER = ["revenue", "expense", "asset", "liability", "equity"];

export function AccountsPanel() {
  const [accounts, setAccounts] = useState<ManagedAccount[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftGuidance, setDraftGuidance] = useState("");
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("expense");
  const [newGuidance, setNewGuidance] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    api.manageAccounts().then(setAccounts).catch((e: Error) => setError(e.message));

  useEffect(() => {
    if (open) void refresh();
  }, [open]);

  function startEdit(account: ManagedAccount) {
    setEditing(account.id);
    setDraftName(account.name);
    setDraftGuidance(account.guidance ?? "");
    setError(null);
  }

  async function save(id: number) {
    setBusy(true);
    try {
      await api.updateAccount(id, { name: draftName, description: draftGuidance });
      setEditing(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleHidden(account: ManagedAccount) {
    setBusy(true);
    setError(null);
    try {
      await api.updateAccount(account.id, { is_active: !account.is_active });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(account: ManagedAccount) {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(account.id);
      await refresh();
    } catch (e) {
      // Carries the "used by N posted transactions … hide it instead" explanation.
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!newName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createAccount({
        name: newName.trim(),
        type: newType,
        description: newGuidance.trim() || null,
      });
      setNewName("");
      setNewGuidance("");
      setAdding(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <section className="accounts-collapsed">
        <button className="link plain" onClick={() => setOpen(true)}>
          Manage categories
        </button>
      </section>
    );
  }

  return (
    <section className="accounts" aria-labelledby="accounts-heading">
      <h2 id="accounts-heading">Your categories</h2>
      <p className="lede">
        These started as our guess. Rename anything so it sounds like your life, add
        what&rsquo;s missing, and hide what you don&rsquo;t use — a shorter list makes
        categorizing faster.
      </p>

      {error && (
        <div className="bad-box" role="alert">
          {error}
        </div>
      )}

      {TYPE_ORDER.map((type) => {
        const group = accounts.filter((a) => a.type === type);
        if (group.length === 0) return null;
        return (
          <div key={type} className="account-group">
            <h3>{TYPE_LABELS[type]}</h3>
            <ul className="account-list">
              {group.map((account) => (
                <li key={account.id} className={account.is_active ? undefined : "hidden-account"}>
                  {editing === account.id ? (
                    <div className="account-edit">
                      <input
                        type="text"
                        value={draftName}
                        onChange={(e) => setDraftName(e.target.value)}
                        aria-label="Category name"
                      />
                      <input
                        type="text"
                        className="wide"
                        value={draftGuidance}
                        placeholder="What belongs here?"
                        onChange={(e) => setDraftGuidance(e.target.value)}
                        aria-label="Guidance"
                      />
                      <button className="primary" disabled={busy} onClick={() => save(account.id)}>
                        Save
                      </button>
                      <button disabled={busy} onClick={() => setEditing(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <span className="account-main">
                        <span className="picker-code">{account.code}</span> {account.name}
                        {!account.is_active && <span className="badge badge-review">hidden</span>}
                        {account.is_statement_account && (
                          <span className="badge badge-transfer">statement</span>
                        )}
                      </span>
                      {account.guidance && <span className="account-hint">{account.guidance}</span>}
                      <span className="account-actions">
                        <button className="link" disabled={busy} onClick={() => startEdit(account)}>
                          rename
                        </button>
                        {!account.is_statement_account && (
                          <button className="link" disabled={busy} onClick={() => toggleHidden(account)}>
                            {account.is_active ? "hide" : "unhide"}
                          </button>
                        )}
                        {/* Only offered when it's real. A button that only sometimes
                            works is the one people learn to distrust (ADR 0010). */}
                        {account.can_delete && (
                          <button className="link" disabled={busy} onClick={() => remove(account)}>
                            delete
                          </button>
                        )}
                      </span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      {adding ? (
        <div className="account-add">
          <input
            type="text"
            placeholder="Category name, e.g. Studio rent"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            aria-label="New category name"
          />
          <select
            value={newType}
            onChange={(e) => setNewType(e.target.value)}
            aria-label="Kind"
          >
            {TYPE_ORDER.map((type) => (
              <option key={type} value={type}>
                {TYPE_LABELS[type]}
              </option>
            ))}
          </select>
          <input
            type="text"
            className="wide"
            placeholder="What belongs here? (optional)"
            value={newGuidance}
            onChange={(e) => setNewGuidance(e.target.value)}
            aria-label="Guidance for the new category"
          />
          <button className="primary" disabled={busy || !newName.trim()} onClick={add}>
            Add
          </button>
          <button disabled={busy} onClick={() => setAdding(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <div className="account-footer">
          <button onClick={() => setAdding(true)}>Add a category</button>
          <button className="link" onClick={() => setOpen(false)}>
            done
          </button>
        </div>
      )}
    </section>
  );
}
