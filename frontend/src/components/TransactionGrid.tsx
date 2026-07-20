import { CategoryPicker } from "./CategoryPicker";
import type { Account, StagedTransaction } from "../lib/api";

/**
 * The categorization grid.
 *
 * Three commitments are visible here:
 *
 * - ADR 0004: choosing a category is a *draft*. Nothing reaches the ledger until the
 *   user commits the batch. This grid originally posted on selection, which froze a
 *   mis-click into an immutable entry — the exact escape hatch the ADR designed and the
 *   UI skipped.
 * - ADR 0006: a category we guessed and one the user taught us never look alike.
 * - ADR 0007: a transfer is not a category, so transfer rows get no picker at all.
 */

interface Props {
  rows: StagedTransaction[];
  accounts: Account[];
  onCategorize: (stagedId: number, accountId: number | null) => void;
  onUnlinkTransfer: (stagedId: number) => void;
  pendingIds: ReadonlySet<number>;
}

export function TransactionGrid({
  rows,
  accounts,
  onCategorize,
  onUnlinkTransfer,
  pendingIds,
}: Props) {
  // Categories are what money is spent on or earned from; statement accounts are where
  // money lives. Both are offered, but they are different questions (ADR 0007).
  const choices = accounts;

  return (
    <table className="grid">
      <thead>
        <tr>
          <th>Date</th>
          <th>Description</th>
          <th className="num">Amount</th>
          <th>Category</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const posted = row.status === "posted";
          const busy = pendingIds.has(row.id);
          return (
            <tr
              key={row.id}
              className={
                row.status === "duplicate"
                  ? "dupe"
                  : row.is_transfer
                    ? "transfer"
                    : posted
                      ? "row-posted"
                      : undefined
              }
            >
              <td className="date">{row.date}</td>
              <td className="desc" title={row.description}>
                {row.description}
                {row.status === "duplicate" && (
                  <span className="badge badge-dupe">possible duplicate</span>
                )}
              </td>
              <td className={row.amount_minor < 0 ? "num out" : "num in"}>{row.amount}</td>

              <td>
                {row.is_transfer ? (
                  // Money moving between your own accounts has no category, and offering
                  // one would be offering a wrong answer.
                  <span className="transfer-cell">
                    {row.amount_minor < 0 ? "Transfer to " : "Transfer from "}
                    <strong>{row.transfer_counterpart?.account ?? "another account"}</strong>
                    <span className="note"> · not income or expense</span>
                  </span>
                ) : (
                  <CategoryPicker
                    accounts={choices}
                    value={row.suggested_account_id}
                    disabled={posted || busy}
                    excludeId={row.account_id}
                    onChange={(accountId) => onCategorize(row.id, accountId)}
                  />
                )}
              </td>

              <td className="source">
                {posted ? (
                  <span className="badge badge-posted">recorded</span>
                ) : row.is_transfer ? (
                  <>
                    <span
                      className="badge badge-transfer"
                      title={
                        row.transfer_counterpart
                          ? `Matched to ${row.transfer_counterpart.description} on ${row.transfer_counterpart.date}`
                          : undefined
                      }
                    >
                      transfer
                    </span>
                    <button
                      className="link"
                      onClick={() => onUnlinkTransfer(row.id)}
                      title="These are two separate transactions, not a transfer"
                    >
                      not a transfer
                    </button>
                  </>
                ) : row.suggested_account_id === null ? (
                  <span className="badge badge-review">needs review</span>
                ) : row.is_starter_rule ? (
                  <span className="badge badge-starter" title={row.reason ?? undefined}>
                    starter rule
                  </span>
                ) : (
                  <span className="badge badge-yours" title={row.reason ?? undefined}>
                    your rule
                  </span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
