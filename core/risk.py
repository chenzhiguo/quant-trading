"""
风险管理模块

核心功能：
1. 仓位控制 - 单笔/总仓位限制
2. 止损止盈 - 自动监控持仓盈亏
3. 每日风控 - 日内亏损限额
4. 订单验证 - 下单前安全检查
5. 交易日志 - 记录所有交易
6. 紧急停止 - 一键暂停交易
"""
import os
import json
from datetime import datetime, date
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
from enum import Enum
from pathlib import Path


class RiskLevel(Enum):
    """风险级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskConfig:
    """风控配置"""
    # 资金控制
    max_trading_capital: float = None          # 交易资金上限（None=使用账户全部资金）
    
    # 仓位控制
    max_single_position_pct: float = 0.10      # 单笔最大仓位 (10%)
    max_total_position_pct: float = 0.80       # 总仓位上限 (80%)
    min_cash_reserve_pct: float = 0.20         # 最低现金保留 (20%)
    
    # 止损止盈
    default_stop_loss_pct: float = 0.05        # 默认止损线 (-5%)
    default_take_profit_pct: float = 0.15      # 默认止盈线 (+15%)
    trailing_stop_enabled: bool = False        # 是否启用移动止损
    trailing_stop_pct: float = 0.03            # 移动止损比例 (3%)
    
    # 每日风控
    daily_loss_limit_pct: float = 0.03         # 每日最大亏损 (3%)
    daily_trade_limit: int = 20                # 每日最大交易次数
    
    # 订单限制
    max_order_value: float = 50000.0           # 单笔最大金额
    min_order_value: float = 100.0             # 单笔最小金额
    
    # 冷却时间
    order_cooldown_seconds: int = 60           # 同一股票下单冷却时间
    
    @classmethod
    def from_file(cls, path: str) -> "RiskConfig":
        """从文件加载配置"""
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
                return cls(**data)
        return cls()
    
    def to_file(self, path: str):
        """保存配置到文件"""
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


@dataclass
class TradeRecord:
    """交易记录"""
    id: str
    timestamp: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: int
    price: float
    value: float
    order_id: Optional[str] = None
    status: str = "pending"  # pending, filled, cancelled, rejected
    reason: str = ""
    pnl: Optional[float] = None  # 平仓时的盈亏
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class PositionRisk:
    """持仓风险信息"""
    symbol: str
    quantity: int
    cost_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss_price: float
    take_profit_price: float
    risk_level: RiskLevel
    
    @property
    def should_stop_loss(self) -> bool:
        return self.current_price <= self.stop_loss_price
    
    @property
    def should_take_profit(self) -> bool:
        return self.current_price >= self.take_profit_price


class RiskManager:
    """风险管理器"""
    
    def __init__(self, config: RiskConfig = None, data_dir: str = None):
        self.config = config or RiskConfig()
        self.data_dir = Path(data_dir or os.path.dirname(__file__) + "/../data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 状态
        self._emergency_stop = False
        self._daily_stats: Dict[str, dict] = {}
        self._last_order_time: Dict[str, datetime] = {}
        self._position_stops: Dict[str, dict] = {}  # symbol -> {stop_loss, take_profit}
        
        # 加载持久化数据
        self._load_state()
    
    # ==================== 紧急停止 ====================
    
    @property
    def is_emergency_stopped(self) -> bool:
        """是否处于紧急停止状态"""
        return self._emergency_stop
    
    def emergency_stop(self, reason: str = "手动触发"):
        """紧急停止所有交易"""
        self._emergency_stop = True
        self._log_event("EMERGENCY_STOP", {"reason": reason})
        print(f"🚨 紧急停止已激活: {reason}")
    
    def resume_trading(self):
        """恢复交易"""
        self._emergency_stop = False
        self._log_event("RESUME_TRADING", {})
        print("✅ 交易已恢复")
    
    # ==================== 资金上限 ====================
    
    def get_effective_balance(self, account_balance: float) -> float:
        """
        获取有效交易资金（考虑 max_trading_capital 限制）
        
        如果设置了 max_trading_capital，返回它与账户余额的较小值
        """
        if self.config.max_trading_capital and self.config.max_trading_capital > 0:
            return min(account_balance, self.config.max_trading_capital)
        return account_balance
    
    # ==================== 订单验证 ====================
    
    def validate_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        account_balance: float,
        current_positions: List[dict]
    ) -> tuple[bool, str]:
        """
        验证订单是否符合风控规则
        
        Returns:
            (is_valid, message)
        """
        # 检查 1: 紧急停止
        if self._emergency_stop:
            return False, "交易已紧急停止，请先调用 resume_trading()"
        
        # 使用有效交易资金（考虑 max_trading_capital 限制）
        effective_balance = self.get_effective_balance(account_balance)
        
        order_value = quantity * price
        
        # 检查 2: 订单金额范围
        if order_value < self.config.min_order_value:
            return False, f"订单金额 {order_value:.2f} 低于最小限制 {self.config.min_order_value}"
        
        if order_value > self.config.max_order_value:
            return False, f"订单金额 {order_value:.2f} 超过最大限制 {self.config.max_order_value}"
        
        # 检查 3: 单笔仓位限制
        max_single_value = effective_balance * self.config.max_single_position_pct
        if order_value > max_single_value:
            return False, f"订单金额 {order_value:.2f} 超过单笔仓位限制 {max_single_value:.2f} ({self.config.max_single_position_pct:.0%})"
        
        # 检查 4: 总仓位限制（仅买入时检查）
        if side.lower() == "buy":
            current_position_value = sum(p.get("market_value", 0) for p in current_positions)
            new_total = current_position_value + order_value
            max_total_value = effective_balance * self.config.max_total_position_pct
            
            if new_total > max_total_value:
                return False, f"买入后总仓位 {new_total:.2f} 将超过限制 {max_total_value:.2f} ({self.config.max_total_position_pct:.0%})"
        
        # 检查 5: 现金保留
        if side.lower() == "buy":
            min_cash = effective_balance * self.config.min_cash_reserve_pct
            available_cash = effective_balance - sum(p.get("market_value", 0) for p in current_positions)
            if available_cash - order_value < min_cash:
                return False, f"买入后现金将低于保留要求 {min_cash:.2f} ({self.config.min_cash_reserve_pct:.0%})"
        
        # 检查 6: 每日交易次数
        today = date.today().isoformat()
        daily_stats = self._get_daily_stats(today)
        if daily_stats["trade_count"] >= self.config.daily_trade_limit:
            return False, f"已达到每日交易次数限制 ({self.config.daily_trade_limit})"
        
        # 检查 7: 每日亏损限额
        if daily_stats["realized_pnl"] < 0:
            loss_pct = abs(daily_stats["realized_pnl"]) / effective_balance
            if loss_pct >= self.config.daily_loss_limit_pct:
                return False, f"已达到每日亏损限额 ({self.config.daily_loss_limit_pct:.1%})"
        
        # 检查 8: 冷却时间
        if symbol in self._last_order_time:
            elapsed = (datetime.now() - self._last_order_time[symbol]).total_seconds()
            if elapsed < self.config.order_cooldown_seconds:
                remaining = self.config.order_cooldown_seconds - elapsed
                return False, f"冷却中，请等待 {remaining:.0f} 秒"
        
        return True, "订单验证通过"
    
    # ==================== 止损止盈 ====================
    
    def set_stop_loss(self, symbol: str, stop_loss_price: float):
        """设置止损价"""
        if symbol not in self._position_stops:
            self._position_stops[symbol] = {}
        self._position_stops[symbol]["stop_loss"] = stop_loss_price
        self._save_state()
    
    def set_take_profit(self, symbol: str, take_profit_price: float):
        """设置止盈价"""
        if symbol not in self._position_stops:
            self._position_stops[symbol] = {}
        self._position_stops[symbol]["take_profit"] = take_profit_price
        self._save_state()
    
    def set_stops_from_cost(self, symbol: str, cost_price: float):
        """根据成本价自动设置止损止盈"""
        stop_loss = cost_price * (1 - self.config.default_stop_loss_pct)
        take_profit = cost_price * (1 + self.config.default_take_profit_pct)
        self.set_stop_loss(symbol, stop_loss)
        self.set_take_profit(symbol, take_profit)
        return stop_loss, take_profit
    
    def check_position_risk(
        self,
        symbol: str,
        quantity: int,
        cost_price: float,
        current_price: float
    ) -> PositionRisk:
        """检查持仓风险"""
        market_value = quantity * current_price
        cost_value = quantity * cost_price
        unrealized_pnl = market_value - cost_value
        unrealized_pnl_pct = unrealized_pnl / cost_value if cost_value > 0 else 0
        
        # 获取或计算止损止盈价
        stops = self._position_stops.get(symbol, {})
        stop_loss_price = stops.get("stop_loss", cost_price * (1 - self.config.default_stop_loss_pct))
        take_profit_price = stops.get("take_profit", cost_price * (1 + self.config.default_take_profit_pct))
        
        # 评估风险级别
        if unrealized_pnl_pct <= -self.config.default_stop_loss_pct:
            risk_level = RiskLevel.CRITICAL
        elif unrealized_pnl_pct <= -0.03:
            risk_level = RiskLevel.HIGH
        elif unrealized_pnl_pct <= -0.01:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        return PositionRisk(
            symbol=symbol,
            quantity=quantity,
            cost_price=cost_price,
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_level=risk_level
        )
    
    def scan_positions_for_exit(
        self,
        positions: List[dict],
        quotes: Dict[str, float]
    ) -> List[PositionRisk]:
        """扫描持仓，返回需要止损/止盈的列表"""
        exit_signals = []
        
        for pos in positions:
            symbol = pos["symbol"]
            current_price = quotes.get(symbol, pos.get("current_price", 0))
            
            if current_price <= 0:
                continue
            
            risk = self.check_position_risk(
                symbol=symbol,
                quantity=pos["quantity"],
                cost_price=pos["cost_price"],
                current_price=current_price
            )
            
            if risk.should_stop_loss or risk.should_take_profit:
                exit_signals.append(risk)
        
        return exit_signals
    
    # ==================== 交易记录 ====================
    
    def record_trade(self, trade: TradeRecord):
        """记录交易"""
        # 更新每日统计
        today = date.today().isoformat()
        daily_stats = self._get_daily_stats(today)
        daily_stats["trade_count"] += 1
        
        if trade.pnl is not None:
            daily_stats["realized_pnl"] += trade.pnl
        
        if trade.side == "buy":
            daily_stats["buy_value"] += trade.value
        else:
            daily_stats["sell_value"] += trade.value
        
        self._daily_stats[today] = daily_stats
        
        # 更新最后下单时间
        self._last_order_time[trade.symbol] = datetime.now()
        
        # 写入日志文件
        self._append_trade_log(trade)
        self._save_state()
    
    def get_daily_stats(self, day: str = None) -> dict:
        """获取每日统计"""
        day = day or date.today().isoformat()
        return self._get_daily_stats(day)
    
    # ==================== 仓位计算 ====================
    
    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        account_balance: float,
        risk_pct: float = None
    ) -> int:
        """
        计算建议的仓位大小
        
        Args:
            symbol: 股票代码
            price: 当前价格
            account_balance: 账户余额
            risk_pct: 风险比例（可选，默认使用配置）
        
        Returns:
            建议买入数量
        """
        # 使用有效交易资金
        effective_balance = self.get_effective_balance(account_balance)
        risk_pct = risk_pct or self.config.max_single_position_pct
        
        # 计算最大可用金额
        max_value = effective_balance * risk_pct
        max_value = min(max_value, self.config.max_order_value)
        
        # 计算数量（美股通常最小单位是1股）
        quantity = int(max_value / price)
        
        return max(0, quantity)
    
    # ==================== 风险报告 ====================
    
    def generate_risk_report(
        self,
        account_balance: float,
        positions: List[dict],
        quotes: Dict[str, float]
    ) -> str:
        """生成风险报告"""
        # 获取有效交易资金
        effective_balance = self.get_effective_balance(account_balance)
        
        lines = []
        lines.append("=" * 50)
        lines.append("📊 风险报告")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 50)
        
        # 账户概览
        total_position_value = sum(p.get("market_value", 0) for p in positions)
        position_pct = total_position_value / effective_balance if effective_balance > 0 else 0
        
        lines.append(f"\n💰 账户概览:")
        lines.append(f"  总资产: {account_balance:,.2f}")
        if self.config.max_trading_capital and self.config.max_trading_capital > 0:
            lines.append(f"  交易资金上限: {self.config.max_trading_capital:,.2f}")
        lines.append(f"  有效交易资金: {effective_balance:,.2f}")
        lines.append(f"  持仓市值: {total_position_value:,.2f} ({position_pct:.1%})")
        lines.append(f"  可用额度: {effective_balance - total_position_value:,.2f}")
        
        # 持仓风险
        lines.append(f"\n📈 持仓风险:")
        critical_count = 0
        high_count = 0
        
        for pos in positions:
            symbol = pos["symbol"]
            current_price = quotes.get(symbol, pos.get("current_price", 0))
            
            if current_price <= 0:
                continue
            
            risk = self.check_position_risk(
                symbol=symbol,
                quantity=pos["quantity"],
                cost_price=pos["cost_price"],
                current_price=current_price
            )
            
            emoji = {
                RiskLevel.LOW: "🟢",
                RiskLevel.MEDIUM: "🟡",
                RiskLevel.HIGH: "🟠",
                RiskLevel.CRITICAL: "🔴"
            }[risk.risk_level]
            
            lines.append(f"  {emoji} {symbol}: {risk.unrealized_pnl_pct:+.2%} (止损: {risk.stop_loss_price:.2f}, 止盈: {risk.take_profit_price:.2f})")
            
            if risk.risk_level == RiskLevel.CRITICAL:
                critical_count += 1
            elif risk.risk_level == RiskLevel.HIGH:
                high_count += 1
        
        if not positions:
            lines.append("  (空仓)")
        
        # 每日统计
        today = date.today().isoformat()
        daily_stats = self._get_daily_stats(today)
        
        lines.append(f"\n📅 今日统计:")
        lines.append(f"  交易次数: {daily_stats['trade_count']} / {self.config.daily_trade_limit}")
        lines.append(f"  已实现盈亏: {daily_stats['realized_pnl']:+,.2f}")
        lines.append(f"  买入金额: {daily_stats['buy_value']:,.2f}")
        lines.append(f"  卖出金额: {daily_stats['sell_value']:,.2f}")
        
        # 风险警告
        warnings = []
        if self._emergency_stop:
            warnings.append("🚨 交易已紧急停止")
        if critical_count > 0:
            warnings.append(f"🔴 {critical_count} 个持仓触及止损线")
        if high_count > 0:
            warnings.append(f"🟠 {high_count} 个持仓风险较高")
        if position_pct > self.config.max_total_position_pct:
            warnings.append(f"⚠️ 总仓位超限 ({position_pct:.1%} > {self.config.max_total_position_pct:.0%})")
        
        if warnings:
            lines.append(f"\n⚠️ 风险警告:")
            for w in warnings:
                lines.append(f"  {w}")
        
        lines.append("\n" + "=" * 50)
        
        return "\n".join(lines)
    
    # ==================== 内部方法 ====================
    
    def _get_daily_stats(self, day: str) -> dict:
        """获取或初始化每日统计"""
        if day not in self._daily_stats:
            self._daily_stats[day] = {
                "trade_count": 0,
                "realized_pnl": 0.0,
                "buy_value": 0.0,
                "sell_value": 0.0,
            }
        return self._daily_stats[day]
    
    def _log_event(self, event_type: str, data: dict):
        """记录事件"""
        log_file = self.data_dir / "risk_events.jsonl"
        event = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "data": data
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    
    def _append_trade_log(self, trade: TradeRecord):
        """追加交易日志"""
        log_file = self.data_dir / "trades.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(trade.to_dict(), ensure_ascii=False) + "\n")
    
    def _save_state(self):
        """保存状态"""
        state_file = self.data_dir / "risk_state.json"
        state = {
            "emergency_stop": self._emergency_stop,
            "daily_stats": self._daily_stats,
            "position_stops": self._position_stops,
        }
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def _load_state(self):
        """加载状态"""
        state_file = self.data_dir / "risk_state.json"
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
                    self._emergency_stop = state.get("emergency_stop", False)
                    self._daily_stats = state.get("daily_stats", {})
                    self._position_stops = state.get("position_stops", {})
            except Exception as e:
                print(f"⚠️ 加载风控状态失败: {e}")


# 单例
_risk_manager: Optional[RiskManager] = None


def get_risk_manager(config: RiskConfig = None) -> RiskManager:
    """获取风险管理器单例"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager(config=config)
    return _risk_manager
