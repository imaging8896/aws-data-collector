import json
import os
import boto3
from openai import OpenAI

from parser.general import GeneralNewsHTMLParser
from request import request_get_news

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')  # type: ignore
table_name = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(table_name)  # type: ignore

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
    Lambda function handler for collecting news URLs
    
    Expected event format:
    {
        "source": "bbc|cnn|nyt|etc",  # Optional, default fetches from all sources
        "limit": 10  # Optional, number of articles to fetch
    }
    """
    try:
        url = event['url']

        response = table.get_item(Key={'url': url})
        if 'Item' not in response:
            raise ValueError(f"URL not found in DynamoDB: {url}")
        data = response['Item']

        try:
            news_content, actual_news_url = get_news_content(url, mobile=True, desktop=True)
        except Exception as content_error:
            raise ValueError(f"Failed to get news content: {str(content_error)}")
        
        if not news_content:
            raise ValueError(f"No news content retrieved from URL: {url}")

        data['content'] = ' '.join(news_content.split())
        
        # Analyze news with OpenAI
        try:
            analysis = analyze_news_with_openai(data.get('title', ''), news_content)
            data['analysis'] = analysis
            print(f"OpenAI analysis completed for URL: {actual_news_url}")
        except Exception as analysis_error:
            print(f"Warning: OpenAI analysis failed: {str(analysis_error)}")
            # Continue even if analysis fails

        if actual_news_url == url:
            table.put_item(Item=data)
        else:
            # URL has been redirected, need to update the primary key
            table.delete_item(Key={'url': url})
            data['url'] = actual_news_url
            table.put_item(Item=data)

        print(f"News content updated for URL: {actual_news_url}")
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'News content collected successfully',
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

def analyze_news_with_openai(title: str, content: str):
    """
    Analyze news content using OpenAI API
    
    Returns:
    {
        "industries": [
            {
                "domain": "產業領域名稱",
                "impact_score": -5 to 5,
                "reason": "影響原因說明"
            }
        ],
        "type": "政策|營收|技術|成本|其他",
        "genre": "新聞類型"
    }
    """
    client = get_openai_client()
    
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
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        response_format={
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
                                    "domain": { "type": "string" },
                                    "impact_score": { "type": "integer", "minimum": -5, "maximum": 5 },
                                    "reason": { "type": "string" }
                                },
                                "required": ["domain", "impact_score", "reason"],
                                "additionalProperties": False
                            }
                        },
                        "genre": { "type": "string" }
                    },
                    "required": ["industries", "genre"],
                    "additionalProperties": False
                }
            }
        }
    )
    
    analysis = json.loads(response.choices[0].message.content)
    return analysis


if __name__ == "__main__":
    import sys
    # For local testing
    test_event = {
        "url": sys.argv[1]
    }
    print(handler(test_event, None))
