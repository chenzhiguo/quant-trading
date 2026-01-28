"""
均线交叉策略

当短期均线上穿长期均线时买入，下穿时卖出。
"""
from .base import BaseStrategy, TradeSignal, Signal


class MACrossStrategy(BaseStrategy):
    """均线交叉策略"""
    
    name = "MA Cross"
    description = "短期均线上穿/下穿长期均线"
    
    def __init__(self, short_period: int = 5, long_period: int = 20):
        super().__init__()
        self.short_period = short_period
        self.long_period = long_period
    
    def analyze(self, symbol: str, data: list) -> TradeSignal:
        """分析行情"""
        if len(data) < self.long_period + 2:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.HOLD,
                price=data[-1]["close"] if data else 0,
                reason=f"数据不足 (需要 {self.long_period + 2} 根K线)",
                confidence=0
            )
        
        # 计算均线
        short_ma = self.calculate_ma(data, self.short_period)
        long_ma = self.calculate_ma(data, self.long_period)
        
        # 对齐数据
        offset = self.long_period - self.short_period
        short_ma = short_ma[offset:]
        
        if len(short_ma) < 2 or len(long_ma) < 2:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.HOLD,
                price=data[-1]["close"],
                reason="均线计算数据不足",
                confidence=0
            )
        
        current_price = data[-1]["close"]
        
        # 判断交叉
        prev_short, curr_short = short_ma[-2], short_ma[-1]
        prev_long, curr_long = long_ma[-2], long_ma[-1]
        
        # 金叉：短期均线从下方上穿长期均线
        if prev_short <= prev_long and curr_short > curr_long:
            # 计算信心度：基于均线差距
            gap = (curr_short - curr_long) / curr_long * 100
            confidence = min(gap / 2, 1.0)  # 差距越大信心越高
            
            return TradeSignal(
                symbol=symbol,
                signal=Signal.BUY,
                price=current_price,
                reason=f"MA{self.short_period}上穿MA{self.long_period} (金叉)",
                confidence=confidence
            )
        
        # 死叉：短期均线从上方下穿长期均线
        if prev_short >= prev_long and curr_short < curr_long:
            gap = (curr_long - curr_short) / curr_long * 100
            confidence = min(gap / 2, 1.0)
            
            return TradeSignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                reason=f"MA{self.short_period}下穿MA{self.long_period} (死叉)",
                confidence=confidence
            )
        
        # 持有
        if curr_short > curr_long:
            reason = f"MA{self.short_period} > MA{self.long_period}，保持多头"
        else:
            reason = f"MA{self.short_period} < MA{self.long_period}，观望中"
        
        return TradeSignal(
            symbol=symbol,
            signal=Signal.HOLD,
            price=current_price,
            reason=reason,
            confidence=0.5
        )
