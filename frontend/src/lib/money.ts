/**
 * Money on the client.
 *
 * Mirror of the backend's money.py, and it exists under the same rule: money is an
 * integer of minor units (cents), never a float. JS is worse than most languages here
 * because every number is a float64 -- there is no int type to fall back on.
 *
 * See docs/decisions/0003-money-as-integer-minor-units.md.
 *
 * The backend already sends a formatted string alongside every amount, so display
 * normally needs nothing from this file. These helpers are for the cases where the UI
 * computes locally (a running total on a selection, say) and must not drift.
 */

/** Integer cents. The branded type makes an accidental float assignment a type error. */
export type Minor = number & { readonly __brand: "Minor" };

export function minor(value: number): Minor {
  if (!Number.isInteger(value)) {
    throw new Error(`money must be integer cents, got ${value}`);
  }
  return value as Minor;
}

export function format(value: Minor | number, symbol = "$"): string {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const whole = Math.floor(abs / 100);
  const cents = abs % 100;
  return `${sign}${symbol}${whole.toLocaleString("en-US")}.${String(cents).padStart(2, "0")}`;
}

/** Accounting style: negatives wear parentheses. */
export function formatAccounting(value: Minor | number, symbol = "$"): string {
  if (value < 0) return `(${format(Math.abs(value), symbol)})`;
  return format(value, symbol);
}

/** Sum integer cents. Exact, because they are integers. */
export function sum(values: readonly (Minor | number)[]): number {
  return values.reduce<number>((total, value) => total + value, 0);
}

/**
 * Parse what a person typed into integer cents. Returns null if it isn't a number.
 *
 * Mirrors backend money.parse() for the formats a human actually types off a bank
 * statement: "8,500.00", "$8500", "(45.00)" for a negative. Deliberately parsed to
 * integer cents *here*, at the boundary, so no float ever carries a monetary value
 * through the app (ADR 0003).
 *
 * The cents are built by string manipulation rather than `Math.round(x * 100)`:
 * "1.15" * 100 is 114.99999999999999 in float64, which rounds to 115 by luck and to
 * the wrong answer for other values. Not a risk worth taking with someone's books.
 */
export function parseInput(text: string): Minor | null {
  let cleaned = text.trim().replace(/[$£€\s,]/g, "");
  if (!cleaned) return null;

  let negative = false;
  const parens = /^\((.*)\)$/.exec(cleaned);
  if (parens) {
    negative = true;
    cleaned = parens[1];
  }
  if (cleaned.startsWith("-")) {
    negative = !negative;
    cleaned = cleaned.slice(1);
  }

  if (!/^\d*(\.\d*)?$/.test(cleaned) || cleaned === "." || cleaned === "") return null;

  const [whole, fraction = ""] = cleaned.split(".");
  const cents = (fraction + "00").slice(0, 2);
  const value = Number(whole || "0") * 100 + Number(cents);
  if (!Number.isSafeInteger(value)) return null;

  return (negative ? -value : value) as Minor;
}
