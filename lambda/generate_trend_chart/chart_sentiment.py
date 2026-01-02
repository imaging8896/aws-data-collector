from io import BytesIO

import matplotlib.pyplot as plt


def generate_sentiment_chart(data):
    """
    圖表 3: 市場情緒趨勢
    {
        "date1": {
            'positive': Decimal(str(stats['sentiment']['positive'])),
            'negative': Decimal(str(stats['sentiment']['negative'])),
            'neutral': Decimal(str(stats['sentiment']['neutral'])),
            'average_score': Decimal(str(round(avg_sentiment, 4)))
        },
        ...
    }
    """
    try:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))
        
        dates = list(sorted(data.keys()))
        days = len(dates)
        
        # Chart 1: Sentiment Score Trend
        avg_scores = []
        positive_counts = []
        negative_counts = []
        neutral_counts = []
        
        for date in dates:
            sentiment_data = data[date]
            avg_score = float(sentiment_data['average_score'])
            avg_scores.append(avg_score)
            positive_counts.append(int(sentiment_data['positive']))
            negative_counts.append(int(sentiment_data['negative']))
            neutral_counts.append(int(sentiment_data['neutral']))
        
        x = range(len(dates))
        
        # Plot sentiment score as line
        ax1_twin = ax1.twinx()
        line = ax1.plot(x, avg_scores, marker='o', linewidth=2.5, markersize=8, 
                       color='#2E86AB', label='情緒指數')
        ax1.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        ax1.fill_between(x, avg_scores, 0, alpha=0.2, color='#2E86AB')
        
        # Add sentiment distribution bars
        ax1_twin.bar(x, positive_counts, alpha=0.3, color='#06D6A0', label='正面新聞')
        ax1_twin.bar(x, [-c for c in negative_counts], alpha=0.3, color='#EF476F', label='負面新聞')
        
        ax1.set_title('市場情緒趨勢', fontsize=16, fontweight='bold')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('平均情緒指數', color='#2E86AB')
        ax1_twin.set_ylabel('新聞數量', color='gray')
        ax1.set_xticks(x)
        ax1.set_xticklabels(dates, rotation=45)
        ax1.tick_params(axis='y', labelcolor='#2E86AB')
        ax1.grid(True, alpha=0.3)
        
        # Combine legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1_twin.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        # Chart 2: Sentiment Distribution Pie Chart (Latest Day)
        latest_date = dates[-1]
        latest_sentiment = data[latest_date]
        
        sizes = [latest_sentiment['positive'], latest_sentiment['neutral'], latest_sentiment['negative']]
        labels_pie = ['正面', '中性', '負面']
        colors_pie = ['#06D6A0', '#FFD166', '#EF476F']
        explode = (0.1, 0, 0)  # Explode positive slice
        
        ax2.pie(sizes, explode=explode, labels=labels_pie, colors=colors_pie,
               autopct='%1.1f%%', shadow=True, startangle=90, textprops={'fontsize': 12})
        ax2.set_title(f'最新市場情緒分布 ({latest_date})', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.read()
        plt.close()
        
        return png_bytes
        
    except Exception as e:
        print(f"Error generating sentiment chart: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
