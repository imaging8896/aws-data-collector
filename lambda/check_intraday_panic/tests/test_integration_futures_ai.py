"""
Integration tests for Futures-AI market statistics fetching.

These tests actually hit the external futures-ai.com website to verify data
can be correctly retrieved and parsed.

Note: These tests may fail outside trading hours or if the website is unavailable.
"""


class TestFuturesAiMarketStats:
    """Integration tests for Futures-AI stock distribution API."""

    def test_get_stock_distribution(self) -> None:
        """Test fetching stock distribution data from futures-ai.com."""
        from futures_ai.market_stats import get_stock_distribution

        result = get_stock_distribution()

        # Note: May return None outside trading hours
        if result is not None:
            # Verify required fields exist
            required_fields = ["up", "down", "unchanged"]
            for field in required_fields:
                assert field in result, f"Missing required field: {field}"
                assert isinstance(result[field], int), f"Field {field} should be int"
                assert result[field] >= 0, f"Field {field} should be >= 0"

            # Verify values are reasonable (Taiwan market has ~2000 stocks)
            assert result["up"] <= 3000, "up count should be reasonable"
            assert result["down"] <= 3000, "down count should be reasonable"
            assert result["unchanged"] <= 3000, "unchanged count should be reasonable"

            # If up_limit and down_limit are present, verify them too
            if "up_limit" in result:
                assert isinstance(result["up_limit"], int)
                assert 0 <= result["up_limit"] <= result["up"]
            if "down_limit" in result:
                assert isinstance(result["down_limit"], int)
                assert 0 <= result["down_limit"] <= result["down"]
