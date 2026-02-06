import backtrader as bt
import math

class BT_Alpha101Strategy(bt.Strategy):
    """
    Backtrader 版 Alpha 101 策略 (增强版: ADX 滤网)
    """
    params = (
        ('period', 10),
        ('adx_period', 14),
        ('adx_threshold', 25), # 趋势强度阈值
        ('printlog', True),
    )

    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
        
        # 添加 ADX 指标
        self.adx = bt.indicators.ADX(
            self.datas[0], 
            period=self.params.adx_period
        )
        
        self.order = None

    def next(self):
        # 1. 计算 Alpha 101
        denominator = (self.datahigh[0] - self.datalow[0]) + 0.001
        alpha_101 = (self.dataclose[0] - self.dataopen[0]) / denominator
        
        current_adx = self.adx[0]
        
        # 2. 交易逻辑
        if not self.position:
            # 买入条件: 
            # 1. Alpha 信号强 (>0.5)
            # 2. ADX 确认有趋势 (>25)
            if alpha_101 > 0.5 and current_adx > self.params.adx_threshold:
                self.log(f'BUY CREATE, {self.dataclose[0]:.2f} (Alpha={alpha_101:.2f}, ADX={current_adx:.1f})')
                self.buy()
        
        else:
            # 卖出条件 (止损/止盈):
            # 1. Alpha 反转 (<-0.5)
            # 2. 或者趋势消失 (ADX掉头向下，虽未实现但可考虑)
            if alpha_101 < -0.5:
                self.log(f'SELL CREATE, {self.dataclose[0]:.2f} (Alpha={alpha_101:.2f}, ADX={current_adx:.1f})')
                self.sell()

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}')
                
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

class BT_MeanReversionStrategy(bt.Strategy):
    """Backtrader 版 均值回归策略"""
    params = (
        ('rsi_period', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('ma_period', 20),
    )

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.ma_period)

    def next(self):
        if not self.position:
            # 价格低于均线 且 RSI 超卖 -> 买入
            if self.data.close[0] < self.sma[0] and self.rsi[0] < self.params.rsi_oversold:
                self.buy()
        else:
            # RSI 超买 -> 卖出
            if self.rsi[0] > self.params.rsi_overbought:
                self.sell()
