"""
智能止损模块 - 现代化止损策略

三大核心策略:
1. 波动率自适应止损 - 根据ATR动态设置止损幅度
2. 收盘价止损 - 只在收盘时判断，消除盘中噪音
3. 相对大盘止损 - 如果大盘也跌，放宽止损

组合决策: 三个策略投票，多数通过才触发止损
"""
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from enum import Enum


class StopDecision(Enum):
    """止损决策"""
    HOLD = "hold"           # 持有不动
    STOP_LOSS = "stop_loss" # 触发止损
    TAKE_PROFIT = "take_profit"  # 触发止盈


@dataclass
class StopVote:
    """单个策略的投票结果"""
    strategy: str
    decision: StopDecision
    reason: str
    confidence: float  # 0-1，置信度


@dataclass
class SmartStopResult:
    """智能止损综合结果"""
    symbol: str
    final_decision: StopDecision
    votes: List[StopVote]
    vote_summary: str
    details: Dict
    
    @property
    def should_exit(self) -> bool:
        return self.final_decision in [StopDecision.STOP_LOSS, StopDecision.TAKE_PROFIT]


@dataclass
class SmartStopConfig:
    """智能止损配置"""
    # 波动率自适应
    atr_period: int = 14                    # ATR 计算周期
    atr_multiplier: float = 2.5             # ATR 倍数 (止损 = 买入价 - ATR * 倍数)
    min_stop_pct: float = 0.03              # 最小止损幅度 3%
    max_stop_pct: float = 0.15              # 最大止损幅度 15%
    
    # 收盘价止损
    use_close_only: bool = True             # 只用收盘价判断
    close_tolerance_minutes: int = 30       # 收盘前后多少分钟视为"收盘时"
    
    # 相对大盘
    market_benchmark: str = "SPY.US"        # 基准指数
    market_correlation_threshold: float = 0.5  # 相关性阈值
    market_drop_buffer: float = 1.2         # 大盘跌幅缓冲 (如果大盘跌5%，个股可以多跌 5%*1.2=6%)
    
    # 投票规则
    vote_threshold: int = 2                 # 需要几票才触发止损 (共3票)
    
    # 止盈
    take_profit_pct: float = 0.15           # 止盈线 15%


class SmartStopManager:
    """智能止损管理器"""
    
    def __init__(self, config: SmartStopConfig = None, data_fetcher = None):
        self.config = config or SmartStopConfig()
        self._fetcher = data_fetcher
        self._atr_cache: Dict[str, Tuple[float, datetime]] = {}  # symbol -> (atr, timestamp)
        self._market_cache: Dict[str, Tuple[float, datetime]] = {}  # benchmark -> (change_pct, timestamp)
    
    @property
    def fetcher(self):
        if self._fetcher is None:
            from .data import get_fetcher
            self._fetcher = get_fetcher()
        return self._fetcher
    
    # ==================== 策略1: 波动率自适应止损 ====================
    
    def calculate_atr(self, symbol: str, period: int = None) -> float:
        """
        计算 ATR (Average True Range)
        
        ATR = 过去N天的 TR 平均值
        TR = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        """
        period = period or self.config.atr_period
        
        # 检查缓存 (1小时有效)
        if symbol in self._atr_cache:
            cached_atr, cached_time = self._atr_cache[symbol]
            if datetime.now() - cached_time < timedelta(hours=1):
                return cached_atr
        
        try:
            candles = self.fetcher.get_kline_df(symbol, days=period + 10)
            if len(candles) < period + 1:
                return 0
            
            tr_list = []
            for i in range(1, len(candles)):
                high = candles[i]["high"]
                low = candles[i]["low"]
                prev_close = candles[i-1]["close"]
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                tr_list.append(tr)
            
            # 取最近 period 天的平均
            atr = sum(tr_list[-period:]) / period
            
            # 缓存
            self._atr_cache[symbol] = (atr, datetime.now())
            
            return atr
            
        except Exception as e:
            print(f"⚠️ 计算 {symbol} ATR 失败: {e}")
            return 0
    
    def get_adaptive_stop_loss(self, symbol: str, cost_price: float) -> float:
        """
        根据 ATR 计算自适应止损价
        
        止损价 = 成本价 - ATR * 倍数
        受 min/max_stop_pct 约束
        """
        atr = self.calculate_atr(symbol)
        
        if atr <= 0:
            # 无法计算 ATR，使用默认 5%
            return cost_price * (1 - 0.05)
        
        # ATR 止损距离
        atr_stop_distance = atr * self.config.atr_multiplier
        atr_stop_pct = atr_stop_distance / cost_price
        
        # 约束在 min/max 范围内
        stop_pct = max(self.config.min_stop_pct, min(self.config.max_stop_pct, atr_stop_pct))
        
        return cost_price * (1 - stop_pct)
    
    def vote_atr_stop(
        self, 
        symbol: str, 
        cost_price: float, 
        current_price: float
    ) -> StopVote:
        """
        策略1投票: ATR自适应止损
        """
        atr = self.calculate_atr(symbol)
        adaptive_stop = self.get_adaptive_stop_loss(symbol, cost_price)
        adaptive_stop_pct = (cost_price - adaptive_stop) / cost_price
        
        # 当前亏损
        pnl_pct = (current_price - cost_price) / cost_price
        
        # 止盈检查
        if pnl_pct >= self.config.take_profit_pct:
            return StopVote(
                strategy="ATR自适应",
                decision=StopDecision.TAKE_PROFIT,
                reason=f"盈利 {pnl_pct:.1%} >= 止盈线 {self.config.take_profit_pct:.0%}",
                confidence=0.9
            )
        
        # 止损检查
        if current_price <= adaptive_stop:
            return StopVote(
                strategy="ATR自适应",
                decision=StopDecision.STOP_LOSS,
                reason=f"价格 {current_price:.2f} <= ATR止损线 {adaptive_stop:.2f} (ATR={atr:.2f}, 止损幅度={adaptive_stop_pct:.1%})",
                confidence=0.8
            )
        
        return StopVote(
            strategy="ATR自适应",
            decision=StopDecision.HOLD,
            reason=f"价格 {current_price:.2f} > ATR止损线 {adaptive_stop:.2f}",
            confidence=0.8
        )
    
    # ==================== 策略2: 收盘价止损 ====================
    
    def is_near_market_close(self) -> bool:
        """
        判断当前是否接近美股收盘时间
        
        美股收盘: 北京时间 4:00 (夏令时) 或 5:00 (冬令时)
        这里简化处理，认为 3:30-5:30 都是"收盘附近"
        """
        now = datetime.now()
        # 北京时间
        hour = now.hour
        minute = now.minute
        
        # 3:30 - 5:30 视为收盘时段
        if hour == 3 and minute >= 30:
            return True
        if hour == 4:
            return True
        if hour == 5 and minute <= 30:
            return True
        
        return False
    
    def get_last_close_price(self, symbol: str) -> Optional[float]:
        """获取最近一个交易日的收盘价"""
        try:
            candles = self.fetcher.get_kline_df(symbol, days=5)
            if candles:
                return candles[-1]["close"]
        except Exception:
            pass
        return None
    
    def vote_close_only(
        self,
        symbol: str,
        cost_price: float,
        current_price: float,
        force_check: bool = False
    ) -> StopVote:
        """
        策略2投票: 收盘价止损
        
        只在收盘时才判断，盘中不触发止损
        force_check=True 可以强制检查（用于收盘后回顾）
        """
        is_close_time = self.is_near_market_close() or force_check
        
        if not is_close_time and self.config.use_close_only:
            return StopVote(
                strategy="收盘价止损",
                decision=StopDecision.HOLD,
                reason="非收盘时段，暂不判断止损",
                confidence=1.0
            )
        
        # 使用简单的固定比例（因为 ATR 策略已经做了动态）
        # 这里用 8% 作为收盘价止损的基准
        close_stop_pct = 0.08
        close_stop_price = cost_price * (1 - close_stop_pct)
        
        pnl_pct = (current_price - cost_price) / cost_price
        
        # 止盈
        if pnl_pct >= self.config.take_profit_pct:
            return StopVote(
                strategy="收盘价止损",
                decision=StopDecision.TAKE_PROFIT,
                reason=f"收盘盈利 {pnl_pct:.1%} >= 止盈线",
                confidence=0.9
            )
        
        # 止损
        if current_price <= close_stop_price:
            return StopVote(
                strategy="收盘价止损",
                decision=StopDecision.STOP_LOSS,
                reason=f"收盘价 {current_price:.2f} 低于止损线 {close_stop_price:.2f} (跌幅 {-pnl_pct:.1%})",
                confidence=0.85
            )
        
        return StopVote(
            strategy="收盘价止损",
            decision=StopDecision.HOLD,
            reason=f"收盘价 {current_price:.2f} 在安全范围内 (止损线 {close_stop_price:.2f})",
            confidence=0.85
        )
    
    # ==================== 策略3: 相对大盘止损 ====================
    
    def get_market_change(self) -> float:
        """
        获取大盘今日涨跌幅
        """
        # 检查缓存 (5分钟有效)
        benchmark = self.config.market_benchmark
        if benchmark in self._market_cache:
            cached_change, cached_time = self._market_cache[benchmark]
            if datetime.now() - cached_time < timedelta(minutes=5):
                return cached_change
        
        try:
            quotes = self.fetcher.get_quote_with_change([benchmark])
            if quotes:
                change_pct = quotes[0]["change_pct"] / 100  # 转为小数
                self._market_cache[benchmark] = (change_pct, datetime.now())
                return change_pct
        except Exception as e:
            print(f"⚠️ 获取大盘行情失败: {e}")
        
        return 0
    
    def vote_relative_market(
        self,
        symbol: str,
        cost_price: float,
        current_price: float
    ) -> StopVote:
        """
        策略3投票: 相对大盘止损
        
        如果大盘也在跌，个股跌幅可以放宽
        例如: 大盘跌3%，个股跌5%，相对只跌了2%，不触发止损
        """
        market_change = self.get_market_change()
        stock_change = (current_price - cost_price) / cost_price
        
        # 相对大盘的超额跌幅
        # 如果大盘跌 -3%，个股跌 -5%，超额跌幅 = -5% - (-3%) = -2%
        excess_drop = stock_change - market_change
        
        # 动态止损线: 基础5% + 大盘跌幅的缓冲
        base_stop = 0.05
        if market_change < 0:
            # 大盘下跌时，放宽止损
            buffer = abs(market_change) * self.config.market_drop_buffer
            adjusted_stop = base_stop + buffer
            adjusted_stop = min(adjusted_stop, self.config.max_stop_pct)  # 最大15%
        else:
            adjusted_stop = base_stop
        
        # 止盈
        if stock_change >= self.config.take_profit_pct:
            return StopVote(
                strategy="相对大盘",
                decision=StopDecision.TAKE_PROFIT,
                reason=f"盈利 {stock_change:.1%} >= 止盈线",
                confidence=0.9
            )
        
        # 止损判断: 用超额跌幅和调整后的止损线比较
        if excess_drop < -adjusted_stop:
            return StopVote(
                strategy="相对大盘",
                decision=StopDecision.STOP_LOSS,
                reason=f"超额跌幅 {excess_drop:.1%} 超过调整止损线 -{adjusted_stop:.1%} (大盘 {market_change:+.1%})",
                confidence=0.75
            )
        
        return StopVote(
            strategy="相对大盘",
            decision=StopDecision.HOLD,
            reason=f"超额跌幅 {excess_drop:.1%} 在容忍范围内 (大盘 {market_change:+.1%}, 调整止损 -{adjusted_stop:.1%})",
            confidence=0.75
        )
    
    # ==================== 组合决策 ====================
    
    def evaluate(
        self,
        symbol: str,
        cost_price: float,
        current_price: float,
        force_close_check: bool = False
    ) -> SmartStopResult:
        """
        综合三个策略进行投票决策
        
        Args:
            symbol: 股票代码
            cost_price: 成本价
            current_price: 当前价
            force_close_check: 强制按收盘价逻辑判断
        
        Returns:
            SmartStopResult 包含投票详情和最终决策
        """
        # 收集三个策略的投票
        votes = [
            self.vote_atr_stop(symbol, cost_price, current_price),
            self.vote_close_only(symbol, cost_price, current_price, force_close_check),
            self.vote_relative_market(symbol, cost_price, current_price),
        ]
        
        # 统计投票
        stop_votes = sum(1 for v in votes if v.decision == StopDecision.STOP_LOSS)
        profit_votes = sum(1 for v in votes if v.decision == StopDecision.TAKE_PROFIT)
        hold_votes = sum(1 for v in votes if v.decision == StopDecision.HOLD)
        
        # 决策逻辑
        if profit_votes >= self.config.vote_threshold:
            final_decision = StopDecision.TAKE_PROFIT
        elif stop_votes >= self.config.vote_threshold:
            final_decision = StopDecision.STOP_LOSS
        else:
            final_decision = StopDecision.HOLD
        
        # 生成摘要
        vote_summary = f"止损:{stop_votes} | 止盈:{profit_votes} | 持有:{hold_votes}"
        
        pnl_pct = (current_price - cost_price) / cost_price
        
        return SmartStopResult(
            symbol=symbol,
            final_decision=final_decision,
            votes=votes,
            vote_summary=vote_summary,
            details={
                "cost_price": cost_price,
                "current_price": current_price,
                "pnl_pct": pnl_pct,
                "atr": self.calculate_atr(symbol),
                "atr_stop": self.get_adaptive_stop_loss(symbol, cost_price),
                "market_change": self.get_market_change(),
            }
        )
    
    def scan_positions(
        self,
        positions: List[Dict],
        quotes: Dict[str, float] = None,
        force_close_check: bool = False
    ) -> List[SmartStopResult]:
        """
        扫描所有持仓，返回需要操作的列表
        
        Args:
            positions: 持仓列表 [{"symbol": "AAPL.US", "cost_price": 150, "quantity": 10}, ...]
            quotes: 实时报价 {symbol: price}
            force_close_check: 强制按收盘价逻辑
        
        Returns:
            需要止损/止盈的持仓列表
        """
        if quotes is None:
            # 获取报价
            symbols = [p["symbol"] for p in positions]
            quote_list = self.fetcher.get_quote_with_change(symbols)
            quotes = {q["symbol"]: q["price"] for q in quote_list}
        
        results = []
        for pos in positions:
            symbol = pos["symbol"]
            cost_price = pos["cost_price"]
            current_price = quotes.get(symbol, 0)
            
            if current_price <= 0:
                continue
            
            result = self.evaluate(
                symbol=symbol,
                cost_price=cost_price,
                current_price=current_price,
                force_close_check=force_close_check
            )
            
            results.append(result)
        
        return results
    
    def generate_report(self, results: List[SmartStopResult]) -> str:
        """生成智能止损报告"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"🧠 智能止损分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        
        # 大盘行情
        market_change = self.get_market_change()
        lines.append(f"\n📊 大盘 ({self.config.market_benchmark}): {market_change:+.2%}")
        
        # 是否收盘时段
        if self.is_near_market_close():
            lines.append("⏰ 当前为收盘时段，收盘价止损策略生效")
        else:
            lines.append("⏰ 非收盘时段，收盘价止损策略暂不生效")
        
        lines.append("")
        
        # 需要操作的持仓
        exit_results = [r for r in results if r.should_exit]
        hold_results = [r for r in results if not r.should_exit]
        
        if exit_results:
            lines.append("🚨 需要操作:")
            for r in exit_results:
                emoji = "🔴" if r.final_decision == StopDecision.STOP_LOSS else "🟢"
                action = "止损" if r.final_decision == StopDecision.STOP_LOSS else "止盈"
                pnl_pct = r.details["pnl_pct"]
                lines.append(f"  {emoji} {r.symbol} [{action}] 盈亏:{pnl_pct:+.1%} | {r.vote_summary}")
                for v in r.votes:
                    vote_emoji = "✓" if v.decision != StopDecision.HOLD else "✗"
                    lines.append(f"      {vote_emoji} {v.strategy}: {v.reason}")
        else:
            lines.append("✅ 无需操作")
        
        lines.append("")
        
        # 安全持仓
        if hold_results:
            lines.append("📋 安全持仓:")
            for r in hold_results:
                pnl_pct = r.details["pnl_pct"]
                atr_stop = r.details["atr_stop"]
                lines.append(f"  🟢 {r.symbol} 盈亏:{pnl_pct:+.1%} | ATR止损线:{atr_stop:.2f} | {r.vote_summary}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)


# 单例
_smart_stop_manager: Optional[SmartStopManager] = None


def get_smart_stop_manager(config: SmartStopConfig = None) -> SmartStopManager:
    """获取智能止损管理器单例"""
    global _smart_stop_manager
    if _smart_stop_manager is None:
        _smart_stop_manager = SmartStopManager(config=config)
    return _smart_stop_manager
