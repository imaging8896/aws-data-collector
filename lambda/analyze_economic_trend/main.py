import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from decimal import Decimal
import boto3

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
news_table_name = os.environ['DYNAMODB_TABLE_NAME']
trend_table_name = os.environ['DYNAMODB_TREND_TABLE_NAME']
news_table = dynamodb.Table(news_table_name)  # type: ignore
trend_table = dynamodb.Table(trend_table_name)  # type: ignore


def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def handler(event, context):
    """
    Analyze economic trend based on news analysis
    
    Expected event format:
    {
        "days": 7  # Number of days to analyze (default: 7)
    }
    
    Returns:
    {
        "trend_data": [
            {
                "date": "2025-12-27",
                "average_impact": 1.5,
                "total_news": 10,
                "positive_count": 6,
                "negative_count": 2,
                "neutral_count": 2,
                "industries": {
                    "半導體": {"average_impact": 2.3, "count": 3},
                    "電動車": {"average_impact": -1.5, "count": 2}
                }
            }
        ]
    }
    """
    try:
        # Get parameters
        days = event.get('days', 7)
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        start_timestamp = int(start_date.timestamp())
        
        # Scan DynamoDB for news with analysis
        daily_data = defaultdict(lambda: {
            'total_impact': 0,
            'count': 0,
            'positive': 0,
            'negative': 0,
            'neutral': 0,
            'industries': defaultdict(lambda: {'total_impact': 0, 'count': 0}),
            'news_items': []
        })
        
        # Scan DynamoDB table with filter for timestamp and analysis
        response = news_table.scan(
            FilterExpression='#ts > :start_ts AND attribute_exists(analysis)',
            ExpressionAttributeNames={'#ts': 'timestamp'},
            ExpressionAttributeValues={':start_ts': start_timestamp}
        )
        
        items = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = news_table.scan(
                FilterExpression='#ts > :start_ts AND attribute_exists(analysis)',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={':start_ts': start_timestamp},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        print(f"Found {len(items)} news items with analysis")
        
        # Process each news item
        for item in items:
            timestamp = int(item['timestamp'])
            date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            analysis = item.get('analysis', {})
            
            if not analysis or 'industries' not in analysis:
                continue
            
            industries = analysis.get('industries', [])
            
            # Calculate overall impact for this news
            if industries:
                news_impact = sum(ind.get('impact_score', 0) for ind in industries) / len(industries)
                
                daily_data[date]['total_impact'] += news_impact
                daily_data[date]['count'] += 1
                
                # Categorize impact
                if news_impact > 0.5:
                    daily_data[date]['positive'] += 1
                elif news_impact < -0.5:
                    daily_data[date]['negative'] += 1
                else:
                    daily_data[date]['neutral'] += 1
                
                # Process industry-specific impacts
                for industry in industries:
                    domain = industry.get('domain', 'Unknown')
                    impact = industry.get('impact_score', 0)
                    
                    daily_data[date]['industries'][domain]['total_impact'] += impact
                    daily_data[date]['industries'][domain]['count'] += 1
                
                # Store news summary
                daily_data[date]['news_items'].append({
                    'url': item.get('url', ''),
                    'title': item.get('title', ''),
                    'impact': Decimal(str(float(news_impact))),
                    'genre': analysis.get('genre', '')
                })
        
        # Generate trend data
        trend_data = []
        for date in sorted(daily_data.keys()):
            data = daily_data[date]
            
            if data['count'] == 0:
                continue
            
            # Calculate average impact
            avg_impact = data['total_impact'] / data['count']
            
            # Process industries
            industries_summary = {}
            for domain, ind_data in data['industries'].items():
                if ind_data['count'] > 0:
                    industries_summary[domain] = {
                        'average_impact': Decimal(str(round(ind_data['total_impact'] / ind_data['count'], 2))),
                        'count': ind_data['count']
                    }
            
            # Sort industries by average impact
            industries_summary = dict(sorted(
                industries_summary.items(),
                key=lambda x: x[1]['average_impact'],
                reverse=True
            ))
            
            trend_data.append({
                'date': date,
                'average_impact': Decimal(str(round(avg_impact, 2))),
                'total_news': data['count'],
                'positive_count': data['positive'],
                'negative_count': data['negative'],
                'neutral_count': data['neutral'],
                'industries': industries_summary,
                'top_news': sorted(data['news_items'], key=lambda x: abs(x['impact']), reverse=True)[:5]
            })
        
        # Calculate overall statistics
        if trend_data:
            overall_avg = sum(d['average_impact'] for d in trend_data) / len(trend_data)
            total_news = sum(d['total_news'] for d in trend_data)
            
            # Identify trending industries
            all_industries = defaultdict(lambda: {'total_impact': 0, 'count': 0})
            for day_data in trend_data:
                for domain, ind_data in day_data['industries'].items():
                    all_industries[domain]['total_impact'] += ind_data['average_impact'] * ind_data['count']
                    all_industries[domain]['count'] += ind_data['count']
            
            trending_industries = []
            for domain, ind_data in all_industries.items():
                if ind_data['count'] > 0:
                    trending_industries.append({
                        'domain': domain,
                        'average_impact': Decimal(str(round(ind_data['total_impact'] / ind_data['count'], 2))),
                        'mentions': ind_data['count']
                    })
            
            trending_industries = sorted(trending_industries, key=lambda x: abs(x['average_impact']), reverse=True)
            
            summary = {
                'period_start': trend_data[0]['date'],
                'period_end': trend_data[-1]['date'],
                'overall_average_impact': round(overall_avg, 2),
                'total_news_analyzed': total_news,
                'trending_industries': trending_industries[:10]
            }
        else:
            summary = {
                'message': 'No news with analysis found in the specified period'
            }
        
        # Save trend data to DynamoDB
        trend_id = None
        if trend_data:
            trend_id = save_trend_data(trend_data, summary, days)
        
        # Return trend_id for Lambda Destination to pass to chart generator
        return {
            'statusCode': 200,
            'body': json.dumps({
                'summary': summary,
                'trend_data': trend_data,
                'trend_id': trend_id
            }, default=decimal_default, ensure_ascii=False),
            'trend_id': trend_id  # Add trend_id at top level for Lambda Destination
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error analyzing economic trend',
                'error': str(e)
            })
        }


def save_trend_data(trend_data, summary, days):
    """
    Save trend data to DynamoDB for later chart generation
    """
    try:
        trend_id = f"trend-{days}d-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        trend_table.put_item(Item={
            'chart_id': trend_id,
            'created_at': int(datetime.now().timestamp()),
            'days': days,
            'period_start': summary.get('period_start'),
            'period_end': summary.get('period_end'),
            'overall_average_impact': Decimal(str(summary.get('overall_average_impact', 0))),
            'total_news_analyzed': summary.get('total_news_analyzed', 0),
            'summary': summary,
            'trend_data': trend_data,
            'chart_generated': False
        })
        
        print(f"Trend data saved to DynamoDB with ID: {trend_id}")
        return trend_id
        
    except Exception as e:
        print(f"Error saving trend data: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # For local testing
    test_event = {
        "days": 7
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
