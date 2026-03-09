"""
Futures-AI Stock Price Change Distribution API.

Fetches real-time stock price change statistics (上漲/下跌/持平家數) from futures-ai.com.
"""

from typing import Any

from curl_cffi import requests

# Futures-AI market insight API URL
FUTURES_AI_API_URL = "https://api.market-insight.futures-ai.com/api/monitor/advance_decline"


def get_stock_distribution(category: str = "上市櫃") -> dict[str, Any] | None:
    """
    Fetch real-time stock price change distribution from futures-ai.com API.

    Args:
        category: Market category to fetch. Default is "上市櫃" (combined TSE+OTC).
                  Other options: "上市", "上櫃", or industry categories.

    Returns:
        Dictionary with stock distribution data or None if failed.
        Example:
        {
            "up": 634,              # 上漲家數
            "down": 1160,           # 下跌家數
            "unchanged": 142,       # 持平家數
            "up_limit": 69,         # 漲停家數
            "down_limit": 7,        # 跌停家數
            "total": 1931,          # 總家數
            "avg_change_percent": -1.23,  # 平均漲跌幅
        }
    """
    try:
        response = requests.get(FUTURES_AI_API_URL, impersonate="chrome", timeout=30)

        if response.status_code != 200:
            print(f"Futures-AI API request failed with status {response.status_code}")
            return None

        data = response.json()
        return _parse_api_response(data, category)

    except Exception as e:
        print(f"Error fetching stock distribution from Futures-AI: {e}")
        return None


def _parse_api_response(data: list[dict[str, Any]], category: str) -> dict[str, Any] | None:
    """
    Parse stock distribution data from API response.

    The API returns a list of items, each with:
    - name: category name (e.g., "上市櫃", "上市", "上櫃", industry names)
    - count: dict mapping percentage change buckets to stock counts
      - Keys: "-11" to "11" where 11 = 漲停, -11 = 跌停, 0 = unchanged
      - Values: number of stocks in that bucket
    - count_total: total number of stocks
    - avg_change_percent: average change percentage

    Args:
        data: API response data (list of category items)
        category: Target category name to extract

    Returns:
        Dictionary with parsed statistics or None if category not found.
    """
    for item in data:
        if item.get("name") == category:
            count = item.get("count", {})

            # Calculate stats from count distribution
            # Positive numbers (1-10) = up, negative (-1 to -10) = down
            # 11 = 漲停 (up limit), -11 = 跌停 (down limit), 0 = unchanged
            up = sum(v for k, v in count.items() if 0 < int(k) < 11)
            down = sum(v for k, v in count.items() if -11 < int(k) < 0)
            unchanged = count.get("0", 0)
            up_limit = count.get("11", 0)
            down_limit = count.get("-11", 0)
            total = item.get("count_total", 0)
            avg_change_percent = item.get("avg_change_percent")

            return {
                "up": up,
                "down": down,
                "unchanged": unchanged,
                "up_limit": up_limit,
                "down_limit": down_limit,
                "total": total,
                "avg_change_percent": avg_change_percent,
            }

    print(f"Category '{category}' not found in API response")
    return None
