import { useCallback, useEffect, useState } from "react";
import {
  api,
  type BalanceSheet,
  type ProfitAndLoss,
  type ReportLine,
  type TrialBalance,
} from "../lib/api";

/**
 * The reports, on screen at last (ADR 0012).
 *
 * These endpoints have existed since PR #1 — tested, exported, correct — and the UI
 * never called one. The original brief asked for a P&L and a Balance Sheet by name, and
 * the only way to see them was curl or a ZIP file.
 *
 * Every line is a button, because principle 8's test is "can the user get from any
 * number to the underlying transactions?" — and until now the answer was no.
 */

interface Props {
  onDrillDown: (accountCode: string, start?: string, end?: string) => void;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function yearStartISO(): string {
  return `${new Date().getFullYear()}-01-01`;
}

// "July 17, 2026" — for the printed statement heading, where an ISO date looks like a
// receipt, not a report. Local midnight so the date doesn't slip a day across UTC.
function formatLong(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

export function ReportsPanel({ onDrillDown }: Props) {
  const [tab, setTab] = useState<"pnl" | "balance" | "trial">("pnl");
  const [start, setStart] = useState(yearStartISO());
  const [end, setEnd] = useState(todayISO());
  const [pnl, setPnl] = useState<ProfitAndLoss | null>(null);
  const [sheet, setSheet] = useState<BalanceSheet | null>(null);
  const [trial, setTrial] = useState<TrialBalance | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, b, t] = await Promise.all([
        api.profitAndLoss(start, end),
        api.balanceSheet(end),
        api.trialBalance(end),
      ]);
      setPnl(p);
      setSheet(b);
      setTrial(t);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [start, end]);

  useEffect(() => {
    void load();
  }, [load]);

  // Every figure is a door. A line with no code (the computed earnings row) isn't one,
  // because there are no transactions behind it — it's arithmetic over other lines.
  const Line = ({ line }: { line: ReportLine }) => (
    <tr>
      <td>
        {line.code ? (
          <button className="drill" onClick={() => onDrillDown(line.code, start, end)}>
            <span className="picker-code">{line.code}</span> {line.name}
          </button>
        ) : (
          <span className="computed">{line.name}</span>
        )}
      </td>
      <td className="num">{line.amount}</td>
    </tr>
  );

  const Section = ({ title, lines, total }: { title: string; lines: ReportLine[]; total: string }) => (
    <>
      <tr className="section-head">
        <th colSpan={2}>{title}</th>
      </tr>
      {lines.length === 0 ? (
        <tr>
          <td colSpan={2} className="muted">
            Nothing yet
          </td>
        </tr>
      ) : (
        lines.map((line) => <Line key={line.code + line.name} line={line} />)
      )}
      <tr className="section-total">
        <td>Total {title.toLowerCase()}</td>
        <td className="num">{total}</td>
      </tr>
    </>
  );

  const reportTitle =
    tab === "pnl" ? "Profit & Loss" : tab === "balance" ? "Balance Sheet" : "Trial Balance";
  const periodLabel =
    tab === "pnl" ? `For ${formatLong(start)} – ${formatLong(end)}` : `As of ${formatLong(end)}`;

  return (
    <section className="reports" aria-labelledby="reports-heading">
      <h2 id="reports-heading">Your reports</h2>
      <p className="lede">
        Click any line to see the transactions behind it. Every number here is added up
        from your books — nothing is stored or cached, so it can&rsquo;t drift.
      </p>

      {error && (
        <div className="bad-box" role="alert">
          {error}
        </div>
      )}

      <div className="report-controls">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "pnl"} onClick={() => setTab("pnl")}>
            Profit &amp; Loss
          </button>
          <button role="tab" aria-selected={tab === "balance"} onClick={() => setTab("balance")}>
            Balance Sheet
          </button>
          <button role="tab" aria-selected={tab === "trial"} onClick={() => setTab("trial")}>
            Trial Balance
          </button>
        </div>
        <div className="report-dates">
          {tab === "pnl" && (
            <>
              <label htmlFor="rep-start">From</label>
              <input
                id="rep-start"
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </>
          )}
          <label htmlFor="rep-end">{tab === "pnl" ? "to" : "as of"}</label>
          <input id="rep-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          {/* A report you can only look at on screen is half a report — the bank and the
              CPA want paper. The print stylesheet does the rest. */}
          <button type="button" className="print-button" onClick={() => window.print()}>
            Print
          </button>
        </div>
      </div>

      {/* Print-only: a real statement heading. On screen the tabs and date pickers say
          which report and period this is; on paper they're gone, so it has to say so. */}
      <div className="report-print-head" aria-hidden="true">
        <p className="print-title">{reportTitle}</p>
        <p className="print-period">{periodLabel}</p>
      </div>

      {tab === "pnl" && pnl && (
        <table className="report">
          <tbody>
            <Section title="Revenue" lines={pnl.revenue.lines} total={pnl.revenue.total} />
            {pnl.cost_of_goods_sold.lines.length > 0 && (
              <Section
                title="Cost of goods sold"
                lines={pnl.cost_of_goods_sold.lines}
                total={pnl.cost_of_goods_sold.total}
              />
            )}
            {pnl.cost_of_goods_sold.lines.length > 0 && (
              <tr className="subtotal">
                <td>Gross profit</td>
                <td className="num">{pnl.gross_profit}</td>
              </tr>
            )}
            <Section
              title="Expenses"
              lines={pnl.operating_expenses.lines}
              total={pnl.operating_expenses.total}
            />
            <tr className="report-bottom-line">
              <td>{pnl.net_income_minor < 0 ? "Net loss" : "Net profit"}</td>
              <td className={pnl.net_income_minor < 0 ? "num out" : "num in"}>
                {pnl.net_income}
              </td>
            </tr>
          </tbody>
        </table>
      )}

      {tab === "balance" && sheet && (
        <table className="report">
          <tbody>
            <Section title="Assets" lines={sheet.assets.lines} total={sheet.assets.total} />
            <Section
              title="Liabilities"
              lines={sheet.liabilities.lines}
              total={sheet.liabilities.total}
            />
            <Section title="Equity" lines={sheet.equity.lines} total={sheet.equity.total} />
            <tr className="report-bottom-line">
              <td>Liabilities and equity</td>
              <td className="num">{sheet.total_liabilities_and_equity}</td>
            </tr>
            <tr>
              <td colSpan={2} className={sheet.balanced ? "ok balance-check" : "bad balance-check"}>
                {sheet.balanced
                  ? "Assets match liabilities plus equity, as they must."
                  : "THESE DO NOT BALANCE — this is a bug, please tell us."}
              </td>
            </tr>
          </tbody>
        </table>
      )}

      {tab === "trial" && trial && (
        <table className="report trial-table">
          <thead>
            <tr>
              <th>Account</th>
              <th className="num">Debit</th>
              <th className="num">Credit</th>
            </tr>
          </thead>
          <tbody>
            {trial.lines.map((line) => (
              <tr key={line.code}>
                <td>
                  <button className="drill" onClick={() => onDrillDown(line.code)}>
                    <span className="picker-code">{line.code}</span> {line.name}
                  </button>
                </td>
                <td className="num">{line.debit}</td>
                <td className="num">{line.credit}</td>
              </tr>
            ))}
            <tr className="report-bottom-line">
              <td>Total</td>
              <td className="num">{trial.total_debits}</td>
              <td className="num">{trial.total_credits}</td>
            </tr>
          </tbody>
        </table>
      )}

      {/* Print-only provenance. If this sheet ends up in front of a bank or an accountant,
          it should say what it is without being asked. */}
      <p className="report-print-foot" aria-hidden="true">
        Prepared {formatLong(todayISO())} with SlowBooks — self-prepared from imported
        records, not reviewed by an accountant.
      </p>
    </section>
  );
}
