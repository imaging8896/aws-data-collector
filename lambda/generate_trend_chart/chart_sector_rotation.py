from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np

from matplotlib.patches import Patch


def generate_sector_rotation_chart(data, categories):
    """
    圖表 1: 資金在產業輪動的趨勢
    - Sankey-like flow diagram showing capital rotation between sectors

    {
        "date1": {
            "sector1": {
                "inflow": 10,
                "outflow": 5,
                "count": 15
            },
            ...
        },
        ...
    }
    """
    try:
        fig = plt.figure(figsize=(18, 12))
        gs = fig.add_gridspec(3, 2, height_ratios=[2, 1.5, 0.5], hspace=0.3, wspace=0.3)
        ax1 = fig.add_subplot(gs[0, :])
        ax2 = fig.add_subplot(gs[1, 0])
        ax3 = fig.add_subplot(gs[1, 1])
        ax_legend = fig.add_subplot(gs[2, :])
        ax_legend.axis('off')
        
        days = len(data)
        dates = list(sorted(data.keys()))
        all_sectors = sorted(categories)
        
        # Define distinct color palette for sectors
        sector_colors = {
            '半導體與晶片': '#E63946',      # Red
            'AI與伺服器': '#F77F00',        # Orange
            '電子零組件與散熱': '#FCBF49',  # Yellow
            '電動車與車用電子': '#06D6A0',  # Teal
            '網通與光通訊': '#118AB2',      # Blue
            '機器人與自動化': '#073B4C',    # Dark Blue
            '金融': '#8338EC',              # Purple
            '消費性電子': '#FF006E',        # Magenta
            '能源與重電': '#FB5607',        # Burnt Orange
            '房地產與營建': '#FFBE0B',      # Gold
            '生技醫療': '#3A86FF',          # Bright Blue
            '航運與物流': '#8AC926',        # Green
            '原物料與鋼鐵': '#6A4C93',      # Deep Purple
            '其他': '#999999'                # Gray
        }
        
        # Fallback colors for any missing categories
        default_colors = plt.cm.tab20(np.linspace(0, 1, 20))
        colors = []
        for i, sector in enumerate(all_sectors):
            if sector in sector_colors:
                # Convert hex to RGB
                hex_color = sector_colors[sector]
                rgb = tuple(int(hex_color.lstrip('#')[i:i+2], 16)/255 for i in (0, 2, 4))
                colors.append(rgb + (1.0,))  # Add alpha channel
            else:
                colors.append(default_colors[i % 20])
        
        # Chart 1: Net Flow by Sector Over Time
        sector_net_flows = {sector: [] for sector in all_sectors}
        
        for date in dates:
            for sector in all_sectors:
                rotation_data = data[date].get(sector, {'inflow': 0, 'outflow': 0})
                net_flow = rotation_data['inflow'] - rotation_data['outflow']
                sector_net_flows[sector].append(int(net_flow))
        
        # Plot stacked area chart
        x = range(len(dates))
        bottom_positive = [0] * len(dates)
        bottom_negative = [0] * len(dates)
        
        # Store handles for custom legend
        legend_handles = []
        
        for i, sector in enumerate(all_sectors):
            flows = sector_net_flows[sector]
            positive_flows = [max(0, f) for f in flows]
            negative_flows = [min(0, f) for f in flows]
            
            # Use edgecolor to make boundaries clearer
            p1 = ax1.fill_between(x, bottom_positive, [bottom_positive[j] + positive_flows[j] for j in range(len(x))],
                            alpha=0.85, color=colors[i], edgecolor='white', linewidth=0.5)
            bottom_positive = [bottom_positive[j] + positive_flows[j] for j in range(len(x))]
            
            ax1.fill_between(x, bottom_negative, [bottom_negative[j] + negative_flows[j] for j in range(len(x))],
                            alpha=0.85, color=colors[i], edgecolor='white', linewidth=0.5)
            bottom_negative = [bottom_negative[j] + negative_flows[j] for j in range(len(x))]
            
            # Create legend handle
            
            legend_handles.append(Patch(facecolor=colors[i], edgecolor='white', label=sector))
        
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=1.5)
        ax1.set_title(f'產業資金輪動趨勢 ({days}天)', fontsize=16, fontweight='bold', pad=15)
        ax1.set_xlabel('日期', fontsize=12)
        ax1.set_ylabel('資金流向 (流入-流出)', fontsize=12)
        ax1.set_xticks(x)
        ax1.set_xticklabels(dates, rotation=45, ha='right')
        ax1.grid(True, alpha=0.3, linestyle='--')
        
        # Chart 2: Current Rotation Status (Latest Day)
        latest_date = dates[-1]
        latest_rotation = data[latest_date]
        
        sectors = []
        inflows = []
        outflows = []
        sector_colors_list = []
        
        for i, sector in enumerate(all_sectors):
            rotation_data = latest_rotation.get(sector, {'inflow': 0, 'outflow': 0})
            if rotation_data['inflow'] > 0 or rotation_data['outflow'] > 0:
                sectors.append(sector)
                inflows.append(rotation_data['inflow'])
                outflows.append(-rotation_data['outflow'])  # Negative for left side
                sector_colors_list.append(colors[all_sectors.index(sector)])
        
        y_pos = np.arange(len(sectors))
        
        ax2.barh(y_pos, outflows, color='#EF476F', label='資金流出', alpha=0.8, edgecolor='white', linewidth=0.5)
        ax2.barh(y_pos, inflows, color='#06D6A0', label='資金流入', alpha=0.8, edgecolor='white', linewidth=0.5)
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(sectors, fontsize=10)
        ax2.set_xlabel('新聞數量', fontsize=11)
        ax2.set_title(f'最新資金流向 ({latest_date})', fontsize=13, fontweight='bold')
        ax2.axvline(x=0, color='black', linestyle='-', linewidth=1)
        ax2.legend(fontsize=10)
        ax2.grid(True, alpha=0.3, axis='x', linestyle='--')
        
        # Chart 3: Sector-wise color reference (top movers)
        # Calculate total net flow for each sector
        sector_total_flow = {}
        for sector in all_sectors:
            total = sum(sector_net_flows[sector])
            if total != 0:
                sector_total_flow[sector] = total
        
        # Sort by absolute value and take top 10
        top_sectors = sorted(sector_total_flow.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
        
        if top_sectors:
            top_sector_names = [s[0] for s in top_sectors]
            top_sector_flows = [s[1] for s in top_sectors]
            top_sector_colors = [colors[all_sectors.index(s[0])] for s in top_sectors]
            
            bars = ax3.barh(range(len(top_sector_names)), top_sector_flows, 
                          color=top_sector_colors, alpha=0.85, edgecolor='white', linewidth=1)
            ax3.set_yticks(range(len(top_sector_names)))
            ax3.set_yticklabels(top_sector_names, fontsize=10)
            ax3.set_xlabel('累積淨流向', fontsize=11)
            ax3.set_title('產業累積資金流向 Top 10', fontsize=13, fontweight='bold')
            ax3.axvline(x=0, color='black', linestyle='-', linewidth=1)
            ax3.grid(True, alpha=0.3, axis='x', linestyle='--')
            
            # Add value labels on bars
            for i, (bar, value) in enumerate(zip(bars, top_sector_flows)):
                if value > 0:
                    ax3.text(value, i, f' +{value}', va='center', fontsize=9, fontweight='bold')
                else:
                    ax3.text(value, i, f' {value}', va='center', ha='right', fontsize=9, fontweight='bold')
        
        # Custom legend at bottom with better layout
        ncol = min(5, len(legend_handles))
        ax_legend.legend(handles=legend_handles, loc='center', ncol=ncol, 
                        frameon=True, fontsize=10, title='產業類別',
                        title_fontsize=11, columnspacing=1.5, handlelength=2)
        
        plt.suptitle('產業資金輪動分析', fontsize=18, fontweight='bold', y=0.98)
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=120, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        png_bytes = buffer.read()
        plt.close()
        
        return png_bytes
        
    except Exception as e:
        print(f"Error generating sector rotation chart: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
