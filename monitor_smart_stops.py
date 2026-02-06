#!/usr/bin/env python3
"""
智能止损监控脚本

使用三策略组合决策:
1. ATR 波动率自适应止损
2. 收盘价止损 (消除盘中噪音)
3. 相对大盘止损 (大盘跌则放宽)

投票机制: 2/3 策略同意才触发止损

使用方式:
    # 常规检查 (盘中不触发止损)
    python monitor_smart_stops.py
    
    # 收盘后强制检查
    python monitor_smart_stops.py --force-close
    
    # 仅报告不执行
    python monitor_smart_stops.py --report-only
    
    # 执行后通知
    python monitor_smart_stops.py --notify
"""
import os
import sys
import argparse
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.smart_stop import (
    get_smart_stop_manager, 
    SmartStopConfig, 
    StopDecision,
    SmartStopResult
)
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


def load_smart_stop_config() -> SmartStopConfig:
    """加载智能止损配置"""
    config_path = os.path.join(
        os.path.dirname(__file__),
        "config",
        "smart_stop_config.json"
    )
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            data = json.load(f)
            return SmartStopConfig(**data)
    return SmartStopConfig()


def retry_action(func, description: str, max_retries: int = 3, delay: int = 2):
    """重试操作"""
    for i in range(max_retries):
        try:
            return func()
        except Exception as e:
            if i < max_retries - 1:
                print(f"⚠️ {description}失败: {e}，正在重试 ({i+1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise e


def monitor_and_execute(
    notify: bool = False, 
    report_only: bool = False,
    force_close: bool = False,
    output_json: bool = False
):
    """智能止损监控与执行"""
    print("=" * 60)
    print(f"🧠 智能止损监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化
    risk_config = load_risk_config()
    smart_config = load_smart_stop_config()
    
    trader = get_trader(risk_config=risk_config)
    smart_stop = get_smart_stop_manager(config=smart_config)
    
    # 获取持仓
    try:
        positions = retry_action(lambda: trader.get_positions(), description="获取持仓")
    except Exception as e:
        print(f"❌ 获取持仓失败: {e}")
        return None, []
    
    if not positions:
        print("\n📋 当前无持仓")
        return None, []
    
    print(f"\n📋 持仓数量: {len(positions)}")
    
    # 智能止损分析
    try:
        results = retry_action(
            lambda: smart_stop.scan_positions(
                positions=positions,
                force_close_check=force_close
            ),
            description="智能止损分析"
        )
    except Exception as e:
        print(f"❌ 智能止损分析失败: {e}")
        return None, []
    
    # 生成报告
    report = smart_stop.generate_report(results)
    print(report)
    
    if report_only:
        print("\n📋 仅报告模式，不执行交易")
        return report, []
    
    # 筛选需要操作的
    exit_results = [r for r in results if r.should_exit]
    
    if not exit_results:
        print("\n✅ 无需执行止损/止盈")
        return report, []
    
    # 执行交易
    print(f"\n🔄 执行 {len(exit_results)} 笔止损/止盈...")
    executed_orders = []
    
    for result in exit_results:
        symbol = result.symbol
        current_price = result.details["current_price"]
        
        # 找到对应的持仓信息
        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not pos:
            continue
        
        quantity = pos["quantity"]
        cost_price = pos["cost_price"]
        
        # 计算盈亏
        pnl = (current_price - cost_price) * quantity
        
        trigger = "stop_loss" if result.final_decision == StopDecision.STOP_LOSS else "take_profit"
        trigger_cn = "止损" if trigger == "stop_loss" else "止盈"
        emoji = "🔴" if trigger == "stop_loss" else "🟢"
        
        print(f"\n{emoji} [{trigger_cn}] {symbol}")
        print(f"   数量: {quantity} 股")
        print(f"   成本: ${cost_price:.2f}")
        print(f"   现价: ${current_price:.2f}")
        print(f"   盈亏: ${pnl:+,.2f}")
        print(f"   投票: {result.vote_summary}")
        
        # 执行卖出
        order = trader.submit_order(
            symbol=symbol,
            side="sell",
            quantity=quantity,
            price=current_price,
            order_type="limit",
            skip_risk_check=True,  # 止损止盈不受风控限制
            set_stops=False
        )
        
        order["trigger"] = trigger
        order["pnl"] = pnl
        order["vote_summary"] = result.vote_summary
        order["votes"] = [
            {"strategy": v.strategy, "decision": v.decision.value, "reason": v.reason}
            for v in result.votes
        ]
        executed_orders.append(order)
    
    # 发送通知
    if notify and executed_orders:
        send_notification(executed_orders)
    
    return report, executed_orders


def send_notification(orders: list):
    """发送通知"""
    print("\n📤 发送通知...")
    
    message_lines = ["⚠️ 智能止损执行通知\n"]
    
    for order in orders:
        trigger = "止损" if order.get("trigger") == "stop_loss" else "止盈"
        pnl = order.get("pnl", 0)
        emoji = "🔴" if pnl < 0 else "🟢"
        
        message_lines.append(
            f"{emoji} [{trigger}] {order['symbol']}: "
            f"{order['quantity']}股 @ ${order['price']:.2f}\n"
            f"   盈亏: ${pnl:+,.2f}\n"
            f"   投票: {order.get('vote_summary', 'N/A')}"
        )
    
    message = "\n".join(message_lines)
    print(message)
    
    # 输出特定格式供 OpenClaw 捕获
    print("\n---NOTIFY---")
    print(message)
    print("---END NOTIFY---")


def main():
    parser = argparse.ArgumentParser(description="智能止损监控")
    parser.add_argument(
        "--report-only", "-r",
        action="store_true",
        help="仅输出报告，不执行交易"
    )
    parser.add_argument(
        "--force-close", "-f",
        action="store_true",
        help="强制按收盘价逻辑判断（收盘后使用）"
    )
    parser.add_argument(
        "--notify", "-n",
        action="store_true",
        help="执行后发送通知"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式"
    )
    
    args = parser.parse_args()
    
    try:
        report, executed_orders = monitor_and_execute(
            notify=args.notify,
            report_only=args.report_only,
            force_close=args.force_close,
            output_json=args.json
        )
        
        if args.json and executed_orders:
            print(json.dumps({
                "executed_orders": executed_orders,
                "count": len(executed_orders)
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
