#!/usr/bin/env python3
"""
组合策略扫描 - 既便宜又好

结合两个维度：
1. MultiFactor 评分 → 股票质量（价值+动量+质量）
2. Trade Signals → 买入时机（Regime Switching + Mean Reversion）

输出：
- 🌟 优质信号：高评分 + 强力信号（最佳机会）
- 🟢 普通信号：有信号但评分一般
- 📊 优质观望：评分高但无信号，等机会
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
from strategies.regime_switching import RegimeSwitchingStrategy
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
    
    # ========== 2. 策略信号扫描 (Regime + MeanReversion) ==========
    print("📉 扫描交易信号...")
    
    # 策略 1: 均值回归 (抄底)
    mr_strategy = MeanReversionStrategy(
        lookback=20,
        min_drop=-10.0,
        rsi_oversold=35,
        ma_deviation=-5.0,
        rsi_overbought=60,
    )
    
    # 策略 2: 趋势切换 (趋势跟踪 + 震荡) - 使用 Optimized V2 参数
    rs_strategy = RegimeSwitchingStrategy(params={
        'adx_threshold': 30,
        'adx_wait_threshold': 25, # 提高观望阈值
        'rsi_oversold': 30,       # 降低超卖阈值防止接飞刀
        'rsi_overbought': 70,
        'alpha_threshold': 0.5,
        'ema_short': 20,          # 趋势过滤
        'ema_long': 50
    })
    
    buy_signals = []
    sell_signals = []
    
    for symbol in symbols:
        try:
            data = fetcher.get_kline_df(symbol, days=150) # 增加天数以确保 EMA50 计算准确
            if not data or len(data) < 60:
                continue
            
            # 运行两个策略
            sig_mr = mr_strategy.analyze(symbol, data)
            sig_rs = rs_strategy.analyze(symbol, data)
            
            # 优先采纳 Regime Switching 的信号 (因为它更全面)
            # 如果两个都有买入信号，合并置信度
            
            final_signal = None
            
            if sig_rs.signal == Signal.BUY:
                final_signal = sig_rs
                # 如果均值回归也提示买入，增加权重
                if sig_mr.signal == Signal.BUY:
                    final_signal.confidence = min(0.99, final_signal.confidence + 0.2)
                    final_signal.reason += " & MR Confirm"
            
            elif sig_mr.signal == Signal.BUY:
                final_signal = sig_mr

            # 如果没有买入信号，检查卖出信号
            if not final_signal or final_signal.signal != Signal.BUY:
                if sig_rs.signal == Signal.SELL:
                    sell_signals.append(sig_rs)
                elif sig_mr.signal == Signal.SELL:
                    sell_signals.append(sig_mr)
            else:
                buy_signals.append(final_signal)
                
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            continue

    print(f"   ✅ 买入信号: {len(buy_signals)} | 卖出信号: {len(sell_signals)}\n")

    # ========== 3. 组合分析 & 输出 ==========
    print("🔗 组合分析...\n")
    
    # 分类买入信号
    high_quality_buys = []
    normal_buys = []
    
    for sig in buy_signals:
        score_info = score_map.get(sig.symbol, {})
        score = score_info.get('score', 0)
        
        # 组合信息
        combined_info = {
            'symbol': sig.symbol,
            'price': sig.price,
            'signal': sig.reason,
            'confidence': sig.confidence,
            'score': score,
            'mf_rank': score_info.get('rank', 999),
            'factors': f"ROE {score_info.get('roe', 0):.1f}%"
        }
        
        if score >= 60 and sig.confidence > 0.6:
            high_quality_buys.append(combined_info)
        else:
            normal_buys.append(combined_info)
            
    # 优质观望 (高分但无信号)
    high_quality_watches = []
    buy_symbols = {s['symbol'] for s in high_quality_buys + normal_buys}
    
    for symbol, info in score_map.items():
        if symbol not in buy_symbols and info.get('score', 0) >= 60:
            high_quality_watches.append({
                'symbol': symbol,
                'price': info.get('close', 0), # 这里可能需要最新价格
                'score': info.get('score', 0),
                'factors': f"ROE {info.get('roe', 0):.1f}%"
            })
            
    # 按分数排序
    high_quality_buys.sort(key=lambda x: x['score'], reverse=True)
    normal_buys.sort(key=lambda x: x['confidence'], reverse=True)
    high_quality_watches.sort(key=lambda x: x['score'], reverse=True)
    
    # --- 输出结果 ---
    
    print("🌟 【优质信号】高评分 + 强力信号")
    print("-" * 70)
    if not high_quality_buys:
        print("   暂无")
    for s in high_quality_buys:
        print(f"   • {s['symbol']} @ ${s['price']:.2f} | 评分 {s['score']:.1f} | {s['signal']}")

    print("\n🟢 【普通信号】信号触发但评分一般")
    print("-" * 70)
    if not normal_buys:
        print("   暂无")
    for s in normal_buys[:15]: # 只显示前15个
        print(f"   • {s['symbol']} @ ${s['price']:.2f} | 置信度 {s['confidence']:.0%} | 多因子 {s['score']:.1f} | {s['signal']}")
    if len(normal_buys) > 15:
        print(f"   ... 还有 {len(normal_buys)-15} 只")

    print("\n📊 【优质观望】高评分但无信号 (等待)")
    print("-" * 70)
    for s in high_quality_watches[:10]:
        print(f"   • {s['symbol']} @ ${s['price']:.2f} | 多因子 {s['score']:.1f} | {s['factors']}")

    print("\n📈 【卖出信号】反弹止盈或止损 (已持仓参考)")
    print("-" * 70)
    for s in sell_signals[:10]:
        print(f"   • {s.symbol} @ ${s.price:.2f} | {s.reason}")
        
    print("\n" + "=" * 70)
    print(f"📊 汇总: 优质信号 {len(high_quality_buys)} | 普通信号 {len(normal_buys)} | 优质观望 {len(high_quality_watches)} | 卖出 {len(sell_signals)}")
    print("=" * 70)

if __name__ == "__main__":
    scan_combined()
