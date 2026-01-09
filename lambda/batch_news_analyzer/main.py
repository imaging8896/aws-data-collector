import json
import os
import boto3
from datetime import datetime
from google import genai
from google.genai import types

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Environment variables
news_table_name = os.environ['DYNAMODB_TABLE_NAME']
batch_table_name = os.environ['DYNAMODB_BATCH_TABLE_NAME']
gemini_secret_name = os.environ['GEMINI_API_KEY_SECRET_NAME']

news_table = dynamodb.Table(news_table_name)
batch_table = dynamodb.Table(batch_table_name)

categories = os.environ['CATEGORIES'].split(',')

# Cache Gemini client
_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        secret_response = secrets_client.get_secret_value(SecretId=gemini_secret_name)
        api_key = secret_response['SecretString']
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def handler(event, context):
    """
    Scan news URL DB for articles without analysis and create a combined Batch API request
    Runs every 3 hours
    """
    try:
        # Scan for news items without analysis
        news_items_to_analyze = scan_unanalyzed_news()
        
        if not news_items_to_analyze:
            print("No news items to analyze")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No unanalyzed news items found',
                    'count': 0
                })
            }
        
        print(f"Found {len(news_items_to_analyze)} news items to analyze")
        
        # Submit combined batch job
        submit_combined_batch(news_items_to_analyze[:10])
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Batch analysis request submitted',
                'count': len(news_items_to_analyze)
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error submitting batch analysis request',
                'error': str(e)
            })
        }


def scan_unanalyzed_news():
    """
    Scan DynamoDB for news items without analysis field
    Excludes news items that are already in pending batch requests
    Returns list of items with url, title, and content
    """
    unanalyzed_items = []
    
    try:
        # First, get all URLs that are in pending batches
        pending_urls = set()
        batch_response = batch_table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'PENDING'}
        )
        
        for item in batch_response.get('Items', []):
            if item['url'] == '__metadata__':
                pending_urls.extend([mapping['url'] for mapping in item['metadata']])
            else:  
                pending_urls.add(item['url'])
        
        # Handle pagination for batch table
        while 'LastEvaluatedKey' in batch_response:
            batch_response = batch_table.scan(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': 'PENDING'},
                ExclusiveStartKey=batch_response['LastEvaluatedKey']
            )
            for item in batch_response.get('Items', []):
                if item['url'] == '__metadata__':
                    pending_urls.extend([mapping['url'] for mapping in item['metadata']])
                else:  
                    pending_urls.add(item['url'])
        
        print(f"Found {len(pending_urls)} URLs in pending batches")
        
        # Scan for items without analysis attribute
        response = news_table.scan(
            FilterExpression='attribute_not_exists(analysis) AND attribute_exists(content)'
        )
        
        # Filter out URLs already in pending batches
        for item in response.get('Items', []):
            if item['url'] not in pending_urls:
                unanalyzed_items.append(item)
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = news_table.scan(
                FilterExpression='attribute_not_exists(analysis) AND attribute_exists(content)',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                if item['url'] not in pending_urls:
                    unanalyzed_items.append(item)
        
        print(f"Found {len(unanalyzed_items)} unanalyzed items (excluding {len(pending_urls)} in pending batches)")
        return unanalyzed_items
        
    except Exception as e:
        print(f"Error scanning for unanalyzed news: {str(e)}")
        raise


def submit_combined_batch(news_items):
    """
    Submit combined batch request to Gemini for all unanalyzed news items
    """
    client = get_gemini_client()
    
    # Create temporary JSONL file with all requests
    batch_timestamp = int(datetime.now().timestamp())
    file_path = f"/tmp/batch_{batch_timestamp}.jsonl"
    
    # Initialize URL order mapping
    url_order_mapping = []
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            for idx, item in enumerate(news_items):
                url = item['url']
                title = item['title']
                content = item['content']

                # 記錄此請求索引對應的 URL
                url_order_mapping.append({
                    'request_index': idx,
                    'url': url
                })
                
                # Generate prompt for this article
                prompt = generate_analysis_prompt(title, content)
                
                # Create request object for Batch API (one line per request)
                request_body = {
                    "custom_id": f"request_{idx}",  # 用於識別此請求
                    "request": {
                        "contents": [
                            {
                                "parts": [
                                    {"text": prompt}
                                ]
                            }
                        ],
                        "generationConfig": {
                            "thinking_config": {
                                "thinking_level": "MEDIUM"
                            },
                            "responseMimeType": "application/json",
                            "temperature": 0.7
                        }
                    }
                }
                
                # Write one line per request (JSONL format)
                f.write(json.dumps(request_body) + '\n')
        
        # Upload file to Gemini
        upload_file = client.files.upload(
            file=file_path,
            config={'mime_type': 'application/jsonl'}
        )
        
        # Create batch job
        batch_job = client.batches.create(
            # model='gemini-3-flash-preview',
            model='gemini-2.5-pro',
            src=upload_file.name
        )

        # Store batch ID with all URLs in DynamoDB
        created_at = batch_timestamp
        batch_table.put_item(Item={
            'batch_id': batch_job.name,
            'url': '__metadata__',  # 特殊標記
            'created_at': created_at,
            'status': 'PENDING',
            'metadata': url_order_mapping
        })
        
        print(f"Created combined batch job {batch_job.name} for {len(news_items)} articles")
        
    except Exception as e:
        print(f"Error submitting batch job: {str(e)}")
        raise
    finally:
        # Clean up temp file
        if os.path.exists(file_path):
            os.remove(file_path)


def generate_analysis_prompt(title, content):
    """
    Generate analysis prompt for a news article
    """
    categories_str = ', '.join(categories)
    
    return f"""
你是一位專業的經濟新聞分析師,專門分析新聞的內容對各產業的影響。
請以此新聞內容為唯一依據，進行以下產業分析:
1.直接影響產業: 新聞內容中提及的所有產業領域
2.間接影響產業: 根據新聞內容推論可能受到影響的相關產業領域

JSON 格式要求，請嚴格遵守，回應以下object in Json：
{{
    "importance_score": 0.6,  // 整體重要性評分 (0到1，0為非常不重要，1為非常重要)
    "market_sentiment": {{
        "score": 0.2,  // 情緒分數 (-1到1，-1為非常負面，1為非常正面)
        "volatility_trigger": false  // 是否可能引發市場劇烈波動 (true或false) 
    }},
    "sector_rotation": [
        {{
            "sector": "請務必從以下清單中選擇最合適的一個分類：{categories_str}",
            "sub_sector": "具體產業領域名稱(例如: CoWoS, 散熱模組, 生成式AI)",
            "trend": "資金流動的趨勢 (流入、流出、持平)",
            "keyword": "資金流動理由"
        }}
    ],
    "entities_mentioned": [
        {{
            "name": "公司或組織名稱",
            "id": "公司對應台股代碼或是美股代碼(如有)，請嚴謹核對公司與代碼的對應關係，若無對應代碼請填name",
            "sentiment_score": 0.3,  // 該實體在新聞中的情緒分數 (-1到1，-1為非常負面，1為非常正面)
            "event": "催化劑事件 (如有)",
            "role": "leader or laggard"  // 該實體在產業中的角色 (leader或laggard)
        }}
    ],
    "institutional_investor_behavior": {{
        "action": "買超 or 賣超",  // 三大法人在新聞中的操作行為
        "reason": "操作原因或背景說明",
        "target_sectors": [
            "請務必從以下清單中選擇最合適的一個分類：{categories_str}"
        ]
    }},
    "investment_themes": ["COWOS", "生成式AI"]  // 根據新聞內容提取的投資主題清單(sub-sectors)
}}

新聞標題: {title}
新聞內容: {content}
請嚴格按照上述 JSON 格式回應，不要包含任何額外的文字說明。
"""


if __name__ == "__main__":
    test_event = {}
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
