"""Build a realistic set of books for professional review.

Produces the export we hand a CPA (see docs/review/cpa-review-request.md). Every
transaction here is chosen to exercise something we specifically want checked -- the
awkward cases, not the easy ones. A clean set of books would tell a reviewer nothing.

    python scripts/make_review_book.py [output_dir]

Writes review-book.zip (the accountant-facing export) and review-book.db (the raw book).
Fictional business, fictional numbers, no real people.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slowbooks import accounts, db, exporting, ledger, reconciliation  # noqa: E402


def build(conn) -> None:
    a = {code: accounts.by_code(conn, code).id for code in
         ["1000", "1010", "1500", "2100", "2500", "3000", "3100", "3900",
          "4000", "4100", "5000", "6050", "6100", "6200", "6250", "6350",
          "6400", "6500", "6600", "6700"]}

    def post(date, desc, lines, **kw):
        return ledger.post(conn, date, desc, lines, **kw)

    # --- Owner funds the business. Equity, not revenue. -----------------------
    post("2026-01-02", "Owner opening investment",
         [ledger.debit(a["1000"], 25_000_00), ledger.credit(a["3000"], 25_000_00)])

    # --- Ordinary revenue ----------------------------------------------------
    for date, amount, who in [
        ("2026-01-15", 8_400_00, "Client A — January retainer"),
        ("2026-02-13", 8_400_00, "Client A — February retainer"),
        ("2026-03-13", 8_400_00, "Client A — March retainer"),
        ("2026-02-20", 12_500_00, "Client B — project milestone"),
        ("2026-03-27", 6_750_00, "Client C — consulting"),
    ]:
        post(date, who, [ledger.debit(a["1000"], amount),
                         ledger.credit(a["4100"], amount)])

    # --- COGS, so gross profit is a real number and not a copy of net --------
    for date, amount, what in [
        ("2026-01-18", 3_100_00, "Subcontractor — January"),
        ("2026-02-19", 4_400_00, "Subcontractor — February"),
        ("2026-03-19", 2_900_00, "Subcontractor — March"),
    ]:
        post(date, what, [ledger.debit(a["5000"], amount),
                          ledger.credit(a["1000"], amount)])

    # --- Ordinary operating expenses ----------------------------------------
    for month, day in [("01", "31"), ("02", "28"), ("03", "31")]:
        post(f"2026-{month}-{day}", "Office rent",
             [ledger.debit(a["6200"], 2_200_00), ledger.credit(a["1000"], 2_200_00)])
        post(f"2026-{month}-{day}", "Utilities",
             [ledger.debit(a["6250"], 180_00), ledger.credit(a["1000"], 180_00)])

    # --- Expenses on the credit card: liability side of the ledger -----------
    for date, amount, what, code in [
        ("2026-01-08", 284_19, "Staples — office supplies", "6100"),
        ("2026-01-26", 412_40, "Delta Air Lines — client visit", "6400"),
        ("2026-02-11", 149_90, "Zoom — annual", "6100"),
        ("2026-03-04", 96_50, "Shell — fuel", "6500"),
        ("2026-03-22", 63_75, "USPS — shipping", "6600"),
    ]:
        post(date, what, [ledger.debit(a[code], amount), ledger.credit(a["2100"], amount)])

    # --- CHECK THIS (§4.4): paying the card is a transfer, not an expense.
    # Booking it as an expense would double-count -- these purchases were already
    # expensed when they were charged.
    post("2026-02-15", "Credit card payment",
         [ledger.debit(a["2100"], 846_49), ledger.credit(a["1000"], 846_49)],
         source="transfer")

    # --- CHECK THIS (§4.4): moving money between own accounts. No P&L impact.
    post("2026-02-02", "Transfer to savings",
         [ledger.debit(a["1010"], 10_000_00), ledger.credit(a["1000"], 10_000_00)],
         source="transfer")

    # --- CHECK THIS (§4.3): owner's draw is equity, never an expense ---------
    for date in ["2026-01-28", "2026-02-26", "2026-03-27"]:
        post(date, "Owner's draw",
             [ledger.debit(a["3100"], 3_000_00), ledger.credit(a["1000"], 3_000_00)])

    # --- CHECK THIS (§6): a loan payment, split by hand.
    # The software cannot do this split itself yet; it's done here manually to show the
    # treatment we believe is correct. Principal reduces the liability (Balance Sheet
    # only); interest is an expense (P&L).
    post("2026-01-05", "Equipment loan — opening",
         [ledger.debit(a["1500"], 18_000_00), ledger.credit(a["2500"], 18_000_00)])
    for date, principal, interest in [
        ("2026-01-31", 892_15, 107_85),
        ("2026-02-28", 896_61, 103_39),
        ("2026-03-31", 901_09, 98_91),
    ]:
        post(date, "Equipment loan payment",
             [ledger.debit(a["2500"], principal),
              ledger.debit(a["6700"], interest),
              ledger.credit(a["1000"], principal + interest)])

    # --- CHECK THIS (§4.6): a correction, done as a reversal ----------------
    mistake = post("2026-03-10", "Personal dinner — miscoded",
                   [ledger.debit(a["6350"], 210_00), ledger.credit(a["2100"], 210_00)])
    ledger.void(conn, mistake, "personal, not a business expense")

    # --- CHECK THIS (§4.5): a reconciled account ----------------------------
    # Checking balance at 2026-01-31, computed from the entries above.
    balance = ledger.account_balance(conn, a["1000"], as_of="2026-01-31")
    reconciliation.reconcile(conn, a["1000"], "2026-01-31", balance, "January statement")


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    out.mkdir(parents=True, exist_ok=True)

    book = out / "review-book.db"
    if book.exists():
        book.unlink()

    conn = db.connect(book)
    db.initialize(conn)
    build(conn)

    archive = out / "review-book.zip"
    archive.write_bytes(exporting.export_zip(conn))

    from slowbooks import money, reports

    pnl = reports.profit_and_loss(conn, "2026-01-01", "2026-03-31")
    sheet = reports.balance_sheet(conn, "2026-03-31")
    trial = reports.trial_balance(conn, "2026-03-31")

    print(f"  {archive}")
    print(f"  {book}\n")
    print("Q1 2026")
    print(f"  Revenue          {pnl['revenue']['total']:>14}")
    print(f"  COGS             {pnl['cost_of_goods_sold']['total']:>14}")
    print(f"  Gross profit     {pnl['gross_profit']:>14}")
    print(f"  Expenses         {pnl['operating_expenses']['total']:>14}")
    print(f"  Net income       {pnl['net_income']:>14}\n")
    print(f"  Assets           {sheet['assets']['total']:>14}")
    print(f"  Liabilities      {sheet['liabilities']['total']:>14}")
    print(f"  Equity           {sheet['equity']['total']:>14}")
    print(f"  Balances         {str(sheet['balanced']):>14}")
    print(f"  Trial balances   {str(trial['balanced']):>14}")

    earnings = next(
        (line for line in sheet["equity"]["lines"]
         if line["name"] == "Current Period Earnings"), None
    )
    agree = earnings and earnings["amount_minor"] == pnl["net_income_minor"]
    print(f"  P&L = BS earnings{str(bool(agree)):>14}")
    print(f"  Ledger balanced  {str(ledger.is_balanced(conn)):>14}")
    uncategorized = ledger.account_balance(conn, accounts.by_code(conn, "6900").id)
    print(f"\n  Uncategorized:   {money.format(uncategorized)}")
    conn.close()


if __name__ == "__main__":
    main()
