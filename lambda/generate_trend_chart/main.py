import json
import os
from datetime import datetime
from decimal import Decimal
import base64
from io import BytesIO
import boto3

# Import matplotlib with non-interactive backend
import matplotlib
matplotlib.use('Agg')  # Must be before importing pyplot
import matplotlib.font_manager
import matplotlib.pyplot as plt

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
trend_table_name = os.environ['DYNAMODB_TREND_TABLE_NAME']
s3_bucket_name = os.environ['S3_CHART_BUCKET_NAME']

trend_table = dynamodb.Table(trend_table_name)  # type: ignore


def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def handler(event, context):
    """
    Generate chart from existing trend data in DynamoDB
    
    Event can be from:
    1. Direct invocation: {"trend_id": "trend-7d-20251227"}
    2. Lambda Destination: {"responsePayload": {"statusCode": 200, "trend_id": "..."}}
    """
    try:
        # Handle Lambda Destination event format
        if 'responsePayload' in event:
            # Extract from Lambda Destination success event
            payload = event['responsePayload']
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
        
        # Check if chart already exists
        if item.get('chart_generated') and item.get('s3_chart_url'):
            print(f"Chart already exists for {trend_id}: {item.get('s3_chart_url')}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Chart already exists',
                    'trend_id': trend_id,
                    'chart_generated': True,
                    's3_chart_url': item.get('s3_chart_url')
                })
            }
        
        # Generate chart and get PNG bytes
        chart_png_bytes = generate_chart(trend_data, summary, days)
        
        if not chart_png_bytes:
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Failed to generate chart'
                })
            }
        
        # Upload to S3
        s3_key = f"charts/{trend_id}.png"
        try:
            s3_client.put_object(
                Bucket=s3_bucket_name,
                Key=s3_key,
                Body=chart_png_bytes,
                ContentType='image/png',
                CacheControl='max-age=86400',  # Cache for 1 day
                Metadata={
                    'trend_id': trend_id,
                    'days': str(days),
                    'generated_at': datetime.now().isoformat()
                }
            )
            
            s3_url = f"s3://{s3_bucket_name}/{s3_key}"
            print(f"Chart uploaded to S3: {s3_url}")
            
        except Exception as e:
            print(f"Failed to upload to S3: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Failed to upload chart to S3',
                    'error': str(e)
                })
            }
        
        # Update DynamoDB with S3 reference
        trend_table.update_item(
            Key={'chart_id': trend_id},
            UpdateExpression='SET s3_chart_url = :url, s3_bucket = :bucket, s3_key = :key, chart_generated = :gen, chart_generated_at = :ts',
            ExpressionAttributeValues={
                ':url': s3_url,
                ':bucket': s3_bucket_name,
                ':key': s3_key,
                ':gen': True,
                ':ts': int(datetime.now().timestamp())
            }
        )
        
        print(f"Chart generated and saved for {trend_id}")
        
        # Lambda Destination will automatically trigger static website generator
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Chart generated successfully',
                'trend_id': trend_id,
                's3_chart_url': s3_url,
                'chart_size_bytes': len(chart_png_bytes)
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


def generate_chart(trend_data, summary, days):
    """
    Generate matplotlib charts and return as base64 string
    """
    try:        
        # Create figure with multiple subplots
        fig = plt.figure(figsize=(16, 12))
        
        # Extract data
        dates = [d['date'] for d in trend_data]
        impacts = [d['average_impact'] for d in trend_data]
        positive_counts = [d['positive_count'] for d in trend_data]
        negative_counts = [d['negative_count'] for d in trend_data]
        neutral_counts = [d['neutral_count'] for d in trend_data]
        
        # 1. Overall Impact Trend Line Chart
        ax1 = plt.subplot(3, 2, 1)
        ax1.plot(dates, impacts, marker='o', linewidth=2, markersize=8, color='#2E86AB')
        ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        ax1.fill_between(range(len(dates)), impacts, 0, alpha=0.3, color='#2E86AB')
        ax1.set_title('整體經濟影響趨勢', fontsize=14, fontweight='bold')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('平均影響分數')
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis='x', rotation=45)
        
        # 2. Sentiment Distribution Stacked Bar Chart
        ax2 = plt.subplot(3, 2, 2)
        x_pos = range(len(dates))
        ax2.bar(x_pos, positive_counts, label='正面', color='#06D6A0')
        ax2.bar(x_pos, neutral_counts, bottom=positive_counts, label='中性', color='#FFD166')
        bottom = [p + n for p, n in zip(positive_counts, neutral_counts)]
        ax2.bar(x_pos, negative_counts, bottom=bottom, label='負面', color='#EF476F')
        ax2.set_title('新聞情緒分布', fontsize=14, fontweight='bold')
        ax2.set_xlabel('日期')
        ax2.set_ylabel('新聞數量')
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(dates, rotation=45)
        ax2.legend()
        ax2.grid(True, alpha=0.3, axis='y')
        
        # 3. Top Industries Impact (Overall)
        ax3 = plt.subplot(3, 2, 3)
        top_industries = summary.get('trending_industries', [])[:10]
        if top_industries:
            industries = [ind['category'] for ind in top_industries]
            industry_impacts = [ind['average_impact'] for ind in top_industries]
            colors = ['#06D6A0' if x > 0 else '#EF476F' for x in industry_impacts]
            
            ax3.barh(industries, industry_impacts, color=colors)
            ax3.axvline(x=0, color='gray', linestyle='--', alpha=0.5)
            ax3.set_title('產業影響排行 (Top 10)', fontsize=14, fontweight='bold')
            ax3.set_xlabel('平均影響分數')
            ax3.grid(True, alpha=0.3, axis='x')
        
        # 4. Daily News Volume
        ax4 = plt.subplot(3, 2, 4)
        news_volumes = [d['total_news'] for d in trend_data]
        ax4.bar(dates, news_volumes, color='#118AB2', alpha=0.7)
        ax4.set_title('每日新聞數量', fontsize=14, fontweight='bold')
        ax4.set_xlabel('日期')
        ax4.set_ylabel('新聞數量')
        ax4.tick_params(axis='x', rotation=45)
        ax4.grid(True, alpha=0.3, axis='y')
        
        # 5. Industry Trend Heatmap (Top 5 industries over time)
        ax5 = plt.subplot(3, 2, 5)
        
        # Get top 5 industries overall
        top_5_industries = [ind['category'] for ind in summary.get('trending_industries', [])[:5]]
        
        if top_5_industries:
            # Create matrix for heatmap
            heatmap_data = []
            for industry in top_5_industries:
                industry_trend = []
                for day_data in trend_data:
                    day_industry = day_data['industries'].get(industry, {})
                    impact = 0
                    if day_industry.get("count", 0) > 0:
                        impact = day_industry["total_impact"] / day_industry["count"]

                    # Convert Decimal to float for matplotlib
                    industry_trend.append(float(impact) if isinstance(impact, Decimal) else impact)
                heatmap_data.append(industry_trend)
            
            im = ax5.imshow(heatmap_data, cmap='RdYlGn', aspect='auto', vmin=-5, vmax=5)
            ax5.set_yticks(range(len(top_5_industries)))
            ax5.set_yticklabels(top_5_industries)
            ax5.set_xticks(range(len(dates)))
            ax5.set_xticklabels(dates, rotation=45)
            ax5.set_title('產業影響熱圖 (Top 5)', fontsize=14, fontweight='bold')
            plt.colorbar(im, ax=ax5, label='影響分數')
        
        # 6. Summary Statistics
        ax6 = plt.subplot(3, 2, 6)
        ax6.axis('off')
        
        summary_text = f"""
        分析期間: {summary.get('period_start', 'N/A')} ~ {summary.get('period_end', 'N/A')}
        
        整體平均影響: {summary.get('overall_average_impact', 0):.2f}
        總新聞數: {summary.get('total_news_analyzed', 0)}
        分析天數: {days} 天
        
        最受影響產業 (Top 3):
        """
        
        for i, ind in enumerate(summary.get('trending_industries', [])[:3], 1):
            summary_text += f"\n{i}. {ind['category']}: {ind['average_impact']:.2f} ({ind['mentions']}則)"
        
        ax6.text(0.1, 0.5, summary_text, fontsize=12, verticalalignment='center',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax6.set_title('統計摘要', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # Convert to PNG bytes
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.read()
        plt.close()
        
        return png_bytes
        
    except Exception as e:
        print(f"Error generating chart: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


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
