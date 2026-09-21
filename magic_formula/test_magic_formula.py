"""Lightweight tests for the Magic Formula implementation (stdlib unittest)."""

import os
import unittest

from magic_formula import (
    Stock,
    load_stocks_from_csv,
    magic_formula_basket,
    rank_stocks,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE_CSV = os.path.join(HERE, "sample_stocks.csv")


class ComputeTests(unittest.TestCase):
    def test_derived_metrics(self):
        s = Stock(
            ticker="X",
            ebit=2500,
            market_cap=10000,
            total_debt=1500,
            cash=2000,
            current_assets=4000,
            current_liabilities=2500,
            net_fixed_assets=3000,
        )
        s.compute()
        # EV = 10000 + 1500 - 2000 = 9500
        self.assertAlmostEqual(s.enterprise_value, 9500)
        # Capital employed = (4000 - 2500) + 3000 = 4500
        self.assertAlmostEqual(s.capital_employed, 4500)
        self.assertAlmostEqual(s.return_on_capital, 2500 / 4500)
        self.assertAlmostEqual(s.earnings_yield, 2500 / 9500)
        self.assertTrue(s.is_rankable())

    def test_undefined_when_capital_non_positive(self):
        s = Stock(ticker="Y", ebit=100, market_cap=1000,
                  current_assets=10, current_liabilities=100, net_fixed_assets=0)
        s.compute()
        self.assertIsNone(s.return_on_capital)  # capital employed < 0
        self.assertFalse(s.is_rankable())

    def test_undefined_when_ev_non_positive(self):
        s = Stock(ticker="Z", ebit=100, market_cap=1000, cash=5000,
                  current_assets=200, current_liabilities=50, net_fixed_assets=100)
        s.compute()
        self.assertIsNone(s.earnings_yield)  # net cash > market cap
        self.assertFalse(s.is_rankable())


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.stocks = load_stocks_from_csv(SAMPLE_CSV)

    def test_filters_exclude_expected_names(self):
        tickers = {r.stock.ticker for r in rank_stocks(self.stocks)}
        self.assertNotIn("BANKco", tickers)     # financials excluded
        self.assertNotIn("POWERCO", tickers)    # utilities excluded
        self.assertNotIn("SMALLCAP", tickers)   # below market-cap floor
        self.assertNotIn("REDINK", tickers)     # negative EBIT
        self.assertNotIn("CASHRICH", tickers)   # net cash -> EV <= 0

    def test_combined_rank_is_sum_and_sorted(self):
        ranked = rank_stocks(self.stocks)
        for r in ranked:
            self.assertEqual(r.combined_rank, r.roc_rank + r.ey_rank)
        sums = [r.combined_rank for r in ranked]
        self.assertEqual(sums, sorted(sums))

    def test_basket_size_limit(self):
        basket = magic_formula_basket(self.stocks, basket_size=3)
        self.assertEqual(len(basket), 3)

    def test_allow_negative_ebit_reincludes_lossmaker(self):
        ranked = rank_stocks(self.stocks, require_positive_ebit=False)
        # REDINK has negative EBIT but positive capital + EV, so it becomes rankable.
        self.assertIn("REDINK", {r.stock.ticker for r in ranked})


if __name__ == "__main__":
    unittest.main(verbosity=2)
