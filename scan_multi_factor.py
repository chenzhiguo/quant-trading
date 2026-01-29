#!/usr/bin/env ./venv/bin/python3
"""
多因子策略扫描脚本

执行 Value + Momentum + Quality 综合选股
"""
import os
import sys
import json
import argparse
from datetime import datetime

# 尝试导入 tabulate
try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.data import get_fetcher
from strategies.multi_factor import MultiFactorStrategy, MultiFactorConfig
from config.watchlist import get_watchlist, list_categories


def scan_multi_factor(category: str = "us_tech", top_n: int = 10):
    """
    扫描多因子策略
    """
    print(f"📊 正在扫描: {category} (Top {top_n})...")
    
    # 1. 获取股票列表
    symbols = get_watchlist(category)
    if not symbols:
        print(f"❌ 未找到分类 {category} 的股票列表")
        return
    
    print(f"📋 股票池: {len(symbols)} 只")
    
    # 2. 获取数据
    fetcher = get_fetcher()
    print("📥 正在获取数据 (包含 K线、基本面)...")
    
    try:
        stocks_data = fetcher.get_multi_factor_data(symbols)
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"✅ 获取到 {len(stocks_data)} 条有效数据")
    
    # 3. 运行策略
    config = MultiFactorConfig(top_n=top_n)
    strategy = MultiFactorStrategy(config)
    
    print("🧠正在计算因子得分...")
    ranked_stocks = strategy.calculate_score(stocks_data)
    
    # 4. 输出结果
    print("\n🏆 多因子选股结果 (VMQ Model):")
    print("=" * 100)
    
    table_data = []
    for i, s in enumerate(ranked_stocks, 1):
        # 格式化数据
        market_cap_b = s.get('market_cap', 0) / 100_000_000 # 亿
        
        table_data.append([
            i,
            s['symbol'],
            f"{s['price']:.2f}",
            f"{s['total_score']:.1f}",
            f"{s['pe_ttm']:.1f}",
            f"{s['pb']:.2f}",
            f"{s['roe']:.1%}",
            f"{s['debt_to_equity']:.2f}",
            f"{s['mom_12m']:.1%}",
            f"{market_cap_b:.1f}亿"
        ])
        
    headers = ["Rank", "Symbol", "Price", "Score", "PE", "PB", "ROE", "D/E", "Mom(12m)", "Mkt Cap"]
    
    if HAS_TABULATE:
        print(tabulate(table_data, headers=headers, tablefmt="simple"))
    else:
        # Fallback simple print
        print(f"{'Rank':<5} {'Symbol':<10} {'Price':<10} {'Score':<8} {'PE':<8} {'PB':<8} {'ROE':<8} {'D/E':<8} {'Mom':<8} {'Mkt Cap'}")
        print("-" * 100)
        for row in table_data:
            # row: [rank, symbol, price, score, pe, pb, roe, de, mom, mkt_cap]
            print(f"{row[0]:<5} {row[1]:<10} {row[2]:<10} {row[3]:<8} {row[4]:<8} {row[5]:<8} {row[6]:<8} {row[7]:<8} {row[8]:<8} {row[9]}")
            
    print("=" * 100)
    
    # 因子解释
    print("\nℹ️  因子说明:")
    print("   • Value (30%): 低PE, 低PB")
    print("   • Momentum (40%): 高12月动量 (均线之上)")
    print("   • Quality (30%): 高ROE, 低负债率")
    
    return ranked_stocks


def main():
    parser = argparse.ArgumentParser(description="多因子选股扫描")
    parser.add_argument("--list", "-l", type=str, default="us_tech", help=f"股票池分类: {list(list_categories().keys())}")
    parser.add_argument("--top", "-n", type=int, default=10, help="显示数量")
    
    args = parser.parse_args()
    
    scan_multi_factor(args.list, args.top)


if __name__ == "__main__":
    main()
