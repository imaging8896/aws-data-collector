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


def get_rsi_color(rsi_value):
    """Get color based on RSI value"""
    if rsi_value >= 70:
        return '#EF476F'  # Overbought - Red
    elif rsi_value >= 50:
        return '#06D6A0'  # Bullish - Green
    elif rsi_value >= 30:
        return '#FFD166'  # Neutral - Yellow
    else:
        return '#4ECDC4'  # Oversold - Cyan


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
        
        # Get RSI data
        rsi_data = item.get('RSI', {})
        
        # Get date range
        start_date = (date.fromisoformat(request_date) - timedelta(days=days - 1)).isoformat()
        end_date = request_date
        
        # Generate HTML
        html_content = generate_html(request_date, start_date, end_date, days, chart_urls, rsi_data)
        
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


def generate_html(request_date, start_date, end_date, days, chart_urls, rsi_data):
    """
    Generate HTML page to display the investment analysis charts and RSI signals
    """
    # Chart titles mapping
    chart_titles = [
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
    
    # Build RSI section
    rsi_section = ""
    if rsi_data:
        # Define display order for indexes
        priority_order = [
            '發行量加權股價',
            '臺灣50',
            '臺灣中型100',
            '小型股300',
            '臺灣高股息',
        ]
        
        # Sort indexes by priority
        sorted_indexes = []
        remaining_indexes = []
        
        for index_name in rsi_data.keys():
            if index_name in priority_order:
                sorted_indexes.append((priority_order.index(index_name), index_name))
            else:
                # Put indexes ending with "類" at the end
                if index_name.endswith('類'):
                    remaining_indexes.append((1, index_name))  # Category type, sort by name
                # else:
                #     remaining_indexes.append((0, index_name))  # Other types first
        
        # Sort priority indexes by their order
        sorted_indexes.sort(key=lambda x: x[0])
        # Sort remaining indexes by type then name
        remaining_indexes.sort(key=lambda x: (x[0], x[1]))
        
        # Combine the lists
        final_order = [name for _, name in sorted_indexes] + [name for _, name in remaining_indexes]
        
        rsi_cards = ""
        for index_name in final_order:
            index_rsi = rsi_data[index_name]
            # Get RSI values
            rsi_5 = float(index_rsi.get('RSI_5', 0))
            rsi_9 = float(index_rsi.get('RSI_9', 0))
            rsi_14 = float(index_rsi.get('RSI_14', 0))
            rsi_22 = float(index_rsi.get('RSI_22', 0))
            signals = index_rsi.get('signals', [])
            medium_strategy = index_rsi.get('medium_strategy', {})
            short_strategy = index_rsi.get('short_strategy', {})
            
            # Get MA values
            ma_5 = float(index_rsi.get('MA_5', 0))
            ma_20 = float(index_rsi.get('MA_20', 0))
            ma_60 = float(index_rsi.get('MA_60', 0))
            
            # Get medium strategy signals
            medium_buy = medium_strategy.get('buy_signal', False)
            medium_sell = medium_strategy.get('sell_signal', False)
            
            # Get short strategy signals
            short_buy = short_strategy.get('buy_signal', False)
            short_sell = short_strategy.get('sell_signal', False)
            
            # Determine overall status color
            if '多頭排列' in signals or '短線轉強' in signals:
                status_color = '#06D6A0'  # Green
                status_icon = '🟢'
            elif '空頭排列' in signals or '短線轉弱' in signals:
                status_color = '#EF476F'  # Red
                status_icon = '🔴'
            else:
                status_color = '#FFD166'  # Yellow
                status_icon = '🟡'
            
            # Build signal badges
            signal_badges = ""
            
            # Add medium-term strategy signal badges first
            if medium_buy:
                color = '#10B981'  # Emerald green
                signal_badges += f'<span class="signal-badge strategy-buy" style="background-color: {color}; font-weight: bold;">💰 中線買入</span>'
            if medium_sell:
                color = '#EF4444'  # Red
                signal_badges += f'<span class="signal-badge strategy-sell" style="background-color: {color}; font-weight: bold;">⚠️ 中線出場</span>'
            
            # Add short-term strategy signal badges
            if short_buy:
                color = '#059669'  # Dark green
                signal_badges += f'<span class="signal-badge strategy-buy" style="background-color: {color}; font-weight: bold;">⚡ 短線買入</span>'
            if short_sell:
                color = '#DC2626'  # Red
                signal_badges += f'<span class="signal-badge strategy-sell" style="background-color: {color}; font-weight: bold;">🚨 短線出場</span>'
            
            # Add technical signals
            for signal in signals:
                # Assign colors based on signal type
                if signal in ['多頭排列', '短線轉強', '強勢整理']:
                    badge_color = '#06D6A0'
                elif signal in ['空頭排列', '短線轉弱', '弱勢整理']:
                    badge_color = '#EF476F'
                elif signal in ['超買', '短線超買']:
                    badge_color = '#FF6B6B'
                elif signal in ['超賣', '短線超賣', '止跌']:
                    badge_color = '#4ECDC4'
                else:
                    badge_color = '#95A5A6'
                
                signal_badges += f'<span class="signal-badge" style="background-color: {badge_color};">{signal}</span>'
            
            rsi_cards += f"""
            <div class="rsi-card">
                <div class="rsi-header" style="border-left: 4px solid {status_color};">
                    <h3>{status_icon} {index_name}</h3>
                </div>
                <div class="rsi-values">
                    <div class="rsi-value">
                        <div class="rsi-label">RSI 5</div>
                        <div class="rsi-number" style="color: {get_rsi_color(rsi_5)};">{rsi_5:.2f}</div>
                    </div>
                    <div class="rsi-value">
                        <div class="rsi-label">RSI 9</div>
                        <div class="rsi-number" style="color: {get_rsi_color(rsi_9)};">{rsi_9:.2f}</div>
                    </div>
                    <div class="rsi-value">
                        <div class="rsi-label">RSI 14</div>
                        <div class="rsi-number" style="color: {get_rsi_color(rsi_14)};">{rsi_14:.2f}</div>
                    </div>
                    <div class="rsi-value">
                        <div class="rsi-label">RSI 22</div>
                        <div class="rsi-number" style="color: {get_rsi_color(rsi_22)};">{rsi_22:.2f}</div>
                    </div>
                </div>
                <div class="ma-values">
                    <div class="ma-value">
                        <div class="ma-label">MA 5</div>
                        <div class="ma-number">{ma_5:.2f}</div>
                    </div>
                    <div class="ma-value">
                        <div class="ma-label">MA 20</div>
                        <div class="ma-number">{ma_20:.2f}</div>
                    </div>
                    <div class="ma-value">
                        <div class="ma-label">MA 60</div>
                        <div class="ma-number">{ma_60:.2f}</div>
                    </div>
                </div>
                <div class="rsi-signals">
                    {signal_badges if signal_badges else '<span class="signal-badge" style="background-color: #95A5A6;">無明顯訊號</span>'}
                </div>
            </div>
            """
        
        rsi_section = f"""
        <div class="rsi-section">
            <h2 class="section-title">📊 指數 RSI 技術訊號</h2>
            <div class="rsi-grid">
                {rsi_cards}
            </div>
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
        .rsi-section {{
            padding: 40px;
            background: #f8f9fa;
        }}
        .section-title {{
            color: #2E86AB;
            font-size: 2em;
            text-align: center;
            margin-bottom: 30px;
            font-weight: bold;
        }}
        .rsi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        .rsi-card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .rsi-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }}
        .rsi-header {{
            padding: 20px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        }}
        .rsi-header h3 {{
            margin: 0;
            font-size: 1.3em;
            color: #2c3e50;
        }}
        .rsi-values {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            padding: 20px;
        }}
        .rsi-value {{
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .rsi-label {{
            font-size: 0.85em;
            color: #6c757d;
            margin-bottom: 5px;
        }}
        .rsi-number {{
            font-size: 1.8em;
            font-weight: bold;
        }}
        .ma-values {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            padding: 0 20px 15px;
        }}
        .ma-value {{
            text-align: center;
            padding: 8px;
            background: #e8f4f8;
            border-radius: 6px;
        }}
        .ma-label {{
            font-size: 0.8em;
            color: #6c757d;
            margin-bottom: 3px;
        }}
        .ma-number {{
            font-size: 1.2em;
            font-weight: 600;
            color: #2E86AB;
        }}
        .rsi-signals {{
            padding: 15px 20px 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .signal-badge {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            color: white;
            font-weight: 500;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
            .rsi-grid {{
                grid-template-columns: 1fr;
            }}
            .rsi-section {{
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
        
        {rsi_section}
        
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