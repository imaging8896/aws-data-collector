"""
Check for market panic signals and send Discord notifications.

Panic Day Definition:
1. Price Panic: Daily drop > 2.5% OR Limit Down Ratio (LDR) > 3%
   - LDR = down_limit / total
2. Volume Explosion: Volume >= 1.25 * avg volume (past 10 days)
3. Liquidity Drain:
   - unchanged z-score (past 60 days) is extreme OR
   - Unchanged Ratio (UCR) < 1.5% OR
   - (Participation Rate > 98.5% AND Down Ratio >= 90%)
"""

import json
import os
import statistics
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TypedDict

import boto3

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

# Environment variables
market_data_table_name = os.environ["MARKET_DATA_TABLE_NAME"]
market_stats_table_name = os.environ["MARKET_STATS_TABLE_NAME"]
discord_notify_function_name = os.environ.get("DISCORD_NOTIFY_FUNCTION_NAME")

market_data_table = dynamodb.Table(market_data_table_name)  # type: ignore
market_stats_table = dynamodb.Table(market_stats_table_name)  # type: ignore

# Constants
LOOKBACK_DAYS = 14  # Check for panic in past 14 days
VOLUME_AVG_DAYS = 10  # Average volume calculation period
ZSCORE_LOOKBACK_DAYS = 60  # Z-score calculation period

# Panic thresholds
PRICE_DROP_THRESHOLD = -2.5  # Daily drop > 2.5%
LDR_THRESHOLD = 3.0  # Limit Down Ratio > 3%
VOLUME_MULTIPLIER = 1.25  # Volume >= 1.25x average
UCR_THRESHOLD = 1.5  # Unchanged Ratio < 1.5%
PARTICIPATION_RATE_THRESHOLD = 98.5  # Participation Rate > 98.5%
DOWN_RATIO_THRESHOLD = 90.0  # Down Ratio >= 90%


class PanicSignal(TypedDict):
    """Panic signal data structure."""

    date: str
    price_panic: bool
    volume_explosion: bool
    liquidity_drain: bool
    details: dict


def decimal_to_float(value: Decimal | float | int | None) -> float | None:
    """Convert Decimal to float for calculations."""
    if value is None:
        return None
    return float(value)


def decimal_to_int(value: Decimal | float | int | None) -> int | None:
    """Convert Decimal to int for calculations."""
    if value is None:
        return None
    return int(value)


def _calculate_total(item: dict) -> int | None:
    """
    Calculate total from market stats item.

    total = up + down + unchanged + untraded + no_comparison

    """

    # Calculate from components
    up = decimal_to_int(item.get("up"))
    down = decimal_to_int(item.get("down"))
    unchanged = decimal_to_int(item.get("unchanged"))
    untraded = decimal_to_int(item.get("untraded"))
    no_comparison = decimal_to_int(item.get("no_comparison"))

    if up is not None and down is not None and unchanged is not None and untraded is not None and no_comparison is not None:
        return up + down + unchanged + untraded + no_comparison

    return None


def get_market_data(symbol: str, start_date: date, end_date: date) -> list[dict]:
    """
    Get market data for a symbol within a date range.

    Args:
        symbol: Stock symbol (e.g., 'TSE01')
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns:
        List of market data items sorted by date descending
    """
    try:
        items: list[dict] = []
        response = market_data_table.query(
            KeyConditionExpression="#s = :symbol AND #d BETWEEN :start AND :end",
            ExpressionAttributeNames={"#s": "symbol", "#d": "date"},
            ExpressionAttributeValues={
                ":symbol": symbol,
                ":start": start_date.isoformat(),
                ":end": end_date.isoformat(),
            },
            ScanIndexForward=False,  # Descending order
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
                ScanIndexForward=False,  # Descending order
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        return items
    except Exception as e:
        print(f"Error fetching market data: {e}")
        return []


def get_market_stats(start_date: date, end_date: date) -> list[dict]:
    """
    Get market statistics within a date range.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns:
        List of market stats items sorted by date descending
    """
    try:
        # market_stats_table has only 'date' as partition key, need to scan
        items: list[dict] = []
        response = market_stats_table.scan(
            FilterExpression="#d BETWEEN :start AND :end",
            ExpressionAttributeNames={"#d": "date"},
            ExpressionAttributeValues={
                ":start": start_date.isoformat(),
                ":end": end_date.isoformat(),
            },
        )
        items.extend(response.get("Items", []))

        while "LastEvaluatedKey" in response:
            response = market_stats_table.scan(
                FilterExpression="#d BETWEEN :start AND :end",
                ExpressionAttributeNames={"#d": "date"},
                ExpressionAttributeValues={
                    ":start": start_date.isoformat(),
                    ":end": end_date.isoformat(),
                },
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        # Sort by date descending
        return sorted(items, key=lambda x: x["date"], reverse=True)
    except Exception as e:
        print(f"Error fetching market stats: {e}")
        return []


def calculate_daily_change_pct(market_data: list[dict], target_date: str) -> float | None:
    """
    Calculate daily price change percentage for a given date.

    Args:
        market_data: List of market data items (sorted by date descending)
        target_date: Target date string (YYYY-MM-DD)

    Returns:
        Daily change percentage or None if not available
    """
    for item in market_data:
        if item["date"] == target_date:
            close = decimal_to_float(item.get("close"))
            change = decimal_to_float(item.get("change"))

            if close is not None and change is not None and close != 0:
                # change is the absolute change, calculate percentage
                prev_close = close - change
                if prev_close != 0:
                    return (change / prev_close) * 100
            return None
    return None


def calculate_volume_ratio(market_data: list[dict], target_date: str) -> float | None:
    """
    Calculate volume ratio compared to past 10-day average.

    Args:
        market_data: List of market data items (sorted by date descending)
        target_date: Target date string (YYYY-MM-DD)

    Returns:
        Volume ratio (current / average) or None if not available
    """
    # Find the target date index
    target_idx = None
    for i, item in enumerate(market_data):
        if item["date"] == target_date:
            target_idx = i
            break

    if target_idx is None:
        return None

    current_volume = decimal_to_float(market_data[target_idx].get("volume"))
    if current_volume is None:
        return None

    # Get past 10 days volumes (excluding current day)
    past_volumes = []
    for i in range(target_idx + 1, min(target_idx + 1 + VOLUME_AVG_DAYS, len(market_data))):
        vol = decimal_to_float(market_data[i].get("volume"))
        if vol is not None:
            past_volumes.append(vol)

    if len(past_volumes) < 5:  # Need at least 5 days for meaningful average
        return None

    avg_volume = sum(past_volumes) / len(past_volumes)
    if avg_volume == 0:
        return None

    return current_volume / avg_volume


def calculate_unchanged_threshold(market_stats: list[dict], target_date: str) -> tuple[int | None, float | None]:
    """
    Calculate unchanged value and threshold (avg - 2*std) based on past 60 days.

    Args:
        market_stats: List of market stats items (sorted by date descending)
        target_date: Target date string (YYYY-MM-DD)

    Returns:
        Tuple of (current_unchanged, threshold) or (None, None) if not available
        Threshold = avg - 2*std of past 60 days unchanged values
    """
    # Find target date index
    target_idx = None
    for i, item in enumerate(market_stats):
        if item["date"] == target_date:
            target_idx = i
            break

    if target_idx is None:
        return None, None

    current_unchanged = decimal_to_int(market_stats[target_idx].get("unchanged"))
    if current_unchanged is None:
        return None, None

    # Get past 60 days unchanged values (excluding current day)
    past_unchanged = []
    for i in range(target_idx + 1, min(target_idx + 1 + ZSCORE_LOOKBACK_DAYS, len(market_stats))):
        val = decimal_to_int(market_stats[i].get("unchanged"))
        if val is not None:
            past_unchanged.append(val)

    if len(past_unchanged) < 30:  # Need at least 30 days for meaningful calculation
        return current_unchanged, None

    mean = statistics.mean(past_unchanged)
    stdev = statistics.stdev(past_unchanged)

    # Threshold = avg - 2*std
    threshold = mean - 2 * stdev

    return current_unchanged, threshold


def check_price_panic(market_data: list[dict], market_stats: list[dict], target_date: str) -> tuple[bool, dict]:
    """
    Check for price panic signal.

    Price Panic: Daily drop > 2.5% OR LDR > 3%

    Args:
        market_data: List of market data items
        market_stats: List of market stats items
        target_date: Target date string

    Returns:
        Tuple of (is_panic, details)
    """
    details: dict = {}

    # Check daily drop
    daily_change = calculate_daily_change_pct(market_data, target_date)
    details["daily_change_pct"] = daily_change

    has_price_drop = daily_change is not None and daily_change < PRICE_DROP_THRESHOLD

    # Check LDR (Limit Down Ratio)
    ldr = None
    for item in market_stats:
        if item["date"] == target_date:
            down_limit = decimal_to_int(item.get("down_limit"))
            total = _calculate_total(item)

            if down_limit is not None and total is not None and total > 0:
                ldr = (down_limit / total) * 100
            break

    details["ldr"] = ldr
    has_high_ldr = ldr is not None and ldr > LDR_THRESHOLD

    return (has_price_drop or has_high_ldr), details


def check_volume_explosion(market_data: list[dict], target_date: str) -> tuple[bool, dict]:
    """
    Check for volume explosion signal.

    Volume Explosion: Volume >= 1.25 * avg volume (past 10 days)

    Args:
        market_data: List of market data items
        target_date: Target date string

    Returns:
        Tuple of (is_explosion, details)
    """
    volume_ratio = calculate_volume_ratio(market_data, target_date)
    details = {"volume_ratio": volume_ratio}

    is_explosion = volume_ratio is not None and volume_ratio >= VOLUME_MULTIPLIER

    return is_explosion, details


def check_liquidity_drain(market_stats: list[dict], target_date: str) -> tuple[bool, dict]:
    """
    Check for liquidity drain signal.

    Liquidity Drain:
    - unchanged z-score (past 60 days) is extreme (< -2) OR
    - UCR < 1.5% OR
    - (Participation Rate > 98.5% AND Down Ratio >= 90%)

    Args:
        market_stats: List of market stats items
        target_date: Target date string

    Returns:
        Tuple of (is_drain, details)
    """
    details: dict = {}

    # Find target date data
    target_data = None
    for item in market_stats:
        if item["date"] == target_date:
            target_data = item
            break

    if target_data is None:
        return False, details

    unchanged = decimal_to_int(target_data.get("unchanged"))
    total = _calculate_total(target_data)
    down = decimal_to_int(target_data.get("down"))
    untraded = decimal_to_int(target_data.get("untraded"))

    # Calculate UCR (Unchanged Ratio)
    ucr = None
    if unchanged is not None and total is not None and total > 0:
        ucr = (unchanged / total) * 100
    details["ucr"] = ucr

    # Calculate participation rate
    participation_rate = None
    if total is not None and untraded is not None and total > 0:
        participation_rate = ((total - untraded) / total) * 100
    details["participation_rate"] = participation_rate

    # Calculate down ratio
    down_ratio = None
    if down is not None and total is not None and total > 0:
        down_ratio = (down / total) * 100
    details["down_ratio"] = down_ratio

    # Calculate unchanged threshold (avg - 2*std)
    current_unchanged, unchanged_threshold = calculate_unchanged_threshold(market_stats, target_date)
    details["unchanged"] = current_unchanged
    details["unchanged_threshold"] = unchanged_threshold

    # Check conditions
    # unchanged < avg - 2*std (i.e., current value is below threshold)
    has_extreme_unchanged = current_unchanged is not None and unchanged_threshold is not None and current_unchanged < unchanged_threshold
    has_low_ucr = ucr is not None and ucr < UCR_THRESHOLD
    has_extreme_participation = (
        participation_rate is not None and down_ratio is not None and participation_rate > PARTICIPATION_RATE_THRESHOLD and down_ratio >= DOWN_RATIO_THRESHOLD
    )

    return (has_extreme_unchanged or has_low_ucr or has_extreme_participation), details


def detect_panic_signals(check_date: date) -> list[PanicSignal]:
    """
    Detect panic signals in the past 14 days from check_date.

    Args:
        check_date: The date to check from (usually today)

    Returns:
        List of panic signals found
    """
    # Calculate date range
    # Need extra days for volume average and z-score calculation
    start_date = check_date - timedelta(days=LOOKBACK_DAYS + ZSCORE_LOOKBACK_DAYS + 10)
    end_date = check_date

    # Fetch data
    market_data = get_market_data("TSE01", start_date, end_date)
    market_stats = get_market_stats(start_date, end_date)

    print(f"Fetched {len(market_data)} market data items, {len(market_stats)} market stats items")

    panic_signals: list[PanicSignal] = []

    # Check each day in the lookback period
    for i in range(LOOKBACK_DAYS):
        target_date = (check_date - timedelta(days=i)).isoformat()

        # Skip if no data for this date
        if not any(item["date"] == target_date for item in market_stats):
            continue

        price_panic, price_details = check_price_panic(market_data, market_stats, target_date)
        volume_explosion, volume_details = check_volume_explosion(market_data, target_date)
        liquidity_drain, liquidity_details = check_liquidity_drain(market_stats, target_date)

        # A panic day requires all three conditions
        if price_panic and volume_explosion and liquidity_drain:
            signal: PanicSignal = {
                "date": target_date,
                "price_panic": price_panic,
                "volume_explosion": volume_explosion,
                "liquidity_drain": liquidity_drain,
                "details": {
                    **price_details,
                    **volume_details,
                    **liquidity_details,
                },
            }
            panic_signals.append(signal)
            print(f"Panic signal detected on {target_date}: {signal}")

    return panic_signals


def send_panic_notification(panic_signals: list[PanicSignal]) -> bool:
    """
    Send panic notification via Discord.

    Args:
        panic_signals: List of panic signals to notify

    Returns:
        True if notification sent successfully
    """
    if not discord_notify_function_name:
        print("Discord notify function not configured")
        return False

    if not panic_signals:
        print("No panic signals to notify")
        return False

    try:
        timestamp = int(datetime.now(timezone.utc).timestamp())

        # Build notification message
        panic_dates = []
        for signal in panic_signals:
            signal_types = []
            if signal["price_panic"]:
                details = signal["details"]
                if details.get("daily_change_pct") is not None and details["daily_change_pct"] < PRICE_DROP_THRESHOLD:
                    signal_types.append(f"跌幅 {details['daily_change_pct']:.2f}%")
                if details.get("ldr") is not None and details["ldr"] > LDR_THRESHOLD:
                    signal_types.append(f"跌停比 {details['ldr']:.2f}%")
            if signal["volume_explosion"]:
                ratio = signal["details"].get("volume_ratio")
                if ratio:
                    signal_types.append(f"爆量 {ratio:.2f}x")
            if signal["liquidity_drain"]:
                details = signal["details"]
                if details.get("ucr") is not None and details["ucr"] < UCR_THRESHOLD:
                    signal_types.append(f"持平比 {details['ucr']:.2f}%")
                unchanged = details.get("unchanged")
                threshold = details.get("unchanged_threshold")
                if unchanged is not None and threshold is not None and unchanged < threshold:
                    signal_types.append(f"持平家數 {unchanged} < {threshold:.0f}")
                if (
                    details.get("participation_rate") is not None
                    and details.get("down_ratio") is not None
                    and details["participation_rate"] > PARTICIPATION_RATE_THRESHOLD
                    and details["down_ratio"] >= DOWN_RATIO_THRESHOLD
                ):
                    signal_types.append(f"參與率 {details['participation_rate']:.1f}% 下跌比 {details['down_ratio']:.1f}%")

            signal_text = ", ".join(signal_types) if signal_types else "恐慌訊號"
            panic_dates.append(f"• **{signal['date']}**: {signal_text}")

        panic_list = "\n".join(panic_dates)

        # Invoke Discord notification Lambda
        payload = {
            "notification_type": "panic",
            "title": "🚨 市場恐慌警報",
            "description": f"過去 {LOOKBACK_DAYS} 天內偵測到 {len(panic_signals)} 個恐慌日",
            "panic_dates": panic_list,
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
        print(f"Error sending panic notification: {e}")
        import traceback

        traceback.print_exc()
        return False


def handler(event, context):
    """
    Lambda handler for checking panic signals.

    Event format:
    {
        "check_date": "2026-03-06"  # Optional, defaults to today
    }
    """
    try:
        # Parse check date
        check_date_str = event.get("check_date")
        if check_date_str:
            check_date = date.fromisoformat(check_date_str)
        else:
            # Use Taiwan time (UTC+8)
            taiwan_tz = timezone(timedelta(hours=8))
            check_date = datetime.now(taiwan_tz).date()

        print(f"Checking panic signals for date: {check_date}")

        # Detect panic signals
        panic_signals = detect_panic_signals(check_date)

        if panic_signals:
            print(f"Found {len(panic_signals)} panic signals")
            send_panic_notification(panic_signals)
        else:
            print("No panic signals detected")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Panic signal check completed",
                    "check_date": check_date.isoformat(),
                    "panic_count": len(panic_signals),
                    "panic_dates": [s["date"] for s in panic_signals],
                }
            ),
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Error checking panic signals", "error": str(e)}),
        }


if __name__ == "__main__":
    # Test locally
    os.environ["MARKET_DATA_TABLE_NAME"] = "dev-aws-data-collector-market-data"
    os.environ["MARKET_STATS_TABLE_NAME"] = "dev-aws-data-collector-market-stats"

    test_event = {"check_date": "2026-03-06"}
    result = handler(test_event, None)
    print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
