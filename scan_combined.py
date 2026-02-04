#!/usr/bin/env python3
"""
组合策略扫描 - 既便宜又好

结合两个维度：
1. MultiFactor 评分 → 股票质量（价值+动量+质量）
2. MeanReversion 信号 → 买入时机（超跌抄底）

输出：
- 🌟 优质抄底：高评分 + 超跌信号（最佳机会）
- 🟢 普通抄底：有信号但评分一般
- 📊 优质观望：评分高但未超跌，等机会
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.data import get_fetcher
from strategies.mean_reversion import MeanReversionStrategy
from strategies.multi_factor import MultiFactorStrategy, MultiFactorConfig
from strategies.base import Signal
from config.watchlist import get_watchlist


def scan_combined(category: str = "all", top_n: int = 30):
    """
    组合策略扫描
    """
    print("=" * 70)
    print(f"🎯 组合策略扫描 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    symbols = get_watchlist(category)
    print(f"📋 股票池: {len(symbols)} 只\n")
    
    fetcher = get_fetcher()
    
    # ========== 1. 多因子评分 ==========
    print("📊 计算多因子评分...")
    try:
        stocks_data = fetcher.get_multi_factor_data(symbols)
        mf_config = MultiFactorConfig(top_n=100)  # 获取所有评分
        mf_strategy = MultiFactorStrategy(mf_config)
        ranked_stocks = mf_strategy.calculate_score(stocks_data)
        
        # 转为字典方便查询
        score_map = {s['symbol']: s for s in ranked_stocks}
        print(f"   ✅ 获取 {len(score_map)} 只股票评分\n")
    except Exception as e:
        print(f"   ❌ 多因子评分失败: {e}")
        score_map = {}
    
    # ========== 2. 均值回归信号 ==========
    print("📉 扫描均值回归信号...")
    mr_strategy = MeanReversionStrategy(
        lookback=20,
        min_drop=-10.0,
        rsi_oversold=35,
        ma_deviation=-5.0,
        rsi_overbought=60,
    )
    
    buy_signals = []
    sell_signals = []
    hold_stocks = []
    
    for symbol in symbols:
        try:
            data = fetcher.get_kline_df(symbol, days=50)
            if not data:
                continue
            
            signal = mr_strategy.analyze(symbol, data)
            
            if signal.signal == Signal.BUY:
                buy_signals.append(signal)
            elif signal.signal == Signal.SELL:
                sell_signals.append(signal)
            else:
                hold_stocks.append(signal)
                
        except Exception as e:
            pass
    
    print(f"   ✅ 买入信号: {len(buy_signals)} | 卖出信号: {len(sell_signals)}\n")
    
    # ========== 3. 组合分析 ==========
    print("🔗 组合分析...\n")
    
    # 分类结果
    premium_buys = []    # 🌟 优质抄底：高评分 + 买入信号
    normal_buys = []     # 🟢 普通抄底：买入信号但评分一般
    premium_watch = []   # 📊 优质观望：高评分但无信号
    
    SCORE_THRESHOLD = 60  # 多因子评分阈值
    
    for signal in buy_signals:
        stock_info = score_map.get(signal.symbol, {})
        mf_score = stock_info.get('total_score', 0)
        
        combined = {
            'symbol': signal.symbol,
            'price': signal.price,
            'mf_score': mf_score,
            'mr_confidence': signal.confidence,
            'mr_reason': signal.reason,
            'pe': stock_info.get('pe_ttm', 0),
            'roe': stock_info.get('roe', 0),
            'mom_12m': stock_info.get('mom_12m', 0),
            # 综合评分 = 多因子 * 0.5 + 均值回归置信度 * 50
            'combined_score': mf_score * 0.5 + signal.confidence * 50
        }
        
        if mf_score >= SCORE_THRESHOLD:
            premium_buys.append(combined)
        else:
            normal_buys.append(combined)
    
    # 高评分但没信号的股票
    for symbol, info in score_map.items():
        if info['total_score'] >= SCORE_THRESHOLD:
            # 检查是否已在买入信号里
            if not any(s.symbol == symbol for s in buy_signals):
                # 检查是否在卖出信号里（已涨，不推荐）
                if not any(s.symbol == symbol for s in sell_signals):
                    premium_watch.append({
                        'symbol': symbol,
                        'price': info['price'],
                        'mf_score': info['total_score'],
                        'pe': info.get('pe_ttm', 0),
                        'roe': info.get('roe', 0),
                        'mom_12m': info.get('mom_12m', 0),
                    })
    
    # 排序
    premium_buys.sort(key=lambda x: -x['combined_score'])
    normal_buys.sort(key=lambda x: -x['mr_confidence'])
    premium_watch.sort(key=lambda x: -x['mf_score'])
    
    # ========== 4. 输出结果 ==========
    
    # 🌟 优质抄底
    print("🌟 【优质抄底】高评分 + 超跌信号 (最佳机会)")
    print("-" * 70)
    if premium_buys:
        print(f"{'股票':<12} {'价格':>10} {'多因子':>8} {'抄底置信':>10} {'综合分':>8} {'原因'}")
        print("-" * 70)
        for s in premium_buys[:top_n]:
            print(f"{s['symbol']:<12} ${s['price']:>8.2f} {s['mf_score']:>7.1f} {s['mr_confidence']:>9.0%} {s['combined_score']:>7.1f}   {s['mr_reason'][:30]}")
    else:
        print("   暂无 (等待优质股票回调)")
    print()
    
    # 🟢 普通抄底
    print("🟢 【普通抄底】有信号但评分较低 (谨慎考虑)")
    print("-" * 70)
    if normal_buys:
        shown = min(10, len(normal_buys))
        for s in normal_buys[:shown]:
            print(f"   • {s['symbol']} @ ${s['price']:.2f} | 置信度 {s['mr_confidence']:.0%} | 多因子 {s['mf_score']:.1f}")
        if len(normal_buys) > shown:
            print(f"   ... 还有 {len(normal_buys) - shown} 只")
    else:
        print("   暂无")
    print()
    
    # 📊 优质观望
    print("📊 【优质观望】高评分但未超跌 (等待回调)")
    print("-" * 70)
    if premium_watch:
        shown = min(10, len(premium_watch))
        for s in premium_watch[:shown]:
            print(f"   • {s['symbol']} @ ${s['price']:.2f} | 多因子 {s['mf_score']:.1f} | ROE {s['roe']:.1%}")
        if len(premium_watch) > shown:
            print(f"   ... 还有 {len(premium_watch) - shown} 只")
    else:
        print("   暂无")
    print()
    
    # 📈 卖出信号（已持仓参考）
    if sell_signals:
        print("📈 【反弹止盈】均值回归卖出信号 (已持仓参考)")
        print("-" * 70)
        for s in sell_signals[:10]:
            print(f"   • {s.symbol} @ ${s.price:.2f} | {s.reason}")
        print()
    
    # 汇总
    print("=" * 70)
    print(f"📊 汇总: 优质抄底 {len(premium_buys)} | 普通抄底 {len(normal_buys)} | 优质观望 {len(premium_watch)} | 卖出 {len(sell_signals)}")
    print("=" * 70)
    
    return {
        'premium_buys': premium_buys,
        'normal_buys': normal_buys,
        'premium_watch': premium_watch,
        'sell_signals': sell_signals,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="组合策略扫描")
    parser.add_argument("--list", "-l", type=str, default="all", help="股票池")
    parser.add_argument("--top", "-n", type=int, default=20, help="显示数量")
    
    args = parser.parse_args()
    scan_combined(args.list, args.top)


if __name__ == "__main__":
    main()
