#!/usr/bin/env python3
"""
量化交易主程序

功能：
1. 扫描自选股，生成交易信号
2. 显示账户状态和持仓
3. 执行策略（模拟/实盘）
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from core.data import get_fetcher
from core.trader import get_trader
from strategies.ma_cross import MACrossStrategy
from strategies.momentum import MomentumStrategy
from strategies.base import Signal
from config.watchlist import get_watchlist


def print_header():
    """打印头部"""
    print("=" * 60)
    print("🤖 长桥量化交易系统")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


def show_account():
    """显示账户信息"""
    trader = get_trader()
    
    print("\n💰 账户资金:")
    balances = trader.get_account_balance()
    for b in balances:
        print(f"  {b.currency}: {b.total_cash:,.2f}")
    
    print("\n📊 当前持仓:")
    positions = trader.get_positions()
    if positions:
        for p in positions:
            print(f"  {p['symbol']}: {p['quantity']}股 @ {p['cost_price']:.2f}")
    else:
        print("  (空仓)")


def scan_signals(symbols: list = None, strategy_name: str = "ma"):
    """
    扫描交易信号
    
    Args:
        symbols: 股票列表
        strategy_name: 策略名称 ("ma" / "momentum")
    """
    if symbols is None:
        symbols = get_watchlist("us_tech")
    
    # 选择策略
    if strategy_name == "momentum":
        strategy = MomentumStrategy()
    else:
        strategy = MACrossStrategy(short_period=5, long_period=20)
    
    print(f"\n📈 策略: {strategy.name}")
    print(f"📋 监控: {len(symbols)} 只股票")
    print("-" * 60)
    
    fetcher = get_fetcher()
    
    buy_signals = []
    sell_signals = []
    
    for symbol in symbols:
        try:
            # 获取K线数据
            data = fetcher.get_kline_df(symbol, days=50)
            
            if not data:
                print(f"  ⚠️ {symbol}: 无数据")
                continue
            
            # 生成信号
            signal = strategy.analyze(symbol, data)
            
            if signal.signal == Signal.BUY:
                buy_signals.append(signal)
                print(f"  {signal}")
            elif signal.signal == Signal.SELL:
                sell_signals.append(signal)
                print(f"  {signal}")
            else:
                # HOLD 信号只在 verbose 模式显示
                pass
                
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
    
    # 汇总
    print("-" * 60)
    print(f"✅ 买入信号: {len(buy_signals)} | 🔴 卖出信号: {len(sell_signals)}")
    
    return buy_signals, sell_signals


def show_realtime_quotes(symbols: list = None):
    """显示实时行情"""
    if symbols is None:
        symbols = get_watchlist("us_tech")[:5]
    
    fetcher = get_fetcher()
    quotes = fetcher.get_quote_with_change(symbols)
    
    print(f"\n📊 实时行情 ({len(quotes)}只):")
    print(f"{'股票':<12} {'最新价':<12} {'涨跌幅':<10} {'成交量'}")
    print("-" * 50)
    
    for q in quotes:
        emoji = "🟢" if q["change_pct"] > 0 else "🔴" if q["change_pct"] < 0 else "⚪"
        print(f"{q['symbol']:<12} ${q['price']:<11.2f} {emoji}{q['change_pct']:>+5.2f}%    {q['volume']:,}")


def main():
    """主函数"""
    print_header()
    
    # 显示账户
    show_account()
    
    # 显示实时行情
    show_realtime_quotes()
    
    # 扫描信号
    print("\n" + "=" * 60)
    print("🔍 信号扫描")
    print("=" * 60)
    
    # 使用均线策略扫描
    buy_signals, sell_signals = scan_signals(strategy_name="ma")
    
    # 使用动量策略扫描
    print()
    buy_signals2, sell_signals2 = scan_signals(strategy_name="momentum")
    
    print("\n" + "=" * 60)
    print("✅ 扫描完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
