#!/usr/bin/env python3
"""
自动交易执行器

功能：
1. 扫描信号 → 自动执行交易
2. 支持模拟盘和实盘（通过环境变量控制）
3. 集成风控模块，确保交易安全

使用方式：
    # 扫描信号并自动执行
    python auto_trade.py
    
    # 仅扫描不执行（预览模式）
    python auto_trade.py --preview
    
    # 指定策略
    python auto_trade.py --strategy momentum
"""
import os
import sys
import argparse
from datetime import datetime
from typing import List, Tuple

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.data import get_fetcher
from core.trader import get_trader
from core.risk import RiskConfig, get_risk_manager
from strategies.ma_cross import MACrossStrategy
from strategies.momentum import MomentumStrategy
from strategies.small_cap_growth import SmallCapGrowthStrategy, create_small_cap_strategy
from strategies.base import Signal, TradeSignal
from config.watchlist import get_watchlist


def load_risk_config() -> RiskConfig:
    """加载风控配置"""
    config_path = os.path.join(
        os.path.dirname(__file__),
        "config",
        "risk_config.json"
    )
    return RiskConfig.from_file(config_path)


def scan_signals(symbols: List[str], strategies: List) -> Tuple[List[TradeSignal], List[TradeSignal]]:
    """
    扫描交易信号
    
    Returns:
        (buy_signals, sell_signals)
    """
    fetcher = get_fetcher()
    buy_signals = []
    sell_signals = []
    
    for symbol in symbols:
        try:
            data = fetcher.get_kline_df(symbol, days=50)
            if not data:
                continue
            
            for strategy in strategies:
                signal = strategy.analyze(symbol, data)
                
                if signal.signal == Signal.BUY:
                    buy_signals.append(signal)
                elif signal.signal == Signal.SELL:
                    sell_signals.append(signal)
                    
        except Exception as e:
            print(f"⚠️ 扫描 {symbol} 失败: {e}")
    
    # 按置信度排序
    buy_signals.sort(key=lambda x: -x.confidence)
    sell_signals.sort(key=lambda x: -x.confidence)
    
    return buy_signals, sell_signals


def execute_signals(
    buy_signals: List[TradeSignal],
    sell_signals: List[TradeSignal],
    trader,
    preview: bool = False,
    max_buy_orders: int = 3,
    min_confidence: float = 0.1
) -> dict:
    """
    执行交易信号
    
    Args:
        buy_signals: 买入信号列表
        sell_signals: 卖出信号列表
        trader: 交易器实例
        preview: 是否预览模式（不实际下单）
        max_buy_orders: 单次最多执行的买入订单数
        min_confidence: 最低置信度要求
    
    Returns:
        执行结果统计
    """
    results = {
        "buy_executed": [],
        "sell_executed": [],
        "buy_skipped": [],
        "sell_skipped": [],
        "errors": []
    }
    
    # 获取当前持仓
    positions = trader.get_positions()
    held_symbols = {p["symbol"] for p in positions}
    
    # 处理卖出信号（优先处理，释放资金）
    print("\n📉 处理卖出信号...")
    for signal in sell_signals:
        if signal.confidence < min_confidence:
            results["sell_skipped"].append({
                "symbol": signal.symbol,
                "reason": f"置信度过低 ({signal.confidence:.0%})"
            })
            continue
        
        # 检查是否持有该股票
        position = next((p for p in positions if p["symbol"] == signal.symbol), None)
        if not position:
            results["sell_skipped"].append({
                "symbol": signal.symbol,
                "reason": "未持有该股票"
            })
            continue
        
        print(f"  🔴 {signal}")
        
        if preview:
            results["sell_skipped"].append({
                "symbol": signal.symbol,
                "reason": "预览模式"
            })
            continue
        
        # 执行卖出
        try:
            order = trader.submit_order(
                symbol=signal.symbol,
                side="sell",
                quantity=position["available"],
                price=signal.price,
                order_type="limit"
            )
            
            if order.get("status") in ["SUBMITTED", "DRY_RUN"]:
                results["sell_executed"].append(order)
            else:
                results["errors"].append({
                    "symbol": signal.symbol,
                    "error": order.get("error", "未知错误")
                })
        except Exception as e:
            results["errors"].append({
                "symbol": signal.symbol,
                "error": str(e)
            })
    
    # 处理买入信号
    print("\n📈 处理买入信号...")
    buy_count = 0
    
    for signal in buy_signals:
        if buy_count >= max_buy_orders:
            results["buy_skipped"].append({
                "symbol": signal.symbol,
                "reason": f"已达到单次最大买入数 ({max_buy_orders})"
            })
            continue
        
        if signal.confidence < min_confidence:
            results["buy_skipped"].append({
                "symbol": signal.symbol,
                "reason": f"置信度过低 ({signal.confidence:.0%})"
            })
            continue
        
        # 检查是否已持有
        if signal.symbol in held_symbols:
            results["buy_skipped"].append({
                "symbol": signal.symbol,
                "reason": "已持有该股票"
            })
            continue
        
        print(f"  🟢 {signal}")
        
        if preview:
            results["buy_skipped"].append({
                "symbol": signal.symbol,
                "reason": "预览模式"
            })
            continue
        
        # 执行买入（使用智能仓位）
        try:
            order = trader.submit_order_with_size(
                symbol=signal.symbol,
                side="buy",
                price=signal.price,
                order_type="limit"
            )
            
            if order.get("status") in ["SUBMITTED", "DRY_RUN"]:
                results["buy_executed"].append(order)
                buy_count += 1
            else:
                results["errors"].append({
                    "symbol": signal.symbol,
                    "error": order.get("error", "未知错误")
                })
        except Exception as e:
            results["errors"].append({
                "symbol": signal.symbol,
                "error": str(e)
            })
    
    return results


def format_results(results: dict) -> str:
    """格式化执行结果"""
    lines = []
    
    if results["buy_executed"]:
        lines.append(f"\n✅ 买入执行: {len(results['buy_executed'])} 笔")
        for order in results["buy_executed"]:
            lines.append(f"   {order['symbol']}: {order['quantity']}股 @ ${order['price']:.2f}")
    
    if results["sell_executed"]:
        lines.append(f"\n✅ 卖出执行: {len(results['sell_executed'])} 笔")
        for order in results["sell_executed"]:
            lines.append(f"   {order['symbol']}: {order['quantity']}股 @ ${order['price']:.2f}")
    
    if results["errors"]:
        lines.append(f"\n❌ 执行失败: {len(results['errors'])} 笔")
        for err in results["errors"]:
            lines.append(f"   {err['symbol']}: {err['error']}")
    
    skipped = len(results["buy_skipped"]) + len(results["sell_skipped"])
    if skipped > 0:
        lines.append(f"\n⏭️ 跳过: {skipped} 笔")
    
    if not any([results["buy_executed"], results["sell_executed"], results["errors"]]):
        lines.append("\n📋 无交易执行")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="自动交易执行器")
    parser.add_argument(
        "--preview", "-p",
        action="store_true",
        help="预览模式（扫描信号但不下单）"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="测试模式（不调用API，仅打印）"
    )
    parser.add_argument(
        "--strategy", "-s",
        choices=["all", "ma", "momentum", "smallcap"],
        default="all",
        help="使用的策略 (all, ma, momentum, smallcap)"
    )
    parser.add_argument(
        "--watchlist", "-w",
        default="us_tech",
        help="自选股列表"
    )
    parser.add_argument(
        "--max-buy", "-m",
        type=int,
        default=3,
        help="单次最多买入订单数"
    )
    parser.add_argument(
        "--min-confidence", "-c",
        type=float,
        default=0.1,
        help="最低置信度要求"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print(f"🤖 自动交易 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化
    risk_config = load_risk_config()
    trader = get_trader(dry_run=args.dry_run, risk_config=risk_config)
    
    # 确定运行模式
    if args.preview:
        mode = "预览模式（仅扫描）"
    elif args.dry_run:
        mode = "测试模式（不调用API）"
    else:
        mode = f"{'模拟盘' if trader.account_type == 'paper' else '⚠️ 实盘'}"
    print(f"📊 运行模式: {mode}")
    
    # 检查是否紧急停止
    if trader.risk.is_emergency_stopped:
        print("🚨 交易已紧急停止，退出")
        return
    
    # 选择策略
    strategies = []
    if args.strategy in ["all", "ma"]:
        strategies.append(MACrossStrategy(short_period=5, long_period=20))
    if args.strategy in ["all", "momentum"]:
        strategies.append(MomentumStrategy(lookback=20, rsi_period=14))
    if args.strategy in ["all", "smallcap"]:
        strategies.append(create_small_cap_strategy(top_n=10))
    
    print(f"📈 策略: {', '.join(s.name for s in strategies)}")
    
    # 获取自选股
    symbols = get_watchlist(args.watchlist)
    print(f"📋 监控: {len(symbols)} 只股票 ({args.watchlist})")
    
    # 扫描信号
    print("\n🔍 扫描信号...")
    buy_signals, sell_signals = scan_signals(symbols, strategies)
    
    print(f"\n📊 信号统计: 买入 {len(buy_signals)} | 卖出 {len(sell_signals)}")
    
    # 执行交易
    results = execute_signals(
        buy_signals=buy_signals,
        sell_signals=sell_signals,
        trader=trader,
        preview=args.preview,
        max_buy_orders=args.max_buy,
        min_confidence=args.min_confidence
    )
    
    # 输出结果
    print(format_results(results))
    
    # 输出每日统计
    daily_stats = trader.risk.get_daily_stats()
    print(f"\n📅 今日统计:")
    print(f"   交易次数: {daily_stats['trade_count']}")
    print(f"   买入金额: ${daily_stats['buy_value']:,.2f}")
    print(f"   卖出金额: ${daily_stats['sell_value']:,.2f}")
    
    print("\n" + "=" * 60)
    print("✅ 自动交易完成")
    print("=" * 60)
    
    # 返回执行数量（供外部判断）
    total_executed = len(results["buy_executed"]) + len(results["sell_executed"])
    return total_executed


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 自动交易失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
