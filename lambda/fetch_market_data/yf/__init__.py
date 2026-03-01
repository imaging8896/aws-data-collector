"""Yahoo Finance data fetcher using yfinance."""

from datetime import date
from decimal import Decimal

import pandas as pd
import yfinance as yf


def get_stock_history(
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    period: str = "1mo",
) -> list[dict] | None:
    """
    Fetch stock historical data using yfinance.

    Args:
        symbol: Stock symbol (e.g., "^TWII" for Taiwan Index, "2330.TW" for TSMC)
        start_date: Start date for historical data (optional)
        end_date: End date for historical data (optional)
        period: Period to fetch if start/end not specified
                Valid periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max

    Returns:
        List of daily data dictionaries or None if no data available.
        Example:
        [
            {
                "date": "2026-03-01",
                "open": Decimal("22500.00"),
                "high": Decimal("22600.00"),
                "low": Decimal("22400.00"),
                "close": Decimal("22550.00"),
                "volume": 1234567890,
            },
            ...
        ]
    """
    ticker = yf.Ticker(symbol)

    if start_date and end_date:
        df = ticker.history(start=start_date.isoformat(), end=end_date.isoformat())
    else:
        df = ticker.history(period=period)

    if df.empty:
        return None

    result = []
    for idx, row in df.iterrows():
        timestamp = pd.Timestamp(idx)
        result.append(
            {
                "date": timestamp.date().isoformat(),
                "open": Decimal(str(round(row["Open"], 2))),
                "high": Decimal(str(round(row["High"], 2))),
                "low": Decimal(str(round(row["Low"], 2))),
                "close": Decimal(str(round(row["Close"], 2))),
                "volume": int(row["Volume"]),
            }
        )

    return result


def get_tw_index_history(
    start_date: date | None = None,
    end_date: date | None = None,
    period: str = "1mo",
) -> list[dict] | None:
    """
    Fetch Taiwan Stock Exchange Weighted Index (TAIEX) historical data.

    Args:
        start_date: Start date for historical data (optional)
        end_date: End date for historical data (optional)
        period: Period to fetch if start/end not specified

    Returns:
        List of daily data dictionaries or None if no data available.
    """
    return get_stock_history("^TWII", start_date, end_date, period)


def get_tw_stock_history(
    stock_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    period: str = "1mo",
) -> list[dict] | None:
    """
    Fetch Taiwan stock historical data.
    Automatically tries .TW (TWSE listed) first, then .TWO (TPEx/OTC) if no data.

    Args:
        stock_id: Taiwan stock ID (e.g., "2330" for TSMC)
        start_date: Start date for historical data (optional)
        end_date: End date for historical data (optional)
        period: Period to fetch if start/end not specified

    Returns:
        List of daily data dictionaries or None if no data available.
    """
    # Try TWSE listed stock first (.TW)
    symbol = f"{stock_id}.TW"
    result = get_stock_history(symbol, start_date, end_date, period)

    if result:
        return result

    # If no data, try TPEx/OTC stock (.TWO)
    symbol = f"{stock_id}.TWO"
    return get_stock_history(symbol, start_date, end_date, period)
