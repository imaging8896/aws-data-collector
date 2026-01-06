import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import boto3

from cnyes.index import Index, get_indexes

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
table_name = os.environ['DYNAMODB_TABLE_NAME']
market_data_table = dynamodb.Table(table_name)


def handler(event, context):
    """
    Fetch Taiwan Stock Index (TSE01) and TSMC (2330) daily price data
    Runs daily at 16:00 Taiwan time (08:00 UTC)

    {
        "index_names": ["tw_index", "2330"],
        "from_days": 30,
    }
    """
    try:
        # Handle Lambda Destination event format
        if 'responsePayload' in event:
            # Extract from Lambda Destination success event
            payload = event['responsePayload']
            if isinstance(payload, dict) and 'body' in payload:
                body = json.loads(payload['body']) if isinstance(payload['body'], str) else payload['body']
                index_names = body.get('index_names', ["tw_index"])
                from_days = body.get('from_days', 14)
            else:
                index_names = payload.get('index_names', ["tw_index"])
                from_days = payload.get('from_days', 14)
        else:
            # Direct invocation
            index_names = event.get('index_names', ["tw_index"])
            from_days = int(event.get('from_days', 14))

        def _to_index(name: str) -> Index:
            if name == "tw_index":
                return Index.tw_index()
            else:
                return Index.tw_stock(name)

        index_names = list(map(_to_index, index_names))

        # Calculate time range: last 30 days
        now = datetime.now(timezone.utc)
        to_timestamp = now
        from_timestamp = now - timedelta(days=from_days)

        print(f"Fetching market data for indexes {[str(idx) for idx in index_names]} from {from_timestamp} to {to_timestamp}")
        data = get_indexes(index_names, from_dt=from_timestamp, to_dt=to_timestamp)
        

        for index, index_data in data.items():
            index_name = index_data['name']
            print(f"Data for {str(index)} {index_name}")
            for date_str, opening, closing, high, low, volume, turnover in index_data['data']:
                # Save to DynamoDB
                market_data_table.put_item(Item={
                    'symbol': index.symbol,
                    'date': date_str,
                    'open': opening,
                    'close': closing,
                    'high': high,
                    'low': low,
                    'volume': volume,
                    'turnover': turnover, # 成交金額
                    'updated_at': int(now.timestamp())
                })
            print(f"Saved {len(index_data['data'])} data points for {str(index)} {index_name}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Market data fetched successfully'
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error fetching market data',
                'error': str(e)
            })
        }


if __name__ == "__main__":
    # Test locally
    test_event = {
        "index_names": ["tw_index", "2330"],
        "from_days": 30,
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
