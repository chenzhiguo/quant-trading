"""
Regime Switching Strategy (趋势/震荡切换策略) - Optimized v2
逻辑与回测脚本 (backtest_portfolio.py) 保持一致
"""
import pandas as pd
import numpy as np
import backtrader as bt # 引入 backtrader
from strategies.base import BaseStrategy, Signal, TradeSignal
from core.history_manager import get_history_manager

class RegimeSwitchingStrategy(BaseStrategy):
    name = "RegimeSwitching"
    description = "基于ADX的趋势/震荡自动切换策略 (Optimized with Trailing Stop)"
    
    def __init__(self, params: dict = None):
        super().__init__(params)
        self.adx_threshold = self.params.get('adx_threshold', 30)
        self.adx_wait_threshold = self.params.get('adx_wait_threshold', 25) # 提高观望阈值到 25
        self.rsi_oversold = self.params.get('rsi_oversold', 30) # 降低超卖阈值防止接飞刀
        self.rsi_overbought = self.params.get('rsi_overbought', 70)
        self.alpha_threshold = self.params.get('alpha_threshold', 0.5)
        self.ema_short = self.params.get('ema_short', 20)
        self.ema_long = self.params.get('ema_long', 50)
        
        # 大盘过滤器配置
        self.use_market_filter = self.params.get('use_market_filter', True)
        self.market_symbol = "SPY.US"
        self.market_df = None
        
        if self.use_market_filter:
            self._load_market_data()

    def _load_market_data(self):
        """加载大盘数据并计算 EMA50"""
        try:
            hm = get_history_manager()
            # 加载最近730天的数据 (与回测一致)
            df = hm.fetch_and_update(self.market_symbol, days=730)
            if df is not None and not df.empty:
                df['market_ema50'] = df['close'].ewm(span=50, adjust=False).mean()
                # 将日期设为索引方便查询
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    # 去除时区信息以匹配 backtrader
                    df['date'] = df['date'].dt.tz_localize(None)
                    df.set_index('date', inplace=True)
                self.market_df = df
                print(f"✅ Market Filter Loaded: {self.market_symbol} (len={len(df)})")
            else:
                print(f"⚠️ Failed to load market data for {self.market_symbol}")
        except Exception as e:
            print(f"⚠️ Error loading market filter: {e}")

    def _check_market_trend(self, current_date):
        """检查大盘趋势 (True=Bullish, False=Bearish)"""
        if not self.use_market_filter or self.market_df is None:
            return True # 默认放行
            
        # 查找当前日期或最近的一个交易日
        try:
            # 尝试直接获取
            if current_date in self.market_df.index:
                row = self.market_df.loc[current_date]
            else:
                # 查找最近的前一个日期 (asof)
                idx = self.market_df.index.get_indexer([current_date], method='pad')[0]
                if idx == -1: return True # 早于大盘数据开始时间
                row = self.market_df.iloc[idx]
            
            # 判断: 价格 > EMA50
            is_bullish = row['close'] > row['market_ema50']
            return is_bullish
        except Exception as e:
            # print(f"Market check error: {e}")
            return True

    def _calc_indicators(self, df):
        """计算 ADX, RSI, ATR, Alpha, EMA"""
        df = df.copy()
        
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
        
        # EMA
        df['ema_short'] = close.ewm(span=self.ema_short, adjust=False).mean()
        df['ema_long'] = close.ewm(span=self.ema_long, adjust=False).mean()
        
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

    def analyze(self, symbol: str, data: list) -> TradeSignal:
        if not data or len(data) < 50: # 需要更多数据计算 EMA50
            return TradeSignal(symbol, Signal.HOLD, 0, "数据不足", 0)
            
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data.copy()
        df.columns = [c.lower() for c in df.columns]
        
        df = self._calc_indicators(df)
        latest = df.iloc[-1]
        price = latest['close']
        
        adx = latest['adx']
        rsi = latest['rsi']
        alpha = latest['alpha']
        ema_s = latest['ema_short']
        ema_l = latest['ema_long']
        atr = latest['atr']
        
        if pd.isna(adx) or pd.isna(rsi):
            return TradeSignal(symbol, Signal.HOLD, price, "指标无效", 0)
            
        mode = "Wait"
        signal = Signal.HOLD
        reason = ""
        confidence = 0.0
        
        # 这里的 reason 格式化为 JSON-like 字符串或者包含特殊标记，方便 Backtrader 解析 ATR
        # Hack: 将 ATR 放入 reason 字符串末尾，例如 "... | ATR=2.5"
        
        # 获取当前Bar的日期
        try:
            current_date = pd.to_datetime(latest['date'])
            # 如果是 timestamp，去除时区
            if hasattr(current_date, 'tz_localize'):
                current_date = current_date.tz_localize(None)
        except:
            current_date = None

        market_bullish = True
        if current_date:
            market_bullish = self._check_market_trend(current_date)

        if adx > self.adx_threshold:
            mode = "Trend"
            # 增加趋势过滤：价格必须在短期均线之上
            if alpha > self.alpha_threshold and price > ema_s:
                # 优化: RSI不过热才开仓
                if rsi < 70:
                    if market_bullish:
                        signal = Signal.BUY
                        confidence = abs(alpha) * (min(adx, 50) / 50)
                        reason = f"Trend Buy (Alpha={alpha:.2f}, ADX={adx:.1f}, P>EMA{self.ema_short})"
                    else:
                        signal = Signal.HOLD
                        reason = f"Trend Wait (Market Bearish: SPY < EMA50)"
                else:
                    signal = Signal.HOLD
                    reason = f"Trend Hold (RSI={rsi:.1f} Overbought)"
            elif alpha < -self.alpha_threshold:
                signal = Signal.SELL
                confidence = abs(alpha) * (min(adx, 50) / 50)
                reason = f"Trend Sell (Alpha={alpha:.2f}, ADX={adx:.1f})"
            else:
                reason = f"Trend Hold (Alpha={alpha:.2f})"
                # 如果持有且跌破 EMA50，建议卖出
                if price < ema_l:
                     signal = Signal.SELL
                     reason += " & Price < EMA50"
                
        elif adx < self.adx_wait_threshold:
            mode = "Range"
            # 只有在价格没有暴跌 (处于 EMA50 附近或之上) 时才做 RSI 抄底
            # 或者跌幅非常深 (RSI < 20)
            if rsi < self.rsi_oversold:
                if price > ema_l or rsi < 20: # 允许回踩 EMA50 (严格) 或极度超卖
                    if market_bullish or rsi < 20: # 极端超卖可以忽略大盘，否则必须大盘向好
                        signal = Signal.BUY
                        confidence = (self.rsi_oversold - rsi) / self.rsi_oversold * 0.8
                        confidence = min(confidence, 0.95)
                        reason = f"Range Buy (RSI={rsi:.1f}, ADX={adx:.1f})"
                    else:
                        signal = Signal.HOLD
                        reason = f"Range Wait (Market Bearish: SPY < EMA50)"
                else:
                    reason = f"Range Wait (RSI={rsi:.1f} but Price < EMA{self.ema_long})"
                    
            elif rsi > self.rsi_overbought:
                signal = Signal.SELL
                confidence = (rsi - self.rsi_overbought) / (100 - self.rsi_overbought) * 0.8
                confidence = min(confidence, 0.95)
                reason = f"Range Sell (RSI={rsi:.1f}, ADX={adx:.1f})"
            else:
                reason = f"Range Hold (RSI={rsi:.1f})"
        else:
            mode = "Wait"
            # 观望区：如果价格跌破 EMA50，卖出
            if price < ema_l:
                signal = Signal.SELL
                reason = f"Wait Sell (Price < EMA{self.ema_long}, ADX={adx:.1f})"
            else:
                signal = Signal.HOLD
                reason = f"Wait Zone (ADX={adx:.1f})"
            confidence = 0.0
                
        vol_note = ""
        if 'volatility' in latest and not pd.isna(latest['volatility']):
            vol_note = f" Vol={latest['volatility']:.1%}"
            
        # 注入 ATR 到 reason 供 BT 策略解析
        return TradeSignal(
            symbol=symbol,
            signal=signal,
            price=price,
            reason=f"[{mode}] {reason}{vol_note} | ATR={atr:.4f}",
            confidence=confidence
        )

class BT_RegimeSwitchingStrategy(bt.Strategy):
    params = dict(
        adx_threshold = 30,
        adx_wait_threshold = 25,
        rsi_oversold = 30,
        rsi_overbought = 70,
        alpha_threshold = 0.5,
        atr_multiplier = 4.0, # ATR 移动止损倍数 (Relaxed to 4.0)
    )

    def __init__(self):
        self.strategy_impl = RegimeSwitchingStrategy(params=self.p.__dict__)
        self.dataclose = self.datas[0].close
        self.order = None 
        self.stop_price = None # 移动止损价
        self.highest_price = 0.0 # 持仓期间最高价
        print("BT_RegimeSwitchingStrategy (Optimized) instance created!")

    def next(self):
        # 获取所有可用的历史数据
        data_dicts = []
        for i in range(-self.data.buflen() + 1, 1):
            dt = bt.num2date(self.data.datetime[i])
            if pd.isna(self.data.close[i]): continue
            data_dicts.append({
                'date': dt.isoformat(),
                'open': self.data.open[i],
                'high': self.data.high[i],
                'low': self.data.low[i],
                'close': self.data.close[i],
                'volume': self.data.volume[i] if not pd.isna(self.data.volume[i]) else 0,
            })
        
        symbol = self.datas[0]._name 
        trade_signal = self.strategy_impl.analyze(symbol, data_dicts)
        
        # 解析 ATR
        atr = 0.0
        try:
            parts = trade_signal.reason.split("ATR=")
            if len(parts) > 1:
                atr = float(parts[1].strip())
        except:
            pass
            
        current_price = self.dataclose[0]
        dt_iso = bt.num2date(self.data.datetime[0]).isoformat()
        
        print(f"[{dt_iso}] Signal: {trade_signal.signal.value} | P={current_price:.2f} | Stop={self.stop_price} | {trade_signal.reason}")

        if self.order: return

        # 移动止损逻辑
        if self.position.size > 0:
            if current_price > self.highest_price:
                self.highest_price = current_price
                # 更新止损价：随价格上涨上移
                if atr > 0:
                    new_stop = current_price - (atr * self.p.atr_multiplier)
                    if self.stop_price is None or new_stop > self.stop_price:
                        self.stop_price = new_stop
            
            # 检查是否触发止损
            if self.stop_price and current_price < self.stop_price:
                print(f"[{dt_iso}] 🛑 TRAILING STOP TRIGGERED (P={current_price:.2f} < Stop={self.stop_price:.2f})")
                self.order = self.sell(size=self.position.size)
                self.stop_price = None # 重置
                return

        # 正常信号处理
        if trade_signal.signal == Signal.BUY:
            if self.position.size == 0: # 只在空仓时买入
                if self.broker.getcash() > 0:
                    size = int(self.broker.getcash() / current_price * 0.95) 
                    if size > 0:
                        self.order = self.buy(size=size)
                        # 设置初始止损
                        if atr > 0:
                            self.stop_price = current_price - (atr * self.p.atr_multiplier)
                            self.highest_price = current_price
                        print(f'[{dt_iso}] BUY CREATE, {current_price:.2f}, Size: {size}, Initial Stop: {self.stop_price}')

        elif trade_signal.signal == Signal.SELL:
            if self.position.size > 0:
                self.order = self.sell(size=self.position.size)
                self.stop_price = None
                print(f'[{dt_iso}] SELL CREATE, {current_price:.2f}, Size: {self.position.size}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            dt = self.datas[0].datetime.date(0)
            if order.isbuy():
                print(f'[{dt.isoformat()}] BUY EXECUTED, Price: {order.executed.price:.2f}')
            else:
                print(f'[{dt.isoformat()}] SELL EXECUTED, Price: {order.executed.price:.2f}')
            self.bar_executed = len(self)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            dt = self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] Order Canceled/Margin/Rejected')
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed: return
        dt = self.datas[0].datetime.date(0)
        print(f'[{dt.isoformat()}] OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}')
