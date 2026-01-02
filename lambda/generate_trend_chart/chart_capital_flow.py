from collections import defaultdict
from io import BytesIO

import matplotlib.pyplot as plt


def generate_capital_flow_chart(data, categories):
    """
    圖表 2: 資金撤離或資金建倉訊號
    - Buy/Sell signals from institutional investors

    {
        "date1": {
            "sector1": {
                "buy": 10,
                "sell": 5
            },
            ...
        },
        ...
    }
    """
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        dates = list(sorted(data.keys()))
        days = len(dates)
        all_sectors = sorted(categories)
        
        # Chart 1: Buy vs Sell Pressure Over Time
        total_buy = []
        total_sell = []
        
        for date in dates:
            buy_count = sum(data[date].get(s, {'buy': 0})['buy'] for s in all_sectors)
            sell_count = sum(data[date].get(s, {'sell': 0})['sell'] for s in all_sectors)
            total_buy.append(buy_count)
            total_sell.append(sell_count)
        
        x = range(len(dates))
        width = 0.35
        
        ax1.bar([i - width/2 for i in x], total_buy, width, label='法人買超訊號', color='#06D6A0', alpha=0.8)
        ax1.bar([i + width/2 for i in x], total_sell, width, label='法人賣超訊號', color='#EF476F', alpha=0.8)
        
        ax1.set_title('法人資金動向', fontsize=14, fontweight='bold')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('訊號數量')
        ax1.set_xticks(x)
        ax1.set_xticklabels(dates, rotation=45)
        ax1.legend()
        ax1.grid(True, alpha=0.3, axis='y')
        
        # Chart 2: Sector-specific signals (Latest period aggregate)
        sector_buy_sell = defaultdict(lambda: {'buy': 0, 'sell': 0})
        
        for date in dates:
            for sector in all_sectors:
                behavior = data[date].get(sector, {'buy': 0, 'sell': 0})
                sector_buy_sell[sector]['buy'] += behavior['buy']
                sector_buy_sell[sector]['sell'] += behavior['sell']
        
        # Calculate net buy/sell
        sector_net = []
        sector_labels = []
        
        for sector, behavior in sector_buy_sell.items():
            net = behavior['buy'] - behavior['sell']
            if net != 0:
                sector_net.append(net)
                sector_labels.append(sector)
        
        # Sort by net value
        sorted_pairs = sorted(zip(sector_net, sector_labels), reverse=True)
        sector_net, sector_labels = zip(*sorted_pairs) if sorted_pairs else ([], [])
        
        colors = ['#06D6A0' if n > 0 else '#EF476F' for n in sector_net]
        
        ax2.barh(range(len(sector_labels)), sector_net, color=colors, alpha=0.8)
        ax2.set_yticks(range(len(sector_labels)))
        ax2.set_yticklabels(sector_labels)
        ax2.set_xlabel('淨買超/賣超 (買-賣)')
        ax2.set_title(f'產業法人動向 ({days}天累計)', fontsize=14, fontweight='bold')
        ax2.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax2.grid(True, alpha=0.3, axis='x')
        
        # Add signal indicator
        for i, (net, label) in enumerate(zip(sector_net, sector_labels)):
            signal = "🟢 建倉" if net > 2 else "🔴 撤離" if net < -2 else ""
            if signal:
                ax2.text(net, i, f" {signal}", va='center', fontsize=10, fontweight='bold')
        
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.read()
        plt.close()
        
        return png_bytes
        
    except Exception as e:
        print(f"Error generating capital flow chart: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
