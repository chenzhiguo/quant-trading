#!/usr/bin/env python3
"""
信号扫描脚本 - 用于 cron 定时调用

输出格式化的信号报告，便于通知推送
"""
import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.data import get_fetcher
from strategies.ma_cross import MACrossStrategy
from strategies.momentum import MomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.base import Signal
from config.watchlist import get_watchlist


def scan_all_signals(symbols: list = None) -> dict:
    """
    扫描所有策略的信号
    
    Returns:
        {
            "time": "2026-01-28 21:30:00",
            "market": "US",
            "signals": [
                {"symbol": "NVDA.US", "signal": "BUY", "price": 188.52, ...},
                ...
            ],
            "summary": {"buy": 2, "sell": 3}
        }
    """
    if symbols is None:
        symbols = get_watchlist("all")
    
    fetcher = get_fetcher()
    
    # 使用均值回归策略（追跌不追涨）
    strategies = [
        MeanReversionStrategy(
            lookback=20,
            min_drop=-10.0,
            rsi_oversold=35,
            ma_deviation=-5.0,
            rsi_overbought=60,
        ),
    ]
    
    all_signals = []
    
    for symbol in symbols:
        try:
            data = fetcher.get_kline_df(symbol, days=50)
            if not data:
                continue
            
            for strategy in strategies:
                signal = strategy.analyze(symbol, data)
                
                # 只记录买卖信号
                if signal.signal in (Signal.BUY, Signal.SELL):
                    all_signals.append({
                        "symbol": signal.symbol,
                        "signal": signal.signal.value,
                        "price": signal.price,
                        "reason": signal.reason,
                        "confidence": signal.confidence,
                        "strategy": strategy.name,
                    })
                    
        except Exception as e:
            print(f"Error scanning {symbol}: {e}", file=sys.stderr)
    
    # 去重（同一股票多个策略可能产生相同信号）
    seen = set()
    unique_signals = []
    for s in all_signals:
        key = (s["symbol"], s["signal"])
        if key not in seen:
            seen.add(key)
            unique_signals.append(s)
    
    # 按信号类型和置信度排序
    unique_signals.sort(key=lambda x: (-x["confidence"], x["signal"]))
    
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": "US",
        "symbols_scanned": len(symbols),
        "signals": unique_signals,
        "summary": {
            "buy": len([s for s in unique_signals if s["signal"] == "BUY"]),
            "sell": len([s for s in unique_signals if s["signal"] == "SELL"]),
        }
    }


def format_report(result: dict) -> str:
    """格式化信号报告（适合消息推送）"""
    lines = []
    
    # 标题
    lines.append(f"📊 **量化信号扫描** ({result['time']})")
    lines.append(f"扫描 {result['symbols_scanned']} 只股票")
    lines.append("")
    
    buy_signals = [s for s in result["signals"] if s["signal"] == "BUY"]
    sell_signals = [s for s in result["signals"] if s["signal"] == "SELL"]
    
    # 买入信号
    if buy_signals:
        lines.append("🟢 **买入信号:**")
        for s in buy_signals:
            conf = int(s["confidence"] * 100)
            lines.append(f"  • {s['symbol']} @ ${s['price']:.2f} ({conf}%)")
            lines.append(f"    {s['reason']}")
        lines.append("")
    
    # 卖出信号
    if sell_signals:
        lines.append("🔴 **卖出信号:**")
        for s in sell_signals:
            conf = int(s["confidence"] * 100)
            lines.append(f"  • {s['symbol']} @ ${s['price']:.2f} ({conf}%)")
            lines.append(f"    {s['reason']}")
        lines.append("")
    
    # 无信号
    if not buy_signals and not sell_signals:
        lines.append("⚪ 暂无明确交易信号")
        lines.append("")
    
    # 汇总
    lines.append(f"📈 买入: {result['summary']['buy']} | 📉 卖出: {result['summary']['sell']}")
    
    return "\n".join(lines)


def main():
    """主函数"""
    # 扫描信号
    result = scan_all_signals()
    
    # 输出 JSON（供程序读取）
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    # 输出格式化报告（供消息推送）
    report = format_report(result)
    print(report)
    
    # 返回码：有信号返回 0，无信号返回 1
    if result["summary"]["buy"] > 0 or result["summary"]["sell"] > 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
