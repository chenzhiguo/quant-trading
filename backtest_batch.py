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

# from backtest.engine import run_backtest # This import will be removed as we are inlining its logic
# from backtest.strategies.regime_switching import BT_RegimeSwitchingStrategy # This will also be removed
from core.history_manager import get_history_manager
from config.watchlist import get_watchlist

import numpy as np
import importlib.util
import importlib.machinery


# 新的 PandasData 定义 (从 run_batch_backtest 内部移到这里)
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

# 日志文件存储目录
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_logs")
os.makedirs(LOG_DIR, exist_ok=True) # 确保日志目录存在


def analyze_volatility(df):
    """计算年化波动率"""
    if df is None or len(df) < 30:
        return 0.0
    
    # 计算日收益率
    df['returns'] = df['close'].pct_change()
    
    # 计算波动率 (年化)
    volatility = df['returns'].std() * np.sqrt(252)
    return volatility


def run_batch_backtest(symbols, days=730, start_cash=40000.0, use_risk_config=True, offline=False, strategy_name="regime_switching"): # Add strategy_name parameter
    results = []
    history = get_history_manager()
    
    print(f"🚀 开始批量回测: 共 {len(symbols)} 只股票")
    print(f"💰 初始本金: ${start_cash:,.2f} | 仓位模式: 80% (全仓)")
    print("-" * 60)

    # 动态加载策略
    STRATEGIES_MAP = {
        "regime_switching": {"module": "regime_switching", "class": "BT_RegimeSwitchingStrategy"},
        "momentum": {"module": "momentum", "class": "MomentumStrategy"},
        "mean_reversion": {"module": "mean_reversion", "class": "MeanReversionStrategy"},
    }

    if strategy_name not in STRATEGIES_MAP:
        raise ValueError(f"未知策略名称: {strategy_name}. 可选: {list(STRATEGIES_MAP.keys())}")

    strategy_info = STRATEGIES_MAP[strategy_name]
    strategy_class_name = strategy_info['class']
    
    # 动态加载策略模块
    # 构建策略文件的绝对路径
    strategy_file_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), # quant-trading 目录
        "strategies", f"{strategy_info['module']}.py" # backtest/strategies/<module_name>.py
    )
    
    # 创建模块加载器
    try:
        # 为了避免循环引用或重复导入，检查模块是否已经被加载
        if strategy_info['module'] in sys.modules:
            strategy_module = sys.modules[strategy_info['module']]
        else:
            spec = importlib.util.spec_from_file_location(strategy_info['module'], strategy_file_path)
            if spec is None:
                raise ImportError(f"无法找到模块规范: {strategy_file_path}")
            strategy_module = importlib.util.module_from_spec(spec)
            sys.modules[strategy_info['module']] = strategy_module
            spec.loader.exec_module(strategy_module)

        SelectedStrategy = getattr(strategy_module, strategy_class_name)
        print(f"✅ 成功加载策略: {strategy_class_name} from {strategy_file_path}")
    except Exception as e:
        raise ImportError(f"无法加载策略 {strategy_class_name} from {strategy_file_path}: {e}")
    
    for symbol in symbols:
        try:
            # 1. 获取数据
            if offline:
                df = history.load_local_data(symbol)
            else:
                df = history.fetch_and_update(symbol, days=days)
            
            if df is None or len(df) < 100:
                print(f"Skipping {symbol} due to insufficient data (len={len(df)})")
                continue
            print(f"Data for {symbol}: len={len(df)}, head=\n{df.head()}\n, tail=\n{df.tail()}")
            
            # 2. 波动率分析与模式选择
            # 注意: 如果是非 RegimeSwitching 策略，这里的风险模式可能需要调整或移除
            vol = analyze_volatility(df)
            
            # 阈值: 40% 波动率
            if vol > 0.40:
                risk_mode = 'atr_trailing'
                mode_desc = "🔥 高波 (ATR+追踪)"
            else:
                risk_mode = 'fixed'
                mode_desc = "🛡️ 稳健 (固定止损)"
            
            # 由于目前波动率分析和 risk_mode 仅用于 RegimeSwitchingStrategy 的日志描述，
            # 对于其他策略可以简化或移除这部分，此处为保持原逻辑先保留
            # 对于非 RegimeSwitching 策略，这里的 mode_desc 可能不准确
            if strategy_name == "regime_switching":
                 print(f"\n>> 回测: {symbol} (波动率: {vol:.1%}) -> {mode_desc}")
            else:
                 print(f"\n>> 回测: {symbol} (策略: {strategy_name})")

            # ------- 新的 Backtrader 运行逻辑开始 -------
            cerebro = bt.Cerebro()
            
            # 1. 添加策略
            cerebro.addstrategy(SelectedStrategy) 
            
            # 2. 添加数据
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            
            data = PandasData(dataname=df)
            cerebro.adddata(data, name=symbol) # Pass name for bt.Strategy._name

            # 3. 设置资金
            cerebro.broker.setcash(start_cash)
            cerebro.broker.setcommission(commission=0.001)
            cerebro.addsizer(bt.sizers.PercentSizer, percents=80) # Addsizer here
            
            # 4. 添加分析器
            cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
            cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
            cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
            
            # 5. 运行
            print(f"🚀 开始回测: {symbol}")
            strats = cerebro.run()
            strat = strats[0]
            # ------- 新的 Backtrader 运行逻辑结束 -------
            
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
    parser.add_argument("--strategy", "-s", default="regime_switching", 
                        choices=["regime_switching", "momentum", "mean_reversion"],
                        help="选择回测策略 (regime_switching, momentum, mean_reversion)")
    parser.add_argument("--symbols", "-sym", type=str, help="指定单个或多个股票符号进行回测，用逗号分隔 (例如: GOOGL.US,MSFT.US)") # <--- 新增
    
    args = parser.parse_args()
    
    # 获取股票池
    if args.symbols: # 如果指定了 --symbols 参数，则使用指定的股票
        symbols = [s.strip() for s in args.symbols.split(',')]
    else: # 否则使用 --list 参数指定的股票池
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
    results = run_batch_backtest(symbols, days=args.days, start_cash=args.cash, 
                                 offline=args.offline, strategy_name=args.strategy) # <-- 传递 strategy_name
    
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
