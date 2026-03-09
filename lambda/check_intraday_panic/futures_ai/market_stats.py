"""
Futures-AI Stock Price Change Distribution API.

Fetches real-time stock price change statistics (上漲/下跌/持平家數) from futures-ai.com.
"""

import re
from typing import Any

from curl_cffi import requests

# Futures-AI stock distribution page URL
FUTURES_AI_URL = "https://www.futures-ai.com/stock-price-change-distribution"


def get_stock_distribution() -> dict[str, Any] | None:
    """
    Fetch real-time stock price change distribution from futures-ai.com.

    Returns:
        Dictionary with stock distribution data or None if failed.
        Example:
        {
            "up": 634,           # 上漲家數
            "down": 1160,        # 下跌家數
            "unchanged": 142,    # 持平家數
            "up_limit": 69,      # 漲停家數
            "down_limit": 7,     # 跌停家數
        }
    """
    try:
        response = requests.get(FUTURES_AI_URL, impersonate="chrome", timeout=30)

        if response.status_code != 200:
            print(f"Futures-AI API request failed with status {response.status_code}")
            return None

        html_content = response.text
        return _parse_stock_distribution(html_content)

    except Exception as e:
        print(f"Error fetching stock distribution from Futures-AI: {e}")
        return None


def _parse_stock_distribution(html_content: str) -> dict[str, Any] | None:
    """
    Parse stock distribution data from HTML content.

    Args:
        html_content: Raw HTML content from the page

    Returns:
        Dictionary with parsed statistics or None if parsing fails.
    """
    stats: dict[str, Any] = {}

    # Define patterns to match common HTML structures for stock statistics
    # Pattern 1: Look for labeled values like "上漲家數：634" or "上漲家數: 634"
    patterns = {
        "up": [
            r"上漲[家數]*[：:\s]*(\d+(?:,\d+)*)",
            r"漲[：:\s]*(\d+(?:,\d+)*)\s*家",
        ],
        "down": [
            r"下跌[家數]*[：:\s]*(\d+(?:,\d+)*)",
            r"跌[：:\s]*(\d+(?:,\d+)*)\s*家",
        ],
        "unchanged": [
            r"持平[家數]*[：:\s]*(\d+(?:,\d+)*)",
            r"平盤[家數]*[：:\s]*(\d+(?:,\d+)*)",
        ],
        "up_limit": [
            r"漲停[家數]*[：:\s]*(\d+(?:,\d+)*)",
        ],
        "down_limit": [
            r"跌停[家數]*[：:\s]*(\d+(?:,\d+)*)",
        ],
    }

    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, html_content)
            if match:
                value_str = match.group(1).replace(",", "")
                stats[field] = int(value_str)
                break

    # Verify we have the essential fields
    required_fields = ["up", "down", "unchanged"]
    if all(field in stats for field in required_fields):
        return stats

    # If primary patterns didn't work, try alternative parsing strategies
    alternative_result = _parse_with_alternative_patterns(html_content)
    if alternative_result:
        return alternative_result

    # Return partial stats if we found some data, otherwise None
    return stats if stats else None


def _parse_with_alternative_patterns(html_content: str) -> dict[str, Any] | None:
    """
    Alternative parsing strategy for different HTML structures.

    This handles cases where the numbers might be in spans, divs, or table cells
    near their labels.

    Args:
        html_content: Raw HTML content

    Returns:
        Dictionary with parsed statistics or None if parsing fails.
    """
    stats: dict[str, Any] = {}

    # Maximum reasonable number of stocks in Taiwan market (including all listed securities)
    max_stock_count = 5000

    # Try to find numbers near Chinese labels in various HTML structures
    # Pattern for: <span>上漲</span><span>634</span> or similar structures
    # Using \d+ for flexible digit matching, with validation after parsing
    label_value_patterns = [
        # Label followed by number in nearby tag
        (r"上漲.*?[>\s](\d+)[<\s]", "up"),
        (r"下跌.*?[>\s](\d+)[<\s]", "down"),
        (r"持平.*?[>\s](\d+)[<\s]", "unchanged"),
        (r"漲停.*?[>\s](\d+)[<\s]", "up_limit"),
        (r"跌停.*?[>\s](\d+)[<\s]", "down_limit"),
        # Alternative: number before or after label
        (r"(\d+)[<\s]*.*?上漲", "up"),
        (r"(\d+)[<\s]*.*?下跌", "down"),
        (r"(\d+)[<\s]*.*?持平", "unchanged"),
    ]

    for pattern, field in label_value_patterns:
        if field not in stats:
            match = re.search(pattern, html_content, re.DOTALL)
            if match:
                try:
                    value = int(match.group(1).replace(",", ""))
                    # Validate the parsed value is within reasonable bounds
                    if 0 <= value <= max_stock_count:
                        stats[field] = value
                except ValueError:
                    continue

    required_fields = ["up", "down", "unchanged"]
    if all(field in stats for field in required_fields):
        return stats

    return None
