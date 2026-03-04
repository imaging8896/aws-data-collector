"""
FinMind API module for fetching Taiwan index data.

Provides TSE01 (發行量加權股價指數) and TPEx (櫃買指數) data.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import requests

# FinMind API endpoint
FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"

# Supported indices
SUPPORTED_INDICES = {
    "TSE01": "TAIEX",  # 發行量加權股價指數
    "OTC101": "TPEx",  # 櫃買指數
}


def get_index_data(index_name: str, data_date: date) -> dict[str, Any] | None:
    """
    Fetch index data from FinMind API for a specific date.

    Args:
        index_name: Index name (TSE01 or OTC101)
        data_date: The date to fetch data for

    Returns:
        Dictionary with index data or None if no data available
    """
    if index_name not in SUPPORTED_INDICES:
        raise ValueError(f"Unsupported index: {index_name}. Supported: {list(SUPPORTED_INDICES.keys())}")

    finmind_id = SUPPORTED_INDICES[index_name]
    date_str = data_date.isoformat()

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": finmind_id,
        "start_date": date_str,
        "end_date": date_str,
    }

    response = requests.get(FINMIND_API_URL, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    if data.get("status") != 200:
        raise ValueError(f"FinMind API error: {data.get('msg', 'Unknown error')}")

    records = data.get("data", [])

    if not records:
        return None

    # FinMind returns list, get first (and only) record for the date
    record = records[0]

    return {
        "symbol": index_name,
        "date": record["date"],
        "open": Decimal(str(record["open"])),
        "high": Decimal(str(record["max"])),
        "low": Decimal(str(record["min"])),
        "close": Decimal(str(record["close"])),
        "volume": int(record["Trading_Volume"]),
        "change": Decimal(str(record["spread"])),
        "trading_money": int(record["Trading_money"]),
        "trading_turnover": int(record["Trading_turnover"]),
    }
