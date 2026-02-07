"""
Regime Switching Strategy (趋势/震荡切换策略)
逻辑与回测脚本 (backtest_portfolio.py) 保持一致
"""
import pandas as pd
import numpy as np
import backtrader as bt # 引入 backtrader
from strategies.base import BaseStrategy, Signal, TradeSignal

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
        if not data or len(data) < 15:
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

class BT_RegimeSwitchingStrategy(bt.Strategy):
    params = dict(
        adx_threshold = 30,
        adx_wait_threshold = 20,
        rsi_oversold = 35,
        rsi_overbought = 65,
        alpha_threshold = 0.5,
    )

    def __init__(self):
        self.strategy_impl = RegimeSwitchingStrategy(params=self.p.__dict__)
        self.dataclose = self.datas[0].close
        self.order = None # 跟踪订单
        print("BT_RegimeSwitchingStrategy instance created!")

    def next(self):
        print(f"[{bt.num2date(self.data.datetime[0]).isoformat()}] next() called for {self.datas[0]._name}")
        data_dicts = []
        # 获取所有可用的历史数据，从最旧的到最新的
        # self.data.buflen() 是可用的数据点数量
        # self.data.close[-idx] 可以访问历史数据，-idx = -(self.data.buflen() - 1) 是最旧的
        for i in range(-self.data.buflen() + 1, 1): # 从最旧的 bar 到当前 bar (索引 0)
            dt = bt.num2date(self.data.datetime[i])
            if pd.isna(self.data.close[i]):
                continue
            data_dicts.append({
                'date': dt.isoformat(),
                'open': self.data.open[i],
                'high': self.data.high[i],
                'low': self.data.low[i],
                'close': self.data.close[i],
                'volume': self.data.volume[i] if not pd.isna(self.data.volume[i]) else 0,
            })
        
        print(f"[{dt.isoformat()}] Current bar: {dt.isoformat()}, Data length for analyze: {len(data_dicts)}")

        symbol = self.datas[0]._name 

        trade_signal = self.strategy_impl.analyze(symbol, data_dicts)
        print(f"[{dt.isoformat()}] Trade Signal: {trade_signal.signal.value} ({trade_signal.reason})")

        if self.order: # 如果有挂单，则不发出新信号
            return

        if trade_signal.signal == Signal.BUY:
            if self.broker.getcash() > 0: # 确保有现金
                # 计算可以买入的股数 (例如，使用所有可用现金的80%)
                size = int(self.broker.getcash() / self.dataclose[0] * 0.8) 
                if size > 0:
                    self.order = self.buy(size=size)
                    print(f'[{dt.isoformat()}] BUY CREATE, {self.dataclose[0]:.2f}, Size: {size}')

        elif trade_signal.signal == Signal.SELL:
            if self.position.size > 0: # 确保持有仓位
                # 卖出所有仓位
                self.order = self.sell(size=self.position.size)
                print(f'[{dt.isoformat()}] SELL CREATE, {self.dataclose[0]:.2f}, Size: {self.position.size}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            return

        # Check if an order has been completed
        # Attention: broker could reject order if not enough cash
        if order.status in [order.Completed]:
            dt = self.datas[0].datetime.date(0)
            if order.isbuy():
                print(
                    '[%s] BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                    (dt.isoformat(),
                     order.executed.price,
                     order.executed.value,
                     order.executed.comm))
            else:  # Sell
                print('[%s] SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                         (dt.isoformat(),
                          order.executed.price,
                          order.executed.value,
                          order.executed.comm))

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            dt = self.datas[0].datetime.date(0)
            print('[%s] Order Canceled/Margin/Rejected' % dt.isoformat())

        # Write down: no pending order
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        dt = self.datas[0].datetime.date(0)
        print(f'[{dt.isoformat()}] OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}')
