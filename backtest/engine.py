import backtrader as bt
import pandas as pd
import datetime

class PandasData(bt.feeds.PandasData):
    """
    适配我们系统 DataFrame 格式的数据馈送类
    我们系统的 DataFrame 列名是: date, open, high, low, close, volume, turnover
    Backtrader 默认需要 datetime index
    """
    params = (
        ('datetime', None), # 使用索引作为 datetime
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1), # 无持仓量数据
    )

def run_backtest(
    strategy_class, 
    data_df, 
    name="Backtest", 
    start_cash=100000.0, 
    commission=0.001,
    **kwargs
):
    """
    通用回测运行函数
    """
    cerebro = bt.Cerebro()
    
    # 1. 添加策略
    cerebro.addstrategy(strategy_class, **kwargs)
    
    # 2. 添加数据
    # 确保 date 是索引
    if 'date' in data_df.columns:
        data_df['date'] = pd.to_datetime(data_df['date'])
        data_df.set_index('date', inplace=True)
    
    data = PandasData(dataname=data_df)
    cerebro.adddata(data, name=name)
    
    # 3. 设置资金
    cerebro.broker.setcash(start_cash)
    
    # 4. 设置佣金 (千分之一)
    cerebro.broker.setcommission(commission=commission)
    
    # 5. 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    # 6. 运行
    print(f"🚀 开始回测: {name}")
    print(f"💰 初始资金: ${start_cash:,.2f}")
    
    results = cerebro.run()
    strat = results[0]
    
    # 7. 输出结果
    final_value = cerebro.broker.getvalue()
    pnl = final_value - start_cash
    pnl_pct = pnl / start_cash
    
    print("-" * 50)
    print(f"🏁 回测结束")
    print(f"💰 最终资金: ${final_value:,.2f}")
    print(f"📈 净收益:   ${pnl:,.2f} ({pnl_pct:+.2%})")
    
    # 分析指标
    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()
    
    print("-" * 50)
    print(f"📊 核心指标:")
    print(f"   夏普比率: {sharpe.get('sharperatio', 0):.2f}")
    print(f"   最大回撤: {drawdown['max']['drawdown']:.2f}%")
    print(f"   总交易数: {trades.get('total', {}).get('total', 0)}")
    win_rate = 0
    if trades.get('total', {}).get('closed', 0) > 0:
        win_rate = trades.get('won', {}).get('total', 0) / trades.get('total', {}).get('closed', 0)
    print(f"   胜率:     {win_rate:.1%}")
    
    # 8. 绘图 (保存为文件)
    try:
        import matplotlib
        matplotlib.use('Agg') # 非交互式后端，避免弹窗 hang 住
        import matplotlib.pyplot as plt
        
        plot_file = f"backtest_result_{name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        print(f"📊 正在绘图保存至 {plot_file} ...")
        
        # Backtrader 的 plot 返回一个 figure list
        figs = cerebro.plot(style='candlestick', volume=False)
        
        if figs and len(figs) > 0:
            for i, fig in enumerate(figs):
                for f in fig:
                    f.savefig(plot_file, dpi=300)
            print(f"✅ 绘图完成")
        else:
            print("⚠️ 绘图未生成 Figures")
            
    except Exception as e:
        print(f"⚠️ 绘图失败: {e}")

    return strat
