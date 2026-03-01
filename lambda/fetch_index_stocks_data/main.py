import json
import os
from datetime import datetime

import boto3

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

# Environment variables
index_stocks_table_name = os.environ["DYNAMODB_INDEX_STOCKS_TABLE_NAME"]
fetch_market_data_function_name = os.environ["FETCH_MARKET_DATA_FUNCTION_NAME"]

index_stocks_table = dynamodb.Table(index_stocks_table_name)  # type: ignore

# Default period for yfinance (5 days of data)
DEFAULT_PERIOD = "5d"
BATCH_SIZE = 20


def get_all_stock_symbols():
    """
    Get all unique stock symbols from the index_stocks_table

    Returns:
        List of stock symbols (e.g., ["2330", "2317", "2882", ...])
    """
    try:
        response = index_stocks_table.scan(ProjectionExpression="stocks")

        items = response.get("Items", [])

        if not items:
            print("No index stocks data found in DynamoDB")
            return []

        # Extract unique stock symbols
        stock_symbols = set()
        for item in items:
            stocks = item.get("stocks", [])
            for stock in stocks:
                symbol = stock.get("symbol")
                if symbol:
                    stock_symbols.add(symbol)

        symbols_list = sorted(list(stock_symbols))
        print(f"Found {len(symbols_list)} unique stock symbols: {symbols_list}")
        return symbols_list

    except Exception as e:
        print(f"Error getting stock symbols: {str(e)}")
        import traceback

        traceback.print_exc()
        return []


def fetch_stocks_batch(stock_symbols: list[str], period: str) -> bool:
    """
    Invoke fetch_market_data Lambda for a batch of stocks using yfinance

    Args:
        stock_symbols: List of stock symbols (max BATCH_SIZE)
        period: yfinance period (e.g., "1y", "1mo", "5d")
    """
    try:
        payload = {"data_type": "yf_stock", "index_names": stock_symbols, "period": period}

        response = lambda_client.invoke(
            FunctionName=fetch_market_data_function_name,
            InvocationType="Event",  # Async invocation
            Payload=json.dumps(payload),
        )

        return response["StatusCode"] == 202

    except Exception as e:
        print(f"Error invoking fetch_market_data: {str(e)}")
        return False


def handler(event, context):
    """
    Lambda handler to fetch market data for all index stocks in batches

    Event format (optional):
    {
        "period": "1y"  # yfinance period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
    }
    """
    try:
        period = event.get("period", DEFAULT_PERIOD)

        print(f"Starting index stocks data fetch at {datetime.now()}")
        print(f"Will fetch data with period: {period}")

        # Get all stock symbols from index_stocks_table
        stock_symbols = get_all_stock_symbols()

        if not stock_symbols:
            raise Exception("No stock symbols found in index_stocks_table")

        # Batch fetch - invoke fetch_market_data for each batch
        total_batches = (len(stock_symbols) + BATCH_SIZE - 1) // BATCH_SIZE
        success_count = 0

        for batch_idx in range(0, len(stock_symbols), BATCH_SIZE):
            batch = stock_symbols[batch_idx : batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1

            print(f"Invoking batch {batch_num}/{total_batches}: {len(batch)} stocks - {batch}")

            if fetch_stocks_batch(batch, period):
                success_count += 1
            else:
                print(f"Failed to invoke batch {batch_num}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Index stocks data fetch triggered",
                    "total_stocks": len(stock_symbols),
                    "total_batches": total_batches,
                    "success_batches": success_count,
                    "period": period,
                }
            ),
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"message": "Error fetching index stocks data", "error": str(e)})}


if __name__ == "__main__":
    result = handler({}, None)
    print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
