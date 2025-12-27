import json
import os

from datetime import datetime
from openai import OpenAI

import boto3
import curl_cffi

from parser.general import GeneralNewsHTMLParser
from request import request_get_news

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')  # type: ignore
news_table_name = os.environ['DYNAMODB_TABLE_NAME']
batch_table_name = os.environ['DYNAMODB_BATCH_TABLE_NAME']
news_table = dynamodb.Table(news_table_name)  # type: ignore
batch_table = dynamodb.Table(batch_table_name)  # type: ignore

# Initialize Secrets Manager client
secrets_client = boto3.client('secretsmanager')
openai_secret_name = os.environ['OPENAI_API_KEY_SECRET_NAME']

# Cache OpenAI client
_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        # Retrieve OpenAI API key from Secrets Manager
        secret_response = secrets_client.get_secret_value(SecretId=openai_secret_name)
        api_key = secret_response['SecretString']
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def handler(event, context):
    """
    Lambda function handler for collecting news content and creating batch analysis request
    
    Expected event format:
    {
        "url": "https://news-url.com/article"
    }
    """
    try:
        url = event['url']

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
            raise ValueError(f"Failed to get news content for {url}: RequestException") from e
        except Exception as content_error:
            # Leave it in the DB
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
        
        # Add to batch analysis queue
        submit_batch(actual_news_url, data['title'], news_content)
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'News content collected and queued for batch analysis',
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


def submit_batch(news_url: str, title: str, content: str):
    """
    Submit batch request to OpenAI
    """
    client = get_openai_client()
        
    # Create batch request file with JSONL format
    system = """
你是一位專業的經濟新聞分析師,專門分析新聞對各產業的影響，可能有一個新聞有多個產業的影響。請以繁體中文回應,並嚴格遵守 JSON 格式。
JSON 範例格式為
{
    "industries": [
        {
            "domain": "產業領域名稱，例如: 半導體、電動車、金融、零售等",
            "impact_score":  2, // Integer -5 to 5
            "reason": "影響原因說明"
        }
    ],
    "genre": "新聞體裁(例如:快訊、深度報導、分析評論、財報、公告等)"
}
"""
    prompt = f"""你是一位專業的經濟新聞分析師。請分析以下新聞內容:
標題: {title}
內容: {content}
"""
    
    custom_id = news_url
    request = {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "result_response",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "industries": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "domain": {"type": "string"},
                                        "impact_score": {"type": "integer", "minimum": -5, "maximum": 5},
                                        "reason": {"type": "string"}
                                    },
                                    "required": ["domain", "impact_score", "reason"],
                                    "additionalProperties": False
                                }
                            },
                            "genre": {"type": "string"}
                        },
                        "required": ["industries", "genre"],
                        "additionalProperties": False
                    }
                }
            }
        }
    }
    
    # Create JSONL content
    jsonl_content = json.dumps(request)
    
    # Upload batch input file
    batch_file = client.files.create(
        file=jsonl_content.encode('utf-8'),
        purpose='batch'
    )
    
    # Create batch
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )
    batch_table.put_item(Item={
        'batch_id': batch.id,
        'url': news_url,
        'created_at': int(datetime.now().timestamp()),
        'last_checked_at': int(datetime.now().timestamp())
    })
    print(f"Created new batch {batch.id}")


if __name__ == "__main__":
    import sys


    test_event = {
        "url": sys.argv[1]
    }
    print(handler(test_event, None))
