# • 買入條件： (20MA > 60MA，代表多頭) 且 (收盤價 > 20MA) 且 (5日 RSI < 45，代表多頭中的短線回檔)。
# • 出場條件： (報酬 > 10%) 或 (5日 RSI > 85，代表超買) 或 (收盤價 < 20MA，代表轉弱停損)。

def check_medium_strategy(index_data):
    """
    Check if medium-term trading strategy conditions are met
    
    Args:
        index_data: dict containing RSI, MA values and current price
        {
            'value': current_price,
            'RSI_5': rsi_5_value,
            'MA_20': ma_20_value,
            'MA_60': ma_60_value
        }
    
    Returns:
        dict with strategy signals:
        {
            'buy_signal': bool,
            'sell_signal': bool,
            'conditions': {
                'ma_20_above_60': bool,
                'price_above_ma20': bool,
                'rsi5_below_45': bool,
                'rsi5_above_85': bool,
                'price_below_ma20': bool
            }
        }
    """
    result = {
        'buy_signal': False,
        'sell_signal': False,
        'conditions': {}
    }
    
    try:
        # Extract values (handle Decimal type)
        current_price = float(index_data.get('value', 0))
        rsi_5 = float(index_data.get('RSI_5', 0))
        ma_20 = float(index_data.get('MA_20', 0))
        ma_60 = float(index_data.get('MA_60', 0))
        
        # Check if we have all required data
        if not all([current_price, rsi_5, ma_20, ma_60]):
            return result
        
        # Calculate conditions
        ma_20_above_60 = ma_20 > ma_60
        price_above_ma20 = current_price > ma_20
        rsi5_below_45 = rsi_5 < 45
        rsi5_above_85 = rsi_5 > 85
        price_below_ma20 = current_price < ma_20
        
        result['conditions'] = {
            'ma_20_above_60': ma_20_above_60,
            'price_above_ma20': price_above_ma20,
            'rsi5_below_45': rsi5_below_45,
            'rsi5_above_85': rsi5_above_85,
            'price_below_ma20': price_below_ma20
        }
        
        # Buy signal: (20MA > 60MA) AND (Price > 20MA) AND (RSI5 < 45)
        result['buy_signal'] = ma_20_above_60 and price_above_ma20 and rsi5_below_45
        
        # Sell signal: (RSI5 > 85) OR (Price < 20MA)
        # Note: We don't check "profit > 10%" here as we don't track entry price in daily stats
        result['sell_signal'] = rsi5_above_85 or price_below_ma20
        
        return result
        
    except (ValueError, TypeError, KeyError) as e:
        print(f"Error checking medium strategy: {e}")
        return result
