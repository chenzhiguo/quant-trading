"""
历史数据管理器
负责本地数据的存储、读取和自动更新 (缓存机制)
"""
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history")

class HistoryManager:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
    def get_file_path(self, symbol):
        # 兼容处理: symbol 中的 .US, .HK 等
        safe_symbol = symbol.replace(".", "_")
        return os.path.join(self.data_dir, f"{safe_symbol}.csv")

    def load_local_data(self, symbol):
        """读取本地 CSV"""
        file_path = self.get_file_path(symbol)
        if not os.path.exists(file_path):
            return None
            
        try:
            df = pd.read_csv(file_path)
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            return df
        except Exception as e:
            print(f"⚠️ 读取本地数据 {symbol} 失败: {e}")
            return None

    def save_data(self, symbol, df):
        """保存数据到 CSV"""
        if df is None or df.empty:
            return
            
        file_path = self.get_file_path(symbol)
        # 确保 date 是字符串格式保存
        df.to_csv(file_path, index=False)
        # print(f"💾 已缓存 {symbol} 数据至 {file_path}")

    def fetch_and_update(self, symbol, days=730, force_update=False):
        """
        智能获取数据:
        1. 检查本地是否存在
        2. 检查本地数据是否足够新 (包含昨天)
        3. 如果旧，增量更新或重新下载
        """
        df_local = self.load_local_data(symbol)
        
        # 目标开始日期
        target_start_date = datetime.now() - timedelta(days=days)
        
        needs_update = False
        
        if df_local is None or df_local.empty or force_update:
            needs_update = True
        else:
            # 检查最新日期
            last_date = df_local['date'].max()
            # 如果最新日期比昨天早 (考虑到时差和周末，宽容度设为2天)
            # 比如今天是周五，最新数据应该是周四收盘；如果是周一，最新可能是周五。
            # 简单起见，如果最新数据比 (现在-1天) 早，就尝试更新
            if last_date < datetime.now() - timedelta(days=1):
                # 还可以进一步判断是否是周末，这里简化处理，有缺口就更新
                needs_update = True
                
            # 检查最早日期是否满足 days 要求
            first_date = df_local['date'].min()
            if first_date > target_start_date + timedelta(days=5): # 允许5天误差
                # 本地数据不够长，需要重新下载更早的
                needs_update = True

        if not needs_update:
            # print(f"✅ {symbol} 使用本地缓存 (最新: {df_local['date'].max().strftime('%Y-%m-%d')})")
            # 过滤出需要的日期范围
            df_local = df_local[df_local['date'] >= target_start_date]
            return df_local

        # 需要更新
        # 策略：简单起见，直接覆盖下载 (yfinance 下载速度很快，增量逻辑复杂且易错)
        # 也可以做增量：start = last_date
        
        # yfinance symbol 转换
        yf_symbol = symbol.replace(".US", "").replace(".HK", ".HK")
        
        try:
            # 多下载一点，防止边界问题
            download_start = target_start_date - timedelta(days=10)
            df_new = yf.download(yf_symbol, start=download_start, progress=False, timeout=15)
            
            if df_new.empty:
                print(f"⚠️ {symbol} 下载为空，使用本地缓存")
                if df_local is not None and not df_local.empty:
                    return df_local[df_local['date'] >= target_start_date] if 'date' in df_local.columns else df_local
                return None
            
            # 清洗数据 (同 backtest_runner_yf.py)
            if isinstance(df_new.columns, pd.MultiIndex):
                df_new.columns = df_new.columns.get_level_values(0)
            
            df_new.columns = [c.lower() for c in df_new.columns]
            df_new.reset_index(inplace=True)
            if 'Date' in df_new.columns:
                df_new.rename(columns={'Date': 'date'}, inplace=True)
            
            # 确保 date 是 datetime
            df_new['date'] = pd.to_datetime(df_new['date'])
            
            # 保存全量
            self.save_data(symbol, df_new)
            
            # 过滤返回
            return df_new[df_new['date'] >= target_start_date]
            
        except Exception as e:
            print(f"⚠️ 更新 {symbol} 失败 ({type(e).__name__}), 使用本地缓存")
            if df_local is not None and not df_local.empty:
                return df_local[df_local['date'] >= target_start_date] if 'date' in df_local.columns else df_local
            return None

# 单例
_history_manager = None
def get_history_manager():
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager
