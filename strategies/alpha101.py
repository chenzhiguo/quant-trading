import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
from .base import BaseStrategy, TradeSignal, Signal

class Alpha101Strategy(BaseStrategy):
    name = "Alpha 101 (Weekly)"
    description = "基于 WorldQuant Alpha 101 因子的周频选股策略"
    
    def __init__(self, period: str = "W"):
        """
        Args:
            period: 重采样周期，'W' 代表周频 (Weekly)
        """
        super().__init__()
        self.period = period

    def resample_to_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        """将日线数据重采样为周线数据"""
        # 确保 date 是 datetime 类型并设为索引
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
        # 定义聚合规则
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # 重采样：'W-FRI' 代表每周五结束
        weekly_df = df.resample('W-FRI').agg(agg_dict)
        
        # 移除包含 NaN 的行（刚开始可能数据不全）
        weekly_df.dropna(inplace=True)
        
        return weekly_df

    # ==================== Alpha 算子 ====================
    def delta(self, series: pd.Series, period: int) -> pd.Series:
        return series.diff(period)

    def sign(self, series: pd.Series) -> pd.Series:
        return np.sign(series)

    def correlation(self, s1: pd.Series, s2: pd.Series, window: int) -> pd.Series:
        return s1.rolling(window=window).corr(s2)
    
    def rank(self, series: pd.Series) -> pd.Series:
        # 注意：真正的 Alpha101 Rank 是截面排序（Cross-sectional Rank）
        # 在单只股票分析中，我们无法做截面排序。
        # 这里的权宜之计是：不做 Rank，直接返回原始值，或者做时序归一化。
        # 为了保持公式原貌，暂返回原始值，后续在选股逻辑中比较各股票的值。
        return series

    # ==================== 具体 Alpha 公式 ====================
    
    def alpha_006(self, df: pd.DataFrame) -> float:
        """
        Alpha#6: (-1 * Correlation(Open, Volume, 10))
        含义：开盘价和成交量的相关性。如果是负相关（量大价跌或量小价涨），Alpha值高。
        逻辑：寻找量价背离的时刻。
        """
        # 注意：这里用的是周线数据，window=10 代表 10 周
        corr = self.correlation(df['open'], df['volume'], window=10)
        alpha = -1 * corr
        return alpha.iloc[-1] if not alpha.empty else 0.0

    def alpha_012(self, df: pd.DataFrame) -> float:
        """
        Alpha#12: Sign(Delta(Volume, 1)) * (-1 * Delta(Close, 1))
        含义：(成交量变化方向) * (价格变化的反方向)
        逻辑：
        - 量增(1) * 价跌(1) = 1 (买入信号？恐慌盘抛售可能是底部)
        - 量减(-1) * 价涨(-1) = 1 (买入信号？缩量上涨，惜售)
        - 量增(1) * 价涨(-1) = -1 (卖出信号？放量上涨可能是顶)
        - 量减(-1) * 价跌(1) = -1 (卖出信号？无量阴跌)
        """
        v_delta = self.delta(df['volume'], 1)
        c_delta = self.delta(df['close'], 1)
        
        # 避免 NaN
        if v_delta.empty or c_delta.empty:
            return 0.0
            
        alpha = self.sign(v_delta) * (-1 * c_delta)
        
        # 取最后一个值。注意：Delta(Close)是有幅度的，所以这个 Alpha 值大小有意义
        return alpha.iloc[-1]

    def alpha_101(self, df: pd.DataFrame) -> float:
        """
        Alpha#101: (Close - Open) / ((High - Low) + 0.001)
        含义：K线实体占总振幅的比例。
        逻辑：
        - 接近 1：光头光脚大阳线（极强多头）
        - 接近 -1：光头光脚大阴线（极强空头）
        - 接近 0：十字星（犹豫）
        这里作为周线因子，捕捉一周的总体趋势强度。
        """
        # 防止除零
        denominator = (df['high'] - df['low']) + 0.001
        alpha = (df['close'] - df['open']) / denominator
        return alpha.iloc[-1] if not alpha.empty else 0.0

    # ==================== 策略主逻辑 ====================

    def analyze(self, symbol: str, data: List[Dict]) -> TradeSignal:
        if not data or len(data) < 30: # 需要足够的数据重采样
            return TradeSignal(symbol, Signal.HOLD, 0, "数据不足", 0)

        # 1. 转换为 DataFrame
        df = pd.DataFrame(data)
        current_price = df.iloc[-1]['close']
        
        # 2. 降频为周线 (Weekly)
        try:
            w_df = self.resample_to_weekly(df)
        except Exception as e:
            return TradeSignal(symbol, Signal.HOLD, current_price, f"重采样失败: {e}", 0)
        
        if len(w_df) < 12: # 至少需要 12 周数据计算 Alpha 6 (window=10)
            return TradeSignal(symbol, Signal.HOLD, current_price, "周线数据不足(需>12周)", 0)

        # 3. 计算 Alpha 因子值
        a6 = self.alpha_006(w_df)
        a12 = self.alpha_012(w_df)
        a101 = self.alpha_101(w_df)
        
        # 4. 综合打分 (简单加权示例)
        # 注意：实际量化中需要对因子进行正交化和回归测试来定权重
        # 这里我们根据物理含义构建一个简易的打分逻辑
        
        score = 0
        reasons = []
        
        # Alpha 6: 负相关性越高越好 (-1 * corr)。范围理论上 [-1, 1]。
        # 如果 corr 是负的 (量价背离)，alpha 是正的。
        if a6 > 0.3:
            score += 1
            reasons.append(f"量价背离(Alpha6={a6:.2f})")
        elif a6 < -0.3:
            score -= 1
            reasons.append(f"量价趋同(Alpha6={a6:.2f})")
            
        # Alpha 12: 如果为正，通常是反转信号
        # 由于 a12 包含价格 delta，数值可能很大，只看符号
        if a12 > 0:
            score += 1
            reasons.append("量价反转(Alpha12>0)")
        elif a12 < 0:
            score -= 1
        
        # Alpha 101: 趋势强度 [-1, 1]
        if a101 > 0.5:
            score += 2 # 强阳线，权重加大
            reasons.append(f"周线大阳(Alpha101={a101:.2f})")
        elif a101 < -0.5:
            score -= 2
            reasons.append(f"周线大阴(Alpha101={a101:.2f})")
            
        # 5. 生成信号
        # 总分范围大概在 -4 到 +4
        confidence = min(abs(score) / 4.0, 1.0)
        
        if score >= 2:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.BUY,
                price=current_price,
                reason=f"周线Alpha强势: {', '.join(reasons)}",
                confidence=confidence,
                timestamp=datetime.now()
            )
        elif score <= -2:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.SELL,
                price=current_price,
                reason=f"周线Alpha弱势: {', '.join(reasons)}",
                confidence=confidence,
                timestamp=datetime.now()
            )
            
        return TradeSignal(
            symbol=symbol,
            signal=Signal.HOLD,
            price=current_price,
            reason=f"Alpha中性 (分={score:.1f})",
            confidence=0.5,
            timestamp=datetime.now()
        )
