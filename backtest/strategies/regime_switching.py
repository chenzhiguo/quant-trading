import backtrader as bt

class BT_RegimeSwitchingStrategy(bt.Strategy):
    """
    状态切换策略 (Regime Switching Strategy)
    
    逻辑：
    - 计算 ADX 指标判断市场状态
    - 强趋势状态 (ADX > 25) -> 执行 Alpha 101 逻辑 (追涨杀跌)
    - 震荡状态 (ADX < 25) -> 执行 均值回归 逻辑 (高抛低吸)
    """
    params = (
        ('adx_period', 14),
        ('adx_threshold', 25),
        ('alpha_period', 10),
        ('rsi_period', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('ma_period', 20),
        ('printlog', True),
    )

    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'{dt.isoformat()}, {txt}')

    def __init__(self):
        # 1. 核心指标: ADX (状态识别)
        self.adx = bt.indicators.ADX(self.datas[0], period=self.params.adx_period)
        
        # 2. Alpha 101 所需数据
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        
        # 3. 均值回归 所需指标
        self.rsi = bt.indicators.RSI(self.datas[0], period=self.params.rsi_period)
        self.sma = bt.indicators.SimpleMovingAverage(self.datas[0], period=self.params.ma_period)
        
        self.regime = None # 当前状态记录

    def next(self):
        current_adx = self.adx[0]
        
        # ----------------------------------------
        # 状态判定
        # ----------------------------------------
        if current_adx > self.params.adx_threshold:
            current_regime = 'TREND'
        else:
            current_regime = 'RANGE'
            
        # 状态切换日志
        if current_regime != self.regime:
            self.log(f'⚡️ REGIME CHANGE: {self.regime} -> {current_regime} (ADX={current_adx:.1f})')
            self.regime = current_regime

        # ----------------------------------------
        # 策略执行
        # ----------------------------------------
        
        # === 场景 A: 强趋势 (跑 Alpha 101) ===
        if current_regime == 'TREND':
            # Alpha#101 计算
            denominator = (self.datahigh[0] - self.datalow[0]) + 0.001
            alpha_101 = (self.dataclose[0] - self.dataopen[0]) / denominator
            
            # 趋势策略买入: 强阳线 + 无持仓
            if not self.position:
                if alpha_101 > 0.5:
                    self.log(f'[Trend-Buy] Strong Alpha ({alpha_101:.2f}) in Trend (ADX={current_adx:.1f})')
                    self.buy()
            
            # 趋势策略卖出: 强阴线 + 有持仓
            elif self.position:
                if alpha_101 < -0.5:
                    self.log(f'[Trend-Sell] Weak Alpha ({alpha_101:.2f}) in Trend (ADX={current_adx:.1f})')
                    self.sell()
                    
        # === 场景 B: 震荡市 (跑 Mean Reversion) ===
        elif current_regime == 'RANGE':
            # 震荡策略买入: 跌破均线 + RSI超卖
            if not self.position:
                if self.dataclose[0] < self.sma[0] and self.rsi[0] < self.params.rsi_oversold:
                    self.log(f'[Range-Buy] Oversold (RSI={self.rsi[0]:.1f}) in Range (ADX={current_adx:.1f})')
                    self.buy()
            
            # 震荡策略卖出: RSI超买 (高抛)
            elif self.position:
                if self.rsi[0] > self.params.rsi_overbought:
                    self.log(f'[Range-Sell] Overbought (RSI={self.rsi[0]:.1f}) in Range (ADX={current_adx:.1f})')
                    self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'>>> EXECUTED BUY  @ {order.executed.price:.2f}')
            elif order.issell():
                self.log(f'>>> EXECUTED SELL @ {order.executed.price:.2f}')
