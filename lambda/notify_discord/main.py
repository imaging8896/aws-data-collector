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


def send_discord_notification(index_name, signal_type, strategy_type, stock_symbols):
    """
    Send notification to Discord via webhook
    
    Args:
        index_name: Name of the index (e.g., "金融類")
        signal_type: Type of signal (e.g., "buy_signal")
        strategy_type: Strategy type ("medium" or "short")
        stock_symbols: List of representative stock symbols with details
    """
    webhook_url = get_discord_webhook_url()
    if not webhook_url:
        print("Discord webhook URL not configured")
        return False
    
    try:
        # Format strategy type in Chinese
        strategy_name = "中線" if strategy_type == "medium" else "短線"
        signal_emoji = "🟢" if signal_type == "buy" else "🔴"
        signal_text = "買入" if signal_type == "buy" else "賣出"
        
        # Create stock list text
        stock_list = "\n".join([
            f"• **{stock['symbol']}** ({stock['name']})"
            for stock in stock_symbols[:5]  # Top 5 stocks
        ])
        
        # Create Discord embed message
        embed = {
            "title": f"{signal_emoji} {index_name} - {strategy_name}{signal_text}訊號",
            "description": f"偵測到 **{index_name}** 出現{strategy_name}{signal_text}訊號",
            "color": 3066993,  # Green color
            "fields": [
                {
                    "name": "📊 代表性股票",
                    "value": stock_list if stock_list else "未找到代表性股票",
                    "inline": False
                },
                {
                    "name": "📅 時間",
                    "value": f"<t:{int(os.environ.get('notification_timestamp', 0))}:F>",
                    "inline": True
                },
                {
                    "name": "📈 策略類型",
                    "value": strategy_name,
                    "inline": True
                }
            ],
            "footer": {
                "text": "AWS Data Collector - 每日一次通知"
            }
        }
        
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
    
    Expected event format:
    {
        "index_name": "金融類",
        "signal_type": "buy",
        "strategy_type": "medium",  # or "short"
        "stock_symbols": [
            {"symbol": "2330", "name": "台積電"},
            {"symbol": "2317", "name": "鴻海"}
        ],
        "timestamp": 1234567890
    }
    """
    try:
        index_name = event.get('index_name', '')
        signal_type = event.get('signal_type', 'buy')
        strategy_type = event.get('strategy_type', 'medium')
        stock_symbols = event.get('stock_symbols', [])
        timestamp = event.get('timestamp', 0)
        
        # Set timestamp as environment variable for embed
        os.environ['notification_timestamp'] = str(timestamp)
        
        if not index_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'index_name is required'})
            }
        
        success = send_discord_notification(
            index_name,
            signal_type,
            strategy_type,
            stock_symbols
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
