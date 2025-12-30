import json
import os
import boto3
from datetime import datetime
from open_news import google

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')  # type: ignore
sqs_client = boto3.client('sqs')

# Environment variables
table_name = os.environ['DYNAMODB_TABLE_NAME']
sqs_queue_url = os.environ['SQS_QUEUE_URL']

table = dynamodb.Table(table_name)  # type: ignore

category_tw_topic_finance_id = "CAAqJQgKIh9DQkFTRVFvSUwyMHZNREpmTjNRU0JYcG9MVlJYS0FBUAE"
category_tw_topic_business_id = "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JYcG9MVlJYR2dKVVZ5Z0FQAQ"

VALID_SOURCE_DOMAINS = {
    # "www.upmedia.mg", # Verified can't get news content e.g. https://www.upmedia.mg/tw/lifestyle/food/247791
    # "tw.stock.yahoo.com", # Worked but need review
    # "tw.news.yahoo.com", # Worked but need review
    # "www.gvm.com.tw", # 遠見雜誌
    # "wantrich.chinatimes.com", # 中時旺得富
    # "www.chinatimes.com", # 中時新聞網
    # "www.cmoney.tw",
    # "www.storm.mg", # 風傳媒
    # "vip.udn.com", # 聯合新聞網 VIP 會員專區
    # https://news.pts.org.tw/video/15379 # 公視新聞
    # "money.udn.com", # 經濟日報 但沒有 article tag, house.udn.com
    # "news.ustv.com.tw", 非凡
    "finance.ettoday.net", # speed.ettoday.net, ai.ettoday.net, house.ettoday.net
    "news.cnyes.com", # hao.cnyes.com
    "www.moneydj.com", 
    "www.ctee.com.tw",
}


def handler(event, context):
    """
    Lambda function handler for collecting news URLs
    
    Expected event format:
    {
        "category_id": "xxxx",
        "category": "topics"  # Optional, topics, articles or stories
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
                and (_get_domain(x.url) != "finance.ettoday.net" or _get_first_path(x.url).lower() == "amp") # https://finance.ettoday.net/news/3089355 這種不符合格式
            ]
                
            stored_count = 0
            stored_urls = []
            for article in news_articles:
                now = datetime.now()
                item = {
                    'url': article.url,  # URL as primary key
                    'title': article.title,
                    'story_url': article.story_url if article.story_url else None,
                    'publish_time': int(article.publish_time.timestamp()) if article.publish_time else int(now.timestamp()),
                    'timestamp': int(now.timestamp()),
                }

                if _get_domain(article.url) == "www.ctee.com.tw" and "一分鐘強弱勢股" in article.title:
                    continue
                
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
                
                # Send message to SQS queue for content collection
                try:
                    sqs_client.send_message(
                        QueueUrl=sqs_queue_url,
                        MessageBody=json.dumps({'url': article.url}),
                        MessageAttributes={
                            'url': {
                                'StringValue': article.url,
                                'DataType': 'String'
                            },
                            'title': {
                                'StringValue': article.title,
                                'DataType': 'String'
                            }
                        }
                    )
                    print(f"Queued content collection for: {article.url}")
                except Exception as sqs_error:
                    print(f"Error queueing content collection for {article.url}: {str(sqs_error)}")
            
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
