import json
import os
import boto3
from datetime import datetime
from open_news import google

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')  # type: ignore
table_name = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(table_name)  # type: ignore

# Initialize Lambda client for invoking content collector
lambda_client = boto3.client('lambda')
content_collector_function = os.environ['CONTENT_COLLECTOR_LAMBDA']

category_tw_topic_finance_id = "CAAqJQgKIh9DQkFTRVFvSUwyMHZNREpmTjNRU0JYcG9MVlJYS0FBUAE"
category_tw_topic_business_id = "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JYcG9MVlJYR2dKVVZ5Z0FQAQ"

VALID_SOURCE_DOMAINS = {
    # "www.upmedia.mg", # Verified can't get news content e.g. https://www.upmedia.mg/tw/lifestyle/food/247791
    "www.moneydj.com", 
    "www.ctee.com.tw",
}


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
        # Get parameters from event
        category = google.Category(event.get('category', google.Category.TOPICS)) # topics, articles or stories
        category_id = event.get('category_id', category_tw_topic_finance_id)
        location = google.Location(event.get('location', google.Location.Taiwan))
        section_id = event.get('section_id', None)

        if news_articles := google.get_news(category, category_id, location, section_id):
            news_articles = [
                x for x in news_articles 
                if _get_domain(x.url) in VALID_SOURCE_DOMAINS 
                and (_get_domain(x.url) != "www.moneydj.com" or _get_first_path(x.url).lower() == "kmdj") # There is 'funddj' 基金網，我們不取用
            ]
                
            stored_count = 0
            stored_urls = []
            for article in news_articles:
                item = {
                    'url': article.url,  # URL as primary key
                    'title': article.title,
                    'story_url': article.story_url if article.story_url else None,
                    'publish_time': int(article.publish_time.timestamp()) if article.publish_time else None,
                    'timestamp': int(datetime.now().timestamp()),
                }
                
                # Put item in DynamoDB
                # Check if URL already exists in DynamoDB
                try:
                    response = table.get_item(Key={'url': article.url})
                    if 'Item' in response:
                        # URL already exists, skip it
                        continue
                except Exception as get_error:
                    print(f"Error checking item: {str(get_error)}")
                
                # Put item only if it doesn't exist
                table.put_item(Item=item)
                stored_count += 1
                stored_urls.append(article.url)
                
                # Trigger content collector Lambda for this URL
                try:
                    lambda_client.invoke(
                        FunctionName=content_collector_function,
                        InvocationType='Event',  # Async invocation
                        Payload=json.dumps({'url': article.url})
                    )
                    print(f"Triggered content collection for: {article.url}")
                except Exception as invoke_error:
                    print(f"Error invoking content collector for {article.url}: {str(invoke_error)}")
            
            print(f"Stored {stored_count} new URLs: {stored_urls}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'News URLs collected successfully',
                    'count': stored_count,
                    'urls': stored_urls
                })
            }
        else:
            print("No news articles found")
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': 'No news articles found'
                })
            }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error collecting news',
                'error': str(e)
            })
        }


def _get_domain(url: str) -> str:
    return url.split("/")[2]


def _get_first_path(url: str) -> str:
    return url.split("/")[3]
