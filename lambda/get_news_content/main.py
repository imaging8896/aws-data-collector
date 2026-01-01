import json
import os
import traceback

from datetime import datetime
from google import genai
from google.genai import types

import boto3
import curl_cffi

from parser.general import GeneralNewsHTMLParser
from request import request_get_news

categories = [
    "半導體與晶片", "AI與伺服器", "電子零組件與散熱", "電動車與車用電子", 
    "網通與光通訊", "機器人與自動化", "金融", "消費性電子", 
    "能源與重電", "房地產與營建", "生技醫療", "航運與物流", 
    "原物料與鋼鐵", "其他"
]

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')  # type: ignore
news_table_name = os.environ['DYNAMODB_TABLE_NAME']
batch_table_name = os.environ['DYNAMODB_BATCH_TABLE_NAME']
news_table = dynamodb.Table(news_table_name)  # type: ignore
batch_table = dynamodb.Table(batch_table_name)  # type: ignore

# Initialize Secrets Manager client
secrets_client = boto3.client('secretsmanager')
gemini_secret_name = os.environ['GEMINI_API_KEY_SECRET_NAME']

# Cache Gemini client
_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        # Retrieve Gemini API key from Secrets Manager
        secret_response = secrets_client.get_secret_value(SecretId=gemini_secret_name)
        api_key = secret_response['SecretString']
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def handler(event, context):
    """
    Lambda function handler for collecting news content and creating batch analysis request
    
    Expected event format:
    1. Direct invocation: {"url": "https://news-url.com/article"}
    2. SQS event: {"Records": [{"body": "{\"url\": \"...\"}"}]}
    """
    try:
        # Handle SQS event format
        if 'Records' in event:
            # Process SQS messages
            batch_item_failures = []
            
            for record in event['Records']:
                try:
                    # Parse message body
                    message_body = json.loads(record['body'])
                    url = message_body['url']
                    
                    # Process the URL
                    process_news_url(url)
                    
                except Exception as e:
                    print(f"Error processing SQS message: {str(e)}")
                    # Report failure for retry
                    batch_item_failures.append({
                        "itemIdentifier": record['messageId']
                    })
            
            # Return batch item failures for SQS to retry
            return {
                'batchItemFailures': batch_item_failures
            }
        else:
            # Direct invocation
            url = event['url']
            result = process_news_url(url)
            return result
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error collecting news content',
                'error': str(e)
            })
        }


def process_news_url(url):
    """
    Process a single news URL: fetch content and create batch analysis request
    """
    try:

        response = news_table.get_item(Key={'url': url})
        if 'Item' not in response:
            raise ValueError(f"URL not found in DynamoDB: {url}")
        data = response['Item']

        try:
            news_content, actual_news_url = get_news_content(url, mobile=True, desktop=True)
        except curl_cffi.exceptions.RequestException as e:
            if e.response is not None and e.response.status_code == 404:
                news_table.delete_item(Key={'url': url})
                print(f"Deleted URL due to 404 Not Found: {url}")
                return
            # Leave it in the DB
            traceback.print_exc()
            raise ValueError(f"Failed to get news content for {url}: {e}")
        except Exception as content_error:
            # Leave it in the DB
            traceback.print_exc()
            raise ValueError(f"Failed to get news content for {url}: {str(content_error)}")
        
        if not news_content:
            # Leave it in the DB
            raise ValueError(f"No news content retrieved from URL: {url}")

        data['content'] = ' '.join(news_content.split())
        
        # Update content in DynamoDB first
        if actual_news_url == url:
            news_table.put_item(Item=data)
        else:
            # URL has been redirected, need to update the primary key
            news_table.delete_item(Key={'url': url})
            data['url'] = actual_news_url
            news_table.put_item(Item=data)

        print(f"News content updated for URL: {actual_news_url}")
        
        # Submit batch job to Gemini
        submit_gemini_batch(actual_news_url, data['title'], news_content)
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'News content collected and batch job submitted',
                'url': actual_news_url
            })
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Failed to get news content from {event}',
                'error': str(e)
            })
        }


def get_news_content(url: str, mobile: bool = True, desktop: bool = True):
    raw_content, news_url = request_get_news(url, mobile=mobile, desktop=desktop)

    parser = GeneralNewsHTMLParser()

    parser.feed(raw_content)

    if not parser.has_content_section:
        raise ValueError(f"No content section(<p>) found in the news article(<article>) of url: {url}")

    return parser.content, news_url


def submit_gemini_batch(news_url: str, title: str, content: str):
    """
    Submit batch request to Gemini
    """
    client = get_gemini_client()
    
    prompt = f"""
你是一位專業的經濟新聞分析師,專門分析新聞的內容對各產業的影響。
請以此新聞內容為唯一依據，進行以下產業分析:
1.直接影響產業: 新聞內容中提及的所有產業領域
2.間接影響產業: 根據新聞內容推論可能受到影響的相關產業領域

JSON 格式要求：
{{
    "industries": [
        {{
            "domain": "具體產業領域名稱(例如: CoWoS, 散熱模組, 生成式AI)",
            "category": "請務必從以下清單中選擇最合適的一個分類：{', '.join(categories)}",
            "impact_score": 2,  // 對該產業的影響評分 (-5 到 5，-5為非常負面，5為非常正面)
            "reason": "影響原因和評分理由"
        }}
    ],
    "type": "新聞類型 (例如: 政策、營收、技術、成本、併購、市場趨勢等)",
    "genre": "新聞體裁(例如: 報導、評論、公告等)",
    "summary": "簡短摘要 (50字以內)"
}}

新聞標題: {title}
新聞內容: {content}

請嚴格按照上述 JSON 格式回應，不要包含任何額外的文字說明。
"""
    
    # Create request object for Batch API
    # The format for Gemini Batch API input file (JSONL)
    request_body = {
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
                    "thinking_level": "HIGH" # MEDIUM, LOW
                },
                "responseMimeType": "application/json",
                "temperature": 0.7
            }
        }
    }
    
    # Create temporary JSONL file
    file_path = f"/tmp/{os.path.basename(news_url)}.jsonl"
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(request_body) + '\n')
        
    try:
        # Upload file to Gemini
        # Note: client.files.upload takes 'file' argument which is the path
        upload_file = client.files.upload(
            file=file_path,
            config={'mime_type': 'application/jsonl'}
        )
        
        # Create batch job
        # model should be the model name
        batch_job = client.batches.create(
            model='gemini-3-flash-preview',
            src=upload_file.name
        )
        
        # Store batch ID in DynamoDB
        batch_table.put_item(Item={
            'batch_id': batch_job.name,
            'url': news_url,
            'created_at': int(datetime.now().timestamp()),
            'status': 'PENDING'
        })
        
        print(f"Created Gemini batch job: {batch_job.name}")
        
    except Exception as e:
        print(f"Error submitting batch job: {e}")
        raise
    finally:
        # Clean up temp file
        if os.path.exists(file_path):
            os.remove(file_path)