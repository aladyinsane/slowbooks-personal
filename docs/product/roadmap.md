# Roadmap

Sequenced by "what proves the thesis," not by "what's easy."

## v0.1 — The spine (current)

The first slice: import → categorize → P&L + Balance Sheet, end to end on thin scope.
The point is to prove the core loop works before adding surface area.

**Scope changed 2026-07-16** (Lauren's call, after review of PR #1): bank reconciliation
and data export moved *up* from v0.2. Reasoning below — both are arguably what make the
rest mean anything.

- [x] Repo structure, docs, ADRs
- [x] Money as integer minor units (`money.py`)
- [x] SQLite schema with debits==credits enforced by trigger
- [x] Default GAAP-shaped Chart of Accounts
- [x] Double-entry ledger engine (post / void-by-reversal)
- [x] CSV import with dialect sniffing + column mapping
- [x] Duplicate detection on import
- [x] Deterministic rule engine + starter rule pack
- [x] P&L (Income Statement)
- [x] Balance Sheet
- [x] Trial Balance (proves the ledger; cheap once the rest exists)
- [x] FastAPI HTTP API
- [x] Frontend toolchain verified (Node 24 installed; typecheck + build + runtime green)
- [x] **Transfers** ← moved up from v0.2 during the grid build, because it was not a
      missing feature but an active defect: the category dropdown excluded bank
      accounts, so a transfer had *no correct option* and the user was forced to
      produce a wrong P&L. See [ADR 0007](../decisions/0007-transfers-are-not-categories.md).
- [x] **Bank reconciliation** ← moved up from v0.2. Turns "these are the numbers,
      probably" into "this period is proven to match the bank." The balance trigger only
      proves the books are *consistent*; this is the only thing that proves they're
      *complete*. See [ADR 0009](../decisions/0009-reconciliation-is-an-assertion.md).
      Reused `is_statement_account` from ADR 0007, as that ADR predicted.
- [x] **Full data export** ← moved up from v0.2. ADR 0001 stakes the entire product on
      "your books are yours"; until export existed that was a slogan. Now a ZIP with
      lossless table dumps, an accountant-readable general ledger, a README that explains
      itself, plus a raw .db download. See [ADR 0008](../decisions/0008-export-is-a-feature-not-a-debug-tool.md).
- [x] React UI — transaction categorization grid (the screen the product is about)
- [x] Visual design pass — calm/document-like ([design.md](design.md)), light + dark,
      contrast measured against WCAG AA in both
- [x] **Reports on screen, and a register to drill into.** The brief asked for a P&L and
      a Balance Sheet; they existed as endpoints from PR #1 and the UI never called one.
      Principle 8's test ("can the user get from any number to the underlying
      transactions?") now passes. See [ADR 0012](../decisions/0012-the-ledger-view-is-a-register.md).

## v0.2 — Trustworthy books

What's left of making the numbers *believable* once reconciliation is in.

- [x] **Period locking.** Closes ADR 0009's named gap: reconciliation detected backdated
      entries but couldn't prevent them. Enforced by a database trigger, and reversals
      now fall forward out of a closed period — the ADR 0004 follow-up coming due. See
      [ADR 0011](../decisions/0011-closing-a-period-locks-it.md). Decided *against*
      auto-locking on reconcile: reconciling one account isn't a statement about the
      period.
- [ ] **Reconciliation discrepancy help.** Today a non-zero difference is a dead end: we
      say *what* the gap is, not *why*. So the feature helps most when it succeeds and
      least when it fails — the wrong way round. Suggesting candidates (a missing
      transaction, a duplicate, an unimported fee) is the real fix.
- [ ] **Line-by-line reconciliation.** All-or-nothing to a date is simpler and wrong for
      anyone with a long statement. The schema already carries `reconciliation_id` per
      line, so this needs no migration.
- [ ] **Refund handling.** Credit reduces the original expense rather than creating
      revenue. Now the *most* likely source of a quietly wrong P&L, since transfers are
      handled. Note our transfer detector currently mistakes a same-week payment/refund
      pair across two accounts for a transfer — the user can reject it, but
      description-aware matching would be better.
- [ ] **Backup nagging + one-click backup.** The biggest risk in ADR 0001 is a user losing
      their only copy. Our headline advantage becomes a liability without this.
- [ ] **Import undo** (batch-level).
- [ ] Cash-basis reporting toggle **[needs CPA review]**

## v0.3 — Not making humans repeat themselves

Principle 5, systematically.

- [ ] Bulk operations (categorize, void) — directly answers a top QuickBooks complaint
- [ ] Real full-text search across transactions — ditto. The register has a substring
      filter (ADR 0012), which is the cheap 80%; this is the rest.
- [ ] Description cleaning (`SQ *COFFEE #1234 SEATTLE WA` → `Square — Coffee`)
- [ ] Rule suggestion from observed corrections
- [ ] Recurring transaction detection
- [ ] Keyboard-first categorization flow

## v0.4 — The accountant gate

The honest counter-argument to this whole product is *"my CPA expects QuickBooks."* Being
nice to use doesn't beat "my accountant can't open your file." These are survival features,
not nice-to-haves.

- [ ] General Ledger report
- [ ] Journal entry export
- [ ] Statement of Cash Flows (the third big-three statement; owners often care most)
- [ ] Manual journal entries (accountants will demand this immediately)
- [ ] Adjusting entries workflow
- [ ] Accountant-friendly export bundle
- [ ] **Get a real CPA to review the ledger and reports.** Blocks any real-user release.

## v0.5 — Loan statements

Called out separately because it's harder than it looks. A loan payment is a split:
principal reduces a liability (Balance Sheet only), interest is an expense (P&L). Most loan
CSVs give one row with one number and no split. Getting this wrong overstates expenses and
understates both profit and the loan balance — wrong on both statements at once.

- [ ] Split transactions (general capability; needed for more than loans)
- [ ] Amortization schedule support
- [ ] Loan account type with principal/interest allocation

## Later / undecided

See [future-features.md](future-features.md).

## Cross-cutting, always

- Performance budget: <100ms categorization, <1s reports at 50k transactions
- Packaging: a thing a non-technical owner can double-click — **done for Windows**
  ([ADR 0013](../decisions/0013-ship-as-a-double-click-app.md)): one `SlowBooks.exe`, no
  Python/Node/terminal. Still to do: code signing, and a macOS/Linux build.
- Test coverage on anything touching money
