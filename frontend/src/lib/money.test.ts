import { describe, expect, it } from "vitest";
import { format, formatAccounting, minor, parseInput, sum } from "./money";

/**
 * Money tests for the client.
 *
 * These exist because parseInput is the first place in this codebase where a human's
 * typing becomes money, and JavaScript is the worst language we use for that: every
 * number is a float64, and there is no int to fall back on. ADR 0003's rule -- no float
 * anywhere near money -- is easy to state and easy to violate by writing `x * 100`.
 */

describe("parseInput", () => {
  it("reads what a person actually types off a statement", () => {
    expect(parseInput("8500")).toBe(850000);
    expect(parseInput("8500.00")).toBe(850000);
    expect(parseInput("8,500.00")).toBe(850000);
    expect(parseInput("$8,500.00")).toBe(850000);
    expect(parseInput("  8500.00  ")).toBe(850000);
    expect(parseInput("0.01")).toBe(1);
    expect(parseInput("0")).toBe(0);
  });

  it("handles negatives, including accounting style", () => {
    expect(parseInput("-45.00")).toBe(-4500);
    expect(parseInput("(45.00)")).toBe(-4500);
    expect(parseInput("($1,234.56)")).toBe(-123456);
  });

  it("pads and truncates the fraction like a cash register", () => {
    expect(parseInput("1.5")).toBe(150);
    expect(parseInput("1.")).toBe(100);
    expect(parseInput(".5")).toBe(50);
    // Sub-cent input is truncated, not rounded. A bank statement never has it, and
    // silently rounding someone's typing is a worse surprise than ignoring the extra.
    expect(parseInput("1.239")).toBe(123);
  });

  it("rejects things that aren't amounts", () => {
    expect(parseInput("")).toBeNull();
    expect(parseInput("   ")).toBeNull();
    expect(parseInput("abc")).toBeNull();
    expect(parseInput("1.2.3")).toBeNull();
    expect(parseInput("$")).toBeNull();
    expect(parseInput(".")).toBeNull();
    expect(parseInput("12abc")).toBeNull();
  });

  it("never produces a fractional cent", () => {
    const inputs = ["1.15", "1.005", "0.07", "1234.56", "99999.99", "0.1", "0.2"];
    for (const text of inputs) {
      const value = parseInput(text);
      expect(Number.isInteger(value)).toBe(true);
    }
  });

  it("avoids the float trap that `x * 100` would walk into", () => {
    // 1.15 * 100 === 114.99999999999999 in float64. Multiplying and rounding gets this
    // one right by luck; string-splitting gets it right by construction.
    expect(parseInput("1.15")).toBe(115);
    expect(parseInput("1.005")).toBe(100); // truncated, not 100.49999...
    expect(parseInput("0.07")! + parseInput("0.01")!).toBe(8);
  });

  it("round-trips through format", () => {
    for (const text of ["0.01", "1234.56", "8500.00", "999999.99"]) {
      expect(parseInput(format(parseInput(text)!))).toBe(parseInput(text));
    }
  });
});

describe("format", () => {
  it("formats cents for display", () => {
    expect(format(850000)).toBe("$8,500.00");
    expect(format(-123456)).toBe("-$1,234.56");
    expect(format(0)).toBe("$0.00");
    expect(format(1)).toBe("$0.01");
    expect(format(99)).toBe("$0.99");
    expect(format(100000000)).toBe("$1,000,000.00");
  });

  it("uses parentheses in accounting style", () => {
    expect(formatAccounting(-123456)).toBe("($1,234.56)");
    expect(formatAccounting(123456)).toBe("$1,234.56");
  });
});

describe("minor", () => {
  it("refuses a non-integer, because that would be a float in disguise", () => {
    expect(() => minor(12.5)).toThrow();
    expect(minor(1250)).toBe(1250);
  });
});

describe("sum", () => {
  it("is exact over many additions", () => {
    // Summing 0.01 ten thousand times drifts in float. In cents it cannot.
    expect(sum(Array(10_000).fill(1))).toBe(10_000);
  });
});
