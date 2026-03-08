"""
Check for intraday ultimate exhaustion panic signal and send Discord notification.

Ultimate Exhaustion Panic Buy Signal (終極竭盡買入訊號):
Triggered at 13:15 Taiwan time when:
1. Panic day conditions are met (price panic OR volume explosion OR liquidity drain)
2. Unchanged ratio < 0.5% (持平家數 / 總家數 < 0.5%)
3. Volume > 1.5 * avg_volume (past 20 trading days)

This signal indicates extreme market selling exhaustion - a potential bottom.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import boto3

# Add parent directory to path for importing panic_common
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from panic_common import (
    LDR_THRESHOLD,
    PRICE_DROP_THRESHOLD,
    UNCHANGED_RATIO_THRESHOLD,
    VOLUME_MULTIPLIER_THRESHOLD,
    check_ldr_panic_from_stats,
    check_price_panic_from_change,
    check_volume_ratio,
    decimal_to_float,
    decimal_to_int,
)
from panic_common import (
    check_unchanged_ratio as common_check_unchanged_ratio,
)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

# Environment variables
market_data_table_name = os.environ.get("MARKET_DATA_TABLE_NAME", "")
market_stats_table_name = os.environ.get("MARKET_STATS_TABLE_NAME", "")
discord_notify_function_name = os.environ.get("DISCORD_NOTIFY_FUNCTION_NAME", "")

market_data_table = dynamodb.Table(market_data_table_name) if market_data_table_name else None  # type: ignore
market_stats_table = dynamodb.Table(market_stats_table_name) if market_stats_table_name else None  # type: ignore

# Constants
VOLUME_AVG_DAYS = 20  # Average volume calculation period (20 trading days)

# Taiwan timezone
TW_TIMEZONE = timezone(timedelta(hours=8))


def get_historical_market_data(symbol: str, days: int) -> list[dict]:
    """
    Get historical market data for volume average calculation.

    Args:
        symbol: Stock symbol (e.g., 'TSE01')
        days: Number of days to fetch

    Returns:
        List of market data items sorted by date descending
    """
    if not market_data_table:
        return []

    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days + 10)  # Extra days for weekends/holidays

        items: list[dict] = []
        response = market_data_table.query(
            KeyConditionExpression="#s = :symbol AND #d BETWEEN :start AND :end",
            ExpressionAttributeNames={"#s": "symbol", "#d": "date"},
            ExpressionAttributeValues={
                ":symbol": symbol,
                ":start": start_date.isoformat(),
                ":end": end_date.isoformat(),
            },
            ScanIndexForward=False,
        )
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = market_data_table.query(
                KeyConditionExpression="#s = :symbol AND #d BETWEEN :start AND :end",
                ExpressionAttributeNames={"#s": "symbol", "#d": "date"},
                ExpressionAttributeValues={
                    ":symbol": symbol,
                    ":start": start_date.isoformat(),
                    ":end": end_date.isoformat(),
                },
                ScanIndexForward=False,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        # Exclude today's data (we use real-time data for today)
        today_str = date.today().isoformat()
        items = [item for item in items if item.get("date") != today_str]

        return items[:days]  # Return only the requested number of days
    except Exception as e:
        print(f"Error fetching historical market data: {e}")
        return []


def calculate_average_volume(market_data: list[dict]) -> float | None:
    """
    Calculate average volume from historical data.

    Args:
        market_data: List of market data items

    Returns:
        Average volume or None if insufficient data
    """
    volumes = []
    for item in market_data:
        volume = decimal_to_int(item.get("volume"))
        if volume is not None and volume > 0:
            volumes.append(volume)

    if len(volumes) < 5:  # Require at least 5 days of data
        return None

    return float(sum(volumes) / len(volumes))


def fetch_realtime_data() -> tuple[dict[str, Any] | None, dict[str, int] | None]:
    """
    Fetch real-time index and market stats data.

    Returns:
        Tuple of (index_data, market_stats) or (None, None) if failed
    """
    # Import here to avoid circular imports in Lambda
    try:
        from twse.realtime import get_realtime_index, get_realtime_market_stats
    except ImportError:
        # For local testing, try relative import
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fetch_market_data"))
        from twse.realtime import get_realtime_index, get_realtime_market_stats

    try:
        index_data = get_realtime_index("TSE01")
        market_stats = get_realtime_market_stats()
        return index_data, market_stats
    except Exception as e:
        print(f"Error fetching real-time data: {e}")
        import traceback

        traceback.print_exc()
        return None, None


def check_price_panic(index_data: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """
    Check if price panic condition is met from real-time index data.

    Args:
        index_data: Real-time index data

    Returns:
        Tuple of (is_panic, details)
    """
    current_price = decimal_to_float(index_data.get("close"))
    yesterday_close = decimal_to_float(index_data.get("yesterday_close"))

    if current_price is None or yesterday_close is None or yesterday_close == 0:
        return False, {"daily_change_pct": None, "current_price": current_price, "yesterday_close": yesterday_close}

    daily_change_pct = ((current_price - yesterday_close) / yesterday_close) * 100

    is_panic, details = check_price_panic_from_change(daily_change_pct)
    details["current_price"] = current_price
    details["yesterday_close"] = yesterday_close

    return is_panic, details


def check_ldr_panic(market_stats: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """
    Check if Limit Down Ratio (LDR) panic condition is met.

    Args:
        market_stats: Real-time market statistics

    Returns:
        Tuple of (is_panic, details)
    """
    is_panic, details = check_ldr_panic_from_stats(market_stats)
    return is_panic, details


def check_volume_explosion(
    index_data: dict[str, Any],
    avg_volume: float | None,
) -> tuple[bool, dict[str, Any]]:
    """
    Check if volume explosion condition is met.

    Args:
        index_data: Real-time index data
        avg_volume: Average volume from historical data

    Returns:
        Tuple of (is_explosion, details)
    """
    current_volume = index_data.get("volume", 0)
    is_explosion, details = check_volume_ratio(current_volume, avg_volume, VOLUME_MULTIPLIER_THRESHOLD)
    return is_explosion, details


def check_unchanged_ratio_condition(market_stats: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """
    Check if unchanged ratio condition is met for ultimate exhaustion.

    Args:
        market_stats: Real-time market statistics

    Returns:
        Tuple of (is_extreme, details)
    """
    is_extreme, details = common_check_unchanged_ratio(market_stats, UNCHANGED_RATIO_THRESHOLD)
    return is_extreme, details


def check_ultimate_exhaustion(
    index_data: dict[str, Any],
    market_stats: dict[str, Any],
    avg_volume: float | None,
) -> dict[str, Any] | None:
    """
    Check for ultimate exhaustion panic buy signal.

    Conditions:
    1. Panic day conditions met (price panic OR LDR panic)
    2. Unchanged ratio < 0.5%
    3. Volume > 1.5 * avg_volume

    Args:
        index_data: Real-time index data
        market_stats: Real-time market statistics
        avg_volume: Average volume from historical data

    Returns:
        Signal details dict if panic detected, None otherwise
    """
    # Check panic conditions
    price_panic, price_details = check_price_panic(index_data)
    ldr_panic, ldr_details = check_ldr_panic(market_stats)

    has_panic = price_panic or ldr_panic

    # Check unchanged ratio
    low_unchanged, unchanged_details = check_unchanged_ratio_condition(market_stats)

    # Check volume explosion
    volume_explosion, volume_details = check_volume_explosion(index_data, avg_volume)

    # Combine all details
    all_details = {
        **price_details,
        **ldr_details,
        **unchanged_details,
        **volume_details,
        "price_panic": price_panic,
        "ldr_panic": ldr_panic,
        "low_unchanged": low_unchanged,
        "volume_explosion": volume_explosion,
    }

    # Log the check
    print("=== Ultimate Exhaustion Check ===")
    daily_change = price_details.get("daily_change_pct")
    ldr = ldr_details.get("ldr")
    unchanged_ratio = unchanged_details.get("unchanged_ratio")
    volume_ratio_val = volume_details.get("volume_ratio")

    print(f"Price Panic: {price_panic} (drop: {daily_change:.2f}% if daily_change else 'N/A')")
    print(f"LDR Panic: {ldr_panic} (LDR: {ldr:.2f}% if ldr else 'N/A')")
    print(f"Low Unchanged: {low_unchanged} (ratio: {unchanged_ratio:.2f}% if unchanged_ratio else 'N/A')")
    print(f"Volume Explosion: {volume_explosion} (ratio: {volume_ratio_val:.2f}x if volume_ratio_val else 'N/A')")

    # Check if all conditions are met for ultimate exhaustion
    all_conditions_met = has_panic and low_unchanged and volume_explosion

    if all_conditions_met:
        print("✅ Ultimate Exhaustion Signal TRIGGERED!")
    elif has_panic:
        print("⚠️ Panic day detected, but not all exhaustion conditions met")
    else:
        print("❌ No panic day detected")

    # Return result if panic day is detected (regardless of exhaustion conditions)
    if has_panic:
        return {
            "signal": all_conditions_met,
            "has_panic": has_panic,
            "all_conditions_met": all_conditions_met,
            "date": index_data.get("date"),
            "time": index_data.get("time"),
            "details": all_details,
        }

    return None


def send_ultimate_exhaustion_notification(signal_data: dict[str, Any]) -> bool:
    """
    Send ultimate exhaustion notification via Discord.

    Args:
        signal_data: Signal data containing details

    Returns:
        True if notification sent successfully
    """
    if not discord_notify_function_name:
        print("Discord notify function not configured")
        return False

    try:
        timestamp = int(datetime.now(TW_TIMEZONE).timestamp())
        details = signal_data.get("details", {})

        # Build condition status
        price_icon = "✅" if details.get("price_panic") else "❌"
        ldr_icon = "✅" if details.get("ldr_panic") else "❌"
        unchanged_icon = "✅" if details.get("low_unchanged") else "❌"
        volume_icon = "✅" if details.get("volume_explosion") else "❌"

        daily_change = details.get("daily_change_pct", 0)
        ldr = details.get("ldr", 0)
        unchanged_ratio = details.get("unchanged_ratio", 0)
        volume_ratio = details.get("volume_ratio", 0)
        current_price = details.get("current_price", 0)

        condition_text = (
            f"{price_icon} 價格恐慌: 跌幅 {daily_change:.2f}% (門檻 < {PRICE_DROP_THRESHOLD}%)"
            f"{' ← 觸發' if details.get('price_panic') else ''}\n"
            f"{ldr_icon} 跌停比: {ldr:.2f}% (門檻 > {LDR_THRESHOLD}%)"
            f"{' ← 觸發' if details.get('ldr_panic') else ''}\n"
            f"{unchanged_icon} 持平比例: {unchanged_ratio:.2f}% (門檻 < {UNCHANGED_RATIO_THRESHOLD}%)\n"
            f"{volume_icon} 成交量: {volume_ratio:.2f}x 平均 (門檻 > {VOLUME_MULTIPLIER_THRESHOLD}x)"
        )

        # Determine title and description based on conditions
        all_conditions_met = signal_data.get("all_conditions_met", False)

        if all_conditions_met:
            title = "🔥 終極竞盡買入訊號"
            description = (
                f"盤中 **{signal_data.get('time', '')}** 偵測到終極竞盡訊號！\n"
                f"目前指數: **{current_price:.2f}** (跌幅 {daily_change:.2f}%)\n\n"
                "市場極度恐慌賣壓竞盡，可考慮進場買入。"
            )
        else:
            title = "🚨 盤中恐慌日竞盡檢查報告"
            description = (
                f"盤中 **{signal_data.get('time', '')}** 偵測到恐慌日\n"
                f"目前指數: **{current_price:.2f}** (跌幅 {daily_change:.2f}%)\n\n"
                "❌ 竞盡條件尚未完全符合，請繼續觀察。"
            )

        # Invoke Discord notification Lambda
        payload = {
            "notification_type": "ultimate_exhaustion",
            "title": title,
            "description": description,
            "conditions": condition_text,
            "timestamp": timestamp,
        }

        response = lambda_client.invoke(
            FunctionName=discord_notify_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        response_payload = json.loads(response["Payload"].read().decode("utf-8"))
        print(f"Discord notification response: {response_payload}")

        status_code = response_payload.get("statusCode")
        return bool(status_code == 200)

    except Exception as e:
        print(f"Error sending notification: {e}")
        import traceback

        traceback.print_exc()
        return False


def handler(event: dict, context: Any) -> dict[str, Any]:
    """
    Lambda handler for checking intraday ultimate exhaustion panic signal.

    This should be triggered at 13:15 Taiwan time on trading days.
    """
    print("=== Check Intraday Ultimate Exhaustion Panic Signal ===")
    now_tw = datetime.now(TW_TIMEZONE)
    print(f"Current Taiwan time: {now_tw.strftime('%Y-%m-%d %H:%M:%S')}")

    # Fetch real-time data
    print("Fetching real-time data...")
    index_data, market_stats = fetch_realtime_data()

    if index_data is None or market_stats is None:
        print("Failed to fetch real-time data")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to fetch real-time data"}),
        }

    print(f"Index data: {index_data}")
    print(f"Market stats: {market_stats}")

    # Verify the data is from today (not yesterday's data on non-trading days)
    today_str = now_tw.strftime("%Y-%m-%d")
    index_date = index_data.get("date", "")
    stats_date = market_stats.get("date", "")

    if index_date != today_str or stats_date != today_str:
        print(f"Data is not from today! Today: {today_str}, Index date: {index_date}, Stats date: {stats_date}")
        print("This is likely a non-trading day or outside trading hours. Skipping check.")
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "signal_detected": False,
                    "reason": "Data is not from today (non-trading day or outside trading hours)",
                    "today": today_str,
                    "index_date": index_date,
                    "stats_date": stats_date,
                }
            ),
        }

    # Get historical data for volume average
    print(f"Fetching historical data for past {VOLUME_AVG_DAYS} days...")
    historical_data = get_historical_market_data("TSE01", VOLUME_AVG_DAYS)
    avg_volume = calculate_average_volume(historical_data)
    print(f"Average volume ({len(historical_data)} days): {avg_volume}")

    # Check for ultimate exhaustion signal
    signal_data = check_ultimate_exhaustion(index_data, market_stats, avg_volume)

    if signal_data:
        # Panic day detected - send notification with all condition statuses
        notification_sent = send_ultimate_exhaustion_notification(signal_data)
        all_conditions_met = signal_data.get("all_conditions_met", False)
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "panic_detected": True,
                    "ultimate_exhaustion": all_conditions_met,
                    "notification_sent": notification_sent,
                    "signal_data": {
                        "date": signal_data.get("date"),
                        "time": signal_data.get("time"),
                        "details": {k: float(v) if isinstance(v, (Decimal, float)) else v for k, v in signal_data.get("details", {}).items()},
                    },
                }
            ),
        }

    # No panic day detected
    return {
        "statusCode": 200,
        "body": json.dumps({"panic_detected": False, "ultimate_exhaustion": False}),
    }


if __name__ == "__main__":
    # Local testing
    result = handler({}, None)
    print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
