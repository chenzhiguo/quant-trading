#!/usr/bin/env python3
"""
回测运行脚本

使用方式:
    python backtest_runner.py --symbol NVDA.US
"""
import os
import sys
import argparse
import pandas as pd

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import run_backtest
from backtest.strategies.adapters import BT_Alpha101Strategy, BT_MeanReversionStrategy
from core.data import get_fetcher

def main():
    parser = argparse.ArgumentParser(description="回测运行器")
    parser.add_argument("--symbol", "-s", default="NVDA.US", help="回测标的")
    parser.add_argument("--strategy", "-t", choices=["alpha", "meanrev"], default="alpha", help="回测策略")
    parser.add_argument("--days", "-d", type=int, default=365, help="回测天数")
    
    args = parser.parse_args()
    
    # 1. 获取数据
    print(f"📥 获取 {args.symbol} 历史数据 ({args.days}天)...")
    fetcher = get_fetcher()
    
    # 获取数据列表
    data_list = fetcher.get_kline_df(args.symbol, days=args.days)
    if not data_list:
        print("❌ 数据获取失败")
        return
        
    df = pd.DataFrame(data_list)
    print(f"✅ 获取 {len(df)} 条K线数据")
    
    # 2. 选择策略
    strategy_class = BT_Alpha101Strategy if args.strategy == "alpha" else BT_MeanReversionStrategy
    
    # 3. 运行回测
    run_backtest(
        strategy_class=strategy_class,
        data_df=df,
        name=f"{args.symbol}_{args.strategy}",
        start_cash=100000.0
    )

if __name__ == "__main__":
    main()
