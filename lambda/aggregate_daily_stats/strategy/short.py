# 短線權證進場應具備以下三個訊號：
# • 動能轉強訊號： 收盤價突破前 3 日最高點，且當日漲幅 > 1%。這代表短線整理結束，新的噴出段開始。
# • RSI 能量積累： 5日 RSI 位於 50 至 65 之間。
#     ◦ 邏輯： 來源資料顯示當 RSI > 85 時已過度超買 [i]。因此，理想的短線權證進場點是 RSI 剛突破 50（多空分界線）但尚未達到 85 的「動能加速期」。
# • 量能配合： 當日成交金額（Turnover）大於 5 日平均成交金額，成交量也隨之放大至 8,514 億。
# 2. 權證專屬：出場與風控條件
# 短線權證極度依賴「快進快出」以規避時間價值歸零的風險。
# • 停利條件 (快取利潤)：
#     1. 5日 RSI > 85 或 90（如 2026/01/16 當日 RSI_5 達 90.51 [i]）。此時權證槓桿效果極大化，應立即出場鎖定利潤，防止拉回導致權證價格劇烈縮水。
#     2. 持有時間不超過 5 至 10 個交易日。
# • 停損條件 (避開盤整)：
#     1. 收盤價跌破前一日低點（代表短線強勢慣性改變）。
#     2. 若買入後 3 天大盤橫盤未漲，必須出場。因為權證每天都在損失時間價值 [i]。

from decimal import Decimal

def check_short_strategy(index_data, historical_data):
    """
    Check if short-term warrant trading strategy conditions are met
    
    Args:
        index_data: dict containing current day RSI, MA values and current price
        {
            'value': current_price,
            'RSI_5': rsi_5_value,
            'turnover': current_turnover  # 當日成交金額
        }
        historical_data: list of dicts containing historical price and turnover data
        [
            {'value': price, 'turnover': turnover, 'date': date_str},  # Most recent (today)
            {'value': price, 'turnover': turnover, 'date': date_str},  # Yesterday
            ...
        ]
    
    Returns:
        dict with strategy signals:
        {
            'buy_signal': bool,
            'sell_signal': bool,
            'conditions': {
                'price_breaks_3day_high': bool,
                'daily_gain_above_1pct': bool,
                'rsi5_in_range_50_65': bool,
                'turnover_above_5day_avg': bool,
                'rsi5_above_85': bool,
                'price_below_prev_low': bool
            }
        }
    """
    result = {
        'buy_signal': False,
        'sell_signal': False,
        'conditions': {}
    }
    
    try:
        # Extract current day values
        current_price = float(index_data.get('value', 0))
        rsi_5 = float(index_data.get('RSI_5', 0))
        current_turnover = float(index_data.get('turnover', 0))
        
        # Check if we have historical data
        if not historical_data or len(historical_data) < 5:
            return result
        
        # Get yesterday's price for daily gain calculation
        prev_price = float(historical_data[1].get('value', 0)) if len(historical_data) > 1 else 0
        
        # Get previous day's low (assuming we have high/low in future, for now use value)
        prev_low = float(historical_data[1].get('value', 0)) if len(historical_data) > 1 else 0
        
        # Calculate conditions
        
        # 1. Price breaks 3-day high
        three_day_high = max([float(historical_data[i].get('value', 0)) for i in range(1, min(4, len(historical_data)))])
        price_breaks_3day_high = current_price > three_day_high
        
        # 2. Daily gain > 1%
        daily_gain_pct = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0
        daily_gain_above_1pct = daily_gain_pct > 1.0
        
        # 3. RSI 5 between 50 and 65
        rsi5_in_range_50_65 = 50 <= rsi_5 <= 65
        
        # 4. Turnover above 5-day average
        five_day_turnovers = [float(historical_data[i].get('turnover', 0)) for i in range(min(5, len(historical_data)))]
        avg_5day_turnover = sum(five_day_turnovers) / len(five_day_turnovers) if five_day_turnovers else 0
        turnover_above_5day_avg = current_turnover > avg_5day_turnover if avg_5day_turnover > 0 else False
        
        # 5. RSI 5 > 85 (sell signal)
        rsi5_above_85 = rsi_5 > 85
        
        # 6. Price below previous day's low (sell signal)
        price_below_prev_low = current_price < prev_low
        
        result['conditions'] = {
            'price_breaks_3day_high': price_breaks_3day_high,
            'daily_gain_above_1pct': daily_gain_above_1pct,
            'daily_gain_pct': Decimal(str(round(daily_gain_pct, 2))),
            'rsi5_in_range_50_65': rsi5_in_range_50_65,
            'turnover_above_5day_avg': turnover_above_5day_avg,
            'rsi5_above_85': rsi5_above_85,
            'price_below_prev_low': price_below_prev_low
        }
        
        # Buy signal: Price breaks 3-day high AND daily gain > 1% AND RSI 5 in 50-65 range AND turnover above 5-day avg
        result['buy_signal'] = (
            price_breaks_3day_high and 
            daily_gain_above_1pct and 
            rsi5_in_range_50_65 and 
            turnover_above_5day_avg
        )
        
        # Sell signal: RSI 5 > 85 OR price below previous low
        result['sell_signal'] = rsi5_above_85 or price_below_prev_low
        
        return result
        
    except (ValueError, TypeError, KeyError) as e:
        print(f"Error checking short strategy: {e}")
        return result
