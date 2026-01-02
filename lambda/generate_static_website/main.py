import json
import os
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
import boto3

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Environment variables
stats_table_name = os.environ['DYNAMODB_STATS_TABLE_NAME']
s3_bucket_name = os.environ['S3_CHART_BUCKET_NAME']
cloudfront_domain = os.environ['CLOUDFRONT_DOMAIN']

stats_table = dynamodb.Table(stats_table_name)  # type: ignore

def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def handler(event, context):
    """
    Generate static HTML page from news analysis charts in DynamoDB
    
    Event can be from:
    1. Direct invocation: {"date": "2025-12-31"}
    2. Lambda Destination: {"responsePayload": {"statusCode": 200, "body": "{...}"}}
    """
    try:
        # Handle Lambda Destination event format
        if 'responsePayload' in event:
            # Extract from Lambda Destination success event
            payload = event['responsePayload']
            if isinstance(payload, dict) and 'body' in payload:
                body = json.loads(payload['body']) if isinstance(payload['body'], str) else payload['body']
                request_date = body.get('date')
            else:
                request_date = payload.get('date')
        else:
            # Direct invocation
            request_date = event.get('date')
        
        if not request_date:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'date is required'
                })
            }
        
        # Retrieve stats data from DynamoDB
        response = stats_table.get_item(Key={'date': request_date})
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': f'Statistics data not found: {request_date}'
                })
            }
        
        item = response['Item']
        days = int(item['days'])
        
        # Get chart URLs (use CloudFront if available)
        chart_s3_bucket = item.get('chart_s3_bucket', None)
        if not chart_s3_bucket:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': f'No charts found: {request_date}'
                })
            }
        chart_s3_keys = item.get('chart_s3_keys', [])
        chart_urls = [
            f"https://{cloudfront_domain}/{key}" for key in chart_s3_keys
        ]
        
        # Get date range
        start_date = (date.fromisoformat(request_date) - timedelta(days=days - 1)).isoformat()
        end_date = request_date
        
        # Generate HTML
        html_content = generate_html(request_date, start_date, end_date, days, chart_urls)
        
        # Upload to S3
        html_key = f"charts/{request_date}.html"
        index_key = "index.html"
        
        try:
            # Upload specific trend HTML
            s3_client.put_object(
                Bucket=s3_bucket_name,
                Key=html_key,
                Body=html_content.encode('utf-8'),
                ContentType='text/html; charset=utf-8',
                CacheControl='max-age=3600',
                Metadata={
                    'date': request_date,
                    'generated_at': datetime.now().isoformat()
                }
            )
            
            # Upload index.html as the latest trend (same content)
            s3_client.put_object(
                Bucket=s3_bucket_name,
                Key=index_key,
                Body=html_content.encode('utf-8'),
                ContentType='text/html; charset=utf-8',
                CacheControl='max-age=300',  # Shorter cache for index (5 minutes)
                Metadata={
                    'date': request_date,
                    'generated_at': datetime.now().isoformat(),
                    'is_latest': 'true'
                }
            )
            
            # Use CloudFront URL if available
            if cloudfront_domain:
                html_url = f"https://{cloudfront_domain}/{html_key}"
                index_url = f"https://{cloudfront_domain}/"
            else:
                html_url = f"https://{s3_bucket_name}.s3.amazonaws.com/{html_key}"
                index_url = f"https://{s3_bucket_name}.s3.amazonaws.com/{index_key}"
            
            print(f"HTML page uploaded to S3: {html_url}")
            print(f"Latest trend available at: {index_url}")
            
        except Exception as e:
            print(f"Failed to upload HTML to S3: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Failed to upload HTML to S3',
                    'error': str(e)
                })
            }
        
        # Update DynamoDB with HTML URL
        stats_table.update_item(
            Key={'date': request_date},
            UpdateExpression='SET s3_html_url = :html, html_generated_at = :ts',
            ExpressionAttributeValues={
                ':html': html_url,
                ':ts': int(datetime.now(timezone.utc).timestamp())
            }
        )
        
        print(f"Static website generated for {request_date}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Static website generated successfully',
                'date': request_date,
                's3_html_url': html_url,
                'latest_url': index_url if cloudfront_domain else f"https://{s3_bucket_name}.s3.amazonaws.com/{index_key}"
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error generating static website',
                'error': str(e)
            })
        }


def generate_html(request_date, start_date, end_date, days, chart_urls):
    """
    Generate HTML page to display the investment analysis charts
    """
    # Chart titles mapping
    chart_titles = [
        "📊 產業資金輪動分析",
        "💰 資金建倉/撤離訊號",
        "📈 市場情緒趨勢",
        "🔥 關鍵字動能",
        "🎯 個股投資機會"
    ]
    
    # Build chart sections
    chart_sections = ""
    for i, chart_url in enumerate(chart_urls):
        title = chart_titles[i] if i < len(chart_titles) else f"圖表 {i+1}"
        chart_sections += f"""
        <div class="chart-container">
            <h2 class="chart-title">{title}</h2>
            <img src="{chart_url}" alt="{title}" onerror="this.onerror=null; this.src=''; this.alt='圖表載入失敗';">
        </div>
        """
    
    # Use UTC+8 timezone
    tz_utc8 = timezone(timedelta(hours=8))
    current_time_utc8 = datetime.now(tz_utc8)

    html_content = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>新聞投資分析 - {request_date}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans TC", sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #2E86AB 0%, #06D6A0 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.2s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #2E86AB;
            margin: 10px 0;
        }}
        .stat-card .label {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        .chart-container {{
            padding: 40px;
            text-align: center;
            border-bottom: 2px solid #f0f0f0;
        }}
        .chart-title {{
            color: #2E86AB;
            margin-bottom: 25px;
            font-size: 1.8em;
            font-weight: bold;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }}
        .chart-container img:hover {{
            transform: scale(1.02);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }}
        .footer {{
            background: #2c3e50;
            color: white;
            text-align: center;
            padding: 20px;
            font-size: 0.9em;
        }}
        @media (max-width: 768px) {{
            .header h1 {{
                font-size: 1.8em;
            }}
            .summary {{
                grid-template-columns: 1fr;
            }}
            .chart-container {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 新聞投資分析報告</h1>
            <p>{start_date} ~ {end_date} ({days} 天)</p>
        </div>
        
        <div class="summary">
            <div class="stat-card">
                <div class="label">分析日期</div>
                <div class="value" style="font-size: 1.5em;">{request_date}</div>
            </div>
            <div class="stat-card">
                <div class="label">分析天數</div>
                <div class="value">{days}</div>
            </div>
            <div class="stat-card">
                <div class="label">圖表數量</div>
                <div class="value">{len(chart_urls)}</div>
            </div>
        </div>
        
        {chart_sections}
        
        <div class="footer">
            <p>🚀 AWS Data Collector - News Investment Analysis | 生成時間: {current_time_utc8.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)</p>
        </div>
    </div>
</body>
</html>
"""
    return html_content

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <date>")
        print("Example: python main.py 2026-01-02")
        sys.exit(1)
    
    test_event = {
        "date": sys.argv[1]
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))