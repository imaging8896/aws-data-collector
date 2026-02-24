import json
import os
import time
from datetime import date, datetime, timedelta, timezone

import boto3

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
market_data_table_name = os.environ["MARKET_DATA_TABLE_NAME"]
investor_data_table_name = os.environ["INVESTOR_DATA_TABLE_NAME"]
index_data_table_name = os.environ["INDEX_DATA_TABLE_NAME"]
market_stats_table_name = os.environ["MARKET_STATS_TABLE_NAME"]
market_data_table = dynamodb.Table(market_data_table_name)  # type: ignore
investor_data_table = dynamodb.Table(investor_data_table_name)  # type: ignore
index_data_table = dynamodb.Table(index_data_table_name)  # type: ignore
market_stats_table = dynamodb.Table(market_stats_table_name)  # type: ignore


def retry_once(func):
    """Decorator to retry a function once on failure"""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"First attempt failed: {str(e)}, retrying in 2 seconds...")
            time.sleep(2)
            return func(*args, **kwargs)

    return wrapper


def handler(event, context):
    """
    Fetch Taiwan Stock Index (TSE01) and TSMC (2330) daily price data
    Runs daily at 16:00 Taiwan time (08:00 UTC)

    {
        "data_type": "index", # index or investor
        "index_names": ["tw_index", "2330"],
        "from_days": 30,
    }
    """
    try:
        # Handle Lambda Destination event format
        if "responsePayload" in event:
            # Extract from Lambda Destination success event
            payload = event["responsePayload"]
            if isinstance(payload, dict) and "body" in payload:
                body = json.loads(payload["body"]) if isinstance(payload["body"], str) else payload["body"]
                data_type = body.get("data_type", "index")
                index_names = body.get("index_names", ["tw_index"])
                from_days = body.get("from_days", 14)
                data_date = date.fromisoformat(body.get("data_date", date.today().isoformat()))
            else:
                data_type = payload.get("data_type", "index")
                index_names = payload.get("index_names", ["tw_index"])
                from_days = payload.get("from_days", 14)
                data_date = date.fromisoformat(payload.get("data_date", date.today().isoformat()))
        else:
            # Direct invocation
            data_type = event.get("data_type", "index")
            index_names = event.get("index_names", ["tw_index"])
            from_days = int(event.get("from_days", 14))
            data_date = date.fromisoformat(event.get("data_date", date.today().isoformat()))

        if data_type == "trades":
            get_trades(index_names, from_days)
        elif data_type == "investor":
            get_investor(data_date)
        elif data_type == "indexes":
            get_indexes(data_date)
        elif data_type == "stock_group_trade":
            get_stock_group_trade(data_date)
        elif data_type == "market_stats":
            get_market_stats(data_date)
        else:
            raise ValueError(f"Unsupported data_type: {data_type}")

        return {"statusCode": 200, "body": json.dumps({"message": f"Market data '{data_type}' fetched successfully"})}

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"message": "Error fetching market data", "error": str(e)})}


@retry_once
def get_trades(index_names, from_days):
    from cnyes.trade import Index, get_trades

    def _to_index(name: str) -> Index:
        if name == "tw_index":
            return Index.tw_index()
        else:
            return Index.tw_stock(name)

    print(f"Getting index data for: {index_names} for last {from_days} days")

    index_names = list(map(_to_index, index_names))

    # Calculate time range: last 30 days
    now = datetime.now(timezone.utc)
    to_timestamp = now
    from_timestamp = now - timedelta(days=from_days)

    print(f"Fetching market data for indexes {[str(idx) for idx in index_names]} from {from_timestamp} to {to_timestamp}")
    data = get_trades(index_names, from_dt=from_timestamp, to_dt=to_timestamp)

    for index, index_data in data.items():
        index_name = index_data["name"]
        print(f"Data for {str(index)} {index_name}")
        for date_str, opening, closing, high, low, volume, turnover in index_data["data"]:
            # Save to DynamoDB
            market_data_table.put_item(
                Item={
                    "symbol": index.symbol,
                    "date": date_str,
                    "open": opening,
                    "close": closing,
                    "high": high,
                    "low": low,
                    "volume": volume,
                    "turnover": turnover,  # 成交金額
                    "updated_at": int(now.timestamp()),
                }
            )
        print(f"Saved {len(index_data['data'])} data points for {str(index)} {index_name}")


@retry_once
def get_investor(data_date: date):
    from twse.investor import get_investor

    print(f"Getting investor data for: {data_date}")

    if data := get_investor(data_date):
        investor_data_table.put_item(
            Item={
                "date": data_date.isoformat(),
                "data": data,
                "updated_at": int(datetime.now(timezone.utc).timestamp()),
            }
        )
        print(f"Saved investor data for {data_date}\n{data}")
    else:
        print(f"No investor data available for {data_date}")


@retry_once
def get_indexes(data_date: date):
    from twse.index import get_indexes

    print("Getting indexes data")

    data = get_indexes(data_date)

    if not data:
        print("No index data available")
        return data

    # Get timestamp for all items
    updated_at = int(datetime.now(timezone.utc).timestamp())

    # Save each index as a separate item with name+date as composite key
    for index_name, index_data in data.items():
        print(f"Index: {index_name}, Value: {index_data['value']}, Date: {index_data['date']}, Diff: {index_data['diff']}, Diff%: {index_data['diff_percent']}")

        # Update item with composite key (name, date)
        # If the item exists, it will be updated; otherwise, it will be created
        index_data_table.update_item(
            Key={"name": index_name, "date": index_data["date"]},
            UpdateExpression="SET #value = :value, #diff = :diff, diff_percent = :diff_percent, updated_at = :updated_at",
            ExpressionAttributeNames={
                "#value": "value",  # 'value' is a reserved word in DynamoDB
                "#diff": "diff",  # 'diff' might be reserved
            },
            ExpressionAttributeValues={
                ":value": index_data["value"],
                ":diff": index_data["diff"],
                ":diff_percent": index_data["diff_percent"],
                ":updated_at": updated_at,
            },
        )

    print(f"Saved/Updated {len(data)} indexes")
    return data


@retry_once
def get_stock_group_trade(data_date: date):
    from twse.stock_group_trade import get_stock_group_trade

    print("Getting stock group trade data")

    data = get_stock_group_trade(data_date)

    if not data:
        print("No stock group trade data available")
        return data

    # Get timestamp for all items
    updated_at = int(datetime.now(timezone.utc).timestamp())

    data_date_str = data_date.isoformat()
    # Save each index as a separate item with name+date as composite key
    for index_name, index_data in data.items():
        print(
            f"Index: {index_name}, Shares: {index_data['shares']}, Date: {data_date_str}, "
            f"Amount: {index_data['amount']}, Transactions: {index_data['transactions']}"
        )

        # Update item with composite key (name, date)
        # If the item exists, it will be updated; otherwise, it will be created
        index_data_table.update_item(
            Key={"name": index_name, "date": data_date_str},
            UpdateExpression="SET #shares = :shares, #amount = :amount, #transactions = :transactions, updated_at = :updated_at",
            ExpressionAttributeNames={"#shares": "shares", "#amount": "amount", "#transactions": "transactions"},
            ExpressionAttributeValues={
                ":shares": index_data["shares"],
                ":amount": index_data["amount"],
                ":transactions": index_data["transactions"],
                ":updated_at": updated_at,
            },
        )

    print(f"Saved/Updated {len(data)} stock group trades")
    return data


@retry_once
def get_market_stats(data_date: date):
    """Fetch and store market statistics (上漲/下跌/平盤家數)"""
    from twse.market_stats import get_market_stats

    print(f"Getting market stats data for: {data_date}")

    data = get_market_stats(data_date)

    if not data:
        print(f"No market stats data available for {data_date}")
        return data

    updated_at = int(datetime.now(timezone.utc).timestamp())

    # Store market stats in DynamoDB
    market_stats_table.put_item(
        Item={
            "date": data_date.isoformat(),
            "up": data["up"],
            "up_limit": data["up_limit"],
            "down": data["down"],
            "down_limit": data["down_limit"],
            "unchanged": data["unchanged"],
            "updated_at": updated_at,
        }
    )

    print(
        f"Saved market stats for {data_date}: "
        f"up={data['up']}, up_limit={data['up_limit']}, "
        f"down={data['down']}, down_limit={data['down_limit']}, "
        f"unchanged={data['unchanged']}"
    )
    return data


if __name__ == "__main__":
    # Test locally
    cur_date = date.today()
    for _ in range(25):
        while True:  # Skip weekends
            if cur_date.weekday() >= 5:
                cur_date -= timedelta(days=1)
                continue

            if not get_stock_group_trade(cur_date):
                cur_date -= timedelta(days=1)
                continue
            test_event = {
                "data_type": "indexes",
                "index_names": ["tw_index", "2330"],
                "from_days": 300,
                "data_date": cur_date.isoformat(),
            }
            result = handler(test_event, None)
            print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))

            test_event = {
                "data_type": "stock_group_trade",
                "index_names": ["tw_index", "2330"],
                "from_days": 300,
                "data_date": cur_date.isoformat(),
            }
            result = handler(test_event, None)
            print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
            break
        cur_date -= timedelta(days=1)
