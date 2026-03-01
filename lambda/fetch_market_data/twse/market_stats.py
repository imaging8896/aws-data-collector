import time
from datetime import date

from curl_cffi import requests


def get_market_stats(data_date: date, _retry_count: int = 0) -> dict | None:
    """
    Fetch Taiwan stock market statistics (上漲/下跌/平盤家數) from TWSE.

    Args:
        data_date: The date to fetch data for
        _retry_count: Internal counter for retry attempts (do not set manually)

    Returns:
        A dictionary containing market statistics or None if no data available.
        Example:
        {
            "up": 450,         # 上漲家數
            "down": 350,       # 下跌家數
            "unchanged": 200,  # 平盤家數
        }
    """
    print(f"Fetching market stats for {data_date}")
    data_date_str_without_dash = data_date.isoformat().replace("-", "")
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={data_date_str_without_dash}&response=json"

    response = requests.get(url, impersonate="chrome")

    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}: {response.text}")

    data = response.json()

    if data.get("stat") == "很抱歉，沒有符合條件的資料!":
        return None

    if "請重新查詢" in data.get("stat"):
        if _retry_count >= 3:
            raise Exception(f"Max retries (3) exceeded for {data_date}: {data.get('stat')}")
        print(f"Got '請重新查詢', retrying ({_retry_count + 1}/3)...")
        time.sleep(5)  # Wait before retrying
        return get_market_stats(data_date, _retry_count + 1)

    if data.get("stat") != "OK":
        raise Exception(f"API error:\n{data}")

    print(f"Got market stats data for {data_date}")

    # Parse the market statistics from "tables" array
    # Looking for the table with title "漲跌證券數合計"
    # Response structure:
    # {
    #     "tables": [
    #         {
    #             "title": "漲跌證券數合計",
    #             "fields": ["類型", "整體市場", "股票"],
    #             "data": [
    #                 ["上漲(漲停)", "8,991(212)", "583(41)"],
    #                 ["下跌(跌停)", "5,307(60)", "400(3)"],
    #                 ["持平", "777", "84"],
    #                 ["未成交", "16,409", "1"],
    #                 ["無比價", "2,597", "0"]
    #             ]
    #         }
    #     ]
    # }
    tables = data.get("tables", [])

    for table in tables:
        title = table.get("title", "")
        fields = table.get("fields", [])
        table_data = table.get("data", [])

        # Find the table with title "漲跌證券數合計"
        if "漲跌證券數合計" in title and "整體市場" in fields:
            result = _parse_market_stats_table(table_data)
            if result:
                return result

    raise Exception(f"Could not find market statistics in response: {data}")


def _parse_market_stats_table(table_data: list) -> dict | None:
    """
    Parse the market statistics table data.

    Args:
        table_data: List of rows from the table.
            Example: [["上漲(漲停)", "8,991(212)", "583(41)"], ...]

    Returns:
        Dictionary with parsed statistics or None if parsing fails.
    """
    stats: dict[str, int] = {}

    for row in table_data:
        if len(row) < 3:
            continue

        row_type = row[0]
        # Use "股票" column (index 2) instead of "整體市場" (index 1)
        stock_value = row[2]

        if "上漲" in row_type:
            # Parse "583(41)" format -> up=583, up_limit=41
            up, up_limit = _parse_value_with_parentheses(stock_value)
            stats["up"] = up
            stats["up_limit"] = up_limit
        elif "下跌" in row_type:
            # Parse "400(3)" format -> down=400, down_limit=3
            down, down_limit = _parse_value_with_parentheses(stock_value)
            stats["down"] = down
            stats["down_limit"] = down_limit
        elif "持平" in row_type:
            stats["unchanged"] = _parse_number(stock_value)

    # Verify we have all required fields
    required_fields = ["up", "up_limit", "down", "down_limit", "unchanged"]
    if all(field in stats for field in required_fields):
        return stats

    return None


def _parse_value_with_parentheses(value: str) -> tuple[int, int]:
    """
    Parse a value like "8,991(212)" into (8991, 212).

    Args:
        value: String in format "number(number)" or just "number"

    Returns:
        Tuple of (main_value, parentheses_value)
    """
    value = value.strip()

    if "(" in value and ")" in value:
        # Split "8,991(212)" into "8,991" and "212"
        main_part = value.split("(")[0]
        paren_part = value.split("(")[1].rstrip(")")
        return _parse_number(main_part), _parse_number(paren_part)

    return _parse_number(value), 0


def _parse_number(value: str) -> int:
    """Parse a number string with commas into an integer."""
    return int(value.replace(",", "").strip())
