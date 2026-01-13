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
index_data_table_name = os.environ['DYNAMODB_INDEX_TABLE_NAME']
gemini_secret_name = os.environ.get('GEMINI_API_KEY_SECRET_NAME')

news_table = dynamodb.Table(news_table_name) # type: ignore
stats_table = dynamodb.Table(stats_table_name) # type: ignore
index_data_table = dynamodb.Table(index_data_table_name) # type: ignore

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


def calculate_rsi(prices, period=14):
    """
    Calculate RSI (Relative Strength Index) for given prices
    prices: list of Decimal values (newest to oldest)
    period: RSI period (default 14)
    Returns: RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None
    
    # Convert to float for calculation
    prices = [float(p) for p in prices]
    
    # Calculate price changes
    deltas = [prices[i] - prices[i + 1] for i in range(len(prices) - 1)]
    
    # Separate gains and losses
    gains = [d if d > 0 else 0 for d in deltas[:period]]
    losses = [-d if d < 0 else 0 for d in deltas[:period]]
    
    # Calculate average gain and loss
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def get_index_rsi_for_date(date_str, periods=[5, 9, 14, 22]):
    """
    Calculate RSI for all indexes on a specific date
    Returns dict: {index_name: {period: rsi_value}}
    """
    if not index_data_table:
        print("Index data table not configured")
        return {}
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        rsi_results = {}
        
        # Get all unique index names
        # Query by date to get all indexes for that date
        response = index_data_table.query(
            IndexName='DateIndex',
            KeyConditionExpression='#date = :date',
            ExpressionAttributeNames={'#date': 'date'},
            ExpressionAttributeValues={':date': date_str}
        )
        
        index_names = [item['name'] for item in response.get('Items', [])]
        
        # Calculate RSI for each index
        max_period = max(periods)
        for index_name in index_names:
            # Get historical data for this index (need max_period + 1 days)
            historical_prices = []
            
            # Query backwards from target date
            for days_back in range(max_period + 1):
                query_date = (target_date - timedelta(days=days_back)).strftime('%Y-%m-%d')
                
                try:
                    item_response = index_data_table.get_item(
                        Key={
                            'name': index_name,
                            'date': query_date
                        }
                    )
                    
                    if 'Item' in item_response and 'value' in item_response['Item']:
                        historical_prices.append(item_response['Item']['value'])
                except Exception as e:
                    print(f"Error getting data for {index_name} on {query_date}: {e}")
                    continue
            
            # Calculate RSI for each period
            if len(historical_prices) > 0:
                rsi_results[index_name] = {}
                for period in periods:
                    rsi_value = calculate_rsi(historical_prices, period)
                    if rsi_value is not None:
                        rsi_results[index_name][f'RSI_{period}'] = Decimal(str(rsi_value))
        
        print(f"Calculated RSI for {len(rsi_results)} indexes on {date_str}")
        return rsi_results
        
    except Exception as e:
        print(f"Error calculating RSI for date {date_str}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


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
        if inst_behavior and inst_behavior.get('action'):
            action = inst_behavior['action'].lower()
            for sector in inst_behavior.get('target_sectors', []):
                if '買' in action or 'buy' in action:
                    daily_stats[date]['institutional_behavior'][sector]['buy'] += 1
                elif '賣' in action or 'sell' in action:
                    daily_stats[date]['institutional_behavior'][sector]['sell'] += 1
        
        # 3. Market Sentiment
        market_sentiment = analysis.get('market_sentiment', {})
        if market_sentiment:
            score = float(market_sentiment['score'])
            daily_stats[date]['sentiment']['scores'].append(score)
            
            # Determine mood based on score (-1 to 1)
            if score > 0.2:
                daily_stats[date]['sentiment']['positive'] += 1
            elif score < -0.2:
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
        
        # Calculate RSI for all indexes
        rsi_data = get_index_rsi_for_date(date)
        
        if 'Item' in existing:
            # Update existing record with RSI
            update_expr = 'SET updated_at = :updated_at, total_news = :total_news, ' \
                         'sector_rotation = :sector_rotation, ' \
                         'institutional_behavior = :institutional_behavior, ' \
                         'sentiment = :sentiment, keywords = :keywords, stocks = :stocks'
            attr_values = {
                ':updated_at': int(datetime.now().timestamp()),
                ':total_news': Decimal(str(stats['total_news'])),
                ':sector_rotation': sector_rotation,
                ':institutional_behavior': institutional_behavior,
                ':sentiment': sentiment,
                ':keywords': keywords,
                ':stocks': stocks
            }
            
            if rsi_data:
                update_expr += ', RSI = :rsi'
                attr_values[':rsi'] = rsi_data
            
            stats_table.update_item(
                Key={'date': date},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=attr_values
            )
        else:
            # Create new record with RSI
            item = {
                'date': date,
                'updated_at': int(datetime.now().timestamp()),
                'total_news': Decimal(str(stats['total_news'])),
                'sector_rotation': sector_rotation,
                'institutional_behavior': institutional_behavior,
                'sentiment': sentiment,
                'keywords': keywords,
                'stocks': stocks
            }
            
            if rsi_data:
                item['RSI'] = rsi_data
            
            stats_table.put_item(Item=item)
        
        print(f"Saved statistics for {date}: {stats['total_news']} news items with RSI for {len(rsi_data)} indexes")
        
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
