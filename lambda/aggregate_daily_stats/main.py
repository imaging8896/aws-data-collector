import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict, Counter
import boto3
from google import genai
from google.genai import types

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

news_table_name = os.environ['DYNAMODB_TABLE_NAME']
stats_table_name = os.environ['DYNAMODB_STATS_TABLE_NAME']
gemini_secret_name = os.environ.get('GEMINI_API_KEY_SECRET_NAME')

news_table = dynamodb.Table(news_table_name)
stats_table = dynamodb.Table(stats_table_name)

# Initialize Gemini client (lazy loading)
_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None and gemini_secret_name:
        try:
            secret_response = secrets_client.get_secret_value(SecretId=gemini_secret_name)
            api_key = secret_response['SecretString']
            _gemini_client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"Failed to initialize Gemini client: {str(e)}")
    return _gemini_client


def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def refine_keywords_with_ai(keywords_list):
    """
    Use AI to consolidate and categorize similar keywords
    Returns refined list of keywords with counts
    """
    if not keywords_list or len(keywords_list) == 0:
        return []
    
    client = get_gemini_client()
    if not client:
        # Fallback to simple counter if AI not available
        counter = Counter(keywords_list)
        return [{'keyword': k, 'count': v, 'related': [k]} for k, v in counter.most_common()]
    
    try:
        # 1. 先在本地統計頻率
        counter = Counter(keywords_list)
        
        # 2. 只取頻率最高的 100 個關鍵字送給 AI (避免 Token 爆炸)
        # 剩下的低頻關鍵字通常對趨勢分析影響較小，可以直接忽略或歸類為其他
        top_keywords = [k for k, v in counter.most_common(100)]

        keywords_str = ', '.join(top_keywords)
        
        prompt = prompt = f"""分析以下投資關鍵字並整理成精煉的類別。

關鍵字列表:
{keywords_str}

請嚴格遵守以下規則:
1. 將相似的關鍵字合併 (例如: "AI", "人工智慧", "GenAI" -> "AI")
2. **最多只能產生 20 個主要類別**，請挑選最重要的。
3. 忽略無意義或過於空泛的詞彙。
4. origin_keywords 必須是輸入列表中的詞。

請嚴格以 JSON 格式回傳，格式如下:
{{
  "refined_keywords": [
    {{"keyword": "AI晶片", "origin_keywords": ["AI", "晶片", "GPU"]}},
    {{"keyword": "電動車", "origin_keywords": ["EV", "特斯拉"]}}
  ]
}}"""
        
        response = client.models.generate_content(
            model='gemini-2.0-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type='application/json' # 強制 JSON 模式
                # thinking_config=types.ThinkingConfig(
                #     include_thoughts=False,
                #     thinking_budget=2000, # 0 至 24576 or -1 for thinking until done
                # )
            )
        )
        
        # Extract JSON from response
        response_text = response.text.strip()
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1]
            response_text = response_text.rsplit('```', 1)[0]
        
        result = json.loads(response_text)
        refined_data = result.get('refined_keywords', [])

        # 3. 重新計算合併後的次數 (使用原始的 counter)
        final_result = []
        processed_keywords = set()

        for item in refined_data:
            # 計算這個類別的總次數 (加總所有 origin_keywords 的原始次數)
            total_count = sum(counter.get(k, 0) for k in item['origin_keywords'])
            
            # 記錄已處理的關鍵字
            for k in item['origin_keywords']:
                processed_keywords.add(k)

            final_result.append({
                'keyword': item['keyword'],
                'count': total_count,
                'related': list(set(item['origin_keywords']))
            })
        
        # 排序並只回傳前 20 名
        final_result.sort(key=lambda x: x['count'], reverse=True)
        
        print(f"AI refined top {len(top_keywords)} keywords into {len(final_result)} categories")
        return final_result[:20]
        
    except Exception as e:
        print(f"Error refining keywords with AI: {str(e)}")
        import traceback
        traceback.print_exc()
        # Fallback to simple counter
        counter = Counter(keywords_list)
        return [{'keyword': k, 'count': v} for k, v in counter.most_common(20)]


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
        latest_date = None
        for date, stats in daily_stats.items():
            save_daily_stats(date, stats)
            saved_count += 1
            if latest_date is None or date > latest_date:
                latest_date = date
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Daily statistics aggregated successfully',
                'days_processed': saved_count,
                'total_news': len(items),
                'date': latest_date  # Pass the latest date to chart generator
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
                if "-" in key:
                    key = key.split("-")[0]
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
        
        # Refine keywords using AI
        raw_keywords = stats['keywords']
        refined_keywords = refine_keywords_with_ai(raw_keywords)
        keywords = [x for x in refined_keywords if x['keyword'].lower() not in {"other", "其他"}]
        
        # Convert stocks data
        stocks = {
            data['name'] if key.lower() in {"null", "n/a"} or not key else key: {
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
