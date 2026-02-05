#!/usr/bin/env python3
"""
动态状态策略扫描 (Regime-based Scanning)

根据市场状态动态选择策略：
1. 强趋势市 (ADX>25) -> 使用 Alpha 101 / Momentum
2. 震荡市 (ADX<20) -> 使用 Mean Reversion

输出：
- 📈 顺势追涨：强趋势 + Alpha 信号
- 📉 逆势抄底：震荡/弱势 + 超卖信号
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.data import get_fetcher
from core.regime import RegimeDetector, MarketRegime
from strategies.mean_reversion import MeanReversionStrategy
from strategies.alpha101 import Alpha101Strategy
from strategies.base import Signal
from config.watchlist import get_watchlist

def scan_dynamic(category: str = "all", top_n: int = 30):
    """
    动态策略扫描
    """
    print("=" * 80)
    print(f"🧭 动态趋势策略扫描 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    symbols = get_watchlist(category)
    fetcher = get_fetcher()
    detector = RegimeDetector()
    
    # 初始化策略
    strategy_mr = MeanReversionStrategy()
    strategy_alpha = Alpha101Strategy(period="W")
    
    results_trend = []   # 趋势信号
    results_reversion = [] # 回归信号
    
    print(f"🔍 扫描 {len(symbols)} 只股票的状态...\n")
    
    print(f"{'股票':<10} {'价格':>8} {'状态':<15} {'ADX':>5} {'策略':<12} {'信号':<20}")
    print("-" * 80)
    
    for symbol in symbols:
        try:
            # 1. 获取数据 (200天以计算周线和ADX)
            df = fetcher.get_kline_df(symbol, days=200)
            if not df or len(df) < 50:
                continue
                
            current_price = df['close'].iloc[-1]
                
            # 2. 识别市场状态
            # get_kline_df 返回的是 list of dict，需要转换
            df_obj = pd.DataFrame(df)
            regime = detector.analyze(symbol, df_obj)
            
            # 3. 动态选择策略
            signal_info = None
            
            # === 场景 A: 强趋势 (ADX > 25) ===
            if regime.adx > 25:
                # 使用 Alpha 101 策略 (周线)
                # Alpha 101 接受 list
                signal = strategy_alpha.analyze(symbol, df)
                
                # 只有顺势信号才采纳
                is_valid = False
                if regime.regime == MarketRegime.TRENDING_UP and signal.signal == Signal.BUY:
                    is_valid = True
                elif regime.regime == MarketRegime.TRENDING_DOWN and signal.signal == Signal.SELL:
                    is_valid = True
                
                if is_valid:
                    signal_info = {
                        "type": "Trend",
                        "signal": signal,
                        "regime": regime
                    }
                    results_trend.append(signal_info)

            # === 场景 B: 震荡/弱趋势 (ADX < 25) ===
            else:
                # 使用均值回归策略 (日线)
                # MeanReversion 接受 list
                signal = strategy_mr.analyze(symbol, df)
                
                if signal.signal in [Signal.BUY, Signal.SELL]:
                    signal_info = {
                        "type": "Reversion",
                        "signal": signal,
                        "regime": regime
                    }
                    results_reversion.append(signal_info)
            
            # 实时打印有信号的
            if signal_info:
                s = signal_info['signal']
                r = signal_info['regime']
                
                # 颜色格式化
                signal_str = f"{s.signal.value} ({s.confidence:.0%})"
                if s.signal == Signal.BUY:
                    signal_str = f"🟢 {signal_str}"
                elif s.signal == Signal.SELL:
                    signal_str = f"🔴 {signal_str}"
                    
                regime_str = "强趋势" if r.adx > 25 else "震荡"
                
                print(f"{symbol:<10} {current_price:>8.2f} {regime_str:<15} {r.adx:>5.1f} {signal_info['type']:<12} {signal_str:<20}")

        except Exception as e:
            # print(f"Error {symbol}: {e}")
            pass
            
    print("-" * 80)
    print("\n📝 总结报告:\n")
    
    # 输出趋势信号
    if results_trend:
        print("🚀 【顺势追涨/杀跌】(强趋势 + Alpha信号)")
        for item in results_trend:
            s = item['signal']
            r = item['regime']
            direction = "上升" if r.regime == MarketRegime.TRENDING_UP else "下降"
            print(f"   • {s.symbol} ({direction}, ADX={r.adx:.1f}): {s.reason}")
    else:
        print("🚀 【顺势追涨】暂无强趋势信号")
        
    print()
    
    # 输出回归信号
    if results_reversion:
        print("⚖️ 【震荡抄底/高抛】(震荡市 + 回归信号)")
        for item in results_reversion:
            s = item['signal']
            r = item['regime']
            print(f"   • {s.symbol} (震荡, ADX={r.adx:.1f}): {s.signal.value} - {s.reason}")
    else:
        print("⚖️ 【震荡抄底】暂无回归信号")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="动态策略扫描")
    parser.add_argument("--list", "-l", type=str, default="all", help="股票池")
    parser.add_argument("--top", "-n", type=int, default=30, help="显示数量")
    
    args = parser.parse_args()
    scan_dynamic(args.list, args.top)

if __name__ == "__main__":
    main()
