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
            
            # Group nearby stocks and add labels with collision avoidance
            min_distance = 0.1  # Minimum distance to be considered "nearby"
            
            # Normalize data for distance calculation
            x_range = max(mentions) - min(mentions) if max(mentions) != min(mentions) else 1
            y_range = max(sentiments) - min(sentiments) if max(sentiments) != min(sentiments) else 1
            
            # Create clusters of nearby stocks
            stock_data = list(zip(stock_names, mentions, sentiments))
            clusters = []
            used = set()
            
            for i, (name1, x1, y1) in enumerate(stock_data):
                if i in used or not (y1 > 0.6 or x1 > 4):
                    continue
                
                cluster = [(name1, x1, y1)]
                used.add(i)
                
                # Find nearby stocks
                for j, (name2, x2, y2) in enumerate(stock_data):
                    if j in used or j == i:
                        continue
                    
                    # Calculate normalized distance
                    norm_dist = ((x1 - x2) / x_range) ** 2 + ((y1 - y2) / y_range) ** 2
                    
                    if norm_dist < min_distance ** 2:
                        cluster.append((name2, x2, y2))
                        used.add(j)
                
                clusters.append(cluster)
            
            # Add annotations for each cluster
            for cluster in clusters:
                # Use centroid of cluster for annotation position
                avg_x = sum(x for _, x, _ in cluster) / len(cluster)
                avg_y = sum(y for _, _, y in cluster) / len(cluster)
                
                # Create label text (combine names if multiple stocks in cluster)
                if len(cluster) == 1:
                    label_text = cluster[0][0]
                else:
                    # Show up to 3 stocks per cluster
                    names = [name for name, _, _ in cluster]
                    label_text = '\n'.join(names)
                
                # Determine text position based on quadrant to avoid overlap
                xlim = ax.get_xlim()
                ylim = ax.get_ylim()
                offset_x = 10 if avg_x < (xlim[1] * 0.6) else -10
                offset_y = 10 if avg_y < (ylim[1] * 0.6) else -10
                ha = 'left' if offset_x > 0 else 'right'
                va = 'bottom' if offset_y > 0 else 'top'
                
                ax.annotate(label_text, (avg_x, avg_y), 
                          xytext=(offset_x, offset_y), 
                          textcoords='offset points',
                          fontsize=9 if len(cluster) == 1 else 8, 
                          ha=ha, va=va,
                          bbox=dict(boxstyle='round,pad=0.4', 
                                   facecolor='yellow', alpha=0.8, edgecolor='black', linewidth=0.5),
                          arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0.2', 
                                        color='black', lw=1, alpha=0.7))
            
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
            ax.text(xlim[1]*0.9, ylim[1]*0.9, '高關注+正面\n投資機會', 
                   ha='right', va='top', fontsize=11, 
                   bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))
            ax.text(xlim[1]*0.9, ylim[0]*0.9, '高關注+負面\n風險警示', 
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