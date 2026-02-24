import json
import os
import time
from datetime import datetime

import boto3

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

# Environment variables
stats_table_name = os.environ["DYNAMODB_STATS_TABLE_NAME"]
discord_notify_function_name = os.environ.get("DISCORD_NOTIFY_FUNCTION_NAME")

stats_table = dynamodb.Table(stats_table_name)  # type: ignore


def get_latest_stats():
    """
    Get the latest daily stats from DynamoDB
    Returns the most recent date's data
    """
    try:
        # Scan to get all dates and find the latest (handle pagination)
        items: list[dict] = []
        response = stats_table.scan(ProjectionExpression="#d, RSI", ExpressionAttributeNames={"#d": "date"})
        items.extend(response.get("Items", []))

        # Handle pagination - DynamoDB scan returns max 1MB per call
        while "LastEvaluatedKey" in response:
            response = stats_table.scan(
                ProjectionExpression="#d, RSI",
                ExpressionAttributeNames={"#d": "date"},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        if not items:
            print("No stats data found in DynamoDB")
            return None, None

        # Find the latest date
        latest_item = max(items, key=lambda x: x["date"])
        latest_date = latest_item["date"]

        print(f"Latest stats date: {latest_date}, total items scanned: {len(items)}")

        # Get full data for latest date
        full_response = stats_table.get_item(Key={"date": latest_date})

        if "Item" not in full_response:
            return latest_date, None

        return latest_date, full_response["Item"]

    except Exception as e:
        print(f"Error getting latest stats: {str(e)}")
        import traceback

        traceback.print_exc()
        return None, None


def check_signals_and_notify(date_str, stats_data):
    """
    Check for buy/sell signals and send Discord notifications

    Args:
        date_str: Date string (YYYY-MM-DD)
        stats_data: Stats data from DynamoDB including RSI and RSI_stock
    """
    if not stats_data or "RSI" not in stats_data:
        print("No RSI data available")
        return

    rsi_data = stats_data.get("RSI", {})
    rsi_stock_data = stats_data.get("RSI_stock", {})

    if not discord_notify_function_name:
        print("Discord notify function not configured")
        return

    try:
        current_timestamp = int(datetime.now().timestamp())

        # Check if we already sent notifications today
        last_notification_time = int(stats_data.get("last_notification_timestamp", 0))

        # Check if notification was sent in the last 20 hours
        if current_timestamp - last_notification_time < 20 * 3600:
            print(f"Already sent notifications for {date_str} at {datetime.fromtimestamp(last_notification_time)}")
            return

        notifications_sent = []

        # Broad market indexes that have no individual stocks but should still notify
        INDEXES_WITHOUT_STOCKS = {"發行量加權股價", "臺灣50"}

        for index_name, index_data in rsi_data.items():
            medium_strategy = index_data.get("medium_strategy", {})
            short_strategy = index_data.get("short_strategy", {})

            # Check for buy signals
            has_medium_buy = medium_strategy.get("buy_signal", False)
            has_short_buy = short_strategy.get("buy_signal", False)

            # Check for sell signals
            has_medium_sell = medium_strategy.get("sell_signal", False)
            has_short_sell = short_strategy.get("sell_signal", False)

            if not (has_medium_buy or has_short_buy or has_medium_sell or has_short_sell):
                continue

            print(f"Signal detected for {index_name}:")
            if has_medium_buy:
                print("  - Medium-term BUY signal")
            if has_short_buy:
                print("  - Short-term BUY signal")
            if has_medium_sell:
                print("  - Medium-term SELL signal")
            if has_short_sell:
                print("  - Short-term SELL signal")

            # Get stock signals from RSI_stock data, only include stocks with buy or sell signals
            index_stock_signals = rsi_stock_data.get(index_name, {})

            stocks_with_signals = []
            for stock_symbol, stock_signal in index_stock_signals.items():
                stock_name = stock_signal.get("name", "")
                has_latest_data = stock_signal.get("has_latest_data", False)
                has_signal = stock_signal.get("has_signal", False)
                buy_signal = stock_signal.get("buy_signal", False)
                sell_signal = stock_signal.get("sell_signal", False)
                rsi_5 = stock_signal.get("rsi_5")
                daily_gain_pct = stock_signal.get("daily_gain_pct")

                if not (buy_signal or sell_signal):
                    continue

                # Convert Decimal to float if needed
                if rsi_5 is not None:
                    rsi_5 = float(rsi_5)
                if daily_gain_pct is not None:
                    daily_gain_pct = float(daily_gain_pct)

                stock_info = {
                    "symbol": stock_symbol,
                    "name": stock_name,
                    "has_latest_data": has_latest_data,
                    "has_signal": has_signal,
                    "buy_signal": buy_signal,
                    "sell_signal": sell_signal,
                    "rsi_5": rsi_5,
                    "daily_gain_pct": daily_gain_pct,
                }
                stocks_with_signals.append(stock_info)

                signal_type = "買入" if buy_signal else "賣出"
                print(f"  Stock {stock_symbol} ({stock_name}): {signal_type} signal, RSI5={rsi_5}, 漲跌={daily_gain_pct}%")

            # Only send notification if index has signal AND there are stocks with signals
            # Exception: broad market indexes (e.g. 發行量加權股價, 臺灣50) have no individual stocks
            if not stocks_with_signals and index_name not in INDEXES_WITHOUT_STOCKS:
                continue

            # Collect all signals for this index
            signals = []
            if has_medium_buy:
                signals.append({"signal_type": "buy", "strategy_type": "medium"})
            if has_short_buy:
                signals.append({"signal_type": "buy", "strategy_type": "short"})
            if has_medium_sell:
                signals.append({"signal_type": "sell", "strategy_type": "medium"})
            if has_short_sell:
                signals.append({"signal_type": "sell", "strategy_type": "short"})

            # Send one consolidated notification per index
            send_notification(index_name, signals, stocks_with_signals, current_timestamp)
            signal_names = [f"{s['strategy_type']}-{s['signal_type']}" for s in signals]
            notifications_sent.append(f"{index_name}: {', '.join(signal_names)}")

            # Add delay between notifications to avoid Discord rate limiting (429)
            time.sleep(1)

        # Update notification timestamp in DynamoDB
        if notifications_sent:
            stats_table.update_item(
                Key={"date": date_str},
                UpdateExpression="SET last_notification_timestamp = :ts, notifications_sent = :notifs",
                ExpressionAttributeValues={":ts": current_timestamp, ":notifs": notifications_sent},
            )
            print(f"Sent {len(notifications_sent)} notifications for {date_str}")
        else:
            print(f"No trading signals detected on {date_str}")

    except Exception as e:
        print(f"Error checking signals and notifying: {str(e)}")
        import traceback

        traceback.print_exc()


def send_notification(index_name, signals, stock_symbols, timestamp):
    """
    Send a consolidated notification to Discord for all signals of an index

    Args:
        index_name: Name of the index
        signals: List of signal dicts with 'signal_type' and 'strategy_type'
        stock_symbols: List of representative stocks
        timestamp: Current timestamp
    """
    try:
        payload = {"index_name": index_name, "signals": signals, "stock_symbols": stock_symbols, "timestamp": timestamp}

        response = lambda_client.invoke(
            FunctionName=discord_notify_function_name,
            InvocationType="Event",  # Async invocation
            Payload=json.dumps(payload),
        )

        signal_desc = ", ".join([f"{s['strategy_type']} {s['signal_type']}" for s in signals])
        print(f"Sent notification for {index_name}: {signal_desc}")
        print(f"Lambda invoke response: {response}")

    except Exception as e:
        print(f"Error sending notification for {index_name}: {str(e)}")


def handler(event, context):
    """
    Lambda handler to check trading signals and send notifications
    Triggered daily at 8:00 AM
    """
    try:
        print(f"Checking trading signals at {datetime.now()}")

        # Get latest stats data
        latest_date, stats_data = get_latest_stats()

        if not latest_date or not stats_data:
            return {"statusCode": 404, "body": json.dumps({"message": "No stats data found"})}

        # Check signals and send notifications
        check_signals_and_notify(latest_date, stats_data)

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Trading signals check completed", "date": latest_date}),
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"message": "Error checking trading signals", "error": str(e)})}


if __name__ == "__main__":
    result = handler({}, None)
    print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
