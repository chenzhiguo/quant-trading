from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

class MarketRegime(Enum):
    TRENDING_UP = "TRENDING_UP"       # 上升趋势 (牛市)
    TRENDING_DOWN = "TRENDING_DOWN"   # 下降趋势 (熊市)
    SIDEWAYS = "SIDEWAYS"             # 震荡市 (猴市)
    VOLATILE = "VOLATILE"             # 剧烈波动 (风险高)

@dataclass
class RegimeAnalysis:
    regime: MarketRegime
    adx: float
    trend_strength: float  # 0-100
    description: str

class RegimeDetector:
    """市场状态识别器"""
    
    def __init__(self, adx_period=14):
        self.adx_period = adx_period

    def calculate_adx(self, df: pd.DataFrame) -> float:
        """计算 ADX 指标 (趋势强度)"""
        # 简化版 ADX 计算
        if len(df) < self.adx_period * 2:
            return 0.0
            
        high = df['high']
        low = df['low']
        close = df['close']
        
        # 1. TR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # 2. DM
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # 3. Smoothed
        atr = tr.rolling(self.adx_period).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(self.adx_period).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(self.adx_period).mean() / atr)
        
        # 4. ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(self.adx_period).mean().iloc[-1]
        
        return adx if not np.isnan(adx) else 0.0

    def analyze(self, symbol: str, data) -> RegimeAnalysis:
        """分析市场状态"""
        # 兼容 list (字典列表) 和 DataFrame
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data
            
        if len(df) < 50:
            return RegimeAnalysis(MarketRegime.SIDEWAYS, 0, 0, "数据不足")

        current_price = df['close'].iloc[-1]
        ma20 = df['close'].rolling(20).mean().iloc[-1]
        ma50 = df['close'].rolling(50).mean().iloc[-1]
        ma200 = df['close'].rolling(200).mean().iloc[-1]
        
        # 计算 ADX
        adx = self.calculate_adx(df)
        
        # 判定逻辑
        
        # 1. 强趋势判断 (ADX > 25)
        if adx > 25:
            # 判断方向
            if ma20 > ma50 > ma200:
                return RegimeAnalysis(
                    MarketRegime.TRENDING_UP,
                    adx,
                    adx, # ADX值即强度
                    f"强上升趋势 (ADX={adx:.1f}, 均线多头)"
                )
            elif ma20 < ma50 < ma200:
                return RegimeAnalysis(
                    MarketRegime.TRENDING_DOWN,
                    adx,
                    adx,
                    f"强下降趋势 (ADX={adx:.1f}, 均线空头)"
                )
        
        # 2. 弱趋势/震荡判断
        # 均线纠缠：价格在 MA200 附近，或 MA20/50 频繁交叉
        price_dev_200 = abs(current_price - ma200) / ma200
        
        if price_dev_200 < 0.05: # 价格在年线上下 5% 晃悠
            return RegimeAnalysis(
                MarketRegime.SIDEWAYS,
                adx,
                0,
                f"年线震荡 (偏离{price_dev_200:.1%})"
            )
            
        # 3. 默认归类
        if current_price > ma50:
            return RegimeAnalysis(MarketRegime.TRENDING_UP, adx, adx*0.5, "弱上升趋势")
        else:
            return RegimeAnalysis(MarketRegime.TRENDING_DOWN, adx, adx*0.5, "弱下降趋势")
