# Magic Formula Stock Ranker

A Python implementation of the **"Magic Formula"** from Joel Greenblatt's book
*The Little Book That Still Beats the Market*.

The book's whole thesis fits on a napkin: **buy good businesses at cheap
prices, systematically, and hold a basket of them.** Greenblatt turns "good"
and "cheap" into two hard numbers, ranks every stock on each, and lets the
combined ranking pick the portfolio. This repo does exactly that.

---

## The formula, from the screenshot

The infographic that inspired this lists five steps. Here is what each one
means and how it maps to the code:

| # | Screenshot step | What it really is | Where it lives |
|---|-----------------|-------------------|----------------|
| 1 | **ROCE** (Return on Capital Employed) | *Is this a good business?* | `Stock.return_on_capital` |
| 2 | **EBIT / EV** (Earnings Yield) | *Is it cheap?* | `Stock.earnings_yield` |
| 3 | Rank every stock on both numbers separately | Two independent leaderboards | `_competition_rank()` |
| 4 | Add the two ranks — lowest combined wins | Reward being good **and** cheap | `RankedStock.combined_rank` |
| 5 | Buy a basket of the top names, hold ~1 year, repeat | Diversify + rebalance annually | `magic_formula_basket()` |

### Step 1 — Return on Capital (quality)

```
Return on Capital = EBIT / (Net Working Capital + Net Fixed Assets)
```

- **EBIT** (Earnings Before Interest and Taxes) is used instead of net income so
  that companies are compared on the earning power of the *business itself*,
  independent of how they are financed (debt vs. equity) or taxed.
- The denominator is **tangible capital employed** — the actual money tied up
  running the business:
  - *Net Working Capital* = Current Assets − Current Liabilities
  - *Net Fixed Assets* = net property, plant & equipment (PP&E)
- Goodwill is deliberately excluded, so a business that earns a lot on little
  real capital scores highly. A high number means a genuinely good business.

> The screenshot labels this **ROCE**. Greenblatt's own term is "Return on
> Capital", and his denominator (tangible capital employed) is a bit stricter
> than a textbook ROCE. This code follows Greenblatt's definition.

### Step 2 — Earnings Yield (cheapness)

```
Earnings Yield = EBIT / Enterprise Value
Enterprise Value (EV) = Market Cap + Total Debt − Cash
```

- **Enterprise Value**, not just market cap, is the true price of the whole
  business: if you bought the company outright you would also take on its debt
  and pocket its cash. EV reflects that.
- A high earnings yield means you get a lot of operating profit per dollar of
  business you buy — i.e. it is cheap. This is the inverse of an EV/EBIT
  multiple.

### Steps 3 & 4 — Rank, then combine

Each stock is ranked from best to worst on Return on Capital, and *separately*
on Earnings Yield (rank 1 = best on that metric). The two rank numbers are then
**added together**, and the stocks with the **lowest combined rank** are the
most attractive.

The genius is in the *addition*. A stock does not need to be the single
cheapest or the single highest-quality name — it needs to be very good on both
at once. The #1 cheapest company might be a failing business (a value trap);
the #1 highest-quality company might be wildly overpriced. Summing the ranks
finds the sweet spot between the two.

### Step 5 — The basket

You buy the top `N` names (Greenblatt suggests ~20–30 to diversify away
single-stock risk), hold for about a year, then re-run the screen and
rebalance. Annual holding is also tax-motivated in the book. `basket_size`
controls `N`.

---

## What gets filtered out (and why)

Before ranking, the screen applies Greenblatt's standard exclusions:

- **Financials & utilities** are dropped. Banks and insurers carry huge
  balance-sheet debt/leverage as part of normal operations, and regulated
  utilities are capital-structure outliers — both distort the capital and
  earnings-yield math.
- **A market-cap floor** removes tiny, illiquid micro-caps that are hard to
  trade and easy to manipulate.
- **Unprofitable companies** (EBIT ≤ 0) are removed — the formula is about good
  businesses, so negative operating earnings are excluded by default (toggle
  with `--allow-negative-ebit`).
- **Undefined metrics** are removed: a company with non-positive capital
  employed or non-positive enterprise value (e.g. more cash than its whole
  market value) can't be ranked meaningfully, so it is skipped.

---

## Usage

No third-party libraries required — just Python 3.9+.

```bash
# Rank the sample data and show the top-20 basket
python3 magic_formula.py sample_stocks.csv

# Show the full ranking, a smaller basket, a higher market-cap floor
python3 magic_formula.py sample_stocks.csv --all
python3 magic_formula.py sample_stocks.csv --basket-size 10
python3 magic_formula.py sample_stocks.csv --min-market-cap 1000

# See every option
python3 magic_formula.py --help
```

### Input format

A CSV with a header row. `ticker` is required; everything else is optional and
defaults to 0. **All monetary columns must be in the same units** (the sample
is in millions of USD, so `--min-market-cap 50` means $50M).

| Column | Meaning |
|--------|---------|
| `ticker` | Symbol (required) |
| `name`, `sector` | Labels; `sector` is used for the financials/utilities filter |
| `ebit` | Earnings before interest & taxes |
| `market_cap` | Price × shares outstanding |
| `total_debt` | Short- + long-term interest-bearing debt |
| `cash` | Cash & equivalents (incl. short-term investments) |
| `current_assets`, `current_liabilities` | For net working capital |
| `net_fixed_assets` | Net PP&E |

`$` signs, thousands commas, and blanks/`N/A` are tolerated.

### Using it as a library

```python
from magic_formula import Stock, rank_stocks, magic_formula_basket

stocks = [
    Stock("AAA", "Alpha Co", "Technology", ebit=250, market_cap=1000,
          total_debt=150, cash=200, current_assets=400,
          current_liabilities=250, net_fixed_assets=300),
    # ...
]

for r in magic_formula_basket(stocks, basket_size=20):
    print(r.stock.ticker, r.combined_rank,
          r.stock.return_on_capital, r.stock.earnings_yield)
```

---

## Sample output

Running against `sample_stocks.csv`:

```
  #  Ticker       ROC      EY  ROC#   EY#   Sum  Name
------------------------------------------------------------
  1  GOODCO     55.6%   26.3%     1     1     2  Good Cheap Co
  2  BARGAIN    37.1%   26.0%     3     2     5  Solid Bargain
  3  CHEAPO     30.0%   24.0%     4     3     7  Deep Value Inc
  4  MOAT       47.3%   13.3%     2     5     7  Wide Moat Corp
  ...
```

`GOODCO` wins by being best on *both* metrics. Note `CHEAPO` and `MOAT` tie at a
combined rank of 7; the tie is broken in favour of the cheaper stock (higher
earnings yield), then alphabetically, so the ordering is always deterministic.

---

## Design notes & reasoning

- **Standard library only.** The math is simple; keeping it dependency-free
  means it runs anywhere without a `pip install`. A production version would
  swap CSV loading for a live fundamentals data source (see below).
- **Competition ranking (1-2-2-4).** Equal metric values share a rank, so ties
  never give one stock an arbitrary edge in the *ranking* step; the arbitrary
  tie-break happens only once, deterministically, at the final sort.
- **Metrics can be "undefined" (`None`).** Rather than silently producing a
  garbage ratio when capital employed or EV is ≤ 0, the code marks the metric
  undefined and drops the stock from the ranking. This mirrors how Greenblatt's
  screen simply omits such names.
- **Filters are configurable.** Excluded sectors, the market-cap floor, and the
  EBIT requirement are all parameters, because the "right" thresholds depend on
  the market and universe you run against.
- **Testable.** `test_magic_formula.py` covers the metric math, the filters,
  the rank-summing, and the basket sizing (`python3 -m unittest`).

## Limitations & honest caveats

This is an educational implementation of a published strategy, **not investment
advice.**

- Results are only as good as the fundamentals you feed in. The hard part in
  practice is sourcing clean, point-in-time data (to avoid look-ahead bias).
- The Magic Formula is a *long-term, systematic* strategy. Greenblatt himself
  stresses it can underperform for years at a time; its edge shows up over
  multi-year horizons and requires the discipline to keep following it.
- Real-world refinements not modelled here: excluding recent IPOs and foreign
  ADRs, using trailing-twelve-month or normalized EBIT, adjusting for
  minority interest / preferred stock in EV, and staggering purchases through
  the year rather than buying the whole basket at once.

### Wiring up live data

To run this on real markets, replace `load_stocks_from_csv` with a loader that
pulls fundamentals from a data provider (e.g. an API or an exported dataset)
and returns `Stock` objects. Everything downstream — the metrics, ranking, and
basket selection — stays the same.

---

*Reference: Joel Greenblatt, "The Little Book That Still Beats the Market"
(Wiley). This code reproduces the book's method for educational purposes.*
