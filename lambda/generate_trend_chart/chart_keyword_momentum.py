from collections import defaultdict, Counter
from io import BytesIO

import matplotlib.pyplot as plt


def generate_keyword_momentum_chart(data):
    """
    圖表 4: 關鍵字動能 (投資主題熱度)
    {
        "date1": [
            {"keyword": "AI", "count": 20, "related": ["AI供應鏈", "生成式AI", ...]},
            ...
        ],
        ...
    }
    """
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        dates = list(sorted(data.keys()))
        days = len(dates)
        
        # Aggregate all keywords with their counts
        all_keywords_count = defaultdict(int)
        keyword_timeline = defaultdict(lambda: defaultdict(int))
        keyword_related = {}  # Store related keywords for tooltip
        
        for date in dates:
            keywords_list = data[date]
            
            # Handle both old format (list of strings) and new format (list of dicts)
            if keywords_list and isinstance(keywords_list[0], dict):
                # New format with refined keywords
                for item in keywords_list:
                    keyword = item['keyword']
                    count = int(item.get('count', 1))
                    related = item.get('related', [])
                    
                    all_keywords_count[keyword] += count
                    keyword_timeline[keyword][date] += count
                    keyword_related[keyword] = related
            else:
                # Old format fallback (simple list)
                for keyword in keywords_list:
                    all_keywords_count[keyword] += 1
                    keyword_timeline[keyword][date] += 1

        # Chart 1: Top 15 Keywords Over Time
        top_keywords = sorted(all_keywords_count.items(), key=lambda x: x[1], reverse=True)[:15]
        top_keywords = [kw for kw, _ in top_keywords]
        
        for keyword in top_keywords:
            counts = [keyword_timeline[keyword][date] for date in dates]
            label = keyword
            # Add related info if available
            if keyword in keyword_related and keyword_related[keyword]:
                related_preview = ', '.join(keyword_related[keyword][:2])
                label = f"{keyword} ({related_preview}...)" if len(keyword_related[keyword]) > 2 else f"{keyword} ({related_preview})"
            ax1.plot(range(len(dates)), counts, marker='o', label=label, linewidth=2, markersize=5)
        
        ax1.set_title(f'熱門投資主題趨勢 (Top 15, {days}天)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('日期', fontsize=11)
        ax1.set_ylabel('提及次數', fontsize=11)
        ax1.set_xticks(range(len(dates)))
        ax1.set_xticklabels(dates, rotation=45, ha='right')
        ax1.legend(loc='upper left', bbox_to_anchor=(1.05, 1), fontsize=8)
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
        
        bars = ax2.barh(range(len(keywords)), momentums, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)
        ax2.set_yticks(range(len(keywords)))
        ax2.set_yticklabels(keywords, fontsize=10)
        ax2.set_xlabel('動能變化 (近期-先前)', fontsize=11)
        ax2.set_title('投資主題動能排行', fontsize=14, fontweight='bold')
        ax2.axvline(x=0, color='black', linestyle='-', linewidth=1)
        ax2.grid(True, alpha=0.3, axis='x')
        
        # Add momentum indicators and value labels
        xlim = ax2.get_xlim()
        x_range = abs(xlim[1] - xlim[0])
        
        for i, (kw, momentum) in enumerate(zip(keywords, momentums)):
            # Momentum arrow (positioned further from bar end)
            if momentum > 0.5:
                arrow_x = momentum + x_range * 0.08
                ax2.text(arrow_x, i, "▲", va='center', fontsize=12, color='red', fontweight='bold')
                # Value label (closer to bar end)
                ax2.text(momentum + x_range * 0.01, i, f' +{momentum:.1f}', va='center', fontsize=9, fontweight='bold')
            elif momentum < -0.5:
                arrow_x = momentum - x_range * 0.08
                ax2.text(arrow_x, i, "▼", va='center', ha='right', fontsize=12, color='blue', fontweight='bold')
                # Value label (closer to bar end)
                ax2.text(momentum - x_range * 0.01, i, f' {momentum:.1f}', va='center', ha='right', fontsize=9, fontweight='bold')
            else:
                # No arrow, just value label
                if momentum > 0:
                    ax2.text(momentum + x_range * 0.01, i, f' +{momentum:.1f}', va='center', fontsize=9, fontweight='bold')
                else:
                    ax2.text(momentum - x_range * 0.01, i, f' {momentum:.1f}', va='center', ha='right', fontsize=9, fontweight='bold')
        
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
