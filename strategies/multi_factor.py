"""
多因子策略 (价值 + 动量 + 质量)

策略逻辑：
1. **价值因子 (Value)**:
   - 低市盈率 (PE TTM)
   - 低市净率 (PB)
   
2. **动量因子 (Momentum)**:
   - 12个月动量 (排除最近1个月)
   - 价格位于200日均线之上
   
3. **质量因子 (Quality)**:
   - 高净资产收益率 (ROE)
   - 低资产负债率 (Debt/Equity)

打分机制：
- 对每个因子进行排序打分 (0-100)
- 加权合成总分
- 选取总分最高的 N 只股票
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import statistics
from .base import BaseStrategy, TradeSignal, Signal

@dataclass
class MultiFactorConfig:
    """多因子策略配置"""
    # 权重配置 (总和应为 1.0)
    weight_value: float = 0.3
    weight_momentum: float = 0.4
    weight_quality: float = 0.3
    
    # 选股数量
    top_n: int = 10
    
    # 过滤条件
    min_market_cap: float = None    # 最小市值 (亿)
    exclude_st: bool = True         # 排除 ST
    exclude_banks: bool = False     # 排除银行股 (银行股估值体系不同)


class MultiFactorStrategy(BaseStrategy):
    """
    多因子选股策略
    结合 Value (价值), Momentum (动量), Quality (质量) 三大类因子
    """
    
    name = "Multi-Factor (VMQ)"
    description = "价值+动量+质量多因子综合选股"
    
    def __init__(self, config: MultiFactorConfig = None):
        super().__init__()
        self.config = config or MultiFactorConfig()
        
    def calculate_score(self, stocks_data: List[Dict]) -> List[Dict]:
        """
        计算多因子得分
        
        Args:
            stocks_data: 包含各项指标的股票数据列表
                Required fields:
                - symbol
                - pe_ttm (市盈率)
                - pb (市净率)
                - roe (净资产收益率)
                - debt_to_equity (资产负债率)
                - mom_12m (12个月动量)
                - price (当前价格)
                - ma200 (200日均线)
        
        Returns:
            添加了 scores 的股票列表
        """
        if not stocks_data:
            return []
            
        # 1. 预处理 & 过滤
        valid_stocks = []
        for s in stocks_data:
            # 基础数据完整性检查
            if any(k not in s for k in ['pe_ttm', 'pb', 'roe', 'mom_12m']):
                continue
                
            # 过滤逻辑
            if self.config.min_market_cap and s.get('market_cap', 0) < self.config.min_market_cap:
                continue
                
            valid_stocks.append(s)
            
        if not valid_stocks:
            return []

        # 2. 计算各因子排名 (Percentile Rank 0-1)
        # Value: PE, PB (越低越好 -> 排名越高)
        self._add_rank(valid_stocks, 'pe_ttm', 'score_pe', ascending=False)
        self._add_rank(valid_stocks, 'pb', 'score_pb', ascending=False)
        
        # Momentum: Mom_12m (越高越好)
        self._add_rank(valid_stocks, 'mom_12m', 'score_mom', ascending=True)
        
        # Quality: ROE (越高越好), Debt/Equity (越低越好)
        self._add_rank(valid_stocks, 'roe', 'score_roe', ascending=True)
        self._add_rank(valid_stocks, 'debt_to_equity', 'score_de', ascending=False)
        
        # 3. 合成因子得分
        for s in valid_stocks:
            # Value Score = (Score_PE + Score_PB) / 2
            s['factor_value'] = (s.get('score_pe', 0) + s.get('score_pb', 0)) / 2
            
            # Momentum Score
            # 如果在200日线之下，动量分打折
            mom_score = s.get('score_mom', 0)
            if s.get('price') and s.get('ma200') and s['price'] < s['ma200']:
                mom_score *= 0.5
            s['factor_momentum'] = mom_score
            
            # Quality Score = (Score_ROE + Score_DE) / 2
            s['factor_quality'] = (s.get('score_roe', 0) + s.get('score_de', 0)) / 2
            
            # Total Score
            s['total_score'] = (
                s['factor_value'] * self.config.weight_value +
                s['factor_momentum'] * self.config.weight_momentum +
                s['factor_quality'] * self.config.weight_quality
            ) * 100
            
        # 4. 排序
        valid_stocks.sort(key=lambda x: x['total_score'], reverse=True)
        
        return valid_stocks[:self.config.top_n]

    def _add_rank(self, data: List[Dict], key: str, score_key: str, ascending: bool = True):
        """计算百分位排名"""
        # 提取有效值
        values = [d[key] for d in data if d.get(key) is not None]
        if not values:
            return
            
        values.sort()
        n = len(values)
        
        for d in data:
            val = d.get(key)
            if val is None:
                d[score_key] = 0
                continue
                
            # 找到排名位置
            rank = 0
            for i, v in enumerate(values):
                if v >= val:
                    rank = i
                    break
            
            # 计算百分位 (0-1)
            percentile = rank / n
            
            # 如果是 ascending=False (值越小越好)，则反转百分位
            # 但我们在 sort 时已经处理了？
            # 不，values.sort() 总是从小到大
            # 如果 ascending=True (值越大越好)，rank 越大越好 -> percentile 越大越好
            # 如果 ascending=False (值越小越好)，rank 越小越好 -> (1 - percentile) 越大越好
            
            if not ascending:
                d[score_key] = 1.0 - percentile
            else:
                d[score_key] = percentile

    def analyze(self, symbol: str, data: list) -> TradeSignal:
        """
        单股分析接口 (主要用于回测或单股检查)
        注意：多因子主要依赖横截面比较，单股分析意义有限
        """
        # 这里仅做简单的趋势判断作为辅助
        return TradeSignal(
            symbol=symbol,
            signal=Signal.HOLD,
            price=0,
            reason="多因子策略需运行 select_stocks 进行横截面选股",
            confidence=0
        )
