from collections import defaultdict, Counter
from io import BytesIO

import matplotlib.pyplot as plt


def generate_keyword_momentum_chart(data):
    """
    圖表 4: 關鍵字動能 (投資主題熱度)
    {
        "date1": ["keyword1", "keyword2", ...],
        ...
    }
    """
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        dates = list(sorted(data.keys()))
        days = len(dates)
        
        # Aggregate all keywords
        all_keywords = Counter()
        keyword_timeline = defaultdict(lambda: defaultdict(int))
        
        for date in dates:
            for keyword in data[date]:
                all_keywords[keyword] += 1
                keyword_timeline[keyword][date] += 1
        
        # Chart 1: Top 15 Keywords Over Time
        top_keywords = [kw for kw, _ in all_keywords.most_common(15)]
        
        for keyword in top_keywords:
            counts = [keyword_timeline[keyword][date] for date in dates]
            ax1.plot(range(len(dates)), counts, marker='o', label=keyword, linewidth=2)
        
        ax1.set_title('熱門投資主題趨勢 (Top 15)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('提及次數')
        ax1.set_xticks(range(len(dates)))
        ax1.set_xticklabels(dates, rotation=45)
        ax1.legend(loc='upper left', bbox_to_anchor=(1.05, 1), fontsize=9)
        ax1.grid(True, alpha=0.3)
        
        # Chart 2: Keyword Momentum (Latest vs Previous)
        # Calculate momentum: (last 2 days avg) - (previous 2 days avg)
        if len(dates) >= 4:
            recent_dates = dates[-2:]
            previous_dates = dates[-4:-2]
        else:
            recent_dates = dates[-1:]
            previous_dates = dates[:-1] if len(dates) > 1 else []
        
        keyword_momentum = {}
        
        for keyword in top_keywords:
            recent_count = sum(keyword_timeline[keyword][d] for d in recent_dates) / len(recent_dates)
            previous_count = sum(keyword_timeline[keyword][d] for d in previous_dates) / len(previous_dates) if previous_dates else 0
            momentum = recent_count - previous_count
            keyword_momentum[keyword] = momentum
        
        # Sort by momentum
        sorted_keywords = sorted(keyword_momentum.items(), key=lambda x: x[1], reverse=True)
        keywords, momentums = zip(*sorted_keywords) if sorted_keywords else ([], [])
        
        colors = ['#06D6A0' if m > 0 else '#EF476F' for m in momentums]
        
        ax2.barh(range(len(keywords)), momentums, color=colors, alpha=0.8)
        ax2.set_yticks(range(len(keywords)))
        ax2.set_yticklabels(keywords)
        ax2.set_xlabel('動能變化 (近期-先前)')
        ax2.set_title('投資主題動能排行', fontsize=14, fontweight='bold')
        ax2.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax2.grid(True, alpha=0.3, axis='x')
        
        # Add momentum indicators
        for i, (kw, momentum) in enumerate(zip(keywords, momentums)):
            if momentum > 0.5:
                ax2.text(momentum, i, " 🔥", va='center', fontsize=12)
            elif momentum < -0.5:
                ax2.text(momentum, i, " ❄️", va='center', fontsize=12)
        
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.read()
        plt.close()
        
        return png_bytes
        
    except Exception as e:
        print(f"Error generating keyword momentum chart: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
