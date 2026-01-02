from collections import defaultdict
from io import BytesIO

import matplotlib.pyplot as plt


def generate_stock_opportunities_chart(data):
    """
    圖表 5: 個股投資機會
    {
        "date1": {
            "2330": {
                'mentions': Decimal(str(data['mentions'])),
                'average_sentiment': Decimal(str(round(data['sentiment'] / data['mentions'], 4))) if data['mentions'] > 0 else Decimal('0'),
                'events': data['events'][:10]  # Keep top 10 events
            }
        },
        ...
    }
    """
    try:
        fig, ax = plt.subplots(figsize=(16, 10))
        
        dates = list(sorted(data.keys()))
        days = len(dates)
        
        # Aggregate stock data
        all_stocks = defaultdict(lambda: {'mentions': 0, 'avg_sentiment': 0, 'events': []})
        
        for date in dates:
            for stock_id, stock_data in data[date].items():
                all_stocks[stock_id]['name'] = stock_data['name']
                all_stocks[stock_id]['mentions'] += int(stock_data['mentions'])
                all_stocks[stock_id]['avg_sentiment'] += float(stock_data['average_sentiment'])
                all_stocks[stock_id]['events'].extend(stock_data['events'])
        
        # Calculate average sentiment
        for stock_key in all_stocks:
            mentions = all_stocks[stock_key]['mentions']
            if mentions > 0:
                all_stocks[stock_key]['avg_sentiment'] /= mentions
        
        # Filter stocks with at least 2 mentions
        significant_stocks = {k: v for k, v in all_stocks.items() if v['mentions'] >= 2}
        
        if not significant_stocks:
            # No data to plot
            ax.text(0.5, 0.5, '暫無足夠個股數據', ha='center', va='center', 
                   fontsize=20, transform=ax.transAxes)
            ax.axis('off')
        else:
            # Create scatter plot: X=Mentions, Y=Sentiment
            stock_names = []
            mentions = []
            sentiments = []
            
            for stock_id, stock_data in significant_stocks.items():
                stock_names.append(f"{stock_data['name']}({stock_id})")
                mentions.append(stock_data['mentions'])
                sentiments.append(stock_data['avg_sentiment'])
            
            # Bubble size based on mentions
            sizes = [m * 100 for m in mentions]
            
            # Color based on sentiment
            colors_scatter = ['#06D6A0' if s > 0.5 else '#EF476F' if s < -0.5 else '#FFD166' 
                            for s in sentiments]
            
            scatter = ax.scatter(mentions, sentiments, s=sizes, c=colors_scatter, 
                               alpha=0.6, edgecolors='black', linewidth=1)
            
            # Add labels for top opportunities
            for i, (name, x, y) in enumerate(zip(stock_names, mentions, sentiments)):
                if y > 0.6 or x > 4:  # High sentiment or high mentions
                    ax.annotate(name, (x, y), xytext=(5, 5), textcoords='offset points',
                              fontsize=9, bbox=dict(boxstyle='round,pad=0.3', 
                              facecolor='yellow', alpha=0.5))
            
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            ax.axhline(y=0.5, color='green', linestyle=':', alpha=0.3, label='正面情緒門檻')
            ax.axhline(y=-0.5, color='red', linestyle=':', alpha=0.3, label='負面情緒門檻')
            
            ax.set_xlabel('提及次數', fontsize=12)
            ax.set_ylabel('平均情緒分數', fontsize=12)
            ax.set_title(f'個股投資機會圖 ({days}天)\n泡泡大小 = 熱度，顏色 = 情緒', 
                        fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend()
            
            # Add quadrant labels
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            ax.text(xlim[1]*0.9, ylim[1]*0.9, '高關注+正面\n💰投資機會', 
                   ha='right', va='top', fontsize=11, 
                   bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))
            ax.text(xlim[1]*0.9, ylim[0]*0.9, '高關注+負面\n⚠️風險警示', 
                   ha='right', va='bottom', fontsize=11,
                   bbox=dict(boxstyle='round', facecolor='lightcoral', alpha=0.5))
        
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.read()
        plt.close()
        
        return png_bytes
        
    except Exception as e:
        print(f"Error generating stock opportunities chart: {str(e)}")
        import traceback
        traceback.print_exc()
        return None