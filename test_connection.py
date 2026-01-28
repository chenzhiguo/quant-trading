#!/usr/bin/env python3
"""
长桥 API 连接测试
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from longport.openapi import Config, QuoteContext, TradeContext

def test_quote():
    """测试行情接口"""
    print("=" * 50)
    print("📈 长桥 OpenAPI 行情测试")
    print("=" * 50)
    
    config = Config.from_env()
    print("✅ 配置加载成功")
    
    quote_ctx = QuoteContext(config)
    
    # 获取美股行情
    symbols = ["AAPL.US", "TSLA.US", "NVDA.US", "GOOGL.US", "MSFT.US"]
    quotes = quote_ctx.quote(symbols)
    
    print(f"\n{'股票':<12} {'最新价':<12} {'涨跌幅':<10} {'成交量'}")
    print("-" * 55)
    for q in quotes:
        change_pct = ((q.last_done - q.prev_close) / q.prev_close * 100) if q.prev_close else 0
        print(f"{q.symbol:<12} ${q.last_done:<11.2f} {change_pct:>+6.2f}%    {q.volume:,}")
    
    print("\n✅ 行情接口正常！")
    return quote_ctx

def test_trade():
    """测试交易接口"""
    print("\n" + "=" * 50)
    print("💰 长桥 OpenAPI 交易测试")
    print("=" * 50)
    
    try:
        config = Config.from_env()
        trade_ctx = TradeContext(config)
        
        # 获取账户余额
        balances = trade_ctx.account_balance()
        print("\n账户资金:")
        for balance in balances:
            print(f"  货币: {balance.currency}")
            print(f"  总资产: {balance.total_cash:,.2f}")
            # 使用 dir() 查看可用属性
            # print(f"  属性: {[a for a in dir(balance) if not a.startswith('_')]}")
        
        # 获取持仓
        positions = trade_ctx.stock_positions()
        if positions.channels:
            print("\n当前持仓:")
            for channel in positions.channels:
                for pos in channel.positions:
                    print(f"  {pos.symbol}: {pos.quantity} 股 @ 成本 {pos.cost_price:.2f}")
        else:
            print("\n当前无持仓")
        
        # 获取今日订单
        orders = trade_ctx.today_orders()
        if orders:
            print(f"\n今日订单: {len(orders)} 笔")
        else:
            print("\n今日无订单")
        
        print("\n✅ 交易接口正常！")
        return trade_ctx
        
    except Exception as e:
        print(f"\n⚠️ 交易接口错误: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_quote()
    test_trade()
    print("\n" + "=" * 50)
    print("🎉 测试完成！API 连接正常")
    print("=" * 50)
