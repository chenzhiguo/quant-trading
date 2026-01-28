"""
策略基类
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime


class Signal(Enum):
    """交易信号"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    """交易信号详情"""
    symbol: str
    signal: Signal
    price: float
    reason: str
    confidence: float  # 0-1
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def __str__(self):
        emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}[self.signal.value]
        return f"{emoji} {self.signal.value} {self.symbol} @ {self.price:.2f} ({self.confidence:.0%}) - {self.reason}"


class BaseStrategy(ABC):
    """策略基类"""
    
    name: str = "BaseStrategy"
    description: str = "策略基类"
    
    def __init__(self, params: dict = None):
        self.params = params or {}
    
    @abstractmethod
    def analyze(self, symbol: str, data: list) -> TradeSignal:
        """
        分析行情，生成交易信号
        
        Args:
            symbol: 股票代码
            data: K线数据 (list of dict)
        
        Returns:
            TradeSignal
        """
        pass
    
    def calculate_ma(self, data: list, period: int, key: str = "close") -> list:
        """计算移动平均线"""
        if len(data) < period:
            return []
        
        ma = []
        for i in range(period - 1, len(data)):
            window = data[i - period + 1:i + 1]
            avg = sum(d[key] for d in window) / period
            ma.append(avg)
        return ma
    
    def calculate_rsi(self, data: list, period: int = 14) -> list:
        """计算 RSI"""
        if len(data) < period + 1:
            return []
        
        gains = []
        losses = []
        
        for i in range(1, len(data)):
            change = data[i]["close"] - data[i-1]["close"]
            gains.append(max(change, 0))
            losses.append(abs(min(change, 0)))
        
        rsi = []
        for i in range(period - 1, len(gains)):
            avg_gain = sum(gains[i - period + 1:i + 1]) / period
            avg_loss = sum(losses[i - period + 1:i + 1]) / period
            
            if avg_loss == 0:
                rsi.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100 - (100 / (1 + rs)))
        
        return rsi
