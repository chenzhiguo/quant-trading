"""
智能止损模块 - 现代化止损策略 (支持自适应风控)

三大核心策略:
1. 波动率自适应止损 - 根据ATR动态设置止损幅度
2. 收盘价止损 - 只在收盘时判断，消除盘中噪音
3. 相对大盘止损 - 如果大盘也跌，放宽止损

组合决策: 三个策略投票，多数通过才触发止损
新特性: 支持基于 Beta 值的自适应风控模式
"""
import os
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
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
    risk_mode: str = "standard" # fixed or atr_trailing
    
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
    take_profit_pct: float = 0.15           # 默认止盈线 15% (将被自适应逻辑覆盖)
    
    # 自适应风控配置
    enable_adaptive_risk: bool = True       # 启用自适应风控
    high_volatility_threshold: float = 0.40 # 年化波动率阈值 (40%)
    
    # 通用风控参数 (统一使用 ATR + 追踪)
    atr_multiplier: float = 3.0             # ATR 止损倍数 (替代 fixed_stop_pct)
    trailing_start_pct: float = 0.05        # 浮盈 5% 开启追踪
    trailing_stop_pct: float = 0.05         # 回撤 5% 离场


class SmartStopManager:
    """智能止损管理器"""
    
    def __init__(self, config: SmartStopConfig = None, data_fetcher = None):
        self.config = config or SmartStopConfig()
        self._fetcher = data_fetcher
        self._atr_cache: Dict[str, Tuple[float, datetime]] = {}  # symbol -> (atr, timestamp)
        self._vol_cache: Dict[str, Tuple[float, datetime]] = {}  # symbol -> (volatility, timestamp)
        self._market_cache: Dict[str, Tuple[float, datetime]] = {}  # benchmark -> (change_pct, timestamp)
        # 最高价缓存 (用于追踪止损) - 实际应用需持久化，这里简化为内存
        self._high_water_mark: Dict[str, float] = {} 
    
    @property
    def fetcher(self):
        if self._fetcher is None:
            from .data import get_fetcher
            self._fetcher = get_fetcher()
        return self._fetcher
    
    def calculate_volatility(self, symbol: str) -> float:
        """计算年化波动率"""
        if symbol in self._vol_cache:
            cached_vol, cached_time = self._vol_cache[symbol]
            if datetime.now() - cached_time < timedelta(days=1):
                return cached_vol
                
        try:
            candles = self.fetcher.get_kline_df(symbol, days=100)
            if len(candles) < 30:
                return 0.0
            
            closes = [c["close"] for c in candles]
            returns = np.diff(closes) / closes[:-1]
            volatility = np.std(returns) * np.sqrt(252)
            
            self._vol_cache[symbol] = (volatility, datetime.now())
            return volatility
        except Exception as e:
            print(f"⚠️ 计算波动率失败 {symbol}: {e}")
            return 0.0

    # ==================== 策略1: 波动率自适应止损 ====================
    
    def calculate_atr(self, symbol: str, period: int = None) -> float:
        period = period or self.config.atr_period
        
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
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                tr_list.append(tr)
            
            atr = sum(tr_list[-period:]) / period
            self._atr_cache[symbol] = (atr, datetime.now())
            return atr
        except Exception:
            return 0
    
    def vote_adaptive_risk(
        self, 
        symbol: str, 
        cost_price: float, 
        current_price: float
    ) -> StopVote:
        """
        自适应风控核心逻辑 (统一使用 ATR + 追踪止盈)
        """
        if not self.config.enable_adaptive_risk:
            return StopVote("自适应风控", StopDecision.HOLD, "未启用", 0)

        # 1. 基础数据
        volatility = self.calculate_volatility(symbol)
        atr = self.calculate_atr(symbol)
        
        # 更新最高价 (水位线)
        if symbol not in self._high_water_mark or current_price > self._high_water_mark[symbol]:
            self._high_water_mark[symbol] = current_price
        
        high_price = self._high_water_mark[symbol]
        
        # 2. 追踪止盈 (统一应用)
        # 只有当浮盈达到 trailing_start_pct 时才激活
        highest_pnl = (high_price - cost_price) / cost_price
        drawdown = (high_price - current_price) / high_price
        
        if highest_pnl >= self.config.trailing_start_pct:
            if drawdown >= self.config.trailing_stop_pct:
                return StopVote(
                    strategy="自适应(追踪)",
                    decision=StopDecision.TAKE_PROFIT,
                    reason=f"追踪止盈触发 (最高盈:{highest_pnl:.1%} 回撤:{drawdown:.1%})",
                    confidence=1.0
                )
        
        # 3. ATR 止损 (统一应用)
        # 止损线 = 成本价 - ATR * 倍数
        stop_price = cost_price - (atr * self.config.atr_multiplier)
        if current_price < stop_price:
            return StopVote(
                strategy="自适应(ATR)",
                decision=StopDecision.STOP_LOSS,
                reason=f"触及ATR止损线 {stop_price:.2f} (ATR={atr:.2f})",
                confidence=0.9
            )
            
        return StopVote(
            strategy="自适应(风控)",
            decision=StopDecision.HOLD,
            reason=f"状态安全 (ATR止损:{stop_price:.2f}, 波动率:{volatility:.1%})",
            confidence=0.5
        )

    # ==================== 策略2: 收盘价止损 (保留作为辅助) ====================
    
    def is_near_market_close(self) -> bool:
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        if hour == 3 and minute >= 30: return True
        if hour == 4: return True
        if hour == 5 and minute <= 30: return True
        return False
    
    def vote_close_only(
        self,
        symbol: str,
        cost_price: float,
        current_price: float,
        force_check: bool = False
    ) -> StopVote:
        is_close_time = self.is_near_market_close() or force_check
        
        if not is_close_time and self.config.use_close_only:
            return StopVote("收盘价止损", StopDecision.HOLD, "非收盘时段", 1.0)
        
        # 兼容旧逻辑，使用固定8%作为硬止损
        stop_price = cost_price * (1 - 0.08)
        if current_price <= stop_price:
            return StopVote("收盘价止损", StopDecision.STOP_LOSS, f"收盘破位 {stop_price:.2f}", 0.85)
            
        return StopVote("收盘价止损", StopDecision.HOLD, "安全", 0.5)
    
    # ==================== 策略3: 相对大盘止损 (保留作为辅助) ====================
    
    def get_market_change(self) -> float:
        benchmark = self.config.market_benchmark
        if benchmark in self._market_cache:
            cached, time = self._market_cache[benchmark]
            if datetime.now() - time < timedelta(minutes=5): return cached
        try:
            quotes = self.fetcher.get_quote_with_change([benchmark])
            if quotes:
                change = quotes[0]["change_pct"] / 100
                self._market_cache[benchmark] = (change, datetime.now())
                return change
        except Exception:
            pass
        return 0
    
    def vote_relative_market(self, symbol: str, cost_price: float, current_price: float) -> StopVote:
        market_change = self.get_market_change()
        stock_change = (current_price - cost_price) / cost_price
        excess_drop = stock_change - market_change
        
        base_stop = 0.05
        if market_change < 0:
            adjusted_stop = base_stop + abs(market_change) * self.config.market_drop_buffer
        else:
            adjusted_stop = base_stop
            
        if excess_drop < -adjusted_stop:
            return StopVote("相对大盘", StopDecision.STOP_LOSS, f"超额跌幅 {excess_drop:.1%}", 0.75)
            
        return StopVote("相对大盘", StopDecision.HOLD, "正常", 0.5)
    
    # ==================== 组合决策 ====================
    
    def evaluate(
        self,
        symbol: str,
        cost_price: float,
        current_price: float,
        force_close_check: bool = False
    ) -> SmartStopResult:
        """
        综合决策
        """
        # 1. 自适应风控投票 (权重最高)
        adaptive_vote = self.vote_adaptive_risk(symbol, cost_price, current_price)
        
        # 2. 其他辅助投票
        close_vote = self.vote_close_only(symbol, cost_price, current_price, force_close_check)
        relative_vote = self.vote_relative_market(symbol, cost_price, current_price)
        
        votes = [adaptive_vote, close_vote, relative_vote]
        
        # 决策逻辑: 自适应风控有一票否决权 (如果是止损/止盈)
        if adaptive_vote.decision != StopDecision.HOLD:
            final_decision = adaptive_vote.decision
        else:
            # 如果自适应觉得没问题，再看其他策略是否强烈建议止损 (且是收盘时)
            stop_votes = sum(1 for v in votes if v.decision == StopDecision.STOP_LOSS)
            if stop_votes >= 2 and (self.is_near_market_close() or force_close_check):
                final_decision = StopDecision.STOP_LOSS
            else:
                final_decision = StopDecision.HOLD
        
        vote_summary = f"主策略:{adaptive_vote.decision.value} | 辅助:{close_vote.decision.value}/{relative_vote.decision.value}"
        pnl_pct = (current_price - cost_price) / cost_price
        
        # 提取模式描述
        vol = self.calculate_volatility(symbol)
        vol_tag = "高波" if vol > self.config.high_volatility_threshold else "稳健"
        mode_desc = f"{vol_tag}(ATR+追踪)"
        
        return SmartStopResult(
            symbol=symbol,
            final_decision=final_decision,
            votes=votes,
            vote_summary=vote_summary,
            details={
                "pnl_pct": pnl_pct,
                "volatility": vol,
                "mode": mode_desc,
                "current_price": current_price
            },
            risk_mode=mode_desc
        )
    
    def scan_positions(
        self,
        positions: List[Dict],
        quotes: Dict[str, float] = None,
        force_close_check: bool = False
    ) -> List[SmartStopResult]:
        if quotes is None:
            symbols = [p["symbol"] for p in positions]
            quote_list = self.fetcher.get_quote_with_change(symbols)
            quotes = {q["symbol"]: q["price"] for q in quote_list}
        
        results = []
        for pos in positions:
            symbol = pos["symbol"]
            cost_price = pos["cost_price"]
            current_price = quotes.get(symbol, 0)
            
            if current_price <= 0: continue
            
            result = self.evaluate(symbol, cost_price, current_price, force_close_check)
            results.append(result)
        
        return results
    
    def generate_report(self, results: List[SmartStopResult]) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append(f"🧠 智能止损分析报告 (自适应版) - {datetime.now().strftime('%H:%M:%S')}")
        lines.append("=" * 60)
        
        exit_results = [r for r in results if r.should_exit]
        hold_results = [r for r in results if not r.should_exit]
        
        if exit_results:
            lines.append("🚨 需要操作:")
            for r in exit_results:
                action = "止损" if r.final_decision == StopDecision.STOP_LOSS else "止盈"
                emoji = "🔴" if action == "止损" else "🟢"
                lines.append(f"  {emoji} {r.symbol} [{action}] 盈亏:{r.details['pnl_pct']:+.1%} ({r.risk_mode})")
                for v in r.votes:
                    if v.decision != StopDecision.HOLD:
                        lines.append(f"      👉 {v.reason}")
        else:
            lines.append("✅ 无需操作")
        
        if hold_results:
            lines.append("\n📋 持仓监控:")
            for r in hold_results:
                vol = r.details.get('volatility', 0)
                lines.append(f"  🟢 {r.symbol} 盈亏:{r.details['pnl_pct']:+.1%} | 波动率:{vol:.1%} | 模式:{r.risk_mode}")
        
        lines.append("=" * 60)
        return "\n".join(lines)


_smart_stop_manager: Optional[SmartStopManager] = None

def get_smart_stop_manager(config: SmartStopConfig = None) -> SmartStopManager:
    global _smart_stop_manager
    if _smart_stop_manager is None:
        _smart_stop_manager = SmartStopManager(config=config)
    return _smart_stop_manager
