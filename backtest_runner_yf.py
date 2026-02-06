#!/usr/bin/env python3
"""
回测运行脚本 (使用 Yahoo Finance 数据)
"""
import os
import sys
import argparse
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import run_backtest
from backtest.strategies.adapters import BT_Alpha101Strategy, BT_MeanReversionStrategy

def download_yahoo_data(symbol, days=365):
    """从 Yahoo Finance 下载数据并清洗"""
    print(f"📥 从 Yahoo Finance 下载 {symbol} 过去 {days} 天数据...")
    
    # yfinance symbol 可能需要去掉后缀或转换
    # 比如 NVDA.US -> NVDA
    yf_symbol = symbol.replace(".US", "").replace(".HK", ".HK") # 港股需要保留 .HK
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    try:
        df = yf.download(yf_symbol, start=start_date, end=end_date, progress=False)
        
        if df.empty:
            print("❌ 数据为空")
            return None
            
        # ⚠️ yfinance 返回的 MultiIndex 列名处理
        # 比如 ('Close', 'NVDA') -> 'close'
        if isinstance(df.columns, pd.MultiIndex):
            # 将列名扁平化
            # 我们只需要第一层 (Open, High, Low, Close, Volume)
            # 但要确认是否包含 Ticker
            df.columns = df.columns.get_level_values(0)
            
        # 统一转为小写
        df.columns = [c.lower() for c in df.columns]
        
        # 确保包含我们需要的列
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]
        if missing:
            print(f"❌ 缺少必要列: {missing}")
            return None
            
        # 重置索引，让 Date 变成列 (run_backtest 会再把它设回索引)
        df.reset_index(inplace=True)
        # 确保日期列名为 'date' (yfinance 默认是 'Date')
        if 'Date' in df.columns:
            df.rename(columns={'Date': 'date'}, inplace=True)
            
        # 打印部分数据验证
        # print(df.head())
        # print(df.tail())
        
        return df
        
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="回测运行器 (Yahoo源)")
    parser.add_argument("--symbol", "-s", default="NVDA.US", help="回测标的")
    parser.add_argument("--strategy", "-t", choices=["alpha", "meanrev"], default="alpha", help="回测策略")
    parser.add_argument("--days", "-d", type=int, default=730, help="回测天数 (默认2年)")
    
    args = parser.parse_args()
    
    # 1. 获取数据 (Yahoo)
    df = download_yahoo_data(args.symbol, days=args.days)
    if df is None:
        return
        
    print(f"✅ 获取 {len(df)} 条K线数据")
    
    # 2. 选择策略
    strategy_class = BT_Alpha101Strategy if args.strategy == "alpha" else BT_MeanReversionStrategy
    
    # 3. 运行回测
    run_backtest(
        strategy_class=strategy_class,
        data_df=df,
        name=f"{args.symbol}_{args.strategy}_yf",
        start_cash=100000.0
    )

if __name__ == "__main__":
    main()
