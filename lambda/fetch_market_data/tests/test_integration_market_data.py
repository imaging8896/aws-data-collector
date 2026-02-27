"""
Integration tests for market data fetching.

These tests actually hit external APIs to verify data can be correctly retrieved.
They are designed to run in CI/CD environment where network access is available.

Note: These tests may fail on non-trading days (weekends, holidays) or if the
external APIs are temporarily unavailable.
"""

import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal


def get_recent_trading_day() -> date:
    """Get a recent date that is likely a trading day (weekday)."""
    target_date = date.today() - timedelta(days=1)
    # Skip backwards to find a weekday
    while target_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        target_date -= timedelta(days=1)
    return target_date


class TestCnyesTrade(unittest.TestCase):
    """Integration tests for CNYES trade data API."""

    def test_get_trades_for_tw_index(self) -> None:
        """Test fetching Taiwan index data from CNYES API."""
        from cnyes.trade import Index, get_trades

        index = Index.tw_index()
        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(days=7)

        result = get_trades([index], from_dt=from_dt, to_dt=now)

        self.assertIn(index, result)
        index_data = result[index]
        self.assertIn("name", index_data)
        self.assertIn("data", index_data)
        self.assertIsInstance(index_data["name"], str)
        self.assertIsInstance(index_data["data"], list)
        # Should have at least some data points
        self.assertGreater(len(index_data["data"]), 0)
        # Verify data structure: (date_str, open, close, high, low, volume, turnover)
        first_data = index_data["data"][0]
        self.assertEqual(len(first_data), 7)
        self.assertIsInstance(first_data[0], str)  # date
        for i in range(1, 7):
            # Open, close, high, low should be Decimal; volume and turnover can be None
            if first_data[i] is not None:
                self.assertIsInstance(first_data[i], Decimal, f"Field {i} should be Decimal")

    def test_get_trades_for_stock(self) -> None:
        """Test fetching stock (2330 TSMC) data from CNYES API."""
        from cnyes.trade import Index, get_trades

        index = Index.tw_stock("2330")
        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(days=7)

        result = get_trades([index], from_dt=from_dt, to_dt=now)

        self.assertIn(index, result)
        index_data = result[index]
        self.assertIn("name", index_data)
        self.assertIn("data", index_data)
        self.assertIsInstance(index_data["name"], str)
        self.assertGreater(len(index_data["data"]), 0)


class TestTwseIndex(unittest.TestCase):
    """Integration tests for TWSE index API."""

    def test_get_indexes(self) -> None:
        """Test fetching index data from TWSE API."""
        from twse.index import get_indexes

        # Use a recent trading day
        test_date = get_recent_trading_day()
        result = get_indexes(test_date)

        # Result should be a dictionary (could be empty on holidays)
        self.assertIsInstance(result, dict)
        if result:  # If data is available
            # Verify structure of each index entry
            for name, data in result.items():
                self.assertIsInstance(name, str)
                self.assertIn("value", data)
                self.assertIn("date", data)
                self.assertIn("diff", data)
                self.assertIn("diff_percent", data)
                self.assertIsInstance(data["value"], Decimal)
                self.assertIsInstance(data["diff"], Decimal)
                self.assertIsInstance(data["diff_percent"], Decimal)


class TestTwseInvestor(unittest.TestCase):
    """Integration tests for TWSE investor data API (三大法人)."""

    def test_get_investor(self) -> None:
        """Test fetching investor (三大法人) data from TWSE API."""
        from twse.investor import get_investor

        test_date = get_recent_trading_day()
        result = get_investor(test_date)

        # Result can be None on non-trading days
        if result is not None:
            self.assertIsInstance(result, dict)
            # Should contain major investor types
            expected_keys = {"自營商(自行買賣)", "自營商(避險)", "投信", "外資"}
            actual_keys = set(result.keys())
            self.assertTrue(expected_keys.issubset(actual_keys), f"Missing expected investor types. Got: {actual_keys}")
            # Verify data structure
            for name, data in result.items():
                self.assertIn("buy", data)
                self.assertIn("sell", data)
                self.assertIsInstance(data["buy"], Decimal)
                self.assertIsInstance(data["sell"], Decimal)


class TestTwseMarketStats(unittest.TestCase):
    """Integration tests for TWSE market statistics API."""

    def test_get_market_stats(self) -> None:
        """Test fetching market statistics (上漲/下跌/平盤家數) from TWSE API."""
        from twse.market_stats import get_market_stats

        test_date = get_recent_trading_day()
        result = get_market_stats(test_date)

        # Result can be None on non-trading days
        if result is not None:
            self.assertIsInstance(result, dict)
            required_fields = ["up", "up_limit", "down", "down_limit", "unchanged"]
            for field in required_fields:
                self.assertIn(field, result, f"Missing required field: {field}")
                self.assertIsInstance(result[field], int)
                self.assertGreaterEqual(result[field], 0)


class TestTwseStockGroupTrade(unittest.TestCase):
    """Integration tests for TWSE stock group trade API."""

    def test_get_stock_group_trade(self) -> None:
        """Test fetching stock group trade data from TWSE API."""
        from twse.stock_group_trade import get_stock_group_trade

        test_date = get_recent_trading_day()
        result = get_stock_group_trade(test_date)

        # Result can be None on non-trading days
        if result is not None:
            self.assertIsInstance(result, dict)
            self.assertGreater(len(result), 0)
            # Verify data structure
            for name, data in result.items():
                self.assertIsInstance(name, str)
                self.assertIn("shares", data)
                self.assertIn("amount", data)
                self.assertIn("transactions", data)
                self.assertIsInstance(data["shares"], Decimal)
                self.assertIsInstance(data["amount"], Decimal)
                self.assertIsInstance(data["transactions"], Decimal)


class TestYahooTwIndex(unittest.TestCase):
    """Integration tests for Yahoo Finance Taiwan index API."""

    def test_get_tw_indexes(self) -> None:
        """Test fetching Taiwan index historical data from Yahoo Finance API."""
        from yahoo.tw_index import get_tw_indexes

        result = get_tw_indexes()

        self.assertIsInstance(result, list)
        # Should have lots of historical data points
        self.assertGreater(len(result), 1000)
        # Verify data structure: (date, open, close, high, low, volume, adjclose)
        first_data = result[0]
        self.assertEqual(len(first_data), 7)
        self.assertIsInstance(first_data[0], str)  # date
        for i in range(1, 7):
            if first_data[i] is not None:
                self.assertIsInstance(first_data[i], Decimal, f"Field {i} should be Decimal")


if __name__ == "__main__":
    unittest.main()
