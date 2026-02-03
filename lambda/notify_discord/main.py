import json
import os
import urllib3
import boto3

# Initialize clients
http = urllib3.PoolManager()
ssm_client = boto3.client('ssm')

# Environment variables
discord_webhook_parameter_name = os.environ.get('DISCORD_WEBHOOK_PARAMETER_NAME')

# Cache for webhook URL
_webhook_url = None

def get_discord_webhook_url():
    """Get Discord webhook URL from Parameter Store"""
    global _webhook_url
    if _webhook_url is None and discord_webhook_parameter_name:
        try:
            response = ssm_client.get_parameter(
                Name=discord_webhook_parameter_name,
                WithDecryption=True
            )
            _webhook_url = response['Parameter']['Value']
        except Exception as e:
            print(f"Failed to get Discord webhook URL: {str(e)}")
    return _webhook_url


def send_discord_notification(index_name, signals, stock_symbols, timestamp):
    """
    Send consolidated notification to Discord via webhook
    
    Args:
        index_name: Name of the index (e.g., "金融類")
        signals: List of signal dicts with 'signal_type' and 'strategy_type'
        stock_symbols: List of representative stock symbols with details
        timestamp: Unix timestamp of the notification
    """
    webhook_url = get_discord_webhook_url()
    if not webhook_url:
        print("Discord webhook URL not configured")
        return False
    
    try:
        # Build signal description
        signal_parts = []
        has_buy = False
        has_sell = False
        
        for signal in signals:
            strategy_name = "中線" if signal['strategy_type'] == "medium" else "短線"
            signal_text = "買入" if signal['signal_type'] == "buy" else "賣出"
            signal_parts.append(f"{strategy_name}{signal_text}")
            
            if signal['signal_type'] == "buy":
                has_buy = True
            else:
                has_sell = True
        
        # Determine emoji and color based on signals
        if has_buy and has_sell:
            signal_emoji = "⚡"  # Mixed signals
            color = 16776960  # Yellow
        elif has_buy:
            signal_emoji = "🟢"
            color = 3066993  # Green
        else:
            signal_emoji = "🔴"
            color = 15158332  # Red
        
        signal_summary = " / ".join(signal_parts)
        
        # Create stock list text
        stock_list = "\n".join([
            f"• **{stock['symbol']}** ({stock['name']})"
            for stock in stock_symbols[:5]  # Top 5 stocks
        ])
        
        # Create Discord embed message
        embed = {
            "title": f"{signal_emoji} {index_name} - {signal_summary}訊號",
            "description": f"偵測到 **{index_name}** 出現以下訊號：\n{signal_summary}",
            "color": color,
            "fields": [],
            "footer": {
                "text": "AWS Data Collector - 每日一次通知"
            }
        }
        
        # Add stock field if available
        if stock_list:
            embed["fields"].append({
                "name": "📊 代表性股票",
                "value": stock_list,
                "inline": False
            })
        
        # Add time field
        embed["fields"].append({
            "name": "📅 時間",
            "value": f"<t:{int(timestamp)}:F>",
            "inline": True
        })
        
        # Add signals summary field
        embed["fields"].append({
            "name": "📈 訊號類型",
            "value": signal_summary,
            "inline": True
        })
        
        payload = {
            "embeds": [embed]
        }
        
        encoded_data = json.dumps(payload).encode('utf-8')
        
        response = http.request(
            'POST',
            webhook_url,
            body=encoded_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status == 204:
            print(f"Successfully sent Discord notification for {index_name}")
            return True
        else:
            print(f"Failed to send Discord notification. Status: {response.status}")
            return False
            
    except Exception as e:
        print(f"Error sending Discord notification: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def handler(event, context):
    """
    Lambda handler for Discord notifications
    
    Expected event format (new consolidated format):
    {
        "index_name": "金融類",
        "signals": [
            {"signal_type": "buy", "strategy_type": "medium"},
            {"signal_type": "buy", "strategy_type": "short"}
        ],
        "stock_symbols": [
            {"symbol": "2330", "name": "台積電"},
            {"symbol": "2317", "name": "鴻海"}
        ],
        "timestamp": 1234567890
    }
    """
    try:
        index_name = event.get('index_name', '')
        signals = event.get('signals', [])
        stock_symbols = event.get('stock_symbols', [])
        timestamp = event.get('timestamp', 0)
        
        # Backward compatibility: convert old format to new format
        if not signals and 'signal_type' in event:
            signals = [{
                'signal_type': event.get('signal_type', 'buy'),
                'strategy_type': event.get('strategy_type', 'medium')
            }]
        
        if not index_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'index_name is required'})
            }
        
        if not signals:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'signals is required'})
            }
        
        success = send_discord_notification(
            index_name,
            signals,
            stock_symbols,
            timestamp
        )
        
        return {
            'statusCode': 200 if success else 500,
            'body': json.dumps({
                'message': 'Notification sent' if success else 'Failed to send notification',
                'index_name': index_name
            })
        }
        
    except Exception as e:
        print(f"Error in handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
