"""
量化交易策略模块

可用策略：
- MACrossStrategy: 均线交叉策略
- MomentumStrategy: 动量策略
- SmallCapGrowthStrategy: 绩优小市值策略（A股）
"""
from .base import BaseStrategy, TradeSignal, Signal
from .ma_cross import MACrossStrategy
from .momentum import MomentumStrategy
from .small_cap_growth import SmallCapGrowthStrategy, create_small_cap_strategy

__all__ = [
    "BaseStrategy",
    "TradeSignal", 
    "Signal",
    "MACrossStrategy",
    "MomentumStrategy",
    "SmallCapGrowthStrategy",
    "create_small_cap_strategy",
]
