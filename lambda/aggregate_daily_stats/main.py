import json
import os
import time
from datetime import datetime, timedelta, date
from decimal import Decimal
from collections import defaultdict, Counter
import boto3
from google import genai
from google.genai import types
from strategy.medium import check_medium_strategy
from strategy.short import check_short_strategy

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

news_table_name = os.environ['DYNAMODB_TABLE_NAME']
stats_table_name = os.environ['DYNAMODB_STATS_TABLE_NAME']
index_data_table_name = os.environ['DYNAMODB_INDEX_TABLE_NAME']
index_stocks_table_name = os.environ.get('DYNAMODB_INDEX_STOCKS_TABLE_NAME', '')
market_data_table_name = os.environ.get('DYNAMODB_MARKET_DATA_TABLE_NAME', '')
gemini_secret_name = os.environ.get('GEMINI_API_KEY_SECRET_NAME')

news_table = dynamodb.Table(news_table_name) # type: ignore
stats_table = dynamodb.Table(stats_table_name) # type: ignore
index_data_table = dynamodb.Table(index_data_table_name) # type: ignore
index_stocks_table = dynamodb.Table(index_stocks_table_name) if index_stocks_table_name else None # type: ignore
market_data_table = dynamodb.Table(market_data_table_name) if market_data_table_name else None # type: ignore

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


def calculate_ma(prices, period):
    """
    Calculate Moving Average for given prices
    prices: list of Decimal values (newest to oldest)
    period: MA period (e.g., 5, 20, 60, 120, 240)
    Returns: MA value or None if insufficient data
    """
    if len(prices) < period:
        return None
    
    # Convert to float and calculate average of most recent 'period' prices
    prices_float = [float(p) for p in prices[:period]]
    ma_value = sum(prices_float) / period
    
    return round(ma_value, 2)


def analyze_rsi_signals(rsi_data):
    """
    Analyze RSI values and generate trading signals
    rsi_data: dict with RSI_5, RSI_9, RSI_14, RSI_22 keys
    Returns: list of signal strings
    """
    signals = []
    
    # Extract RSI values (handle both Decimal and float)
    try:
        rsi_5 = float(rsi_data.get('RSI_5', 0))
        rsi_9 = float(rsi_data.get('RSI_9', 0))
        rsi_14 = float(rsi_data.get('RSI_14', 0))
        rsi_22 = float(rsi_data.get('RSI_22', 0))
    except (ValueError, TypeError):
        return signals
    
    # 檢查是否所有 RSI 值都有效
    if not all([rsi_5, rsi_9, rsi_14, rsi_22]):
        return signals
    
    # 1. 多頭排列: RSI 5 > 9 > 14 > 22
    if rsi_5 > rsi_9 > rsi_14 > rsi_22:
        signals.append('多頭排列')
    
    # 2. 空頭排列: RSI 5 < 9 < 14 < 22
    if rsi_5 < rsi_9 < rsi_14 < rsi_22:
        signals.append('空頭排列')
    
    # 3. 短線超買: RSI 5 or 9 > 85
    if rsi_5 > 85 or rsi_9 > 85:
        signals.append('短線超買')
    
    # 4. 超買: RSI 14 or 22 > 70
    if rsi_14 > 70 or rsi_22 > 70:
        signals.append('超買')
    
    # 5. 止跌: RSI < 30
    if rsi_5 < 30 or rsi_9 < 30:
        signals.append('止跌')
    
    # 6. 趨勢轉折: RSI 22 在 50 附近 (45-55)
    if 45 <= rsi_22 <= 55:
        signals.append('趨勢轉折')
    
    # 額外訊號
    
    # 7. 短線超賣: RSI 5 or 9 < 15
    if rsi_5 < 15 or rsi_9 < 15:
        signals.append('短線超賣')
    
    # 8. 超賣: RSI 14 or 22 < 30
    if rsi_14 < 30 or rsi_22 < 30:
        signals.append('超賣')
    
    # 9. 黃金交叉: 短期 RSI 向上穿越長期 RSI (簡化版: 5 > 9 且 9 > 14)
    if rsi_5 > rsi_9 and rsi_9 > rsi_14 and not (rsi_5 > rsi_9 > rsi_14 > rsi_22):
        signals.append('短線轉強')
    
    # 10. 死亡交叉: 短期 RSI 向下穿越長期 RSI (簡化版: 5 < 9 且 9 < 14)
    if rsi_5 < rsi_9 and rsi_9 < rsi_14 and not (rsi_5 < rsi_9 < rsi_14 < rsi_22):
        signals.append('短線轉弱')
    
    # 11. 背離訊號: RSI 14 與 RSI 22 方向不一致
    if abs(rsi_14 - rsi_22) > 15:
        if rsi_14 > rsi_22:
            signals.append('短期強於長期')
        else:
            signals.append('短期弱於長期')
    
    # 12. 強勢整理: 所有 RSI > 50 且 < 70
    if all(50 < rsi < 70 for rsi in [rsi_5, rsi_9, rsi_14, rsi_22]):
        signals.append('強勢整理')
    
    # 13. 弱勢整理: 所有 RSI > 30 且 < 50
    if all(30 < rsi < 50 for rsi in [rsi_5, rsi_9, rsi_14, rsi_22]):
        signals.append('弱勢整理')
    
    return signals


def get_index_rsi_for_date(date_str, periods=[5, 9, 14, 22]):
    """
    Calculate RSI and MA for all indexes on a specific date
    Returns dict: {index_name: {RSI_X: value, MA_X: value, signals: [...]}}
    """
    if not index_data_table:
        print("Index data table not configured")
        return {}
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        rsi_results = {}
        
        # Get all unique index names
        # Query by date to get all indexes for that date
        request_date = date_str
        index_names = []
        for _ in range(20):
            response = index_data_table.query(
                IndexName='DateIndex',
                KeyConditionExpression='#date = :date',
                ExpressionAttributeNames={'#date': 'date'},
                ExpressionAttributeValues={':date': date_str}
            )
            if items := response.get('Items', []):
                index_names.extend([item['name'] for item in items])
                break
            date_str = (date.fromisoformat(date_str) - timedelta(days=1)).isoformat()
        else:
            print(f"No index data found around date {request_date} to {date_str}")
            return
        
        # Calculate RSI and MA for each index
        max_rsi_period = max(periods)
        max_ma_period = 240  # Maximum MA period
        max_period = max(max_rsi_period, max_ma_period)
        
        for index_name in index_names:
            if index_name == "電子類":
                continue

            # Get historical data for this index (need max_period days)
            # Skip weekends and holidays by querying until we get enough valid prices

            query_response = index_data_table.query(
                KeyConditionExpression='#n = :n AND #d <= :d',
                ExpressionAttributeNames={'#n': 'name', '#d': 'date'},
                ExpressionAttributeValues={':n': index_name, ':d': target_date.strftime('%Y-%m-%d')},
                ScanIndexForward=False,
                Limit=max_period + 1
            )
            
            if any(['value' not in x for x in query_response.get('Items', [])]):
                raise ValueError(f"Missing 'value' field in index data for {index_name} on {date_str}")
            historical_prices = [i['value'] for i in query_response.get('Items', [])]
            historical_turnover = [i.get('turnover', 0) for i in query_response.get('Items', [])]
            
            # Calculate RSI and MA for each period
            if len(historical_prices) >= max_rsi_period + 1:
                print(f"{index_name}: Collected {len(historical_prices)} prices")
                result_data = {}
                
                # Calculate RSI
                for period in periods:
                    rsi_value = calculate_rsi(historical_prices, period)
                    if rsi_value is not None:
                        result_data[f'RSI_{period}'] = Decimal(str(rsi_value))
                
                # Calculate MA (Moving Average)
                ma_periods = [5, 20, 60, 120, 240]
                for ma_period in ma_periods:
                    ma_name = f'MA_{ma_period}'
                    ma_value = calculate_ma(historical_prices, ma_period)
                    if ma_value is not None:
                        result_data[ma_name] = Decimal(str(ma_value))
                    else:
                        print(f"{index_name}: Insufficient data for {ma_name} (have {len(historical_prices)} prices)")
                        break
                
                # Analyze signals if we have all RSI values
                rsi_count = sum(1 for key in result_data if key.startswith('RSI_'))
                if rsi_count == len(periods):
                    signals = analyze_rsi_signals({k: v for k, v in result_data.items() if k.startswith('RSI_')})
                    
                    # Prepare historical data for short strategy
                    historical_data = []
                    for item in query_response.get('Items', []):
                        historical_data.append({
                            'value': item.get('value'),
                            'turnover': item.get('turnover', 0),
                            'date': item.get('date')
                        })
                    
                    # Add current price and check strategies
                    current_price = float(historical_prices[0]) if historical_prices else 0
                    current_turnover = float(historical_turnover[0]) if historical_turnover else 0
                    
                    strategy_data = {
                        'value': current_price,
                        'turnover': current_turnover,
                        **result_data
                    }
                    
                    # Check medium-term strategy
                    medium_strategy_result = check_medium_strategy(strategy_data)
                    
                    # Check short-term strategy
                    short_strategy_result = check_short_strategy(strategy_data, historical_data)
                    
                    rsi_results[index_name] = {
                        **result_data,
                        'signals': signals,
                        'medium_strategy': medium_strategy_result,
                        'short_strategy': short_strategy_result
                    }
                else:
                    rsi_results[index_name] = result_data

            else:
                print(f"{index_name}: Insufficient data - only {len(historical_prices)} prices (need {max_rsi_period + 1})")
        
        print(f"Calculated RSI and MA for {len(rsi_results)} indexes on {date_str}")
        return rsi_results
        
    except Exception as e:
        print(f"Error calculating RSI for date {date_str}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}


def get_all_index_stocks():
    """
    Get all stocks from index_stocks_table
    Returns dict: {index_name: [{'symbol': ..., 'name': ...}, ...]}
    """
    if not index_stocks_table:
        print("Index stocks table not configured")
        return {}
    
    try:
        response = index_stocks_table.scan()
        items = response.get('Items', [])
        
        result = {}
        for item in items:
            index_name = item.get('index_name')
            stocks = item.get('stocks', [])
            if index_name and stocks:
                result[index_name] = stocks
        
        print(f"Retrieved stocks for {len(result)} indexes")
        return result
        
    except Exception as e:
        print(f"Error getting index stocks: {str(e)}")
        return {}


def get_stock_historical_data(symbol, target_date, days=10):
    """
    Get historical price data for a stock from market_data_table
    
    Args:
        symbol: Stock symbol (e.g., "2330")
        target_date: Target date string (YYYY-MM-DD)
        days: Number of days of historical data to retrieve
    
    Returns:
        List of dicts with date, close, high, low, turnover (newest to oldest)
    """
    if not market_data_table:
        return []
    
    try:
        response = market_data_table.query(
            KeyConditionExpression='symbol = :symbol AND #date <= :target_date',
            ExpressionAttributeNames={'#date': 'date'},
            ExpressionAttributeValues={
                ':symbol': symbol,
                ':target_date': target_date
            },
            ScanIndexForward=False,  # Newest first
            Limit=days
        )
        
        items = response.get('Items', [])
        if not items:
            return []
        
        # Convert Decimal to float
        historical_data = []
        for item in items:
            historical_data.append({
                'date': item.get('date'),
                'close': float(item.get('close', 0)),
                'high': float(item.get('high', 0)),
                'low': float(item.get('low', 0)),
                'turnover': float(item.get('turnover', 0))
            })
        
        return historical_data
        
    except Exception as e:
        print(f"Error getting historical data for {symbol}: {str(e)}")
        return []


def check_stock_short_signal(stock_symbol, target_date):
    """
    Check short-term trading signal for a stock using strategy/short.py
    
    Args:
        stock_symbol: Stock symbol (e.g., "2330")
        target_date: Target date string (YYYY-MM-DD)
    
    Returns:
        dict with signal info
    """
    result = {
        'has_signal': False,
        'buy_signal': False,
        'sell_signal': False,
        'rsi_5': None,
        'daily_gain_pct': None,
        'has_latest_data': False
    }
    
    # Get historical data for this stock
    historical_data = get_stock_historical_data(stock_symbol, target_date, days=10)
    
    if not historical_data or len(historical_data) < 6:
        return result
    
    # Check if we have the target date's data
    if historical_data[0]['date'] != target_date:
        return result
    
    result['has_latest_data'] = True
    
    # Extract prices for RSI calculation (close prices, newest to oldest)
    prices = [d['close'] for d in historical_data]
    
    # Calculate RSI-5
    rsi_5 = calculate_rsi(prices, period=5)
    if rsi_5 is not None:
        result['rsi_5'] = Decimal(str(rsi_5))
    
    if rsi_5 is None:
        return result
    
    # Prepare data for check_short_strategy
    # Convert stock data format to match index data format expected by check_short_strategy
    current = historical_data[0]
    
    index_data = {
        'value': current['close'],
        'RSI_5': Decimal(str(rsi_5)),
        'turnover': current['turnover']
    }
    
    # Convert historical data format: use 'close' as 'value', 'low' for prev_low check
    strategy_historical_data = []
    for d in historical_data:
        strategy_historical_data.append({
            'value': d['close'],
            'high': d['high'],
            'low': d['low'],
            'turnover': d['turnover'],
            'date': d['date']
        })
    
    # Use shared short strategy logic
    strategy_result = check_short_strategy(index_data, strategy_historical_data)
    
    result['buy_signal'] = strategy_result.get('buy_signal', False)
    result['sell_signal'] = strategy_result.get('sell_signal', False)
    result['has_signal'] = result['buy_signal'] or result['sell_signal']
    
    # Get daily_gain_pct from conditions
    conditions = strategy_result.get('conditions', {})
    if 'daily_gain_pct' in conditions:
        result['daily_gain_pct'] = conditions['daily_gain_pct']
    
    return result


def get_stock_rsi_for_date(date_str):
    """
    Calculate RSI and short-term signals for all index stocks on a specific date
    Returns dict: {index_name: {stock_symbol: {rsi_5, daily_gain_pct, buy_signal, sell_signal, ...}}}
    """
    if not index_stocks_table or not market_data_table:
        print("Index stocks table or market data table not configured")
        return {}
    
    try:
        # Get all index stocks
        all_index_stocks = get_all_index_stocks()
        
        if not all_index_stocks:
            print("No index stocks found")
            return {}
        
        rsi_stock_results = {}
        
        for index_name, stocks in all_index_stocks.items():
            stock_results = {}
            
            for stock in stocks:
                stock_symbol = stock.get('symbol', '')
                stock_name = stock.get('name', '')
                
                if not stock_symbol:
                    continue
                
                # Calculate signal for this stock
                signal = check_stock_short_signal(stock_symbol, date_str)
                
                stock_results[stock_symbol] = {
                    'name': stock_name,
                    'has_latest_data': signal['has_latest_data'],
                    'has_signal': signal['has_signal'],
                    'buy_signal': signal['buy_signal'],
                    'sell_signal': signal['sell_signal'],
                    'rsi_5': signal['rsi_5'],
                    'daily_gain_pct': signal['daily_gain_pct']
                }
            
            if stock_results:
                rsi_stock_results[index_name] = stock_results
        
        total_stocks = sum(len(stocks) for stocks in rsi_stock_results.values())
        print(f"Calculated RSI for {total_stocks} stocks across {len(rsi_stock_results)} indexes on {date_str}")
        return rsi_stock_results
        
    except Exception as e:
        print(f"Error calculating stock RSI for date {date_str}: {str(e)}")
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
        
        # 2. 只取頻率最高的 45 個關鍵字送給 AI (避免 Token 爆炸)
        # 剩下的低頻關鍵字通常對趨勢分析影響較小，可以直接忽略或歸類為其他
        most_common = [(k, v) for k, v in counter.most_common(45) if v > 1]
        print(f"Refining {len(most_common)} keywords with AI\n{most_common}")
        top_keywords = [k for k, _ in most_common]

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
            model='gemini-2.5-flash-lite',
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

        # Print token usage
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            print(f"Token usage - Input: {usage.prompt_token_count}, Output: {usage.candidates_token_count}, Total: {usage.total_token_count}")
        
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
        
        time.sleep(1)  # 避免過快呼叫 AI 服務
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
        'sentiment': {'positive': 0, 'negative': 0, 'neutral': 0, 'scores': []},
        'keywords': [],
        'stocks': defaultdict(lambda: {'name': '', 'mentions': 0, 'sentiment': 0, 'events': []})
    })
    
    for item in items:
        publish_time = int(item['publish_time'])
        date = datetime.fromtimestamp(publish_time).strftime('%Y-%m-%d')
        analysis = item.get('analysis', {})
        
        if not analysis:
            continue
        
        daily_stats[date]['date'] = date
        daily_stats[date]['total_news'] += 1
        
        # 1. Market Sentiment
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
        
        # 3. Investment Themes (Keywords)
        daily_stats[date]['keywords'].extend(analysis.get('investment_themes', []))
        
        # 4. Stock Opportunities
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
        
        # Calculate RSI for all index stocks
        rsi_stock_data = get_stock_rsi_for_date(date)
        
        if 'Item' in existing:
            # Update existing record with RSI and RSI_stock
            update_expr = 'SET updated_at = :updated_at, total_news = :total_news, ' \
                         'sentiment = :sentiment, keywords = :keywords, stocks = :stocks'
            attr_values = {
                ':updated_at': int(datetime.now().timestamp()),
                ':total_news': Decimal(str(stats['total_news'])),
                ':sentiment': sentiment,
                ':keywords': keywords,
                ':stocks': stocks
            }
            
            if rsi_data:
                update_expr += ', RSI = :rsi'
                attr_values[':rsi'] = rsi_data
            
            if rsi_stock_data:
                update_expr += ', RSI_stock = :rsi_stock'
                attr_values[':rsi_stock'] = rsi_stock_data
            
            stats_table.update_item(
                Key={'date': date},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=attr_values
            )
        else:
            # Create new record with RSI and RSI_stock
            item = {
                'date': date,
                'updated_at': int(datetime.now().timestamp()),
                'total_news': Decimal(str(stats['total_news'])),
                'sentiment': sentiment,
                'keywords': keywords,
                'stocks': stocks
            }
            
            if rsi_data:
                item['RSI'] = rsi_data
            
            if rsi_stock_data:
                item['RSI_stock'] = rsi_stock_data
            
            stats_table.put_item(Item=item)
        
        stock_count = sum(len(stocks) for stocks in rsi_stock_data.values()) if rsi_stock_data else 0
        print(f"Saved statistics for {date}: {stats['total_news']} news items with RSI for {len(rsi_data)} indexes and {stock_count} stocks")
  
    except Exception as e:
        print(f"Error saving stats for {date}: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_event = {
        "days": 2
    }
    result = handler(test_event, None)
    print(json.dumps(json.loads(result['body']), indent=2, ensure_ascii=False))
