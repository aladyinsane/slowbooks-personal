"""Money tests.

These are the tests that justify ADR 0003. If any of them fail, the ledger is
untrustworthy no matter how correct everything above it is.
"""

from __future__ import annotations

import pytest

from slowbooks import money


class TestParse:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("$1,234.56", 123456),
            ("1234.56", 123456),
            ("1,234.56", 123456),
            ("$0.01", 1),
            ("0", 0),
            ("-45", -4500),
            ("-45.00", -4500),
            ("(45.00)", -4500),      # accounting-style negative
            ("($1,234.56)", -123456),
            ("1.234,56", 123456),    # European
            ("€1.234,56", 123456),
            ("  $12.00  ", 1200),
            ("5", 500),              # bare integer is dollars, not cents
            ("3,000", 300000),           # US thousands grouping, no cents
            ("15,000", 1500000),
            ("100,000", 10000000),
            ("1,234,567", 123456700),    # multiple thousands groups
            ("1,234,567.89", 123456789), # thousands grouping plus real cents
            ("-3,000", -300000),
            ("12,50", 1250),             # short European decimal, not thousands
            ("3,5", 350),
        ],
    )
    def test_parses_real_world_formats(self, text, expected):
        assert money.parse(text) == expected

    @pytest.mark.parametrize("text", ["", "   ", "abc", "$", "12.34.56"])
    def test_rejects_garbage(self, text):
        with pytest.raises(money.MoneyParseError):
            money.parse(text)

    def test_rounds_half_up(self):
        # Banks occasionally emit sub-cent precision. Round, never truncate.
        assert money.parse("1.005") == 101
        assert money.parse("1.004") == 100


class TestFloatTraps:
    """The bugs ADR 0003 exists to prevent."""

    def test_the_classic(self):
        # 0.1 + 0.2 != 0.3 in float. In cents it is exact, and always will be.
        assert money.parse("0.1") + money.parse("0.2") == money.parse("0.3")

    def test_no_drift_over_many_additions(self):
        # Summing 0.01 ten thousand times drifts in float. Not here.
        assert sum(money.parse("0.01") for _ in range(10_000)) == money.parse("100.00")

    def test_round_trip_is_lossless(self):
        for text in ["0.01", "1234.56", "999999.99", "0.10", "0.20", "0.30"]:
            assert money.parse(money.format(money.parse(text))) == money.parse(text)


class TestFormat:
    @pytest.mark.parametrize(
        "minor,expected",
        [
            (123456, "$1,234.56"),
            (-123456, "-$1,234.56"),
            (0, "$0.00"),
            (1, "$0.01"),
            (100, "$1.00"),
            (99, "$0.99"),
            (100000000, "$1,000,000.00"),
        ],
    )
    def test_format(self, minor, expected):
        assert money.format(minor) == expected

    def test_accounting_format_uses_parens_for_negatives(self):
        assert money.format_accounting(-123456) == "($1,234.56)"
        assert money.format_accounting(123456) == "$1,234.56"


class TestAllocate:
    def test_splitting_ten_dollars_three_ways_loses_no_cent(self):
        shares = money.allocate(1000, [1, 1, 1])
        assert sum(shares) == 1000
        assert sorted(shares) == [333, 333, 334]

    def test_proportional_split(self):
        # A $1,200 loan payment split 75/25 principal/interest.
        shares = money.allocate(120000, [75, 25])
        assert shares == [90000, 30000]
        assert sum(shares) == 120000

    @pytest.mark.parametrize(
        "total,weights",
        [
            (100, [1, 1, 1]),
            (1, [1, 1]),
            (999999, [7, 3, 11]),
            (10, [1, 1, 1, 1, 1, 1, 1]),
            (5, [2, 2, 2, 2]),
        ],
    )
    def test_allocation_always_conserves_the_total(self, total, weights):
        assert sum(money.allocate(total, weights)) == total

    def test_negative_totals_conserve_too(self):
        # Refunds and reversals are negative; allocation must not leak a cent there.
        assert sum(money.allocate(-1000, [1, 1, 1])) == -1000

    def test_zero_weights_are_allowed_alongside_real_ones(self):
        assert money.allocate(1000, [1, 0, 1]) == [500, 0, 500]

    @pytest.mark.parametrize("weights", [[], [0, 0], [-1, 2]])
    def test_rejects_impossible_weights(self, weights):
        with pytest.raises(ValueError):
            money.allocate(1000, weights)
