import json
import os
import boto3

from parser.general import GeneralNewsHTMLParser
from request import request_get_news

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')  # type: ignore
table_name = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(table_name)  # type: ignore


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

        news_content, actual_news_url = get_news_content(url, mobile=True, desktop=True)

        data['content'] = news_content

        if actual_news_url == url:
            table.put_item(Item=data)
        else:
            # URL has been redirected, need to update the primary key
            table.delete_item(Key={'url': url})
            data['url'] = actual_news_url
            table.put_item(Item=data)
            
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
