import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import boto3

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Environment variables
trend_table_name = os.environ['DYNAMODB_TREND_TABLE_NAME']
s3_bucket_name = os.environ['S3_CHART_BUCKET_NAME']
cloudfront_domain = os.environ.get('CLOUDFRONT_DOMAIN', '')

trend_table = dynamodb.Table(trend_table_name)  # type: ignore


def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def handler(event, context):
    """
    Generate static HTML page from trend data in DynamoDB
    
    Event can be from:
    1. Direct invocation: {"trend_id": "trend-7d-20251227"}
    2. Lambda Destination: {"responsePayload": {"statusCode": 200, "body": "{...}"}}
    """
    try:
        # Handle Lambda Destination event format
        if 'responsePayload' in event:
            # Extract from Lambda Destination success event
            payload = event['responsePayload']
            if isinstance(payload, dict) and 'body' in payload:
                body = json.loads(payload['body']) if isinstance(payload['body'], str) else payload['body']
                trend_id = body.get('trend_id')
            else:
                trend_id = payload.get('trend_id')
        else:
            # Direct invocation
            trend_id = event.get('trend_id')
        
        if not trend_id:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'trend_id is required'
                })
            }
        
        # Retrieve trend data from DynamoDB
        response = trend_table.get_item(Key={'chart_id': trend_id})
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': f'Trend data not found: {trend_id}'
                })
            }
        
        item = response['Item']
        trend_data = item.get('trend_data', [])
        summary = item.get('summary', {})
        days = int(item.get('days', 7))
        
        # Get chart URL (use CloudFront if available)
        s3_chart_url = item.get('s3_chart_url', '')
        s3_bucket = item.get('s3_bucket', s3_bucket_name)
        s3_key = item.get('s3_key', f'charts/{trend_id}.png')
        
        # Use CloudFront URL for better performance and security
        if cloudfront_domain:
            chart_url = f"https://{cloudfront_domain}/{s3_key}"
        elif s3_chart_url.startswith('s3://'):
            chart_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_key}"
        else:
            chart_url = s3_chart_url
        
        # Generate HTML
        html_content = generate_html(trend_id, trend_data, summary, days, chart_url)
        
        # Upload to S3
        html_key = f"charts/{trend_id}.html"
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
                    'trend_id': trend_id,
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
                    'trend_id': trend_id,
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
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Failed to upload HTML to S3',
                    'error': str(e)
                })
            }
        
        # Update DynamoDB with HTML URL
        trend_table.update_item(
            Key={'chart_id': trend_id},
            UpdateExpression='SET s3_html_url = :html, html_generated_at = :ts',
            ExpressionAttributeValues={
                ':html': html_url,
                ':ts': int(datetime.now().timestamp())
            }
        )
        
        print(f"Static website generated for {trend_id}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Static website generated successfully',
                'trend_id': trend_id,
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


def generate_html(trend_id, trend_data, summary, days, chart_url):
    """
    Generate HTML page to display the chart and summary
    """
    # Extract summary statistics
    period_start = summary.get('period_start', 'N/A')
    period_end = summary.get('period_end', 'N/A')
    overall_avg = summary.get('overall_average_impact', 0)
    total_news = summary.get('total_news_analyzed', 0)
    trending_industries = summary.get('trending_industries', [])[:10]
    
    # Build industry table rows
    industry_rows = ""
    for i, ind in enumerate(trending_industries, 1):
        category = ind.get('category', 'N/A')
        avg_impact = ind.get('average_impact', 0)
        mentions = ind.get('mentions', 0)
        impact_class = 'positive' if avg_impact > 0 else 'negative' if avg_impact < 0 else 'neutral'
        industry_rows += f"""
        <tr>
            <td>{i}</td>
            <td>{category}</td>
            <td class="{impact_class}">{avg_impact:.2f}</td>
            <td>{mentions}</td>
        </tr>
        """
    
    # Build daily trend table rows
    daily_rows = ""
    for day in trend_data:
        date = day.get('date', 'N/A')
        avg_impact = day.get('average_impact', 0)
        total = day.get('total_news', 0)
        positive = day.get('positive_count', 0)
        negative = day.get('negative_count', 0)
        neutral = day.get('neutral_count', 0)
        impact_class = 'positive' if avg_impact > 0 else 'negative' if avg_impact < 0 else 'neutral'
        
        daily_rows += f"""
        <tr>
            <td>{date}</td>
            <td class="{impact_class}">{avg_impact:.2f}</td>
            <td>{total}</td>
            <td class="positive">{positive}</td>
            <td class="neutral">{neutral}</td>
            <td class="negative">{negative}</td>
        </tr>
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
    <title>經濟趨勢分析 - {trend_id}</title>
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
            max-width: 1400px;
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
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        }}
        .data-section {{
            padding: 40px;
        }}
        .data-section h2 {{
            color: #2E86AB;
            margin-bottom: 20px;
            font-size: 1.8em;
            border-bottom: 3px solid #06D6A0;
            padding-bottom: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
        }}
        th {{
            background: #2E86AB;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #e9ecef;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .positive {{
            color: #06D6A0;
            font-weight: bold;
        }}
        .negative {{
            color: #EF476F;
            font-weight: bold;
        }}
        .neutral {{
            color: #FFD166;
            font-weight: bold;
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
            .data-section {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 經濟趨勢分析報告</h1>
            <p>{period_start} ~ {period_end} ({days} 天)</p>
        </div>
        
        <div class="summary">
            <div class="stat-card">
                <div class="label">整體平均影響</div>
                <div class="value {('positive' if overall_avg > 0 else 'negative' if overall_avg < 0 else 'neutral')}">{overall_avg:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="label">總新聞數</div>
                <div class="value">{total_news}</div>
            </div>
            <div class="stat-card">
                <div class="label">分析天數</div>
                <div class="value">{days}</div>
            </div>
            <div class="stat-card">
                <div class="label">受影響產業</div>
                <div class="value">{len(trending_industries)}</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h2 style="color: #2E86AB; margin-bottom: 20px;">📊 視覺化分析</h2>
            <img src="{chart_url}" alt="經濟趨勢圖表" onerror="this.onerror=null; this.src=''; this.alt='圖表載入失敗';">
        </div>
        
        <div class="data-section">
            <h2>🏭 產業影響排行 (Top 10)</h2>
            <table>
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>產業</th>
                        <th>平均影響</th>
                        <th>相關新聞數</th>
                    </tr>
                </thead>
                <tbody>
                    {industry_rows}
                </tbody>
            </table>
        </div>
        
        <div class="data-section">
            <h2>📅 每日趨勢詳情</h2>
            <table>
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>平均影響</th>
                        <th>總新聞</th>
                        <th>正面</th>
                        <th>中性</th>
                        <th>負面</th>
                    </tr>
                </thead>
                <tbody>
                    {daily_rows}
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>🚀 AWS Data Collector | 生成時間: {current_time_utc8.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8) | Trend ID: {trend_id}</p>
        </div>
    </div>
</body>
</html>
    """
    
    return html_content


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <trend_id>")
        sys.exit(1)
    
    test_event = {
        "trend_id": sys.argv[1]
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
