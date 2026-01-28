"""
动量策略

追踪强势股票，买入近期涨幅大的股票。
结合 RSI 避免追高。
"""
from .base import BaseStrategy, TradeSignal, Signal


class MomentumStrategy(BaseStrategy):
    """动量策略"""
    
    name = "Momentum"
    description = "追踪强势股票，结合RSI过滤"
    
    def __init__(
        self, 
        lookback: int = 20,      # 回看周期
        rsi_period: int = 14,    # RSI 周期
        rsi_oversold: int = 30,  # 超卖阈值
        rsi_overbought: int = 70 # 超买阈值
    ):
        super().__init__()
        self.lookback = lookback
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
    
    def analyze(self, symbol: str, data: list) -> TradeSignal:
        """分析行情"""
        min_len = max(self.lookback, self.rsi_period + 1)
        
        if len(data) < min_len:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.HOLD,
                price=data[-1]["close"] if data else 0,
                reason=f"数据不足 (需要 {min_len} 根K线)",
                confidence=0
            )
        
        current_price = data[-1]["close"]
        
        # 计算动量（过去 N 日涨幅）
        lookback_price = data[-self.lookback]["close"]
        momentum = (current_price - lookback_price) / lookback_price * 100
        
        # 计算 RSI
        rsi_values = self.calculate_rsi(data, self.rsi_period)
        current_rsi = rsi_values[-1] if rsi_values else 50
        
        # 判断信号
        # 买入条件：动量强 + RSI 不超买
        if momentum > 5 and current_rsi < self.rsi_overbought:
            confidence = min(momentum / 20, 1.0) * (1 - current_rsi / 100)
            return TradeSignal(
                symbol=symbol,
                signal=Signal.BUY,
                price=current_price,
                reason=f"{self.lookback}日涨幅 {momentum:.1f}%, RSI {current_rsi:.0f}",
                confidence=confidence
            )
        
        # 卖出条件：RSI 超买 或 动量转负
        if current_rsi > self.rsi_overbought:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                reason=f"RSI超买 ({current_rsi:.0f} > {self.rsi_overbought})",
                confidence=min((current_rsi - self.rsi_overbought) / 30, 1.0)
            )
        
        if momentum < -5:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                reason=f"{self.lookback}日跌幅 {momentum:.1f}%",
                confidence=min(abs(momentum) / 20, 1.0)
            )
        
        # 持有
        return TradeSignal(
            symbol=symbol,
            signal=Signal.HOLD,
            price=current_price,
            reason=f"动量 {momentum:.1f}%, RSI {current_rsi:.0f}",
            confidence=0.5
        )
