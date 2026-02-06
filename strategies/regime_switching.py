"""
Regime Switching Strategy (趋势/震荡切换策略)
逻辑与回测脚本 (backtest_portfolio.py) 保持一致
"""
import pandas as pd
import numpy as np
from .base import BaseStrategy, Signal, TradeSignal

class RegimeSwitchingStrategy(BaseStrategy):
    name = "RegimeSwitching"
    description = "基于ADX的趋势/震荡自动切换策略"
    
    def __init__(self, params: dict = None):
        super().__init__(params)
        self.adx_threshold = self.params.get('adx_threshold', 30)
        self.adx_wait_threshold = self.params.get('adx_wait_threshold', 20)
        self.rsi_oversold = self.params.get('rsi_oversold', 35)
        self.rsi_overbought = self.params.get('rsi_overbought', 65)
        self.alpha_threshold = self.params.get('alpha_threshold', 0.5)
        
    def analyze(self, symbol: str, data: list) -> TradeSignal:
        if not data or len(data) < 50:
            return TradeSignal(symbol, Signal.HOLD, 0, "数据不足", 0)
            
        # 转为 DataFrame
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data.copy()
            
        # 确保列名小写
        df.columns = [c.lower() for c in df.columns]
        
        # 计算指标
        df = self._calc_indicators(df)
        
        # 获取最新一行
        latest = df.iloc[-1]
        price = latest['close']
        
        adx = latest['adx']
        rsi = latest['rsi']
        alpha = latest['alpha']
        
        if pd.isna(adx) or pd.isna(rsi):
            return TradeSignal(symbol, Signal.HOLD, price, "指标无效", 0)
            
        # 状态判断 (优化后)
        mode = "Wait"
        signal = Signal.HOLD
        reason = ""
        confidence = 0.0
        
        if adx > self.adx_threshold:
            # 趋势模式: Alpha 信号
            mode = "Trend"
            if alpha > self.alpha_threshold:
                signal = Signal.BUY
                confidence = abs(alpha) * (min(adx, 50) / 50)
                reason = f"Trend Buy (Alpha={alpha:.2f}, ADX={adx:.1f})"
            elif alpha < -self.alpha_threshold:
                signal = Signal.SELL
                confidence = abs(alpha) * (min(adx, 50) / 50)
                reason = f"Trend Sell (Alpha={alpha:.2f}, ADX={adx:.1f})"
            else:
                reason = f"Trend Hold (Alpha={alpha:.2f})"
                
        elif adx < self.adx_wait_threshold:
            # 震荡模式: RSI 信号
            mode = "Range"
            if rsi < self.rsi_oversold:
                signal = Signal.BUY
                confidence = (self.rsi_oversold - rsi) / self.rsi_oversold * 0.8
                # 限制最大置信度
                confidence = min(confidence, 0.95)
                reason = f"Range Buy (RSI={rsi:.1f}, ADX={adx:.1f})"
            elif rsi > self.rsi_overbought:
                signal = Signal.SELL
                confidence = (rsi - self.rsi_overbought) / (100 - self.rsi_overbought) * 0.8
                confidence = min(confidence, 0.95)
                reason = f"Range Sell (RSI={rsi:.1f}, ADX={adx:.1f})"
            else:
                reason = f"Range Hold (RSI={rsi:.1f})"
        else:
            # 观望模式 (20 <= ADX <= 30)
            mode = "Wait"
            signal = Signal.HOLD
            reason = f"Wait Zone (ADX={adx:.1f})"
            confidence = 0.0
                
        # 附加波动率信息
        vol_note = ""
        if 'volatility' in latest and not pd.isna(latest['volatility']):
            vol_note = f" Vol={latest['volatility']:.1%}"
            
        return TradeSignal(
            symbol=symbol,
            signal=signal,
            price=price,
            reason=f"[{mode}] {reason}{vol_note}",
            confidence=confidence
        )

    def _calc_indicators(self, df):
        """计算 ADX, RSI, ATR, Alpha"""
        df = df.copy()
        
        # 简单处理，如果数据量大可能会慢，但对于单只股票 50-200 行很快
        high = df['high']
        low = df['low']
        close = df['close']
        prev_close = close.shift(1)
        
        # ATR (14)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        # RSI (14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ADX (14)
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        atr14 = df['atr']
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        df['adx'] = dx.rolling(14).mean()
        
        # Alpha
        df['alpha'] = (plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        
        # 波动率 (年化, 60日)
        df['returns'] = close.pct_change()
        df['volatility'] = df['returns'].rolling(60).std() * np.sqrt(252)
        
        return df
