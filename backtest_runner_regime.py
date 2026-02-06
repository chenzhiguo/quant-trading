#!/usr/bin/env python3
"""
回测运行器 (Regime Switching 专用)
"""
import os
import sys
import argparse
import pandas as pd
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import run_backtest
from backtest.strategies.regime_switching import BT_RegimeSwitchingStrategy
# 复用之前的 yahoo 下载函数
from backtest_runner_yf import download_yahoo_data

def main():
    parser = argparse.ArgumentParser(description="回测运行器 (Regime Switching)")
    parser.add_argument("--symbol", "-s", default="NVDA.US", help="回测标的")
    parser.add_argument("--days", "-d", type=int, default=730, help="回测天数")
    
    args = parser.parse_args()
    
    # 1. 获取数据
    df = download_yahoo_data(args.symbol, days=args.days)
    if df is None:
        return
        
    print(f"✅ 获取 {len(df)} 条K线数据")
    
    # 2. 运行回测 (使用 Regime Switching 策略)
    run_backtest(
        strategy_class=BT_RegimeSwitchingStrategy,
        data_df=df,
        name=f"{args.symbol}_RegimeSwitching",
        start_cash=100000.0,
        # 传入策略参数
        adx_threshold=25,
        rsi_oversold=35,
        rsi_overbought=65
    )

if __name__ == "__main__":
    main()
