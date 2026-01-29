"""
数据获取模块
"""
import os
from datetime import datetime, timedelta
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 尝试导入 longport，如果失败则使用 Mock
try:
    from longport.openapi import Config, QuoteContext, Period, AdjustType
    # 尝试导入财务上下文
    try:
        from longport.openapi import FinancialContext
    except ImportError:
        FinancialContext = None
    HAS_LONGPORT = True
except ImportError:
    HAS_LONGPORT = False
    Config = None
    QuoteContext = None
    FinancialContext = None
    
    # Mock Enums
    class Period:
        Day = "Day"
        Week = "Week"
    
    class AdjustType:
        ForwardAdjust = "Forward"
    
    print("⚠️  longport library not found. Using Mock Data mode.")


class MockQuote:
    """模拟行情对象"""
    def __init__(self, symbol, price, pe=None, pb=None, mkt_cap=None):
        self.symbol = symbol
        self.last_done = price
        self.prev_close = price * 0.99
        self.volume = 1000000
        self.turnover = 10000000
        self.high = price * 1.01
        self.low = price * 0.99
        self.open = price
        self.pe_ttm = pe or 20.0
        self.pb_ratio = pb or 3.0
        self.market_cap = mkt_cap or 50_000_000_000
        self.timestamp = datetime.now()


class MockCandle:
    """模拟K线对象"""
    def __init__(self, close):
        self.close = close
        self.open = close
        self.high = close
        self.low = close
        self.volume = 10000
        self.turnover = 100000
        self.timestamp = datetime.now()


class DataFetcher:
    """行情数据获取器"""
    
    def __init__(self):
        if HAS_LONGPORT:
            self.config = Config.from_env()
            self.quote_ctx = QuoteContext(self.config)
            
            if FinancialContext:
                try:
                    self.financial_ctx = FinancialContext(self.config)
                except Exception:
                    self.financial_ctx = None
            else:
                self.financial_ctx = None
        else:
            self.quote_ctx = None
            self.financial_ctx = None
    
    def get_realtime_quotes(self, symbols: list) -> list:
        """获取实时行情"""
        if HAS_LONGPORT:
            return self.quote_ctx.quote(symbols)
        else:
            # Mock Data
            import random
            return [
                MockQuote(
                    s, 
                    random.uniform(100, 200),
                    pe=random.uniform(10, 50),
                    pb=random.uniform(1, 10),
                    mkt_cap=random.uniform(1e9, 1e12)
                ) for s in symbols
            ]
    
    def get_candlesticks(
        self, 
        symbol: str, 
        period: Period = Period.Day if HAS_LONGPORT else "Day",
        count: int = 100,
        adjust: AdjustType = AdjustType.ForwardAdjust if HAS_LONGPORT else "Forward"
    ) -> list:
        """获取K线数据"""
        if HAS_LONGPORT:
            return self.quote_ctx.candlesticks(symbol, period, count, adjust)
        else:
            # Mock Data: 生成随机波动
            import random
            base_price = 100
            data = []
            for i in range(count):
                base_price *= (1 + random.uniform(-0.02, 0.02))
                data.append(MockCandle(base_price))
            return data
    
    def get_quote_with_change(self, symbols: list) -> list:
        """获取行情及涨跌幅"""
        quotes = self.get_realtime_quotes(symbols)
        result = []
        for q in quotes:
            # Mock Data 兼容
            prev_close = getattr(q, 'prev_close', q.last_done)
            change = float(q.last_done) - float(prev_close) if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0
            
            result.append({
                "symbol": q.symbol,
                "price": float(q.last_done),
                "prev_close": float(prev_close),
                "change": float(change),
                "change_pct": float(change_pct),
                "volume": int(q.volume),
                "turnover": float(q.turnover),
                "high": float(q.high),
                "low": float(q.low),
                "open": float(q.open),
            })
        return result
    
    def get_kline_df(self, symbol: str, days: int = 100):
        """获取K线数据并转为 DataFrame 格式的字典列表"""
        candles = self.get_candlesticks(symbol, Period.Day, days)
        data = []
        for c in candles:
            data.append({
                "date": c.timestamp.strftime("%Y-%m-%d"),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": int(c.volume),
                "turnover": float(c.turnover),
            })
        return data

    def get_multi_factor_data(self, symbols: list) -> list:
        """
        获取多因子策略所需的数据
        
        包括: PE, PB, Market Cap, ROE, Debt/Equity, 12月动量, 200日均线
        """
        quotes = self.get_realtime_quotes(symbols)
        result = []
        
        for q in quotes:
            symbol = q.symbol
            
            # 1. 基础行情与估值
            # 注意：不同 API 版本字段可能不同，这里使用 getattr 防御
            pe_ttm = getattr(q, 'pe_ttm', None)
            pb = getattr(q, 'pb_ratio', None)
            market_cap = getattr(q, 'market_cap', 0)
            price = float(q.last_done)
            
            # 2. 计算动量 (12个月涨幅 & MA200)
            # 获取过去 365 天的数据 (约 252 交易日)
            try:
                # 优化：只取 weekly 数据以减少点数，或者取 daily 但只取关键点
                # 这里取 daily 300个点以计算 MA200 和 Momentum
                candles = self.get_candlesticks(symbol, Period.Day, 300)
                
                if len(candles) > 200:
                    closes = [float(c.close) for c in candles]
                    
                    # MA200
                    ma200 = sum(closes[-200:]) / 200
                    
                    # 12个月动量 (当前价格 / 1年前价格 - 1)
                    # 排除最近1个月 (即 compare price vs price_12m_ago)
                    # 近1个月约 20 交易日
                    if len(closes) > 250:
                        price_12m_ago = closes[-250]
                        price_1m_ago = closes[-20]
                        
                        # 传统的 12-1 动量: 最近1个月剔除
                        mom_12m = (price_1m_ago / price_12m_ago) - 1
                    else:
                        mom_12m = 0
                else:
                    ma200 = None
                    mom_12m = None
            except Exception:
                ma200 = None
                mom_12m = None
            
            # 3. 财务质量 (ROE, Debt/Equity)
            # 如果没有 financial ctx，暂时给默认值或 mock
            roe = 0.15  # 示例默认值 (15%)
            debt_to_equity = 0.5 # 示例默认值 (50%)
            
            if self.financial_ctx:
                # TODO: 实现真实的财务数据获取
                # indicators = self.financial_ctx.get_key_indicators(symbol)
                # roe = indicators.roe
                pass
                
            result.append({
                "symbol": symbol,
                "price": price,
                "pe_ttm": pe_ttm if pe_ttm else 0,
                "pb": pb if pb else 0,
                "market_cap": market_cap,
                "roe": roe,
                "debt_to_equity": debt_to_equity,
                "mom_12m": mom_12m if mom_12m is not None else 0,
                "ma200": ma200 if ma200 is not None else price,
            })
            
        return result



# 单例
_fetcher = None

def get_fetcher() -> DataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = DataFetcher()
    return _fetcher
