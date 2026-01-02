import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import boto3

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
news_table_name = os.environ['DYNAMODB_TABLE_NAME']
stats_table_name = os.environ['DYNAMODB_STATS_TABLE_NAME']
news_table = dynamodb.Table(news_table_name)
stats_table = dynamodb.Table(stats_table_name)


def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def handler(event, context):
    """
    Aggregate daily statistics from news data
    Runs hourly to update current day statistics
    
    Expected event format:
    {
        "days": 2  # Number of days to aggregate (default: 2)
    }
    """
    try:
        days = event.get('days', 2)
        
        # Calculate date range
        today = datetime.now()
        end_date = datetime(year=today.year, month=today.month, day=today.day)
        start_date = end_date - timedelta(days=days)
        start_timestamp = int(start_date.timestamp()) - 1
        
        # Fetch news data with analysis
        response = news_table.scan(
            FilterExpression='#pt > :start_ts AND attribute_exists(analysis)',
            ExpressionAttributeNames={'#pt': 'publish_time'},
            ExpressionAttributeValues={':start_ts': start_timestamp}
        )
        
        items = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = news_table.scan(
                FilterExpression='#pt > :start_ts AND attribute_exists(analysis)',
                ExpressionAttributeNames={'#pt': 'publish_time'},
                ExpressionAttributeValues={':start_ts': start_timestamp},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        print(f"Found {len(items)} news items with analysis")
        
        # Aggregate data by date
        daily_stats = aggregate_by_date(items)
        
        # Save to DynamoDB
        saved_count = 0
        for date, stats in daily_stats.items():
            save_daily_stats(date, stats)
            saved_count += 1
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Daily statistics aggregated successfully',
                'days_processed': saved_count,
                'total_news': len(items)
            }, default=decimal_default)
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error aggregating daily statistics',
                'error': str(e)
            })
        }


def aggregate_by_date(items):
    """
    Aggregate news items into daily statistics
    """
    daily_stats = defaultdict(lambda: {
        'date': '',
        'total_news': 0,
        'sector_rotation': defaultdict(lambda: {'inflow': 0, 'outflow': 0, 'count': 0}),
        'institutional_behavior': defaultdict(lambda: {'buy': 0, 'sell': 0}),
        'sentiment': {'positive': 0, 'negative': 0, 'neutral': 0, 'scores': []},
        'keywords': [],
        'stocks': defaultdict(lambda: {'name': '', 'mentions': 0, 'sentiment': 0, 'events': []})
    })
    
    for item in items:
        publish_time = int(item['publish_time'])
        date = datetime.fromtimestamp(publish_time).strftime('%Y-%m-%d')
        analysis = item.get('analysis', {})
        
        if not analysis or 'sector_rotation' not in analysis:
            continue
        
        daily_stats[date]['date'] = date
        daily_stats[date]['total_news'] += 1
        
        # 1. Sector Rotation
        for rotation in analysis.get('sector_rotation', []):
            sector = rotation['sector']
            trend = rotation['trend'].lower()
            
            if '流入' in trend or 'inflow' in trend:
                daily_stats[date]['sector_rotation'][sector]['inflow'] += 1
            elif '流出' in trend or 'outflow' in trend:
                daily_stats[date]['sector_rotation'][sector]['outflow'] += 1
            elif '持平' in trend or 'neutral' in trend:
                daily_stats[date]['sector_rotation'][sector]['inflow'] = 0
                daily_stats[date]['sector_rotation'][sector]['outflow'] = 0
            else:
                raise ValueError(f"Unknown trend value: {trend}")
            
            daily_stats[date]['sector_rotation'][sector]['count'] += 1
        
        # 2. Institutional Investor Behavior
        inst_behavior = analysis.get('institutional_investor_behavior', {})
        if inst_behavior:
            action = inst_behavior.get('action', '').lower()
            for sector in inst_behavior.get('target_sectors', []):
                if '買' in action or 'buy' in action:
                    daily_stats[date]['institutional_behavior'][sector]['buy'] += 1
                elif '賣' in action or 'sell' in action:
                    daily_stats[date]['institutional_behavior'][sector]['sell'] += 1
        
        # 3. Market Sentiment
        market_sentiment = analysis.get('market_sentiment', {})
        if market_sentiment:
            mood = market_sentiment['overall_mood'].lower()
            score = float(market_sentiment['score'])
            
            daily_stats[date]['sentiment']['scores'].append(score)
            
            if '正面' in mood or 'positive' in mood:
                daily_stats[date]['sentiment']['positive'] += 1
            elif '負面' in mood or 'negative' in mood:
                daily_stats[date]['sentiment']['negative'] += 1
            else:
                daily_stats[date]['sentiment']['neutral'] += 1
        
        # 4. Investment Themes (Keywords)
        daily_stats[date]['keywords'].extend(analysis.get('investment_themes', []))
        
        # 5. Stock Opportunities
        for entity in analysis.get('entities_mentioned', []):
            stock_id = entity['id']
            stock_name = entity['name']
            sentiment_score = float(entity['sentiment_score'])
            event = entity['event']
            
            if stock_id:
                key = stock_id
                if "." in key:
                    key = key.split(".")[0]
                daily_stats[date]['stocks'][key]['name'] = stock_name
                daily_stats[date]['stocks'][key]['mentions'] += 1
                daily_stats[date]['stocks'][key]['sentiment'] += sentiment_score
                if event:
                    daily_stats[date]['stocks'][key]['events'].append(event)
    
    return daily_stats


def save_daily_stats(date, stats):
    """
    Save daily statistics to DynamoDB
    """
    try:
        # Convert nested defaultdict to regular dict for DynamoDB
        sector_rotation = {
            sector: {
                'inflow': Decimal(str(data['inflow'])),
                'outflow': Decimal(str(data['outflow'])),
                'count': Decimal(str(data['count']))
            }
            for sector, data in stats['sector_rotation'].items()
        }
        
        institutional_behavior = {
            sector: {
                'buy': Decimal(str(data['buy'])),
                'sell': Decimal(str(data['sell']))
            }
            for sector, data in stats['institutional_behavior'].items()
        }
        
        # Calculate average sentiment score
        sentiment_scores = stats['sentiment']['scores']
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        
        sentiment = {
            'positive': Decimal(str(stats['sentiment']['positive'])),
            'negative': Decimal(str(stats['sentiment']['negative'])),
            'neutral': Decimal(str(stats['sentiment']['neutral'])),
            'average_score': Decimal(str(round(avg_sentiment, 4)))
        }
        
        # Convert Counter to dict
        keywords = stats['keywords']
        
        # Convert stocks data
        stocks = {
            key: {
                'name': data['name'],
                'mentions': Decimal(str(data['mentions'])),
                'average_sentiment': Decimal(str(round(data['sentiment'] / data['mentions'], 4))) if data['mentions'] > 0 else Decimal('0'),
                'events': data['events'][:10]  # Keep top 10 events
            }
            for key, data in stats['stocks'].items()
        }
        
        # Put item to DynamoDB
        # Check if record exists
        existing = stats_table.get_item(Key={'date': date})
        
        if 'Item' in existing:
            # Update existing record
            stats_table.update_item(
            Key={'date': date},
            UpdateExpression='SET updated_at = :updated_at, total_news = :total_news, '
                     'sector_rotation = :sector_rotation, '
                     'institutional_behavior = :institutional_behavior, '
                     'sentiment = :sentiment, keywords = :keywords, stocks = :stocks',
            ExpressionAttributeValues={
                ':updated_at': int(datetime.now().timestamp()),
                ':total_news': Decimal(str(stats['total_news'])),
                ':sector_rotation': sector_rotation,
                ':institutional_behavior': institutional_behavior,
                ':sentiment': sentiment,
                ':keywords': keywords,
                ':stocks': stocks
            }
            )
        else:
            # Create new record
            stats_table.put_item(Item={
                'date': date,
                'updated_at': int(datetime.now().timestamp()),
                'total_news': Decimal(str(stats['total_news'])),
                'sector_rotation': sector_rotation,
                'institutional_behavior': institutional_behavior,
                'sentiment': sentiment,
                'keywords': keywords,
                'stocks': stocks
            })
        
        print(f"Saved statistics for {date}: {stats['total_news']} news items")
        
    except Exception as e:
        print(f"Error saving stats for {date}: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_event = {
        "days": 14
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
