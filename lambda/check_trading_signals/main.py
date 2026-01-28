import json
import os
from datetime import datetime
import boto3
from google import genai
from google.genai import types

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')
lambda_client = boto3.client('lambda')

# Environment variables
stats_table_name = os.environ['DYNAMODB_STATS_TABLE_NAME']
gemini_secret_name = os.environ.get('GEMINI_API_KEY_SECRET_NAME')
discord_notify_function_name = os.environ.get('DISCORD_NOTIFY_FUNCTION_NAME')

stats_table = dynamodb.Table(stats_table_name) # type: ignore

# Initialize Gemini client (lazy loading)
_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None and gemini_secret_name:
        try:
            secret_response = secrets_client.get_secret_value(SecretId=gemini_secret_name)
            api_key = secret_response['SecretString']
            _gemini_client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"Failed to initialize Gemini client: {str(e)}")
    return _gemini_client


def find_representative_stocks(client, index_name):
    """
    Use AI to find representative stocks for a given index
    
    Args:
        client: Gemini AI client
        index_name: Name of the index (e.g., "金融類", "半導體類")
    
    Returns:
        List of dicts with stock information
    """
    if not client:
        print(f"AI client not available for finding stocks")
        return []
    
    try:
        prompt = f"""請找出「{index_name}」這個台股指數中最具代表性的前 5 家上市公司。

要求：
1. 只回傳台灣上市公司（股票代號為 4 位數字）
2. 按市值和產業代表性排序
3. 提供股票代號、公司名稱、以及為何具代表性的簡短理由

請以 JSON 格式回傳，格式如下：
{{
  "stocks": [
    {{"symbol": "2330", "name": "台積電", "reason": "全球半導體龍頭"}},
    {{"symbol": "2317", "name": "鴻海", "reason": "電子代工龍頭"}}
  ]
}}

注意：
- 確保股票代號正確且為台灣上市公司
- 最多回傳 5 家公司
- 理由簡潔（10 字以內）
"""

        response = client.models.generate_content(
            model='gemini-2.0-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type='application/json'
            )
        )
        
        response_text = response.text.strip()
        
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1]
            response_text = response_text.rsplit('```', 1)[0]
        
        result = json.loads(response_text)
        stocks = result.get('stocks', [])
        
        print(f"Found {len(stocks)} representative stocks for {index_name}: {stocks}")
        return stocks
        
    except Exception as e:
        print(f"Error finding representative stocks for {index_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def get_latest_stats():
    """
    Get the latest daily stats from DynamoDB
    Returns the most recent date's data
    """
    try:
        # Scan to get all dates and find the latest
        response = stats_table.scan(
            ProjectionExpression='#d, RSI, last_notification_timestamp',
            ExpressionAttributeNames={'#d': 'date'}
        )
        
        items = response.get('Items', [])
        
        if not items:
            print("No stats data found in DynamoDB")
            return None, None
        
        # Find the latest date
        latest_item = max(items, key=lambda x: x['date'])
        latest_date = latest_item['date']
        
        print(f"Latest stats date: {latest_date}")
        
        # Get full data for latest date
        full_response = stats_table.get_item(Key={'date': latest_date})
        
        if 'Item' not in full_response:
            return latest_date, None
        
        return latest_date, full_response['Item']
        
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
        stats_data: Stats data from DynamoDB including RSI
    """
    if not stats_data or 'RSI' not in stats_data:
        print("No RSI data available")
        return
    
    rsi_data = stats_data.get('RSI', {})
    
    if not discord_notify_function_name:
        print("Discord notify function not configured")
        return
    
    try:
        current_timestamp = int(datetime.now().timestamp())
        
        # Check if we already sent notifications today
        last_notification_time = int(stats_data.get('last_notification_timestamp', 0))
        
        # Check if notification was sent in the last 20 hours
        if current_timestamp - last_notification_time < 20 * 3600:
            print(f"Already sent notifications for {date_str} at {datetime.fromtimestamp(last_notification_time)}")
            return
        
        client = get_gemini_client()
        notifications_sent = []
        
        for index_name, index_data in rsi_data.items():
            # Only process indexes ending with "類" but skip "其他類"
            if not index_name.endswith('類') or index_name == '其他類':
                continue
            
            medium_strategy = index_data.get('medium_strategy', {})
            short_strategy = index_data.get('short_strategy', {})
            
            # Check for buy signals
            has_medium_buy = medium_strategy.get('buy_signal', False)
            has_short_buy = short_strategy.get('buy_signal', False)
            
            # Check for sell signals
            has_medium_sell = medium_strategy.get('sell_signal', False)
            has_short_sell = short_strategy.get('sell_signal', False)
            
            if not (has_medium_buy or has_short_buy or has_medium_sell or has_short_sell):
                continue
            
            print(f"Signal detected for {index_name}:")
            if has_medium_buy:
                print(f"  - Medium-term BUY signal")
            if has_short_buy:
                print(f"  - Short-term BUY signal")
            if has_medium_sell:
                print(f"  - Medium-term SELL signal")
            if has_short_sell:
                print(f"  - Short-term SELL signal")
            
            # Find representative stocks using AI
            representative_stocks = find_representative_stocks(client, index_name)
            
            # Send notifications for each signal type
            if has_medium_buy:
                send_notification(index_name, 'buy', 'medium', representative_stocks, current_timestamp)
                notifications_sent.append(f"{index_name}-medium-buy")
            
            if has_short_buy:
                send_notification(index_name, 'buy', 'short', representative_stocks, current_timestamp)
                notifications_sent.append(f"{index_name}-short-buy")
            
            if has_medium_sell:
                send_notification(index_name, 'sell', 'medium', representative_stocks, current_timestamp)
                notifications_sent.append(f"{index_name}-medium-sell")
            
            if has_short_sell:
                send_notification(index_name, 'sell', 'short', representative_stocks, current_timestamp)
                notifications_sent.append(f"{index_name}-short-sell")
        
        # Update notification timestamp in DynamoDB
        if notifications_sent:
            stats_table.update_item(
                Key={'date': date_str},
                UpdateExpression='SET last_notification_timestamp = :ts, notifications_sent = :notifs',
                ExpressionAttributeValues={
                    ':ts': current_timestamp,
                    ':notifs': notifications_sent
                }
            )
            print(f"Sent {len(notifications_sent)} notifications for {date_str}")
        else:
            print(f"No trading signals detected for indexes ending with '類' on {date_str}")
        
    except Exception as e:
        print(f"Error checking signals and notifying: {str(e)}")
        import traceback
        traceback.print_exc()


def send_notification(index_name, signal_type, strategy_type, stock_symbols, timestamp):
    """
    Send a single notification to Discord
    """
    try:
        payload = {
            'index_name': index_name,
            'signal_type': signal_type,
            'strategy_type': strategy_type,
            'stock_symbols': stock_symbols,
            'timestamp': timestamp
        }
        
        response = lambda_client.invoke(
            FunctionName=discord_notify_function_name,
            InvocationType='Event',  # Async invocation
            Payload=json.dumps(payload)
        )
        
        print(f"Sent {strategy_type} {signal_type} notification for {index_name}")
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
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': 'No stats data found'
                })
            }
        
        # Check signals and send notifications
        check_signals_and_notify(latest_date, stats_data)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Trading signals check completed',
                'date': latest_date
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error checking trading signals',
                'error': str(e)
            })
        }


if __name__ == "__main__":
    result = handler({}, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
