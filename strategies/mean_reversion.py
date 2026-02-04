"""
均值回归策略 (Mean Reversion)

核心理念：追跌不追涨
- 买入：股价大幅下跌后超卖，等待反弹
- 卖出：反弹到均线附近或超买时离场

适合逆向投资风格。
"""
from .base import BaseStrategy, TradeSignal, Signal


class MeanReversionStrategy(BaseStrategy):
    """均值回归策略 - 追跌抄底"""
    
    name = "MeanReversion"
    description = "均值回归，追跌不追涨"
    
    def __init__(
        self,
        lookback: int = 20,           # 回看周期（计算跌幅）
        ma_period: int = 20,          # 均线周期
        rsi_period: int = 14,         # RSI 周期
        # 买入条件
        min_drop: float = -10.0,      # 最小跌幅阈值 (%)
        rsi_oversold: int = 35,       # RSI 超卖阈值
        ma_deviation: float = -5.0,   # 偏离均线阈值 (%)
        # 卖出条件
        rsi_overbought: int = 60,     # RSI 超买阈值（反弹后离场）
        take_profit: float = 10.0,    # 止盈涨幅 (%)
        stop_loss: float = -20.0,     # 止损跌幅 (%)
    ):
        super().__init__()
        self.lookback = lookback
        self.ma_period = ma_period
        self.rsi_period = rsi_period
        self.min_drop = min_drop
        self.rsi_oversold = rsi_oversold
        self.ma_deviation = ma_deviation
        self.rsi_overbought = rsi_overbought
        self.take_profit = take_profit
        self.stop_loss = stop_loss
    
    def analyze(self, symbol: str, data: list) -> TradeSignal:
        """分析行情"""
        min_len = max(self.lookback, self.ma_period, self.rsi_period + 1)
        
        if len(data) < min_len:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.HOLD,
                price=data[-1]["close"] if data else 0,
                reason=f"数据不足 (需要 {min_len} 根K线)",
                confidence=0
            )
        
        current_price = data[-1]["close"]
        
        # 1. 计算 N 日涨跌幅
        lookback_price = data[-self.lookback]["close"]
        change_pct = (current_price - lookback_price) / lookback_price * 100
        
        # 2. 计算均线和偏离度
        ma_values = self.calculate_ma(data, self.ma_period)
        current_ma = ma_values[-1] if ma_values else current_price
        ma_dev = (current_price - current_ma) / current_ma * 100
        
        # 3. 计算 RSI
        rsi_values = self.calculate_rsi(data, self.rsi_period)
        current_rsi = rsi_values[-1] if rsi_values else 50
        
        # 4. 计算布林带（辅助判断）
        bb_lower, bb_upper = self._calculate_bollinger(data, self.ma_period)
        near_bb_lower = current_price <= bb_lower * 1.02 if bb_lower else False
        
        # ========== 买入逻辑 (抄底) ==========
        # 条件1: 大幅下跌
        is_oversold = change_pct <= self.min_drop
        # 条件2: RSI 超卖
        rsi_low = current_rsi <= self.rsi_oversold
        # 条件3: 价格低于均线
        below_ma = ma_dev <= self.ma_deviation
        
        # 满足任意两个条件即可触发买入信号
        buy_score = sum([is_oversold, rsi_low, below_ma, near_bb_lower])
        
        if buy_score >= 2:
            # 计算置信度：条件满足越多、偏离越大，置信度越高
            confidence = min(1.0, (
                abs(change_pct) / 30 * 0.4 +           # 跌幅贡献
                (self.rsi_oversold - current_rsi) / 35 * 0.3 +  # RSI贡献
                abs(ma_dev) / 15 * 0.3                 # 均线偏离贡献
            ))
            confidence = max(0.1, min(confidence, 1.0))
            
            reasons = []
            if is_oversold:
                reasons.append(f"{self.lookback}日跌{change_pct:.1f}%")
            if rsi_low:
                reasons.append(f"RSI {current_rsi:.0f}")
            if below_ma:
                reasons.append(f"低于MA{self.ma_period} {ma_dev:.1f}%")
            if near_bb_lower:
                reasons.append("触及布林下轨")
            
            return TradeSignal(
                symbol=symbol,
                signal=Signal.BUY,
                price=current_price,
                reason="超卖抄底: " + ", ".join(reasons),
                confidence=confidence
            )
        
        # ========== 卖出逻辑 (止盈/止损) ==========
        # 条件1: RSI 超买（反弹到位）
        if current_rsi >= self.rsi_overbought:
            confidence = min((current_rsi - self.rsi_overbought) / 30 + 0.3, 1.0)
            return TradeSignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                reason=f"反弹止盈: RSI {current_rsi:.0f} (>{self.rsi_overbought})",
                confidence=confidence
            )
        
        # 条件2: 价格回到均线上方（均值回归完成）
        if ma_dev >= 2.0 and change_pct > 0:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                reason=f"均值回归: 价格已回到MA{self.ma_period}上方 {ma_dev:.1f}%",
                confidence=0.5
            )
        
        # 条件3: 继续暴跌（止损）
        if change_pct <= self.stop_loss:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                reason=f"止损: {self.lookback}日跌幅 {change_pct:.1f}%",
                confidence=0.9
            )
        
        # ========== 持有 ==========
        return TradeSignal(
            symbol=symbol,
            signal=Signal.HOLD,
            price=current_price,
            reason=f"观望: {self.lookback}日{change_pct:+.1f}%, RSI {current_rsi:.0f}, MA偏离{ma_dev:+.1f}%",
            confidence=0.5
        )
    
    def _calculate_bollinger(self, data: list, period: int, num_std: float = 2.0):
        """计算布林带"""
        if len(data) < period:
            return None, None
        
        # 计算均值
        closes = [d["close"] for d in data[-period:]]
        ma = sum(closes) / period
        
        # 计算标准差
        variance = sum((c - ma) ** 2 for c in closes) / period
        std = variance ** 0.5
        
        lower = ma - num_std * std
        upper = ma + num_std * std
        
        return lower, upper
