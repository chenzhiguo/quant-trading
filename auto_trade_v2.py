#!/usr/bin/env python3
"""
自动交易执行器 (支持Regime动态切换)

功能：
1. 识别市场状态 (Regime Detector)
2. 动态选择策略 (Alpha101 / MeanReversion)
3. 自动执行交易

使用方式：
    # 扫描信号并自动执行 (默认大师共识池)
    python auto_trade_v2.py
    
    # 仅扫描不执行
    python auto_trade_v2.py --preview
"""
import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.data import get_fetcher
from core.trader import get_trader
from core.risk import RiskConfig
from core.regime import RegimeDetector, MarketRegime
from strategies.mean_reversion import MeanReversionStrategy
from strategies.alpha101 import Alpha101Strategy
from strategies.base import Signal, TradeSignal
from config.watchlist import get_watchlist
import pandas as pd

def load_risk_config() -> RiskConfig:
    config_path = os.path.join(os.path.dirname(__file__), "config", "risk_config.json")
    return RiskConfig.from_file(config_path)

def scan_and_execute(
    watchlist: str = "us_consensus",
    max_buy_orders: int = 2,
    preview: bool = False,
    dry_run: bool = False
):
    print("=" * 60)
    print(f"🧠 动态智能交易 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化组件
    risk_config = load_risk_config()
    trader = get_trader(dry_run=dry_run, risk_config=risk_config)
    fetcher = get_fetcher()
    detector = RegimeDetector()
    
    # 策略池
    strategy_mr = MeanReversionStrategy(min_drop=-10.0, rsi_oversold=35)
    strategy_alpha = Alpha101Strategy(period="W")
    
    symbols = get_watchlist(watchlist)
    print(f"📋 监控: {len(symbols)} 只股票 ({watchlist})")
    
    # 获取持仓信息（用于去重和卖出验证）
    positions = trader.get_positions()
    held_symbols = {p["symbol"] for p in positions}
    position_map = {p["symbol"]: p for p in positions}
    
    buy_signals = []
    sell_signals = []
    
    print("\n🔍 逐个分析股票状态与信号...")
    
    for symbol in symbols:
        try:
            # 1. 获取数据 (200天)
            df_list = fetcher.get_kline_df(symbol, days=200)
            if not df_list or len(df_list) < 50:
                continue
            
            df = pd.DataFrame(df_list)
            
            # 2. 识别状态
            regime = detector.analyze(symbol, df)
            
            # 3. 动态策略选择
            signal = None
            strategy_name = ""
            
            if regime.adx > 25:
                # === 强趋势模式 ===
                strategy_name = "Alpha101(趋势)"
                raw_signal = strategy_alpha.analyze(symbol, df_list)
                
                # 过滤：只做顺势
                if regime.regime == MarketRegime.TRENDING_UP and raw_signal.signal == Signal.BUY:
                    signal = raw_signal
                    signal.reason = f"[顺势追涨] {signal.reason}"
                elif regime.regime == MarketRegime.TRENDING_DOWN and raw_signal.signal == Signal.SELL:
                    signal = raw_signal
                    signal.reason = f"[顺势止损] {signal.reason}"
                    
            else:
                # === 震荡模式 ===
                strategy_name = "MeanReversion(震荡)"
                raw_signal = strategy_mr.analyze(symbol, df_list)
                signal = raw_signal
                if signal.signal == Signal.BUY:
                    signal.reason = f"[震荡抄底] {signal.reason}"
                elif signal.signal == Signal.SELL:
                    signal.reason = f"[震荡高抛] {signal.reason}"
            
            # 4. 信号分类
            if signal and signal.signal in [Signal.BUY, Signal.SELL]:
                print(f"   📊 {symbol:<8} | 状态: {regime.description[:10]}.. | 策略: {strategy_name} -> {signal.signal.value}")
                
                if signal.signal == Signal.BUY:
                    if symbol not in held_symbols:
                        buy_signals.append(signal)
                elif signal.signal == Signal.SELL:
                    if symbol in held_symbols:
                        sell_signals.append(signal)
                        
        except Exception as e:
            # print(f"Error {symbol}: {e}")
            pass

    # 5. 执行阶段
    print(f"\n💡 决策: 待买入 {len(buy_signals)} | 待卖出 {len(sell_signals)}")
    
    # 先处理卖出
    for signal in sell_signals:
        if preview:
            print(f"   [预览卖出] {signal.symbol} @ {signal.price} | {signal.reason}")
            continue
            
        print(f"   📉 执行卖出: {signal.symbol}")
        pos = position_map.get(signal.symbol)
        trader.submit_order(
            symbol=signal.symbol, 
            side="sell", 
            quantity=pos["available"], 
            price=signal.price
        )
        
    # 再处理买入 (限制数量)
    executed_buys = 0
    # 按置信度排序
    buy_signals.sort(key=lambda x: -x.confidence)
    
    for signal in buy_signals:
        if executed_buys >= max_buy_orders:
            print(f"   ⚠️ 跳过买入 {signal.symbol}: 达到单次最大买入数 ({max_buy_orders})")
            continue
            
        if preview:
            print(f"   [预览买入] {signal.symbol} @ {signal.price} | {signal.reason}")
            executed_buys += 1
            continue
            
        print(f"   📈 执行买入: {signal.symbol} | {signal.reason}")
        trader.submit_order_with_size(
            symbol=signal.symbol,
            side="buy",
            price=signal.price
        )
        executed_buys += 1

    print("\n✅ 完成")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", "-p", action="store_true", help="预览模式")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Dry Run")
    parser.add_argument("--list", "-l", default="us_consensus", help="股票池")
    parser.add_argument("--max-buy", "-m", type=int, default=2, help="最大买入数")
    args = parser.parse_args()
    
    scan_and_execute(
        watchlist=args.list,
        max_buy_orders=args.max_buy,
        preview=args.preview,
        dry_run=args.dry_run
    )

if __name__ == "__main__":
    main()
