#!/usr/bin/env python3
"""
回测运行脚本 (CSV模式)

当没有实时 API 权限时，使用本地 CSV 进行回测
"""
import os
import sys
import argparse
import pandas as pd

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import run_backtest
from backtest.strategies.adapters import BT_Alpha101Strategy, BT_MeanReversionStrategy

def main():
    parser = argparse.ArgumentParser(description="回测运行器")
    parser.add_argument("--file", "-f", default="mock_NVDA.US.csv", help="CSV数据文件")
    parser.add_argument("--strategy", "-t", choices=["alpha", "meanrev"], default="alpha", help="回测策略")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"❌ 文件不存在: {args.file}")
        print("💡 请先运行: python quant-trading/backtest/mock_data_gen.py")
        return

    # 1. 加载数据
    print(f"📥 加载数据: {args.file}...")
    df = pd.read_csv(args.file)
    print(f"✅ 加载 {len(df)} 条数据")
    
    # 2. 选择策略
    strategy_class = BT_Alpha101Strategy if args.strategy == "alpha" else BT_MeanReversionStrategy
    
    # 3. 运行回测
    symbol = os.path.basename(args.file).replace("mock_", "").replace(".csv", "")
    run_backtest(
        strategy_class=strategy_class,
        data_df=df,
        name=f"{symbol}_{args.strategy}",
        start_cash=100000.0
    )

if __name__ == "__main__":
    main()
