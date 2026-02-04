import json
import os
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
import boto3

# Import matplotlib with non-interactive backend
import matplotlib
matplotlib.use('Agg')  # Must be before importing pyplot
import matplotlib.font_manager
import matplotlib.pyplot as plt

from chart_keyword_momentum import generate_keyword_momentum_chart
from chart_stock_opportunities import generate_stock_opportunities_chart

# Register custom font
font_path = os.getenv("NOTO_SERIF_TC_FONT_PATH", "NotoSerifTC-VF.ttf")
if os.path.exists(font_path):
    matplotlib.font_manager.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = 'Noto Serif TC'

plt.rcParams['axes.unicode_minus'] = False

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Environment variables
stats_table_name = os.environ['DYNAMODB_STATS_TABLE_NAME']
s3_bucket_name = os.environ['S3_CHART_BUCKET_NAME']

categories = os.environ['CATEGORIES'].split(',')

stats_table = dynamodb.Table(stats_table_name)  # type: ignore

def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def handler(event, context):
    """
    Generate chart from statistics in DynamoDB
    
    Event can be from:
    1. Direct invocation: {"days": 7}
    2. Lambda Destination: {"responsePayload": {"statusCode": 200, "body": "{...}"}}
    """
    try:
        # Handle Lambda Destination event format
        if 'responsePayload' in event:
            # Extract from Lambda Destination success event
            payload = event['responsePayload']
            if isinstance(payload, dict) and 'body' in payload:
                body = json.loads(payload['body']) if isinstance(payload['body'], str) else payload['body']
                days = body.get('days', 14)
            else:
                days = payload.get('days', 14)
        else:
            # Direct invocation
            days = int(event.get('days', 14))

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 1)
        start_date_str = start_date.date().strftime("%Y-%m-%d")
        
        # Fetch news data with analysis
        response = stats_table.scan(
            FilterExpression='#dt > :start_date_str',
            ExpressionAttributeNames={'#dt': 'date'},
            ExpressionAttributeValues={':start_date_str': start_date_str}
        )
        
        items = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = stats_table.scan(
                FilterExpression='#dt > :start_date_str',
                ExpressionAttributeNames={'#dt': 'date'},
                ExpressionAttributeValues={':start_date_str': start_date_str},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        print(f"Found {len(items)} statistics items")

        latest_date = max(date.fromisoformat(item['date']) for item in items)
        existing_keys = set()

        keywords_data = {}
        stock_opportunities_data = {}
        for item in items:
            statistics_date = date.fromisoformat(item['date'])

            if statistics_date == latest_date:
                existing_keys = list(item.get('chart_s3_keys', []))

            keywords_data[statistics_date] = item.get('keywords', [])
            stock_opportunities_data[statistics_date] = item.get('stocks', {})

        tz_utc8 = timezone(timedelta(hours=8))
        timestamp = int(datetime.now(tz_utc8).timestamp())
        
        # Delete old chart files to save S3 storage cost
        for old_key in existing_keys:
            try:
                s3_client.delete_object(Bucket=s3_bucket_name, Key=old_key)
                print(f"Deleted old chart: {old_key}")
            except Exception as e:
                print(f"Failed to delete old chart {old_key}: {str(e)}")
        
        existing_keys = []

        stats_table.update_item(
            Key={'date': latest_date.isoformat()},
            UpdateExpression='SET chart_s3_bucket = :bucket, days= :days, chart_s3_keys = :keys',
            ExpressionAttributeValues={':bucket': s3_bucket_name, ':days': days, ':keys': list(existing_keys)}
        )

        # 1. Generate keyword momentum chart
        keyword_momentum_chart_bytes = generate_keyword_momentum_chart(keywords_data)

        s3_key = f"charts/keyword-momentum/{latest_date.isoformat()}-{timestamp}.png"
        upload_chart_to_s3(keyword_momentum_chart_bytes, s3_bucket_name, s3_key, {
            'date': latest_date.isoformat(),
            'chart_type': 'keyword_momentum',
            'generated_at': datetime.now(tz_utc8).isoformat()
        })
        existing_keys.append(s3_key)

        stats_table.update_item(
            Key={'date': latest_date.isoformat()},
            UpdateExpression='SET keyword_momentum_chart_generated = :keyword_momentum_gen, keyword_momentum_chart_updated_at = :ts, chart_s3_keys = :keys',
            ExpressionAttributeValues={
            ':keyword_momentum_gen': True,
            ':ts': datetime.now(tz_utc8).isoformat(),
            ':keys': existing_keys
            }
        )
        
        # 2. Generate stock opportunities chart
        stock_opportunities_chart_bytes = generate_stock_opportunities_chart(stock_opportunities_data)

        s3_key = f"charts/stock-opportunities/{latest_date.isoformat()}-{timestamp}.png"
        upload_chart_to_s3(stock_opportunities_chart_bytes, s3_bucket_name, s3_key, {
            'date': latest_date.isoformat(),
            'chart_type': 'stock_opportunities',
            'generated_at': datetime.now(tz_utc8).isoformat()
        })
        existing_keys.append(s3_key)

        stats_table.update_item(
            Key={'date': latest_date.isoformat()},
            UpdateExpression='SET stock_opportunities_chart_generated = :stock_opportunities_gen, stock_opportunities_chart_updated_at = :ts, chart_s3_keys = :keys',
            ExpressionAttributeValues={
            ':stock_opportunities_gen': True,
            ':ts': datetime.now(tz_utc8).isoformat(),
            ':keys': existing_keys
            }
        )

        # Lambda Destination will automatically trigger static website generator
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Chart generated successfully',
                'date': latest_date.isoformat(),
                'days': days,
                's3_keys': list(existing_keys)
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error generating chart',
                'error': str(e)
            })
        }

def upload_chart_to_s3(chart_bytes, s3_bucket, s3_key, metadata):
    """
    Upload chart bytes to S3 and return the S3 URL
    """
    try:
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=chart_bytes,
            ContentType='image/png',
            CacheControl='max-age=86400',  # Cache for 1 day
            Metadata=metadata
        )
        
        s3_url = f"s3://{s3_bucket}/{s3_key}"
        print(f"Chart uploaded to S3: {s3_url}")
        return s3_url
        
    except Exception as e:
        print(f"Failed to upload chart to S3: {str(e)}")
        raise


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <days>")
        sys.exit(1)
    
    test_event = {
        "days": sys.argv[1]
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
