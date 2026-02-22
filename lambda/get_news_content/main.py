import json
import os
import traceback

import boto3
import curl_cffi
from parser.general import GeneralNewsHTMLParser
from request import request_get_news

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')  # type: ignore
news_table_name = os.environ['DYNAMODB_TABLE_NAME']
news_table = dynamodb.Table(news_table_name)  # type: ignore


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
