"""
绩优小市值策略

策略逻辑（来自猫哥AI量化）：
1. 股票池准备：过滤ST股、次新股（<250天）、科创板/创业板/北交所
2. 成长因子筛选：营收同比和净利润同比高于中位数（前50%）
3. 按流通市值从小到大排序，选前N只

核心理念：
- 小市值股票成长空间大，10亿→50亿比500亿→2500亿容易
- 用相对排名（中位数）而非固定阈值，适应不同市场环境
- 结合成长因子剔除"垃圾股"，选出业绩增长的"优等生"

适用市场：A股
调仓周期：每周
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from .base import BaseStrategy, TradeSignal, Signal


@dataclass
class StockFilter:
    """股票过滤器配置"""
    exclude_st: bool = True           # 过滤ST股票
    exclude_new_stocks: bool = True   # 过滤次新股
    new_stock_days: int = 250         # 次新股定义（上市天数）
    exclude_kcb: bool = True          # 过滤科创板（688）
    exclude_cyb: bool = True          # 过滤创业板（300）
    exclude_bj: bool = True           # 过滤北交所（.BJ）


@dataclass
class GrowthFilter:
    """成长因子筛选配置"""
    use_relative_rank: bool = True    # 使用相对排名（中位数）
    revenue_percentile: float = 0.5   # 营收同比百分位（前50%）
    profit_percentile: float = 0.5    # 净利润同比百分位（前50%）
    min_revenue_yoy: float = None     # 固定阈值：最低营收同比（可选）
    min_profit_yoy: float = None      # 固定阈值：最低净利润同比（可选）


@dataclass
class SmallCapConfig:
    """绩优小市值策略配置"""
    stock_filter: StockFilter = field(default_factory=StockFilter)
    growth_filter: GrowthFilter = field(default_factory=GrowthFilter)
    top_n: int = 10                   # 选股数量
    use_float_value: bool = True      # 使用流通市值（vs 总市值）
    max_market_cap: float = None      # 最大市值限制（亿元，可选）
    min_market_cap: float = None      # 最小市值限制（亿元，可选）


class SmallCapGrowthStrategy(BaseStrategy):
    """
    绩优小市值策略
    
    选股逻辑：
    1. 基础过滤：剔除ST、次新股、特定板块
    2. 成长筛选：营收同比和净利润同比高于市场中位数
    3. 市值排序：按流通市值从小到大，选前N只
    
    适用于 A 股市场的因子投资策略。
    """
    
    name = "Small Cap Growth"
    description = "绩优小市值策略：成长因子 + 小市值因子双重筛选"
    
    def __init__(self, config: SmallCapConfig = None):
        super().__init__()
        self.config = config or SmallCapConfig()
    
    def filter_stock_pool(
        self, 
        stocks: List[Dict], 
        trade_date: datetime = None
    ) -> List[Dict]:
        """
        Step 1: 准备股票池，过滤不符合条件的股票
        
        Args:
            stocks: 股票列表，每个元素包含:
                - symbol: 股票代码
                - name: 股票名称
                - list_date: 上市日期 (YYYYMMDD 或 datetime)
            trade_date: 交易日期（用于计算次新股）
        
        Returns:
            过滤后的股票列表
        """
        if trade_date is None:
            trade_date = datetime.now()
        
        filtered = []
        cfg = self.config.stock_filter
        
        for stock in stocks:
            symbol = stock.get("symbol", "")
            name = stock.get("name", "")
            list_date = stock.get("list_date")
            
            # 过滤 ST 股票
            if cfg.exclude_st:
                if any(tag in name for tag in ["ST", "*", "退"]):
                    continue
            
            # 过滤次新股
            if cfg.exclude_new_stocks and list_date:
                if isinstance(list_date, str):
                    try:
                        list_dt = datetime.strptime(list_date, "%Y%m%d")
                    except ValueError:
                        list_dt = datetime.strptime(list_date, "%Y-%m-%d")
                else:
                    list_dt = list_date
                
                days_listed = (trade_date - list_dt).days
                if days_listed < cfg.new_stock_days:
                    continue
            
            # 过滤科创板（688开头）
            if cfg.exclude_kcb and symbol.startswith("688"):
                continue
            
            # 过滤创业板（300开头）
            if cfg.exclude_cyb and symbol.startswith("300"):
                continue
            
            # 过滤北交所（.BJ结尾）
            if cfg.exclude_bj and symbol.endswith(".BJ"):
                continue
            
            filtered.append(stock)
        
        return filtered
    
    def filter_by_growth(
        self, 
        stocks: List[Dict],
        financial_data: Dict[str, Dict]
    ) -> List[Dict]:
        """
        Step 2: 用成长因子筛选
        
        Args:
            stocks: 股票列表
            financial_data: 财务数据，格式:
                {
                    "symbol": {
                        "rev_yoy": 营收同比增长率,
                        "profit_yoy": 净利润同比增长率
                    }
                }
        
        Returns:
            筛选后的股票列表（成长性高于中位数）
        """
        cfg = self.config.growth_filter
        
        # 收集所有有效的财务数据
        valid_stocks = []
        rev_values = []
        profit_values = []
        
        for stock in stocks:
            symbol = stock.get("symbol")
            fin = financial_data.get(symbol, {})
            
            rev_yoy = fin.get("rev_yoy")
            profit_yoy = fin.get("profit_yoy")
            
            if rev_yoy is not None and profit_yoy is not None:
                valid_stocks.append({
                    **stock,
                    "rev_yoy": rev_yoy,
                    "profit_yoy": profit_yoy
                })
                rev_values.append(rev_yoy)
                profit_values.append(profit_yoy)
        
        if not valid_stocks:
            return []
        
        # 计算阈值
        if cfg.use_relative_rank:
            # 使用相对排名（中位数）
            rev_values.sort()
            profit_values.sort()
            
            rev_idx = int(len(rev_values) * (1 - cfg.revenue_percentile))
            profit_idx = int(len(profit_values) * (1 - cfg.profit_percentile))
            
            rev_threshold = rev_values[rev_idx] if rev_idx < len(rev_values) else rev_values[-1]
            profit_threshold = profit_values[profit_idx] if profit_idx < len(profit_values) else profit_values[-1]
        else:
            # 使用固定阈值
            rev_threshold = cfg.min_revenue_yoy or 0
            profit_threshold = cfg.min_profit_yoy or 0
        
        # 筛选高于阈值的股票
        filtered = [
            s for s in valid_stocks
            if s["rev_yoy"] >= rev_threshold and s["profit_yoy"] >= profit_threshold
        ]
        
        return filtered
    
    def rank_by_market_cap(
        self, 
        stocks: List[Dict],
        market_data: Dict[str, Dict]
    ) -> List[Dict]:
        """
        Step 3: 按市值排序选股
        
        Args:
            stocks: 股票列表
            market_data: 市值数据，格式:
                {
                    "symbol": {
                        "total_value": 总市值,
                        "float_value": 流通市值
                    }
                }
        
        Returns:
            按市值排序并筛选后的股票列表
        """
        cfg = self.config
        
        # 添加市值数据
        stocks_with_cap = []
        for stock in stocks:
            symbol = stock.get("symbol")
            mkt = market_data.get(symbol, {})
            
            if cfg.use_float_value:
                market_cap = mkt.get("float_value")
            else:
                market_cap = mkt.get("total_value")
            
            if market_cap is None:
                continue
            
            # 转换为亿元
            market_cap_yi = market_cap / 100000000 if market_cap > 10000 else market_cap
            
            # 市值范围过滤
            if cfg.max_market_cap and market_cap_yi > cfg.max_market_cap:
                continue
            if cfg.min_market_cap and market_cap_yi < cfg.min_market_cap:
                continue
            
            stocks_with_cap.append({
                **stock,
                "market_cap": market_cap,
                "market_cap_yi": market_cap_yi
            })
        
        # 按市值从小到大排序
        stocks_with_cap.sort(key=lambda x: x["market_cap"])
        
        # 选前 N 只
        return stocks_with_cap[:cfg.top_n]
    
    def select_stocks(
        self,
        all_stocks: List[Dict],
        financial_data: Dict[str, Dict],
        market_data: Dict[str, Dict],
        trade_date: datetime = None
    ) -> List[Dict]:
        """
        执行完整的选股流程
        
        Args:
            all_stocks: 全部股票列表
            financial_data: 财务数据（营收/利润同比）
            market_data: 市值数据
            trade_date: 交易日期
        
        Returns:
            最终选中的股票列表
        """
        # Step 1: 过滤股票池
        pool = self.filter_stock_pool(all_stocks, trade_date)
        
        # Step 2: 成长因子筛选
        growth_stocks = self.filter_by_growth(pool, financial_data)
        
        # Step 3: 市值排序选股
        selected = self.rank_by_market_cap(growth_stocks, market_data)
        
        return selected
    
    def analyze(self, symbol: str, data: list) -> TradeSignal:
        """
        分析单只股票（兼容基类接口）
        
        注意：此策略主要用于批量选股（select_stocks），
        单股分析仅提供基础的技术面辅助判断。
        
        Args:
            symbol: 股票代码
            data: K线数据
        
        Returns:
            交易信号
        """
        if not data or len(data) < 20:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.HOLD,
                price=data[-1]["close"] if data else 0,
                reason="数据不足，无法分析",
                confidence=0
            )
        
        current_price = data[-1]["close"]
        
        # 计算简单的技术指标辅助判断
        ma5 = self.calculate_ma(data, 5)
        ma20 = self.calculate_ma(data, 20)
        
        if not ma5 or not ma20:
            return TradeSignal(
                symbol=symbol,
                signal=Signal.HOLD,
                price=current_price,
                reason="均线计算失败",
                confidence=0
            )
        
        # 判断趋势
        trend_up = ma5[-1] > ma20[-1]
        
        # 计算近期涨幅
        change_5d = (current_price - data[-5]["close"]) / data[-5]["close"] * 100
        change_20d = (current_price - data[-20]["close"]) / data[-20]["close"] * 100
        
        if trend_up and change_5d > 0:
            signal = Signal.BUY
            reason = f"上升趋势，5日涨幅 {change_5d:.1f}%"
            confidence = min(0.3 + change_5d / 20, 0.8)
        elif not trend_up and change_5d < -3:
            signal = Signal.SELL
            reason = f"下降趋势，5日跌幅 {change_5d:.1f}%"
            confidence = min(0.3 + abs(change_5d) / 20, 0.8)
        else:
            signal = Signal.HOLD
            reason = f"震荡整理，20日涨幅 {change_20d:.1f}%"
            confidence = 0.5
        
        return TradeSignal(
            symbol=symbol,
            signal=signal,
            price=current_price,
            reason=reason,
            confidence=confidence
        )
    
    def get_strategy_info(self) -> Dict:
        """获取策略配置信息"""
        cfg = self.config
        return {
            "name": self.name,
            "description": self.description,
            "filters": {
                "exclude_st": cfg.stock_filter.exclude_st,
                "exclude_new_stocks": cfg.stock_filter.exclude_new_stocks,
                "new_stock_days": cfg.stock_filter.new_stock_days,
                "exclude_kcb": cfg.stock_filter.exclude_kcb,
                "exclude_cyb": cfg.stock_filter.exclude_cyb,
                "exclude_bj": cfg.stock_filter.exclude_bj,
            },
            "growth_filter": {
                "use_relative_rank": cfg.growth_filter.use_relative_rank,
                "revenue_percentile": cfg.growth_filter.revenue_percentile,
                "profit_percentile": cfg.growth_filter.profit_percentile,
            },
            "selection": {
                "top_n": cfg.top_n,
                "use_float_value": cfg.use_float_value,
                "max_market_cap": cfg.max_market_cap,
                "min_market_cap": cfg.min_market_cap,
            }
        }


# 便捷工厂函数
def create_small_cap_strategy(
    top_n: int = 10,
    exclude_cyb: bool = True,
    exclude_bj: bool = True,
    max_market_cap: float = None,
    min_market_cap: float = None
) -> SmallCapGrowthStrategy:
    """
    创建绩优小市值策略实例
    
    Args:
        top_n: 选股数量
        exclude_cyb: 是否排除创业板
        exclude_bj: 是否排除北交所
        max_market_cap: 最大市值限制（亿元）
        min_market_cap: 最小市值限制（亿元）
    
    Returns:
        策略实例
    """
    config = SmallCapConfig(
        stock_filter=StockFilter(
            exclude_cyb=exclude_cyb,
            exclude_bj=exclude_bj
        ),
        top_n=top_n,
        max_market_cap=max_market_cap,
        min_market_cap=min_market_cap
    )
    return SmallCapGrowthStrategy(config)
