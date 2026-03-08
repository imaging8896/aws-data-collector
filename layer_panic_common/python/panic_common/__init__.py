"""
Common panic detection logic shared between check_panic_signal and check_intraday_panic.

This module contains:
- Common constants (thresholds)
- Utility functions (decimal conversion, total calculation)
- Panic condition checks (price panic, LDR panic)
"""

from decimal import Decimal
from typing import Any

# ============================================================
# Common Constants
# ============================================================

# Panic thresholds
PRICE_DROP_THRESHOLD = -2.5  # Daily drop > 2.5%
LDR_THRESHOLD = 3.0  # Limit Down Ratio > 3%
VOLUME_MULTIPLIER = 1.25  # Volume >= 1.25x average (for historical check)
UCR_THRESHOLD = 1.5  # Unchanged Ratio < 1.5%
PARTICIPATION_RATE_THRESHOLD = 98.5  # Participation Rate > 98.5%
DOWN_RATIO_THRESHOLD = 90.0  # Down Ratio >= 90%

# Entry signal thresholds
BULL_REVERSAL_RATIO_THRESHOLD = 2.0  # 上漲/下跌 > 2
UP_LIMIT_RATIO_THRESHOLD = 1.5  # 漲停家數佔市場總家數 > 1.5%

# Ultimate exhaustion thresholds (for intraday check)
UNCHANGED_RATIO_THRESHOLD = 0.5  # Unchanged ratio < 0.5%
VOLUME_MULTIPLIER_THRESHOLD = 1.5  # Volume > 1.5x average


# ============================================================
# Utility Functions
# ============================================================


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


def calculate_total(stats: dict[str, Any]) -> int | None:
    """
    Calculate total from market stats.

    total = up + down + unchanged + untraded + no_comparison

    Args:
        stats: Dictionary containing market stats fields

    Returns:
        Total count or None if any field is missing
    """
    up = decimal_to_int(stats.get("up"))
    down = decimal_to_int(stats.get("down"))
    unchanged = decimal_to_int(stats.get("unchanged"))
    untraded = decimal_to_int(stats.get("untraded"))
    no_comparison = decimal_to_int(stats.get("no_comparison"))

    if all(v is not None for v in [up, down, unchanged, untraded, no_comparison]):
        return up + down + unchanged + untraded + no_comparison  # type: ignore

    return None


# ============================================================
# Panic Condition Checks
# ============================================================


def check_price_panic_from_change(
    daily_change_pct: float | None,
) -> tuple[bool, dict[str, Any]]:
    """
    Check if price panic condition is met based on daily change percentage.

    Price Panic: Daily drop > 2.5%

    Args:
        daily_change_pct: Daily price change percentage

    Returns:
        Tuple of (is_panic, details)
    """
    details: dict[str, Any] = {"daily_change_pct": daily_change_pct}

    if daily_change_pct is None:
        return False, details

    is_panic = daily_change_pct < PRICE_DROP_THRESHOLD
    return is_panic, details


def check_ldr_panic_from_stats(
    market_stats: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """
    Check if Limit Down Ratio (LDR) panic condition is met.

    LDR = down_limit / total > 3%

    Args:
        market_stats: Market statistics dictionary

    Returns:
        Tuple of (is_panic, details)
    """
    details: dict[str, Any] = {}

    down_limit = decimal_to_int(market_stats.get("down_limit"))
    total = calculate_total(market_stats)

    details["down_limit"] = down_limit
    details["total"] = total

    if total is None or total == 0 or down_limit is None:
        details["ldr"] = None
        return False, details

    ldr = (down_limit / total) * 100
    details["ldr"] = ldr

    is_panic = ldr > LDR_THRESHOLD
    return is_panic, details


def check_unchanged_ratio(
    market_stats: dict[str, Any],
    threshold: float = UNCHANGED_RATIO_THRESHOLD,
) -> tuple[bool, dict[str, Any]]:
    """
    Check if unchanged ratio is below threshold.

    Unchanged ratio = unchanged / total

    Args:
        market_stats: Market statistics dictionary
        threshold: Threshold percentage (default 0.5%)

    Returns:
        Tuple of (is_below_threshold, details)
    """
    details: dict[str, Any] = {}

    unchanged = decimal_to_int(market_stats.get("unchanged"))
    total = calculate_total(market_stats)

    details["unchanged"] = unchanged
    details["total"] = total

    if total is None or total == 0 or unchanged is None:
        details["unchanged_ratio"] = None
        return False, details

    unchanged_ratio = (unchanged / total) * 100
    details["unchanged_ratio"] = unchanged_ratio

    is_below = unchanged_ratio < threshold
    return is_below, details


def check_volume_ratio(
    current_volume: int | float | None,
    avg_volume: float | None,
    threshold: float = VOLUME_MULTIPLIER_THRESHOLD,
) -> tuple[bool, dict[str, Any]]:
    """
    Check if volume ratio exceeds threshold.

    Args:
        current_volume: Current day's volume
        avg_volume: Average volume from historical data
        threshold: Volume multiplier threshold

    Returns:
        Tuple of (exceeds_threshold, details)
    """
    details: dict[str, Any] = {
        "current_volume": current_volume,
        "avg_volume": avg_volume,
    }

    if current_volume is None or avg_volume is None or avg_volume == 0:
        details["volume_ratio"] = None
        return False, details

    volume_ratio = current_volume / avg_volume
    details["volume_ratio"] = volume_ratio

    exceeds = volume_ratio >= threshold
    return exceeds, details


# ============================================================
# Panic Day Detection
# ============================================================


def is_panic_day(
    market_data_item: dict[str, Any],
    market_stats_item: dict[str, Any],
    past_volumes: list[int | float],
    past_unchanged: list[int] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """
    Check if a given day is a panic day.

    Panic Day Definition:
    1. Price Panic: Daily drop > 2.5% OR LDR > 3%
    2. Volume Explosion: Volume >= 1.25x average
    3. Liquidity Drain:
       - unchanged z-score < -2 (unchanged < avg - 2*std) OR
       - UCR < 1.5% OR
       - (Participation Rate > 98.5% AND Down Ratio >= 90%)

    Args:
        market_data_item: Market data for the target day (must have 'close', 'change', 'volume')
        market_stats_item: Market stats for the target day
        past_volumes: List of volumes from past days for average calculation
        past_unchanged: List of unchanged values from past 60 days for z-score calculation (optional)

    Returns:
        Tuple of (is_panic, details)
    """
    details: dict[str, Any] = {
        "price_panic": False,
        "ldr_panic": False,
        "volume_explosion": False,
        "liquidity_drain": False,
    }

    # Check price panic - calculate daily_change_pct then use shared function
    close = decimal_to_float(market_data_item.get("close"))
    change = decimal_to_float(market_data_item.get("change"))
    daily_change_pct = None
    if close is not None and change is not None and close != 0:
        prev_close = close - change
        if prev_close != 0:
            daily_change_pct = (change / prev_close) * 100

    price_panic, price_details = check_price_panic_from_change(daily_change_pct)
    details["price_panic"] = price_panic
    details["daily_change_pct"] = price_details.get("daily_change_pct")

    # Check LDR panic
    ldr_panic, ldr_details = check_ldr_panic_from_stats(market_stats_item)
    details["ldr_panic"] = ldr_panic
    details["ldr"] = ldr_details.get("ldr")

    # Check volume explosion
    volume_explosion = False
    current_volume = decimal_to_int(market_data_item.get("volume"))
    details["current_volume"] = current_volume

    if current_volume and past_volumes:
        avg_volume = sum(past_volumes) / len(past_volumes)
        details["avg_volume"] = avg_volume
        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
            details["volume_ratio"] = volume_ratio
            volume_explosion = volume_ratio >= VOLUME_MULTIPLIER

    details["volume_explosion"] = volume_explosion

    # Check liquidity drain
    # Condition 1: UCR < 1.5%
    unchanged = decimal_to_int(market_stats_item.get("unchanged"))
    total = calculate_total(market_stats_item)
    ucr = None
    has_low_ucr = False
    if unchanged is not None and total is not None and total > 0:
        ucr = (unchanged / total) * 100
        has_low_ucr = ucr < UCR_THRESHOLD
    details["ucr"] = ucr
    details["has_low_ucr"] = has_low_ucr

    # Condition 2: unchanged z-score < -2 (unchanged < avg - 2*std)
    has_extreme_unchanged = False
    unchanged_threshold = None
    if past_unchanged and len(past_unchanged) >= 30 and unchanged is not None:
        import statistics

        mean = statistics.mean(past_unchanged)
        stdev = statistics.stdev(past_unchanged)
        unchanged_threshold = mean - 2 * stdev
        has_extreme_unchanged = unchanged < unchanged_threshold
    details["unchanged"] = unchanged
    details["unchanged_threshold"] = unchanged_threshold
    details["has_extreme_unchanged"] = has_extreme_unchanged

    # Condition 3: Participation Rate > 98.5% AND Down Ratio >= 90%
    down = decimal_to_int(market_stats_item.get("down"))
    untraded = decimal_to_int(market_stats_item.get("untraded"))
    participation_rate = None
    down_ratio = None
    has_extreme_participation = False

    if total is not None and untraded is not None and total > 0:
        participation_rate = ((total - untraded) / total) * 100
    if down is not None and total is not None and total > 0:
        down_ratio = (down / total) * 100
    if participation_rate is not None and down_ratio is not None:
        has_extreme_participation = participation_rate > PARTICIPATION_RATE_THRESHOLD and down_ratio >= DOWN_RATIO_THRESHOLD

    details["participation_rate"] = participation_rate
    details["down_ratio"] = down_ratio
    details["has_extreme_participation"] = has_extreme_participation

    # Liquidity drain: any of the three conditions
    liquidity_drain = has_low_ucr or has_extreme_unchanged or has_extreme_participation
    details["liquidity_drain"] = liquidity_drain

    # Panic day requires: (price_panic OR ldr_panic) AND volume_explosion AND liquidity_drain
    is_panic = (price_panic or ldr_panic) and volume_explosion and liquidity_drain

    return is_panic, details
