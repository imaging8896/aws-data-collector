import json
import os
from datetime import datetime
import boto3
from google import genai
from google.genai import types

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Environment variables
index_stocks_table_name = os.environ['DYNAMODB_INDEX_STOCKS_TABLE_NAME']
stats_table_name = os.environ['DYNAMODB_STATS_TABLE_NAME']
gemini_secret_name = os.environ.get('GEMINI_API_KEY_SECRET_NAME')

index_stocks_table = dynamodb.Table(index_stocks_table_name) # type: ignore
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


def get_taiwan_indexes_from_stats():
    """
    Get Taiwan stock indexes from stats table
    Extracts all index names that end with "類" and are not "其他類"
    
    Returns:
        List of index names
    """
    try:
        # Scan to get all dates
        response = stats_table.scan(
            ProjectionExpression='RSI'
        )
        
        items = response.get('Items', [])
        
        if not items:
            print("No stats data found in DynamoDB")
            return []
        
        # Extract all unique index names from RSI data
        index_names = set()
        for item in items:
            rsi_data = item.get('RSI', {})
            for index_name in rsi_data.keys():
                # Only include indexes ending with "類" but skip "其他類"
                if index_name.endswith('類') and index_name != '其他類':
                    index_names.add(index_name)
        
        taiwan_indexes = sorted(list(index_names))
        print(f"Found {len(taiwan_indexes)} Taiwan stock indexes: {taiwan_indexes}")
        return taiwan_indexes
        
    except Exception as e:
        print(f"Error getting Taiwan indexes from stats table: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def find_representative_stocks_batch(client, index_names):
    """
    Use AI to find representative stocks for multiple indexes in one request
    
    Args:
        client: Gemini AI client
        index_names: List of index names (e.g., ["金融類", "半導體類", ...])
    
    Returns:
        Dict mapping index_name to list of stock dicts
    """
    if not client:
        print(f"AI client not available for finding stocks")
        return {}
    
    if not index_names:
        print("No index names provided")
        return {}
    
    try:
        # Format index names as a numbered list for the prompt
        index_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(index_names)])
        
        prompt = f"""請根據「台灣證券交易所」(TWSE) 的產業分類資料，找出以下類股指數中最具代表性的前 5 家上市公司。

這些類股指數是由台灣證券交易所建立的產業分類，請確保回傳的股票確實屬於該類股指數的成分股。

類股指數列表：
{index_list}

要求：
1. 只回傳台灣證券交易所上市公司（股票代號為 4 位數字）
2. 股票必須是該類股指數的成分股（依據 TWSE 產業分類）
3. 按市值和產業代表性排序
4. 提供股票代號、公司名稱、以及為何具代表性的簡短理由

請以 JSON 格式回傳，格式如下：
{{
  "index_stocks": {{
    "金融保險類": [
      {{"symbol": "2882", "name": "國泰金", "reason": "金控龍頭"}},
      {{"symbol": "2881", "name": "富邦金", "reason": "金控市值第二"}}
    ],
    "半導體類": [
      {{"symbol": "2330", "name": "台積電", "reason": "全球半導體龍頭"}},
      {{"symbol": "2303", "name": "聯電", "reason": "晶圓代工第二"}}
    ]
  }}
}}

注意：
- 確保股票代號正確且確實在台灣證券交易所上市
- 確保股票屬於對應的 TWSE 類股指數成分股
- 每個類股指數最多回傳 5 家公司
- 理由簡潔（10 字以內）
- 必須包含所有指定的類股指數
"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type='application/json'
            )
        )
        
        # Print token usage
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            print(f"Token usage - Input: {usage.prompt_token_count}, Output: {usage.candidates_token_count}, Total: {usage.total_token_count}")
        
        response_text = response.text.strip()
        
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1]
            response_text = response_text.rsplit('```', 1)[0]
        
        result = json.loads(response_text)
        index_stocks = result.get('index_stocks', {})
        
        print(f"Found stocks for {len(index_stocks)} indexes in single request")
        return index_stocks
        
    except Exception as e:
        print(f"Error finding representative stocks in batch: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


def update_index_stocks():
    """
    Update representative stocks for all Taiwan stock indexes
    This should be run monthly to keep the stock list fresh
    Indexes are fetched dynamically from stats table
    All indexes are processed in a single AI request
    """
    # Get Taiwan stock indexes from stats table
    taiwan_indexes = get_taiwan_indexes_from_stats()
    
    if not taiwan_indexes:
        print("No Taiwan stock indexes found")
        return {
            'updated': 0,
            'failed': 0,
            'indexes': []
        }
    
    client = get_gemini_client()
    if not client:
        print("Failed to initialize Gemini client, cannot update stocks")
        return {
            'updated': 0,
            'failed': len(taiwan_indexes),
            'indexes': []
        }
    
    updated_count = 0
    failed_count = 0
    updated_indexes = []
    
    try:
        print(f"Processing all {len(taiwan_indexes)} indexes in a single AI request...")
        
        # Get all stocks in one AI request
        index_stocks_dict = find_representative_stocks_batch(client, taiwan_indexes)
        
        if not index_stocks_dict:
            print("Failed to get stocks from AI")
            return {
                'updated': 0,
                'failed': len(taiwan_indexes),
                'indexes': []
            }
        
        # Store each index's stocks in DynamoDB
        for index_name in taiwan_indexes:
            try:
                stocks = index_stocks_dict.get(index_name, [])
                
                if stocks and isinstance(stocks, list) and len(stocks) > 0:
                    # Store in DynamoDB
                    index_stocks_table.put_item(
                        Item={
                            'index_name': index_name,
                            'stocks': stocks,
                            'updated_at': datetime.now().isoformat(),
                            'updated_timestamp': int(datetime.now().timestamp())
                        }
                    )
                    updated_count += 1
                    updated_indexes.append(index_name)
                    print(f"Updated {index_name} with {len(stocks)} stocks")
                else:
                    failed_count += 1
                    print(f"No stocks returned for {index_name}")
                    
            except Exception as e:
                failed_count += 1
                print(f"Error storing stocks for {index_name}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        return {
            'updated': updated_count,
            'failed': failed_count,
            'indexes': updated_indexes
        }
        
    except Exception as e:
        print(f"Error in update_index_stocks: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'updated': 0,
            'failed': len(taiwan_indexes),
            'indexes': []
        }


def handler(event, context):
    """
    Lambda handler to update representative stocks for all indexes
    Triggered monthly on the 1st at 00:00
    """
    try:
        print(f"Starting index stocks update at {datetime.now()}")
        
        result = update_index_stocks()
        
        print(f"Update completed: {result['updated']} updated, {result['failed']} failed")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Index stocks update completed',
                'result': result
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error updating index stocks',
                'error': str(e)
            })
        }


if __name__ == "__main__":
    result = handler({}, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
