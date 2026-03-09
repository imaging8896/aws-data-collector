"""
Unit tests for Futures-AI market statistics parsing.

These tests verify the HTML parsing logic without making network requests.
"""


class TestFuturesAiParsing:
    """Unit tests for Futures-AI HTML parsing functions."""

    def test_parse_stock_distribution_basic_format(self) -> None:
        """Test parsing stock distribution from basic HTML format."""
        from futures_ai.market_stats import _parse_stock_distribution

        html = """
        <div class="stats">
            上漲家數：634
            下跌家數：1160
            持平家數：142
        </div>
        """
        result = _parse_stock_distribution(html)

        assert result is not None
        assert result["up"] == 634
        assert result["down"] == 1160
        assert result["unchanged"] == 142

    def test_parse_stock_distribution_with_limits(self) -> None:
        """Test parsing stock distribution including limit up/down counts."""
        from futures_ai.market_stats import _parse_stock_distribution

        html = """
        <div class="stats">
            上漲家數: 634
            下跌家數: 1160
            持平家數: 142
            漲停家數: 69
            跌停家數: 7
        </div>
        """
        result = _parse_stock_distribution(html)

        assert result is not None
        assert result["up"] == 634
        assert result["down"] == 1160
        assert result["unchanged"] == 142
        assert result["up_limit"] == 69
        assert result["down_limit"] == 7

    def test_parse_stock_distribution_colon_format(self) -> None:
        """Test parsing with full-width colon (：) format."""
        from futures_ai.market_stats import _parse_stock_distribution

        html = """
        上漲：500
        下跌：600
        持平：100
        """
        result = _parse_stock_distribution(html)

        assert result is not None
        assert result["up"] == 500
        assert result["down"] == 600
        assert result["unchanged"] == 100

    def test_parse_stock_distribution_with_commas(self) -> None:
        """Test parsing numbers with comma separators."""
        from futures_ai.market_stats import _parse_stock_distribution

        html = """
        上漲家數：1,234
        下跌家數：2,345
        持平家數：567
        """
        result = _parse_stock_distribution(html)

        assert result is not None
        assert result["up"] == 1234
        assert result["down"] == 2345
        assert result["unchanged"] == 567

    def test_parse_stock_distribution_missing_fields_returns_partial(self) -> None:
        """Test parsing returns partial result when some required fields are missing."""
        from futures_ai.market_stats import _parse_stock_distribution

        html = """
        上漲家數：634
        下跌家數：400
        """  # Missing unchanged
        result = _parse_stock_distribution(html)

        # Should return partial result with what we found
        assert result is not None
        assert result.get("up") == 634
        assert result.get("down") == 400
        # unchanged should be missing
        assert "unchanged" not in result

    def test_parse_stock_distribution_no_matching_fields_returns_none(self) -> None:
        """Test parsing returns None when no fields can be matched."""
        from futures_ai.market_stats import _parse_stock_distribution

        html = """<html><body>No valid data here</body></html>"""
        result = _parse_stock_distribution(html)

        # Should return None because no fields were found
        assert result is None

    def test_parse_stock_distribution_invalid_html(self) -> None:
        """Test parsing returns None for invalid/empty HTML."""
        from futures_ai.market_stats import _parse_stock_distribution

        result = _parse_stock_distribution("")
        assert result is None

        result = _parse_stock_distribution("<html><body>No data</body></html>")
        assert result is None
