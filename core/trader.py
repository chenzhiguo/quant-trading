"""
交易执行模块（集成风控）
"""
import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from longport.openapi import (
    Config, TradeContext, 
    OrderSide, OrderType, TimeInForceType,
    OutsideRTH
)

from .risk import get_risk_manager, RiskConfig, TradeRecord


class Trader:
    """交易执行器（带风控）"""
    
    def __init__(self, dry_run: bool = None, risk_config: RiskConfig = None):
        """
        初始化交易器
        
        Args:
            dry_run: 是否模拟执行（None 时根据环境变量决定）
            risk_config: 风控配置
        """
        self.config = Config.from_env()
        self.trade_ctx = TradeContext(self.config)
        
        # 根据环境变量决定是否 dry_run
        if dry_run is None:
            env = os.getenv("LONGPORT_ENV", "paper")
            self.dry_run = env != "production"
        else:
            self.dry_run = dry_run
        
        # 初始化风控
        self.risk = get_risk_manager(config=risk_config)
        
        if self.dry_run:
            print("🔔 交易器已启动 [模拟模式]")
        else:
            print("⚠️ 交易器已启动 [实盘模式]")
    
    def get_account_balance(self) -> list:
        """获取账户余额"""
        return self.trade_ctx.account_balance()
    
    def get_total_balance(self, currency: str = "USD") -> float:
        """获取指定币种的总余额"""
        balances = self.get_account_balance()
        for b in balances:
            if b.currency == currency:
                return float(b.total_cash)
        return 0.0
    
    def get_positions(self) -> list:
        """获取持仓"""
        positions = self.trade_ctx.stock_positions()
        result = []
        if positions.channels:
            for channel in positions.channels:
                for pos in channel.positions:
                    result.append({
                        "symbol": pos.symbol,
                        "quantity": int(pos.quantity),
                        "available": int(pos.available_quantity),
                        "cost_price": float(pos.cost_price),
                        "market_value": float(pos.market or 0),
                    })
        return result
    
    def get_today_orders(self) -> list:
        """获取今日订单"""
        return self.trade_ctx.today_orders()
    
    def submit_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "limit",  # "limit" or "market"
        skip_risk_check: bool = False,
        set_stops: bool = True,  # 买入时自动设置止损止盈
    ) -> dict:
        """
        提交订单（带风控检查）
        
        Args:
            symbol: 股票代码
            side: 买卖方向 ("buy" / "sell")
            quantity: 数量
            price: 价格（限价单必填）
            order_type: 订单类型
            skip_risk_check: 是否跳过风控检查（危险！）
            set_stops: 买入时是否自动设置止损止盈
        
        Returns:
            订单信息
        """
        order_value = quantity * (price or 0)
        
        order_info = {
            "id": str(uuid.uuid4())[:8],
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "value": order_value,
            "order_type": order_type,
            "time": datetime.now().isoformat(),
        }
        
        # 风控检查
        if not skip_risk_check:
            account_balance = self.get_total_balance("USD")
            positions = self.get_positions()
            
            is_valid, message = self.risk.validate_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price or 0,
                account_balance=account_balance,
                current_positions=positions
            )
            
            if not is_valid:
                order_info["status"] = "REJECTED"
                order_info["error"] = message
                print(f"❌ 订单被风控拒绝: {message}")
                
                # 记录被拒绝的交易
                self.risk.record_trade(TradeRecord(
                    id=order_info["id"],
                    timestamp=order_info["time"],
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price or 0,
                    value=order_value,
                    status="rejected",
                    reason=message
                ))
                
                return order_info
        
        # 模拟模式
        if self.dry_run:
            order_info["status"] = "DRY_RUN"
            order_info["message"] = "模拟下单，未实际执行"
            print(f"🔔 [DRY RUN] {side.upper()} {quantity} {symbol} @ {price}")
            
            # 记录模拟交易
            self.risk.record_trade(TradeRecord(
                id=order_info["id"],
                timestamp=order_info["time"],
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price or 0,
                value=order_value,
                status="dry_run",
                reason="模拟执行"
            ))
            
            # 模拟模式下也设置止损止盈（用于测试）
            if set_stops and side.lower() == "buy" and price:
                stop_loss, take_profit = self.risk.set_stops_from_cost(symbol, price)
                order_info["stop_loss"] = stop_loss
                order_info["take_profit"] = take_profit
                print(f"   止损: {stop_loss:.2f} | 止盈: {take_profit:.2f}")
            
            return order_info
        
        # 实际下单
        order_side = OrderSide.Buy if side.lower() == "buy" else OrderSide.Sell
        
        if order_type.lower() == "market":
            lb_order_type = OrderType.Market
        else:
            lb_order_type = OrderType.LO  # 限价单
        
        try:
            response = self.trade_ctx.submit_order(
                symbol=symbol,
                order_type=lb_order_type,
                side=order_side,
                submitted_quantity=quantity,
                submitted_price=Decimal(str(price)) if price else None,
                time_in_force=TimeInForceType.Day,
                outside_rth=OutsideRTH.RTHOnly,
            )
            
            order_info["order_id"] = response.order_id
            order_info["status"] = "SUBMITTED"
            print(f"✅ 订单已提交: {response.order_id}")
            
            # 记录交易
            self.risk.record_trade(TradeRecord(
                id=order_info["id"],
                timestamp=order_info["time"],
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price or 0,
                value=order_value,
                order_id=response.order_id,
                status="submitted",
                reason=""
            ))
            
            # 买入成功后设置止损止盈
            if set_stops and side.lower() == "buy" and price:
                stop_loss, take_profit = self.risk.set_stops_from_cost(symbol, price)
                order_info["stop_loss"] = stop_loss
                order_info["take_profit"] = take_profit
                print(f"   止损: {stop_loss:.2f} | 止盈: {take_profit:.2f}")
            
            return order_info
            
        except Exception as e:
            order_info["status"] = "ERROR"
            order_info["error"] = str(e)
            print(f"❌ 下单失败: {e}")
            
            # 记录失败
            self.risk.record_trade(TradeRecord(
                id=order_info["id"],
                timestamp=order_info["time"],
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price or 0,
                value=order_value,
                status="error",
                reason=str(e)
            ))
            
            return order_info
    
    def submit_order_with_size(
        self,
        symbol: str,
        side: str,
        price: float,
        risk_pct: float = None,
        **kwargs
    ) -> dict:
        """
        智能下单：自动计算仓位大小
        
        Args:
            symbol: 股票代码
            side: 买卖方向
            price: 价格
            risk_pct: 风险比例（可选，默认使用风控配置）
            **kwargs: 其他参数传递给 submit_order
        
        Returns:
            订单信息
        """
        account_balance = self.get_total_balance("USD")
        quantity = self.risk.calculate_position_size(
            symbol=symbol,
            price=price,
            account_balance=account_balance,
            risk_pct=risk_pct
        )
        
        if quantity <= 0:
            return {
                "symbol": symbol,
                "status": "REJECTED",
                "error": "计算出的仓位为0，可能资金不足或价格过高"
            }
        
        return self.submit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            **kwargs
        )
    
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if self.dry_run:
            print(f"🔔 [DRY RUN] 取消订单 {order_id}")
            return True
        
        try:
            self.trade_ctx.cancel_order(order_id)
            print(f"✅ 订单已取消: {order_id}")
            return True
        except Exception as e:
            print(f"❌ 取消失败: {e}")
            return False
    
    def check_and_execute_stops(self, quotes: dict = None) -> list:
        """
        检查并执行止损止盈
        
        Args:
            quotes: 实时报价 {symbol: price}，如果不传则自动获取
        
        Returns:
            执行的止损止盈订单列表
        """
        positions = self.get_positions()
        
        if not positions:
            return []
        
        # 获取报价
        if quotes is None:
            from .data import get_fetcher
            fetcher = get_fetcher()
            symbols = [p["symbol"] for p in positions]
            quote_list = fetcher.get_quote_with_change(symbols)
            quotes = {q["symbol"]: q["price"] for q in quote_list}
        
        # 扫描需要止损止盈的持仓
        exit_signals = self.risk.scan_positions_for_exit(positions, quotes)
        
        executed_orders = []
        
        for risk in exit_signals:
            if risk.should_stop_loss:
                print(f"🔴 触发止损: {risk.symbol} @ {risk.current_price:.2f} (止损线: {risk.stop_loss_price:.2f})")
                reason = "stop_loss"
            else:
                print(f"🟢 触发止盈: {risk.symbol} @ {risk.current_price:.2f} (止盈线: {risk.take_profit_price:.2f})")
                reason = "take_profit"
            
            # 执行卖出
            order = self.submit_order(
                symbol=risk.symbol,
                side="sell",
                quantity=risk.quantity,
                price=risk.current_price,
                order_type="limit",
                skip_risk_check=True,  # 止损止盈不受风控限制
                set_stops=False
            )
            
            order["trigger"] = reason
            order["pnl"] = risk.unrealized_pnl
            executed_orders.append(order)
        
        return executed_orders
    
    def get_risk_report(self) -> str:
        """获取风险报告"""
        account_balance = self.get_total_balance("USD")
        positions = self.get_positions()
        
        # 获取报价
        quotes = {}
        if positions:
            from .data import get_fetcher
            fetcher = get_fetcher()
            symbols = [p["symbol"] for p in positions]
            quote_list = fetcher.get_quote_with_change(symbols)
            quotes = {q["symbol"]: q["price"] for q in quote_list}
        
        return self.risk.generate_risk_report(
            account_balance=account_balance,
            positions=positions,
            quotes=quotes
        )
    
    def emergency_stop(self, reason: str = "手动触发"):
        """紧急停止交易"""
        self.risk.emergency_stop(reason)
    
    def resume_trading(self):
        """恢复交易"""
        self.risk.resume_trading()


# 单例
_trader = None


def get_trader(dry_run: bool = None, risk_config: RiskConfig = None) -> Trader:
    """
    获取交易器单例
    
    Args:
        dry_run: 是否模拟模式（None 时根据 LONGPORT_ENV 环境变量决定）
        risk_config: 风控配置
    """
    global _trader
    if _trader is None:
        _trader = Trader(dry_run=dry_run, risk_config=risk_config)
    return _trader
