#!/usr/bin/env python3
"""
批量回测运行器 (Regime Switching)
"""
import os
import sys
import argparse
import pandas as pd
from datetime import datetime
import backtrader as bt
import matplotlib
matplotlib.use('Agg')

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest.engine import run_backtest
from backtest.strategies.regime_switching import BT_RegimeSwitchingStrategy
# from backtest_runner_yf import download_yahoo_data # 替换为 HistoryManager
from core.history_manager import get_history_manager
from config.watchlist import get_watchlist

import numpy as np

def analyze_volatility(df):
    """计算年化波动率"""
    if df is None or len(df) < 30:
        return 0.0
    
    # 计算日收益率
    df['returns'] = df['close'].pct_change()
    
    # 计算波动率 (年化)
    volatility = df['returns'].std() * np.sqrt(252)
    return volatility

def run_batch_backtest(symbols, days=730, start_cash=40000.0, use_risk_config=True, offline=False):
    results = []
    history = get_history_manager()
    
    print(f"🚀 开始批量回测: 共 {len(symbols)} 只股票")
    print(f"💰 初始本金: ${start_cash:,.2f} | 仓位模式: 80% (全仓)")
    print("-" * 60)
    
    for symbol in symbols:
        try:
            # 1. 获取数据
            if offline:
                df = history.load_local_data(symbol)
            else:
                df = history.fetch_and_update(symbol, days=days)
            
            if df is None or len(df) < 100:
                continue
                
            # 2. 波动率分析与模式选择
            vol = analyze_volatility(df)
            
            # 阈值: 40% 波动率
            if vol > 0.40:
                risk_mode = 'atr_trailing'
                mode_desc = "🔥 高波 (ATR+追踪)"
            else:
                risk_mode = 'fixed'
                mode_desc = "🛡️ 稳健 (固定止损)"
            
            print(f"\n>> 回测: {symbol} (波动率: {vol:.1%}) -> {mode_desc}")
            
            # 3. 运行回测
            cerebro = bt.Cerebro()
            
            cerebro.addstrategy(
                BT_RegimeSwitchingStrategy,
                adx_threshold=30,
                adx_wait_threshold=20,
                rsi_oversold=30,
                rsi_overbought=70,
                atr_multiplier=3.0,
                trailing_start_pct=0.05,
                trailing_stop_pct=0.05
            )
            
            cerebro.addsizer(bt.sizers.PercentSizer, percents=80)
            
            # ... Data Feed ...
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            
            class PandasData(bt.feeds.PandasData):
                params = (
                    ('datetime', None),
                    ('open', 'open'),
                    ('high', 'high'),
                    ('low', 'low'),
                    ('close', 'close'),
                    ('volume', 'volume'),
                    ('openinterest', -1),
                )
            
            data = PandasData(dataname=df)
            cerebro.adddata(data)
            
            cerebro.broker.setcash(start_cash)
            cerebro.broker.setcommission(commission=0.001)
            
            # ... Running ...
            
            # 分析器
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
            
            # 运行
            strats = cerebro.run()
            strat = strats[0]
            
            # 收集结果
            final_value = cerebro.broker.getvalue()
            pnl_pct = (final_value - start_cash) / start_cash
            
            trades = strat.analyzers.trades.get_analysis()
            total_trades = trades.get('total', {}).get('total', 0)
            win_rate = 0
            if trades.get('total', {}).get('closed', 0) > 0:
                win_rate = trades.get('won', {}).get('total', 0) / trades.get('total', {}).get('closed', 0)
            
            max_dd = strat.analyzers.drawdown.get_analysis()['max']['drawdown']
            sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio', 0)
            if sharpe is None: sharpe = 0
            
            results.append({
                "Symbol": symbol,
                "Return": pnl_pct,
                "Trades": total_trades,
                "WinRate": win_rate,
                "MaxDD": max_dd,
                "Sharpe": sharpe
            })
            
        except Exception as e:
            print(f"❌ {symbol} 回测出错: {e}")

    return results

def main():
    parser = argparse.ArgumentParser(description="批量回测工具")
    parser.add_argument("--list", "-l", default="us_tech", help="股票池 (us_tech, us_ai, cn_adr...)")
    parser.add_argument("--days", "-d", type=int, default=730, help="回测天数")
    parser.add_argument("--cash", "-c", type=float, default=40000.0, help="初始本金")
    parser.add_argument("--offline", action="store_true", help="仅使用本地缓存数据")
    
    args = parser.parse_args()
    
    # 获取股票池
    symbols = get_watchlist(args.list)
    
    # offline 模式: 只用缓存的股票
    if args.offline:
        import glob
        cached_files = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "history", "*.csv"))
        cached_symbols = set()
        for f in cached_files:
            name = os.path.basename(f).replace(".csv", "").replace("_", ".")
            cached_symbols.add(name)
        symbols = [s for s in symbols if s in cached_symbols]
        print(f"📂 离线模式: 使用本地缓存 ({len(symbols)} 只)")
    
    # 运行批量回测
    results = run_batch_backtest(symbols, days=args.days, start_cash=args.cash, offline=args.offline)
    
    # 输出汇总报告
    if results:
        df_res = pd.DataFrame(results)
        
        # 格式化
        df_res['Return'] = df_res['Return'].apply(lambda x: f"{x:+.2%}")
        df_res['WinRate'] = df_res['WinRate'].apply(lambda x: f"{x:.1%}")
        df_res['MaxDD'] = df_res['MaxDD'].apply(lambda x: f"{x:.2f}%")
        df_res['Sharpe'] = df_res['Sharpe'].apply(lambda x: f"{x:.2f}")
        
        print("\n" + "="*60)
        print("📊 批量回测结果汇总 (全仓模式 + 混合止损)")
        print("="*60)
        print(df_res.to_string(index=False))
        print("="*60)
    else:
        print("❌ 未生成任何结果")

if __name__ == "__main__":
    main()
