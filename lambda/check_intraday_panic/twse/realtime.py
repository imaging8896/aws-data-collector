"""
TWSE Real-time (Intraday) Market Data API.

Provides real-time index data and market statistics during trading hours.
Trading hours: 9:00 AM - 13:30 PM Taiwan time (UTC+8)
"""

from decimal import Decimal
from typing import Any

from curl_cffi import requests

# TWSE Real-time API endpoint
TWSE_REALTIME_API = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"

# Index mapping
INDEX_CODES = {
    "TSE01": "tse_t00.tw",  # 發行量加權股價指數
}


def get_realtime_index(index_name: str = "TSE01") -> dict[str, Any] | None:
    """
    Fetch real-time index data from TWSE.

    Args:
        index_name: Index name (currently only TSE01 supported)

    Returns:
        Dictionary with real-time index data or None if no data available.
        Example:
        {
            "symbol": "TSE01",
            "date": "2026-03-08",
            "time": "13:15:00",
            "open": Decimal("33483.94"),
            "high": Decimal("33829.49"),
            "low": Decimal("33322.52"),
            "close": Decimal("33599.54"),  # Current price
            "volume": 10206581156,  # Accumulated volume
            "yesterday_close": Decimal("33672.94"),
        }
    """
    if index_name not in INDEX_CODES:
        raise ValueError(f"Unsupported index: {index_name}. Supported: {list(INDEX_CODES.keys())}")

    index_code = INDEX_CODES[index_name]

    params = {
        "ex_ch": index_code,
        "json": "1",
        "delay": "0",
    }

    response = requests.get(TWSE_REALTIME_API, params=params, impersonate="chrome", timeout=30)

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    data = response.json()

    if data.get("rtcode") != "0000":
        raise Exception(f"API error: {data}")

    msg_array = data.get("msgArray", [])
    if not msg_array:
        return None

    record = msg_array[0]

    # Parse date from format "20260308" to "2026-03-08"
    raw_date = record.get("d", "")
    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) == 8 else raw_date

    # Parse time from format "13:15:00"
    time_str = record.get("t", "")

    # Get current price (z), if not available use yesterday close (y)
    current_price = record.get("z", "")
    if current_price == "-" or not current_price:
        current_price = record.get("y", "0")

    # Note: For index (t00.tw), the real-time API doesn't provide volume ("v" field is missing).
    # We need to fetch volume from MI_INDEX API separately.
    volume = _get_market_total_volume()

    return {
        "symbol": index_name,
        "date": formatted_date,
        "time": time_str,
        "open": Decimal(str(record.get("o", "0")).replace(",", "")),
        "high": Decimal(str(record.get("h", "0")).replace(",", "")),
        "low": Decimal(str(record.get("l", "0")).replace(",", "")),
        "close": Decimal(str(current_price).replace(",", "")),
        "volume": volume,
        "yesterday_close": Decimal(str(record.get("y", "0")).replace(",", "")),
    }


def _get_market_total_volume() -> int:
    """
    Fetch total market volume from TWSE MI_INDEX API.

    This gets the "成交股數" from "大盤統計資訊" table, "總計" row.

    Returns:
        Total market volume (成交股數) or 0 if failed.
    """
    try:
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json"
        response = requests.get(url, impersonate="chrome", timeout=30)

        if response.status_code != 200:
            print(f"Failed to fetch market volume: status {response.status_code}")
            return 0

        data = response.json()

        if data.get("stat") != "OK":
            print(f"MI_INDEX API returned: {data.get('stat')}")
            return 0

        # Find the table with "大盤統計資訊" in title
        tables = data.get("tables", [])
        for table in tables:
            title = table.get("title", "")
            if "大盤統計資訊" in title:
                table_data = table.get("data", [])
                # Find the "總計" row
                for row in table_data:
                    if len(row) >= 3 and "總計" in row[0]:
                        # Row format: ['總計(1~15)', '成交金額', '成交股數', '成交筆數']
                        volume_str = row[2].replace(",", "")
                        return int(volume_str)
        return 0
    except Exception as e:
        print(f"Error fetching market volume: {e}")
        return 0


def get_realtime_market_stats() -> dict[str, Any] | None:
    """
    Fetch real-time market statistics (上漲/下跌/持平家數) from TWSE MI_INDEX API.

    This API returns current day's statistics during trading hours.
    Note: During non-trading hours, this returns the LAST trading day's data.

    Returns:
        Dictionary with market statistics or None if no data available.
        Example:
        {
            "date": "2026-03-08",  # The date of the data (may be yesterday on non-trading days)
            "up": 573,           # 上漲家數 (含漲停)
            "up_limit": 33,      # 漲停家數
            "down": 408,         # 下跌家數 (含跌停)
            "down_limit": 4,     # 跌停家數
            "unchanged": 86,     # 持平家數
            "untraded": 0,       # 未成交家數
            "no_comparison": 1,  # 無比價家數
        }
    """
    # MI_INDEX without date parameter returns current/latest data
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json"

    response = requests.get(url, impersonate="chrome", timeout=30)

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    data = response.json()

    if data.get("stat") != "OK":
        # During non-trading hours, may return error
        print(f"MI_INDEX API returned: {data.get('stat')}")
        return None

    # Get the date from response
    raw_date = data.get("date", "")
    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) == 8 else raw_date

    # Parse the market statistics from "tables" array
    tables = data.get("tables", [])

    for table in tables:
        title = table.get("title", "")
        fields = table.get("fields", [])
        table_data = table.get("data", [])

        # Find the table with title "漲跌證券數合計"
        if "漲跌證券數合計" in title and "整體市場" in fields:
            result = _parse_market_stats_table(table_data)
            if result:
                result["date"] = formatted_date
                return result

    return None


def _parse_market_stats_table(table_data: list) -> dict[str, int | str] | None:
    """
    Parse the market statistics table data.

    Args:
        table_data: List of rows from the table.

    Returns:
        Dictionary with parsed statistics or None if parsing fails.
    """
    stats: dict[str, int | str] = {}

    for row in table_data:
        if len(row) < 3:
            continue

        row_type = row[0]
        # Use "股票" column (index 2) instead of "整體市場" (index 1)
        stock_value = row[2]

        if "上漲" in row_type:
            up, up_limit = _parse_value_with_parentheses(stock_value)
            stats["up"] = up
            stats["up_limit"] = up_limit
        elif "下跌" in row_type:
            down, down_limit = _parse_value_with_parentheses(stock_value)
            stats["down"] = down
            stats["down_limit"] = down_limit
        elif "持平" in row_type:
            stats["unchanged"] = _parse_number(stock_value)
        elif "未成交" in row_type:
            stats["untraded"] = _parse_number(stock_value)
        elif "無比價" in row_type:
            stats["no_comparison"] = _parse_number(stock_value)

    required_fields = ["up", "up_limit", "down", "down_limit", "unchanged", "untraded", "no_comparison"]
    if all(field in stats for field in required_fields):
        return stats

    return None


def _parse_value_with_parentheses(value: str) -> tuple[int, int]:
    """Parse a value like "8,991(212)" into (8991, 212)."""
    value = value.strip()

    if "(" in value and ")" in value:
        main_part = value.split("(")[0]
        paren_part = value.split("(")[1].rstrip(")")
        return _parse_number(main_part), _parse_number(paren_part)

    return _parse_number(value), 0


def _parse_number(value: str) -> int:
    """Parse a number string with commas into an integer."""
    return int(value.replace(",", "").strip())
