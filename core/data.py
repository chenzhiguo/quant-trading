"""
数据获取模块
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from longport.openapi import Config, QuoteContext, Period, AdjustType


class DataFetcher:
    """行情数据获取器"""
    
    def __init__(self):
        self.config = Config.from_env()
        self.quote_ctx = QuoteContext(self.config)
    
    def get_realtime_quotes(self, symbols: list) -> list:
        """获取实时行情"""
        return self.quote_ctx.quote(symbols)
    
    def get_candlesticks(
        self, 
        symbol: str, 
        period: Period = Period.Day,
        count: int = 100,
        adjust: AdjustType = AdjustType.ForwardAdjust
    ) -> list:
        """获取K线数据"""
        return self.quote_ctx.candlesticks(symbol, period, count, adjust)
    
    def get_quote_with_change(self, symbols: list) -> list:
        """获取行情及涨跌幅"""
        quotes = self.get_realtime_quotes(symbols)
        result = []
        for q in quotes:
            change = q.last_done - q.prev_close if q.prev_close else 0
            change_pct = (change / q.prev_close * 100) if q.prev_close else 0
            result.append({
                "symbol": q.symbol,
                "price": float(q.last_done),
                "prev_close": float(q.prev_close),
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


# 单例
_fetcher = None

def get_fetcher() -> DataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = DataFetcher()
    return _fetcher
