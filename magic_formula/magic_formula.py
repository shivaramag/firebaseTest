"""
Magic Formula stock ranking.

An implementation of the "Magic Formula" from Joel Greenblatt's book
*The Little Book That Still Beats the Market*.

The idea is to buy good businesses at cheap prices, quantified by two metrics:

  1. Return on Capital (a "good business")
         ROC = EBIT / (Net Working Capital + Net Fixed Assets)

  2. Earnings Yield (a "cheap price")
         EY  = EBIT / Enterprise Value
         EV  = Market Cap + Total Debt - Cash

Each stock is ranked separately on both metrics (rank 1 = best). The two
ranks are added together, and the stocks with the *lowest* combined rank are
the most attractive. You then buy a basket of the top-ranked names, hold for
about a year, and repeat.

This module has no third-party dependencies (standard library only) so it can
run anywhere. See README.md for the full explanation and reasoning.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional


# Sectors Greenblatt excludes from the screen. Financials and utilities have
# balance sheets that make the capital / earnings-yield math misleading.
DEFAULT_EXCLUDED_SECTORS = frozenset({"financials", "financial", "utilities", "utility"})

# Default minimum market capitalization, expressed in the SAME UNITS as the
# input amounts. The sample data is in millions of USD, so 50 == $50M.
# Greenblatt's own screener lets you pick a floor (e.g. $50M, $200M, $1B, $2B,
# $5B) to avoid illiquid micro-caps. Set --min-market-cap to match your data.
DEFAULT_MIN_MARKET_CAP = 50.0

# Default number of names in the basket.
DEFAULT_BASKET_SIZE = 20


@dataclass
class Stock:
    """A single company with the fundamentals the Magic Formula needs.

    All monetary values should be in the same currency and units (e.g. dollars).
    """

    ticker: str
    name: str = ""
    sector: str = ""

    # Operating earnings. EBIT = Earnings Before Interest and Taxes.
    ebit: float = 0.0

    # Pieces needed to value the whole business (Enterprise Value).
    market_cap: float = 0.0          # price * shares outstanding
    total_debt: float = 0.0          # short-term + long-term interest-bearing debt
    cash: float = 0.0                # cash + cash equivalents (and short-term investments)

    # Pieces needed for Return on Capital (tangible capital employed).
    current_assets: float = 0.0
    current_liabilities: float = 0.0
    net_fixed_assets: float = 0.0    # net PP&E (property, plant & equipment)

    # --- Derived metrics (filled in by compute()) ---
    enterprise_value: float = field(default=0.0, init=False)
    capital_employed: float = field(default=0.0, init=False)
    return_on_capital: Optional[float] = field(default=None, init=False)
    earnings_yield: Optional[float] = field(default=None, init=False)

    def compute(self) -> None:
        """Populate the derived metrics from the raw inputs."""
        # Enterprise Value: what it would cost to buy the whole business.
        self.enterprise_value = self.market_cap + self.total_debt - self.cash

        # Tangible capital employed = net working capital + net fixed assets.
        net_working_capital = self.current_assets - self.current_liabilities
        self.capital_employed = net_working_capital + self.net_fixed_assets

        # Return on Capital. Undefined when capital employed is <= 0 (the
        # business runs on negative capital, so the ratio is not meaningful).
        if self.capital_employed > 0:
            self.return_on_capital = self.ebit / self.capital_employed
        else:
            self.return_on_capital = None

        # Earnings Yield. Undefined when EV is <= 0 (net cash exceeds market
        # cap + debt), where the yield is not meaningful.
        if self.enterprise_value > 0:
            self.earnings_yield = self.ebit / self.enterprise_value
        else:
            self.earnings_yield = None

    def is_rankable(self) -> bool:
        """Whether both metrics are defined (required to be ranked)."""
        return self.return_on_capital is not None and self.earnings_yield is not None


@dataclass
class RankedStock:
    """A stock plus its ranks and combined Magic Formula score."""

    stock: Stock
    roc_rank: int
    ey_rank: int

    @property
    def combined_rank(self) -> int:
        return self.roc_rank + self.ey_rank


def _competition_rank(
    stocks: list[Stock], key, higher_is_better: bool = True
) -> dict[str, int]:
    """Rank stocks by ``key`` using standard competition ranking (1224).

    Equal values receive the same rank; the next distinct value skips ahead.
    Rank 1 is the best. Returns a mapping of ticker -> rank.
    """
    ordered = sorted(stocks, key=key, reverse=higher_is_better)
    ranks: dict[str, int] = {}
    previous_value = object()  # sentinel that never equals a real value
    previous_rank = 0
    for position, stock in enumerate(ordered, start=1):
        value = key(stock)
        if value != previous_value:
            previous_rank = position
            previous_value = value
        ranks[stock.ticker] = previous_rank
    return ranks


def rank_stocks(
    stocks: Iterable[Stock],
    *,
    excluded_sectors: Iterable[str] = DEFAULT_EXCLUDED_SECTORS,
    min_market_cap: float = DEFAULT_MIN_MARKET_CAP,
    require_positive_ebit: bool = True,
) -> list[RankedStock]:
    """Run the Magic Formula and return stocks ordered best-first.

    Steps 1-4 of the formula:
      1. Compute Return on Capital for every stock.
      2. Compute Earnings Yield for every stock.
      3. Rank every stock on both numbers separately.
      4. Add the two ranks together; the lowest combined number wins.

    Filters applied first (Greenblatt's standard exclusions):
      * drop excluded sectors (financials, utilities),
      * drop names below the market-cap floor,
      * drop unprofitable companies (EBIT <= 0) when required,
      * drop names where either metric is undefined (non-positive capital
        employed or enterprise value).
    """
    excluded = {s.strip().lower() for s in excluded_sectors}

    eligible: list[Stock] = []
    for stock in stocks:
        stock.compute()

        if stock.sector.strip().lower() in excluded:
            continue
        if stock.market_cap < min_market_cap:
            continue
        if require_positive_ebit and stock.ebit <= 0:
            continue
        if not stock.is_rankable():
            continue
        eligible.append(stock)

    # Step 3: rank separately. Higher ROC and higher EY are both better.
    roc_ranks = _competition_rank(
        eligible, key=lambda s: s.return_on_capital, higher_is_better=True
    )
    ey_ranks = _competition_rank(
        eligible, key=lambda s: s.earnings_yield, higher_is_better=True
    )

    ranked = [
        RankedStock(stock=s, roc_rank=roc_ranks[s.ticker], ey_rank=ey_ranks[s.ticker])
        for s in eligible
    ]

    # Step 4: lowest combined rank wins. Break ties by earnings yield (cheaper
    # first), then ticker for a stable, deterministic order.
    ranked.sort(
        key=lambda r: (
            r.combined_rank,
            -(r.stock.earnings_yield or 0.0),
            r.stock.ticker,
        )
    )
    return ranked


def magic_formula_basket(
    stocks: Iterable[Stock], basket_size: int = DEFAULT_BASKET_SIZE, **kwargs
) -> list[RankedStock]:
    """Return the top ``basket_size`` names to buy (step 5)."""
    return rank_stocks(stocks, **kwargs)[:basket_size]


# --------------------------------------------------------------------------- #
# CSV loading + command-line interface
# --------------------------------------------------------------------------- #

# Columns read from the CSV. Numeric columns default to 0.0 when missing/blank.
_NUMERIC_COLUMNS = (
    "ebit",
    "market_cap",
    "total_debt",
    "cash",
    "current_assets",
    "current_liabilities",
    "net_fixed_assets",
)


def _to_float(value: Optional[str]) -> float:
    """Parse a CSV cell into a float, tolerating $ , and blanks."""
    if value is None:
        return 0.0
    cleaned = value.strip().replace(",", "").replace("$", "")
    if cleaned == "" or cleaned.lower() in {"na", "n/a", "none", "null"}:
        return 0.0
    return float(cleaned)


def load_stocks_from_csv(path: str) -> list[Stock]:
    """Load stocks from a CSV file.

    Required header: ``ticker``. Optional: ``name``, ``sector`` and the numeric
    fundamentals columns (see ``_NUMERIC_COLUMNS``). Unknown columns are ignored.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "ticker" not in reader.fieldnames:
            raise ValueError("CSV must have a header row containing a 'ticker' column")

        stocks: list[Stock] = []
        for line_no, row in enumerate(reader, start=2):
            ticker = (row.get("ticker") or "").strip()
            if not ticker:
                continue  # skip blank lines
            try:
                stocks.append(
                    Stock(
                        ticker=ticker,
                        name=(row.get("name") or "").strip(),
                        sector=(row.get("sector") or "").strip(),
                        **{col: _to_float(row.get(col)) for col in _NUMERIC_COLUMNS},
                    )
                )
            except ValueError as exc:
                raise ValueError(f"Bad numeric value on CSV line {line_no}: {exc}") from exc
    return stocks


def _format_pct(value: Optional[float]) -> str:
    return f"{value * 100:6.1f}%" if value is not None else "   n/a"


def print_ranking(ranked: list[RankedStock], limit: Optional[int] = None) -> None:
    """Pretty-print the ranking table to stdout."""
    rows = ranked if limit is None else ranked[:limit]
    header = (
        f"{'#':>3}  {'Ticker':<8} {'ROC':>7} {'EY':>7} "
        f"{'ROC#':>5} {'EY#':>5} {'Sum':>5}  Name"
    )
    print(header)
    print("-" * max(len(header), 60))
    for i, r in enumerate(rows, start=1):
        print(
            f"{i:>3}  {r.stock.ticker:<8} "
            f"{_format_pct(r.stock.return_on_capital)} "
            f"{_format_pct(r.stock.earnings_yield)} "
            f"{r.roc_rank:>5} {r.ey_rank:>5} {r.combined_rank:>5}  {r.stock.name}"
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rank stocks with Joel Greenblatt's Magic Formula.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("csv", help="Path to a CSV of stock fundamentals.")
    parser.add_argument(
        "-n", "--basket-size", type=int, default=DEFAULT_BASKET_SIZE,
        help="Number of top names to show as the basket.",
    )
    parser.add_argument(
        "--min-market-cap", type=float, default=DEFAULT_MIN_MARKET_CAP,
        help="Minimum market capitalization filter.",
    )
    parser.add_argument(
        "--exclude-sectors", default=",".join(sorted(DEFAULT_EXCLUDED_SECTORS)),
        help="Comma-separated sectors to exclude (case-insensitive).",
    )
    parser.add_argument(
        "--allow-negative-ebit", action="store_true",
        help="Keep companies with EBIT <= 0 (off by default).",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Print the full ranking, not just the basket.",
    )
    args = parser.parse_args(argv)

    try:
        stocks = load_stocks_from_csv(args.csv)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    excluded_sectors = [s for s in args.exclude_sectors.split(",") if s.strip()]
    ranked = rank_stocks(
        stocks,
        excluded_sectors=excluded_sectors,
        min_market_cap=args.min_market_cap,
        require_positive_ebit=not args.allow_negative_ebit,
    )

    if not ranked:
        print("No stocks passed the filters. Check your data and thresholds.")
        return 0

    total = len(ranked)
    print(f"Ranked {total} eligible stock(s) with the Magic Formula.\n")
    print_ranking(ranked, limit=None if args.all else args.basket_size)
    if not args.all and total > args.basket_size:
        print(f"\nShowing top {args.basket_size} of {total}. Use --all to see everything.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # Output was piped into a command that closed early (e.g. `| head`).
        # Exit quietly instead of dumping a traceback.
        sys.exit(0)
