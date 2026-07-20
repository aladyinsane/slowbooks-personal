/**
 * Typed client for the local SlowBooks API.
 *
 * Vite proxies /api to the backend in dev (see vite.config.ts), so this is always a
 * same-origin call to a process on this machine. There is no remote (ADR 0001).
 *
 * Longer term these types should be generated from FastAPI's OpenAPI schema rather
 * than hand-maintained -- tracked in ADR 0002's follow-ups.
 */

const BASE = "/api";

export interface Account {
  id: number;
  code: string;
  name: string;
  type: "asset" | "liability" | "equity" | "revenue" | "expense";
  normal_balance: "debit" | "credit";
  /**
   * An account you can import a statement for and move money between (ADR 0007).
   * Replaces the old `code.startsWith("10")` guess, which wrongly offered Accounts
   * Receivable and Equipment as transfer targets.
   */
  is_statement_account: boolean;
  /** One plain sentence explaining what belongs here. Shown at the moment of choosing. */
  guidance: string | null;
}

export interface StagedTransaction {
  id: number;
  date: string;
  description: string;
  amount_minor: number;
  amount: string;
  status: "pending" | "posted" | "duplicate" | "ignored";
  /** The statement account this row was imported from. */
  account_id: number;
  suggested_account_id: number | null;
  suggested_account: string | null;
  /** Why this was suggested. Principle 8 -- always show the work. */
  reason: string | null;
  rule_id: number | null;
  /**
   * True when the suggestion came from the shipped starter pack rather than a rule the
   * user taught us. ADR 0006: a guess and a taught rule must never look alike, because
   * a plausible-but-wrong category is easy to click past.
   */
  is_starter_rule: boolean;
  /** Paired with its other side. A transfer has no category (ADR 0007). */
  is_transfer: boolean;
  transfer_match_id: number | null;
  transfer_counterpart: {
    account: string;
    date: string;
    description: string;
  } | null;
}

export interface ImportSummary {
  batch_id: number;
  filename: string;
  rows_read: number;
  duplicates_flagged: number;
  auto_categorized: number;
  /** How many suggestions are shipped guesses (ADR 0006). */
  from_starter_rules: number;
  /** Transfers detected between the user's own accounts (ADR 0007). */
  transfer_pairs_found: number;
  /** True on the first import where starter rules fired and weren't acknowledged. */
  warn_about_starter_rules: boolean;
  needs_review: number;
  date_range: string[];
}

export interface ReportLine {
  code: string;
  name: string;
  amount_minor: number;
  amount: string;
}

export interface ReportSection {
  lines: ReportLine[];
  total_minor: number;
  total: string;
}

/** "Income & Expenses" (ADR 0015) -- what accounting calls Profit & Loss. */
export interface IncomeAndExpenses {
  report: string;
  basis: string;
  period: { start: string; end: string };
  revenue: ReportSection;
  operating_expenses: ReportSection;
  net_income_minor: number;
  net_income: string;
}

/** "Net Worth" (ADR 0015) -- what accounting calls a Balance Sheet. */
export interface NetWorth {
  report: string;
  as_of: string;
  assets: ReportSection;
  liabilities: ReportSection;
  equity: ReportSection;
  total_liabilities_and_equity: string;
  balanced: boolean;
}

/**
 * Reconciliation (ADR 0009). Note this is the user's *assertion* that the books match
 * the bank, not a status we computed — which is why the bank's balance is an input.
 */
export interface ReconciliationPreview {
  account_id: number;
  account: string;
  statement_date: string;
  statement_balance_minor: number;
  statement_balance: string;
  book_balance_minor: number;
  book_balance: string;
  difference_minor: number;
  difference: string;
  unreconciled_line_count: number;
  can_reconcile: boolean;
  /** Plain-language nudge toward the cause of a gap. Null when it matches. */
  hint: string | null;
}

export interface ReconciliationRecord {
  id: number;
  account_id: number;
  statement_date: string;
  statement_balance: string;
  book_balance: string;
  reconciled_at: string;
  note: string | null;
  reverses_id: number | null;
}

export interface ReconciliationStatus {
  account_id: number;
  account: string;
  reconciled_through: string | null;
  reconciliation_id: number | null;
  current_balance_minor: number;
}

export interface BackdatedEntry {
  entry_id: number;
  entry_date: string;
  description: string;
  account_code: string;
  account_name: string;
  statement_date: string;
}

/** The register: transactions, date order, running balance (ADR 0012). */
export interface RegisterLine {
  entry_id: number;
  date: string;
  description: string;
  memo: string | null;
  /** This line's own account. Needed by the all-accounts view. */
  account: string;
  account_code: string;
  /** Where the money went — the register hides debits/credits, not the story. */
  other_side: string | null;
  amount_minor: number;
  amount: string;
  /** Null unless the view is one account and unfiltered — otherwise it means nothing. */
  running_balance_minor: number | null;
  running_balance: string | null;
  source: string;
  is_reversal: boolean;
  reconciled: boolean;
}

export interface Register {
  /** Null in the all-accounts view. */
  account: { id: number; code: string; name: string; type: string } | null;
  start: string | null;
  end: string | null;
  query: string | null;
  is_filtered: boolean;
  /**
   * False for all-accounts or a search. A running balance needs one account (so the
   * column means something) and no filter (a search result isn't a statement).
   */
  has_running_balance: boolean;
  opening_balance: string | null;
  closing_balance: string | null;
  closing_balance_minor: number | null;
  /**
   * The whole filtered set, across every page. This is the drill-down contract: the
   * user clicked this number on a report, and it must survive pagination.
   */
  total: string;
  total_minor: number;
  /** Rows in the whole filtered set. */
  total_count: number;
  /** This page only — not the whole filtered set. */
  page_total: string;
  page_total_minor: number;
  /** Rows on this page. */
  count: number;
  limit: number;
  offset: number;
  has_more: boolean;
  lines: RegisterLine[];
}

export interface TrialBalanceLine {
  code: string;
  name: string;
  type: string;
  debit: string;
  credit: string;
  debit_minor: number;
  credit_minor: number;
}

export interface TrialBalance {
  as_of: string;
  lines: TrialBalanceLine[];
  total_debits: string;
  total_credits: string;
  balanced: boolean;
}

/** Period closing (ADR 0011). Closing freezes everything on or before the date. */
export interface PeriodClose {
  id: number;
  closed_through: string;
  closed_at: string;
  note: string | null;
  /** Set when this record reopens an earlier close. Append-only, like the ledger. */
  reopens_id: number | null;
}

export interface PeriodStatus {
  closed_through: string | null;
  first_open_date: string;
  current_close: PeriodClose | null;
  history: PeriodClose[];
}

export interface PeriodReadiness {
  through: string;
  unreconciled_accounts: { account: string; reconciled_through: string | null }[];
  uncategorized_transactions: number;
  /** Advisory only — nothing here blocks a close (ADR 0011). */
  is_tidy: boolean;
}

/** Chart-of-accounts management (ADR 0010). */
export interface ManagedAccount extends Account {
  is_active: boolean;
  usage: {
    posted_lines: number;
    staged_transactions: number;
    rules: number;
    reconciliations: number;
  };
  /** False once anything references it. "Hide" is the honest verb then. */
  can_delete: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    // FastAPI puts the human-readable message in `detail`. Surfacing it beats a
    // generic failure toast -- the import errors in particular name the exact line.
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; ledger_balanced: boolean }>("/health"),

  bookFile: () =>
    request<{
      path: string;
      directory: string;
      filename: string;
      exists: boolean;
      size_bytes: number;
    }>("/book-file"),

  listAccounts: () => request<Account[]>("/accounts"),

  importStatement: (accountId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportSummary>(`/imports?account_id=${accountId}`, {
      method: "POST",
      body: form,
    });
  },

  listStaged: (batchId: number) =>
    request<StagedTransaction[]>(`/imports/${batchId}/transactions`),

  /**
   * Choose a category WITHOUT posting (ADR 0004's draft zone). Reversible; the grid
   * used to post on selection, which froze a mis-click into an immutable entry.
   */
  categorize: (stagedId: number, accountId: number | null) =>
    request<{ id: number; account_id: number | null }>(`/staged/${stagedId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId }),
    }),

  postStaged: (stagedId: number, accountId?: number) =>
    request<{ entry_id: number }>(`/staged/${stagedId}/post`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId ?? null }),
    }),

  postBatch: (batchId: number) =>
    request<{ posted: number; still_pending: number }>(`/imports/${batchId}/post`, {
      method: "POST",
    }),

  unlinkTransfer: (stagedId: number) =>
    fetch(`${BASE}/staged/${stagedId}/transfer-match`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`could not unlink transfer: ${r.status}`);
    }),

  incomeAndExpenses: (start: string, end: string) =>
    request<IncomeAndExpenses>(`/reports/income-and-expenses?start=${start}&end=${end}`),

  netWorth: (asOf: string) =>
    request<NetWorth>(`/reports/net-worth?as_of=${asOf}`),

  trialBalance: (asOf: string) =>
    request<TrialBalance>(`/reports/trial-balance?as_of=${asOf}`),

  /**
   * Where every report number drills down to (principle 8).
   * `accountId: null` lists every account — a list, not a statement, so no balance.
   */
  register: (opts: {
    accountId?: number | null;
    start?: string;
    end?: string;
    q?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const params = new URLSearchParams();
    if (opts.accountId != null) params.set("account_id", String(opts.accountId));
    if (opts.start) params.set("start", opts.start);
    if (opts.end) params.set("end", opts.end);
    if (opts.q) params.set("q", opts.q);
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.offset) params.set("offset", String(opts.offset));
    return request<Register>(`/reports/register?${params}`);
  },

  periodStatus: () => request<PeriodStatus>("/periods"),

  periodReadiness: (through: string) =>
    request<PeriodReadiness>(`/periods/readiness?through=${through}`),

  closePeriod: (through: string, note?: string) =>
    request<PeriodClose>("/periods/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ through, note: note ?? null }),
    }),

  reopenPeriod: (closeId: number, reason?: string) =>
    request<PeriodClose>(`/periods/${closeId}/reopen`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason ?? null }),
    }),

  manageAccounts: () => request<ManagedAccount[]>("/accounts/manage"),

  nextCode: (type: string) =>
    request<{ code: string }>(`/accounts/next-code?type=${type}`),

  createAccount: (payload: {
    name: string;
    type: string;
    description?: string | null;
    // Omitted on purpose: the number range is what makes the type safe, so picking it
    // is our job (ADR 0010).
    code?: string;
  }) =>
    request<Account>("/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  updateAccount: (
    id: number,
    payload: { name?: string; description?: string | null; is_active?: boolean },
  ) =>
    request<Account>(`/accounts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  deleteAccount: async (id: number) => {
    const response = await fetch(`${BASE}/accounts/${id}`, { method: "DELETE" });
    if (!response.ok) {
      // 409 carries the "used by 14 posted transactions" explanation, which is the
      // whole point — surface it rather than a generic failure.
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail ?? `${response.status} ${response.statusText}`);
    }
  },

  previewReconciliation: (
    accountId: number,
    statementDate: string,
    statementBalanceMinor: number,
  ) =>
    request<ReconciliationPreview>(
      `/reconciliation/preview?account_id=${accountId}` +
        `&statement_date=${statementDate}` +
        `&statement_balance_minor=${statementBalanceMinor}`,
    ),

  reconcile: (
    accountId: number,
    statementDate: string,
    statementBalanceMinor: number,
    note?: string,
  ) =>
    request<ReconciliationRecord>("/reconciliation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        account_id: accountId,
        statement_date: statementDate,
        statement_balance_minor: statementBalanceMinor,
        note: note ?? null,
      }),
    }),

  reconciliationStatus: () => request<ReconciliationStatus[]>("/reconciliation/status"),

  reconciliationHistory: (accountId?: number) =>
    request<ReconciliationRecord[]>(
      accountId ? `/reconciliation?account_id=${accountId}` : "/reconciliation",
    ),

  undoReconciliation: (id: number, reason?: string) =>
    request<ReconciliationRecord>(`/reconciliation/${id}/undo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason ?? null }),
    }),

  backdatedEntries: () => request<BackdatedEntry[]>("/reconciliation/backdated"),

  /**
   * Download URLs rather than fetch() calls: the browser's own download machinery
   * handles the file, so we don't buffer a whole archive in JS just to hand it back.
   */
  exportZipUrl: `${BASE}/export/zip`,
  exportDatabaseUrl: `${BASE}/export/database`,
  exportJsonUrl: `${BASE}/export/json`,

  starterRulesAcknowledged: () =>
    request<{ acknowledged: boolean }>("/settings/starter-rules-acknowledged"),

  acknowledgeStarterRules: () =>
    request<{ acknowledged: boolean }>("/settings/starter-rules-acknowledged", {
      method: "POST",
    }),
};
