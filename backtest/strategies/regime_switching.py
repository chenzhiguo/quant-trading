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
        ('adx_period', 14), # Add ADX period back
        ('adx_threshold', 30), # 强趋势状态判断ADX > 30
        ('adx_wait_threshold', 20), # 震荡状态判断ADX < 20, 观望区 20 <= ADX <= 30
        ('alpha_period', 10),
        ('rsi_period', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('ma_period', 20),
        
        # 新增均线和布林带参数
        ('short_ma_period', 10),
        ('long_ma_period', 20),
        ('bb_period', 20),
        ('bb_dev', 2.0), # 布林带标准差倍数
        
        # === 旧参数：无追踪止盈，可能使用固定止损 ===
        ('atr_period', 14),
        ('atr_multiplier', 3.0),      # ATR 保持 3.0 以便对比策略层面的差异
        ('trailing_start_pct', 99.0),  # 禁用追踪止盈 (设为很大)
        ('trailing_stop_pct', 0.05),
        
        ('log_filepath', None), # 新增：日志文件路径
        ('printlog', True),
    )

    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            log_message = f'{dt.isoformat()}, {txt}'
            print(log_message) # 仍然打印到控制台，以便快速查看
            if self.log_file:
                self.log_file.write(log_message + '\n')

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
        
        # 新增均线和布林带指标
        self.short_ma = bt.indicators.SMA(self.datas[0].close, period=self.params.short_ma_period)
        self.long_ma = bt.indicators.SMA(self.datas[0].close, period=self.params.long_ma_period)
        self.bband = bt.indicators.BollingerBands(self.datas[0].close, period=self.params.bb_period, devfactor=self.params.bb_dev)
        
        # 4. ATR (智能止损)
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)
        
        self.regime = None # 当前状态记录
        self.stop_price = None # 当前止损价
        self.highest_price = None # 持仓期间最高价 (用于追踪止损)

        if self.params.log_filepath:
            self.log_file = open(self.params.log_filepath, 'w')
        else:
            self.log_file = None

    def next(self):
        current_adx = self.adx[0]
        
        # ----------------------------------------
        # 0. 风控检查
        # ----------------------------------------
        if self.position:
            cost_price = self.position.price
            current_price = self.dataclose[0]
            pnl_pct = (current_price - cost_price) / cost_price
            
            # 统一使用 ATR 基础止损 + 追踪止盈
            # 更新最高价
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price
            
            # 1. 追踪止盈 (优先) - 只有当浮盈达到一定比例才开启
            if self.highest_price:
                highest_pnl = (self.highest_price - cost_price) / cost_price
                if highest_pnl >= self.params.trailing_start_pct:
                    # 计算相对于最高价的回撤
                    drawdown = (self.highest_price - current_price) / self.highest_price
                    
                    if drawdown >= self.params.trailing_stop_pct:
                        self.log(f'🛡️ TRAILING STOP (High: {self.highest_price:.2f}, Drawdown: {drawdown:.2%})')
                        self.close()
                        return

            # 2. ATR 基础止损 (保底)
            # 确保 self.stop_price 已经设置 (即买入操作已经完成)
            if self.stop_price and current_price < self.stop_price:
                self.log(f'🛑 ATR STOP TRIGGERED @ {current_price:.2f} (Stop: {self.stop_price:.2f})')
                self.close()
                return

        # ----------------------------------------
        # 状态判定
        # ----------------------------------------
        # ADX 阈值调整为 30 (强趋势) 和 20 (震荡)
        if current_adx > self.params.adx_threshold: # ADX > 30 强趋势
            current_regime = 'TREND'
        elif current_adx < self.params.adx_wait_threshold: # ADX < 20 震荡
            current_regime = 'RANGE'
        else: # 20 <= ADX <= 30 观望区
            current_regime = 'WAIT'
            
        # 状态切换日志
        if current_regime != self.regime:
            self.log(f'⚡️ REGIME CHANGE: {self.regime} -> {current_regime} (ADX={current_adx:.1f})')
            self.regime = current_regime

        # ----------------------------------------
        # 策略执行
        # ----------------------------------------
        
        # 不在观望区域进行交易
        if current_regime == 'WAIT':
            if self.position:
                self.log(f'⏸️ WAIT REGIME, HOLDING POSITION (ADX={current_adx:.1f})')
            else:
                self.log(f'⏸️ WAIT REGIME, NO TRADING (ADX={current_adx:.1f})')
            return # 在观望区域直接返回，不执行交易逻辑
            
        # === 场景 A: 强趋势 (跑 Alpha 101 + MA金叉确认) ===
        if current_regime == 'TREND':
            # Alpha#101 计算
            denominator = (self.datahigh[0] - self.datalow[0]) + 0.001
            alpha_101 = (self.dataclose[0] - self.dataopen[0]) / denominator
            
            # 趋势策略买入: 强阳线 + 无持仓 + MA金叉确认
            if not self.position:
                # 价格突破 Alpha 101 信号
                alpha_buy_signal = alpha_101 > 0.5
                
                # MA金叉确认条件
                ma_golden_cross = (self.short_ma[-1] <= self.long_ma[-1]) and \
                                  (self.short_ma[0] > self.long_ma[0])
                
                if alpha_buy_signal and ma_golden_cross:
                    self.log(f'[Trend-Buy] Strong Alpha ({alpha_101:.2f}) AND MA Golden Cross in Trend (ADX={current_adx:.1f})')
                    self.buy()
            
            # 趋势策略卖出: 强阴线 + 有持仓 (保持不变，因为是止损或止盈)
            elif self.position:
                if alpha_101 < -0.5:
                    self.log(f'[Trend-Sell] Weak Alpha ({alpha_101:.2f}) in Trend (ADX={current_adx:.1f})')
                    self.sell()
                    
        # === 场景 B: 震荡市 (跑 Mean Reversion + 布林带确认) ===
        elif current_regime == 'RANGE':
            # 震荡策略买入: 跌破均线 + RSI超卖 + 布林带下轨确认
            if not self.position:
                # RSI超卖信号
                rsi_oversold_signal = self.rsi[0] < self.params.rsi_oversold
                
                # 布林带下轨确认条件
                bb_lower_band_confirm = self.dataclose[0] < self.bband.lines.bot[0]
                
                if self.dataclose[0] < self.sma[0] and rsi_oversold_signal and bb_lower_band_confirm:
                    self.log(f'[Range-Buy] Oversold (RSI={self.rsi[0]:.1f}) AND BB Lower Band in Range (ADX={current_adx:.1f})')
                    self.buy()
            
            # 震荡策略卖出: RSI超买 + 布林带上轨确认 (高抛)
            elif self.position:
                # RSI超买信号
                rsi_overbought_signal = self.rsi[0] > self.params.rsi_overbought
                
                # 布林带上轨确认条件
                bb_upper_band_confirm = self.dataclose[0] > self.bband.lines.top[0]
                
                if rsi_overbought_signal and bb_upper_band_confirm:
                    self.log(f'[Range-Sell] Overbought (RSI={self.rsi[0]:.1f}) AND BB Upper Band in Range (ADX={current_adx:.1f})')
                    self.sell()

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'>>> EXECUTED BUY  @ {order.executed.price:.2f}')
                self.highest_price = order.executed.price
                
                # 设置 ATR 止损线
                atr_value = self.atr[0]
                stop_dist = atr_value * self.params.atr_multiplier
                self.stop_price = order.executed.price - stop_dist
                self.log(f'🛡️ ATR Stop Set: {self.stop_price:.2f} (Dist: {stop_dist:.2f})')
                
            elif order.issell():
                self.log(f'>>> EXECUTED SELL @ {order.executed.price:.2f}')
                self.stop_price = None
                self.highest_price = None

    def stop(self):
        if self.log_file:
            self.log_file.close()
