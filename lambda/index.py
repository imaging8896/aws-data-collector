import json
import os
import boto3
from datetime import datetime
from open_news import google

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')  # type: ignore
table_name = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(table_name)  # type: ignore

category_tw_topic_finance_id = "CAAqJQgKIh9DQkFTRVFvSUwyMHZNREpmTjNRU0JYcG9MVlJYS0FBUAE"
category_tw_topic_business_id = "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JYcG9MVlJYR2dKVVZ5Z0FQAQ"

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
            stored_count = 0
            stored_ids = []
            for article in news_articles:
                article_id = article.url
                item = {
                    'id': article_id,
                    'title': article.title,
                    'story_url': article.story_url if article.story_url else None,
                    'publish_time': int(article.publish_time.timestamp()) if article.publish_time else None,
                    'timestamp': int(datetime.now().timestamp()),
                }
                
                # Put item in DynamoDB
                table.put_item(Item=item)
                stored_count += 1
                stored_ids.append(article_id)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'News URLs collected successfully',
                    'count': stored_count,
                    'article_ids': stored_ids
                })
            }
        else:
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
