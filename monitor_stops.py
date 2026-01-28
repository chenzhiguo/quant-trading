#!/usr/bin/env python3
"""
止损止盈监控脚本

功能：
1. 定期检查持仓，触发止损/止盈时自动平仓
2. 输出风险报告
3. 支持作为 cron 任务运行

使用方式：
    # 检查并执行止损止盈
    python monitor_stops.py
    
    # 仅输出风险报告（不执行交易）
    python monitor_stops.py --report-only
    
    # 检查后发送通知
    python monitor_stops.py --notify
"""
import os
import sys
import argparse
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.trader import get_trader
from core.risk import RiskConfig


def load_risk_config() -> RiskConfig:
    """加载风控配置"""
    config_path = os.path.join(
        os.path.dirname(__file__),
        "config",
        "risk_config.json"
    )
    return RiskConfig.from_file(config_path)


def monitor_and_execute(notify: bool = False, report_only: bool = False):
    """监控并执行止损止盈"""
    print("=" * 60)
    print(f"🔍 止损止盈监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化交易器
    risk_config = load_risk_config()
    trader = get_trader(risk_config=risk_config)
    
    # 生成风险报告
    report = trader.get_risk_report()
    print(report)
    
    if report_only:
        print("\n📋 仅报告模式，不执行交易")
        return report
    
    # 检查并执行止损止盈
    print("\n🔄 检查止损止盈...")
    executed_orders = trader.check_and_execute_stops()
    
    if executed_orders:
        print(f"\n📊 执行了 {len(executed_orders)} 笔止损止盈:")
        for order in executed_orders:
            trigger = "止损" if order.get("trigger") == "stop_loss" else "止盈"
            pnl = order.get("pnl", 0)
            emoji = "🔴" if pnl < 0 else "🟢"
            print(f"  {emoji} [{trigger}] {order['symbol']}: {order['quantity']}股 @ {order['price']:.2f}, 盈亏: {pnl:+.2f}")
    else:
        print("✅ 无需执行止损止盈")
    
    # 发送通知
    if notify and executed_orders:
        send_notification(executed_orders)
    
    return report, executed_orders


def send_notification(orders: list):
    """发送通知（可扩展为 Telegram/Email 等）"""
    print("\n📤 发送通知...")
    
    # 这里可以集成 Telegram 通知
    # 目前只是打印
    message_lines = ["⚠️ 止损止盈执行通知\n"]
    
    for order in orders:
        trigger = "止损" if order.get("trigger") == "stop_loss" else "止盈"
        pnl = order.get("pnl", 0)
        emoji = "🔴" if pnl < 0 else "🟢"
        message_lines.append(
            f"{emoji} [{trigger}] {order['symbol']}: "
            f"{order['quantity']}股 @ ${order['price']:.2f}, "
            f"盈亏: ${pnl:+.2f}"
        )
    
    message = "\n".join(message_lines)
    print(message)
    
    # TODO: 实际发送到 Telegram
    # 可以通过输出特定格式让 Clawdbot 捕获并发送


def main():
    parser = argparse.ArgumentParser(description="止损止盈监控")
    parser.add_argument(
        "--report-only", "-r",
        action="store_true",
        help="仅输出报告，不执行交易"
    )
    parser.add_argument(
        "--notify", "-n",
        action="store_true",
        help="执行后发送通知"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式（供程序解析）"
    )
    
    args = parser.parse_args()
    
    try:
        result = monitor_and_execute(
            notify=args.notify,
            report_only=args.report_only
        )
        
        if args.json:
            import json
            if isinstance(result, tuple):
                report, orders = result
                print(json.dumps({
                    "report": report,
                    "executed_orders": [o for o in orders]
                }, ensure_ascii=False, indent=2))
        
        print("\n" + "=" * 60)
        print("✅ 监控完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 监控失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
