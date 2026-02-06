#!/usr/bin/env python3
"""
组合回测 (Portfolio Backtest)
- 统一资金池，全市场选股
- 按信号强度排序，择优入场
- 真实模拟组合收益
"""
import os
import sys
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.history_manager import get_history_manager
from config.watchlist import get_watchlist, LEVERAGED_ETF

# ===== 指标计算 =====
def calc_indicators(df):
    """计算 ADX, RSI, ATR 等指标"""
    df = df.copy()
    
    # ATR (14日)
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    # RSI (14日)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ADX (14日)
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    atr14 = df['atr']
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    df['adx'] = dx.rolling(14).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    
    # Alpha (动量因子)
    df['alpha'] = (df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'] + 1e-10)
    
    # 波动率 (年化)
    df['returns'] = close.pct_change()
    df['volatility'] = df['returns'].rolling(60).std() * np.sqrt(252)
    
    return df


def generate_signals(df, symbol):
    """生成买卖信号"""
    signals = []
    
    adx_threshold = 25
    rsi_oversold = 35
    rsi_overbought = 65
    alpha_threshold = 0.5
    
    for i in range(100, len(df)):
        row = df.iloc[i]
        date = row['date'] if 'date' in df.columns else df.index[i]
        
        adx = row['adx']
        rsi = row['rsi']
        alpha = row['alpha']
        vol = row['volatility']
        
        if pd.isna(adx) or pd.isna(rsi):
            continue
        
        is_trend = adx > adx_threshold
        
        signal = None
        strength = 0
        
        if is_trend:
            # 趋势模式: Alpha 买入
            if alpha > alpha_threshold:
                signal = 'BUY'
                strength = abs(alpha) * (adx / 50)  # 信号强度
            elif alpha < -alpha_threshold:
                signal = 'SELL'
                strength = abs(alpha) * (adx / 50)
        else:
            # 震荡模式: RSI 超卖买入
            if rsi < rsi_oversold:
                signal = 'BUY'
                strength = (rsi_oversold - rsi) / rsi_oversold * 0.8
            elif rsi > rsi_overbought:
                signal = 'SELL'
                strength = (rsi - rsi_overbought) / (100 - rsi_overbought) * 0.8
        
        if signal:
            signals.append({
                'date': date,
                'symbol': symbol,
                'signal': signal,
                'strength': strength,
                'price': row['close'],
                'adx': adx,
                'rsi': rsi,
                'alpha': alpha,
                'atr': row['atr'],
                'volatility': vol,
                'is_trend': is_trend
            })
    
    return signals


class PortfolioBacktest:
    """组合回测引擎"""
    
    def __init__(self, initial_cash=40000, max_positions=3, position_pct=0.30):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.max_positions = max_positions
        self.position_pct = position_pct  # 每只股票仓位比例
        
        self.positions = {}  # symbol -> {shares, entry_price, entry_date, stop_price, high_since_entry}
        self.trades = []
        self.equity_curve = []
        self.daily_values = {}  # date -> portfolio value
        
    def get_portfolio_value(self, prices):
        """计算组合总价值"""
        value = self.cash
        for symbol, pos in self.positions.items():
            if symbol in prices:
                value += pos['shares'] * prices[symbol]
        return value
    
    def can_buy(self):
        """是否可以开新仓"""
        return len(self.positions) < self.max_positions
    
    def buy(self, symbol, price, date, atr, volatility):
        """买入"""
        if symbol in self.positions:
            return False
        
        # 计算仓位
        position_value = self.cash * self.position_pct
        if position_value < 100:  # 至少100刀
            return False
            
        shares = int(position_value / price)
        if shares < 1:
            return False
        
        cost = shares * price * 1.001  # 含手续费
        if cost > self.cash:
            shares = int(self.cash * 0.99 / price)
            cost = shares * price * 1.001
        
        if shares < 1:
            return False
        
        self.cash -= cost
        
        # 止损价: 高波动用 ATR, 低波动用固定8%
        if volatility > 0.40:
            stop_price = price - 2.5 * atr
        else:
            stop_price = price * 0.92
        
        self.positions[symbol] = {
            'shares': shares,
            'entry_price': price,
            'entry_date': date,
            'stop_price': stop_price,
            'high_since_entry': price,
            'volatility': volatility
        }
        
        self.trades.append({
            'symbol': symbol,
            'action': 'BUY',
            'date': date,
            'price': price,
            'shares': shares,
            'value': shares * price
        })
        
        return True
    
    def sell(self, symbol, price, date, reason='signal'):
        """卖出"""
        if symbol not in self.positions:
            return False
        
        pos = self.positions[symbol]
        proceeds = pos['shares'] * price * 0.999  # 含手续费
        self.cash += proceeds
        
        pnl = (price - pos['entry_price']) / pos['entry_price']
        
        self.trades.append({
            'symbol': symbol,
            'action': 'SELL',
            'date': date,
            'price': price,
            'shares': pos['shares'],
            'value': proceeds,
            'pnl': pnl,
            'reason': reason,
            'hold_days': (date - pos['entry_date']).days if hasattr(date, 'days') or isinstance(date, datetime) else 0
        })
        
        del self.positions[symbol]
        return True
    
    def check_stops(self, symbol, high, low, close, date):
        """检查止损/追踪止盈"""
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        
        # 更新最高价
        if high > pos['high_since_entry']:
            pos['high_since_entry'] = high
            
            # 高波动股票: 追踪止损
            if pos['volatility'] > 0.40:
                # 盈利超过10%后启动追踪
                if (pos['high_since_entry'] - pos['entry_price']) / pos['entry_price'] > 0.10:
                    trailing_stop = pos['high_since_entry'] * 0.95  # 从高点回撤5%
                    if trailing_stop > pos['stop_price']:
                        pos['stop_price'] = trailing_stop
        
        # 检查止损
        if low <= pos['stop_price']:
            return 'stop'
        
        # 检查止盈 (稳健股票: 固定20%止盈)
        if pos['volatility'] <= 0.40:
            if close >= pos['entry_price'] * 1.20:
                return 'profit'
        
        return None
    
    def run(self, all_data, all_signals):
        """运行组合回测"""
        # 按日期合并所有信号
        signals_by_date = defaultdict(list)
        for sig in all_signals:
            date = sig['date']
            if isinstance(date, str):
                date = pd.to_datetime(date)
            signals_by_date[date].append(sig)
        
        # 获取所有交易日
        all_dates = set()
        for symbol, df in all_data.items():
            dates = df['date'] if 'date' in df.columns else df.index
            all_dates.update(pd.to_datetime(dates))
        
        all_dates = sorted(all_dates)
        
        # 逐日回测
        for date in all_dates:
            prices = {}
            highs = {}
            lows = {}
            
            for symbol, df in all_data.items():
                df_date = df['date'] if 'date' in df.columns else df.index
                mask = pd.to_datetime(df_date) == date
                if mask.any():
                    row = df[mask].iloc[0]
                    prices[symbol] = row['close']
                    highs[symbol] = row['high']
                    lows[symbol] = row['low']
            
            # 1. 检查现有持仓的止损
            symbols_to_sell = []
            for symbol in list(self.positions.keys()):
                if symbol in prices:
                    reason = self.check_stops(symbol, highs[symbol], lows[symbol], prices[symbol], date)
                    if reason:
                        symbols_to_sell.append((symbol, reason))
            
            for symbol, reason in symbols_to_sell:
                self.sell(symbol, prices[symbol], date, reason)
            
            # 2. 处理当日信号
            day_signals = signals_by_date.get(date, [])
            
            # 卖出信号
            for sig in day_signals:
                if sig['signal'] == 'SELL' and sig['symbol'] in self.positions:
                    self.sell(sig['symbol'], sig['price'], date, 'signal')
            
            # 买入信号 (按强度排序)
            buy_signals = [s for s in day_signals if s['signal'] == 'BUY' and s['symbol'] not in self.positions]
            buy_signals.sort(key=lambda x: x['strength'], reverse=True)
            
            for sig in buy_signals:
                if not self.can_buy():
                    break
                if sig['symbol'] in prices:
                    self.buy(sig['symbol'], sig['price'], date, sig['atr'], sig['volatility'])
            
            # 3. 记录当日组合价值
            portfolio_value = self.get_portfolio_value(prices)
            self.equity_curve.append({
                'date': date,
                'value': portfolio_value,
                'cash': self.cash,
                'positions': len(self.positions)
            })
        
        return self.get_results()
    
    def get_results(self):
        """计算回测结果"""
        if not self.equity_curve:
            return None
        
        eq_df = pd.DataFrame(self.equity_curve)
        eq_df['returns'] = eq_df['value'].pct_change()
        
        final_value = eq_df['value'].iloc[-1]
        total_return = (final_value - self.initial_cash) / self.initial_cash
        
        # 最大回撤
        eq_df['peak'] = eq_df['value'].cummax()
        eq_df['drawdown'] = (eq_df['peak'] - eq_df['value']) / eq_df['peak']
        max_drawdown = eq_df['drawdown'].max()
        
        # Sharpe (假设无风险利率 5%)
        if eq_df['returns'].std() > 0:
            sharpe = (eq_df['returns'].mean() * 252 - 0.05) / (eq_df['returns'].std() * np.sqrt(252))
        else:
            sharpe = 0
        
        # 交易统计
        sell_trades = [t for t in self.trades if t['action'] == 'SELL']
        if sell_trades:
            wins = [t for t in sell_trades if t.get('pnl', 0) > 0]
            win_rate = len(wins) / len(sell_trades)
        else:
            win_rate = 0
        
        return {
            'initial_cash': self.initial_cash,
            'final_value': final_value,
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'sharpe': sharpe,
            'total_trades': len(self.trades),
            'sell_trades': len(sell_trades),
            'win_rate': win_rate,
            'equity_curve': eq_df,
            'trades': self.trades
        }


def main():
    parser = argparse.ArgumentParser(description="组合回测")
    parser.add_argument("--list", "-l", default="optimized", help="股票池")
    parser.add_argument("--days", "-d", type=int, default=730, help="回测天数")
    parser.add_argument("--cash", "-c", type=float, default=40000.0, help="初始本金")
    parser.add_argument("--max-pos", "-m", type=int, default=8, help="最大持仓数")
    parser.add_argument("--pos-pct", "-p", type=float, default=0.10, help="单只仓位比例")
    parser.add_argument("--offline", action="store_true", help="仅使用本地缓存")
    parser.add_argument("--exclude-etf", action="store_true", help="排除杠杆ETF")
    parser.add_argument("--max-vol", type=float, default=1.0, help="最大波动率阈值 (排除超过的股票)")
    
    args = parser.parse_args()
    
    # 获取股票池
    symbols = get_watchlist(args.list)
    
    # 排除 ETF
    if args.exclude_etf:
        etf_set = set(LEVERAGED_ETF)
        symbols = [s for s in symbols if s not in etf_set]
        print(f"📦 排除 ETF 后: {len(symbols)} 只股票")
    
    # 离线模式
    if args.offline:
        import glob
        cached_files = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "history", "*.csv"))
        cached_symbols = set()
        for f in cached_files:
            name = os.path.basename(f).replace(".csv", "").replace("_", ".")
            cached_symbols.add(name)
        symbols = [s for s in symbols if s in cached_symbols]
        print(f"📂 离线模式: 使用本地缓存 ({len(symbols)} 只)")
    
    print(f"\n🚀 组合回测开始")
    print(f"💰 本金: ${args.cash:,.2f} | 最大持仓: {args.max_pos} | 单仓比例: {args.pos_pct:.0%}")
    print("-" * 60)
    
    # 加载数据
    history = get_history_manager()
    all_data = {}
    all_signals = []
    
    for symbol in symbols:
        try:
            if args.offline:
                df = history.load_local_data(symbol)
            else:
                df = history.fetch_and_update(symbol, days=args.days)
            
            if df is None or len(df) < 100:
                continue
            
            # 确保 date 列
            if 'date' not in df.columns and df.index.name != 'date':
                df = df.reset_index()
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            
            # 计算指标
            df = calc_indicators(df)
            
            # 检查波动率是否超过阈值
            avg_vol = df['volatility'].iloc[-60:].mean() if len(df) > 60 else df['volatility'].mean()
            if pd.notna(avg_vol) and avg_vol > args.max_vol:
                print(f"  ⊘ {symbol}: 波动率 {avg_vol:.1%} 超过阈值 {args.max_vol:.0%}，跳过")
                continue
            
            all_data[symbol] = df
            
            # 生成信号
            signals = generate_signals(df, symbol)
            all_signals.extend(signals)
            
            print(f"  ✓ {symbol}: {len(df)} 日数据, {len(signals)} 个信号")
            
        except Exception as e:
            print(f"  ✗ {symbol}: {e}")
    
    print(f"\n📊 共加载 {len(all_data)} 只股票, {len(all_signals)} 个信号")
    
    # 运行组合回测
    bt = PortfolioBacktest(
        initial_cash=args.cash,
        max_positions=args.max_pos,
        position_pct=args.pos_pct
    )
    
    results = bt.run(all_data, all_signals)
    
    if results:
        print("\n" + "=" * 60)
        print("📈 组合回测结果")
        print("=" * 60)
        print(f"初始资金:     ${results['initial_cash']:,.2f}")
        print(f"最终资金:     ${results['final_value']:,.2f}")
        print(f"总收益率:     {results['total_return']:+.2%}")
        print(f"最大回撤:     {results['max_drawdown']:.2%}")
        print(f"夏普比率:     {results['sharpe']:.2f}")
        print(f"总交易次数:   {results['total_trades']}")
        print(f"卖出次数:     {results['sell_trades']}")
        print(f"胜率:         {results['win_rate']:.1%}")
        print("=" * 60)
        
        # 保存交易记录
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        trades_df = pd.DataFrame(results['trades'])
        trades_df.to_csv(os.path.join(output_dir, 'portfolio_trades.csv'), index=False)
        print(f"\n💾 交易记录已保存至 {output_dir}/portfolio_trades.csv")
        
        # 保存权益曲线
        results['equity_curve'].to_csv(os.path.join(output_dir, 'equity_curve.csv'), index=False)
        print(f"💾 权益曲线已保存至 {output_dir}/equity_curve.csv")
    else:
        print("❌ 回测失败")


if __name__ == "__main__":
    main()
