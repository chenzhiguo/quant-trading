import pandas as pd
import random
from datetime import datetime, timedelta

def generate_mock_data(symbol="NVDA.US", days=365):
    """生成模拟 CSV 数据"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    dates = pd.date_range(start=start_date, end=end_date, freq='B') # 工作日
    data = []
    
    price = 100.0
    for d in dates:
        # 模拟随机波动
        change = random.uniform(-0.03, 0.03) 
        # 加上一点动量趋势
        if "NVDA" in symbol:
            change += 0.001 # 长期上涨
            
        price *= (1 + change)
        high = price * (1 + random.uniform(0, 0.02))
        low = price * (1 - random.uniform(0, 0.02))
        open_price = price * (1 + random.uniform(-0.01, 0.01))
        vol = int(random.uniform(1000000, 5000000))
        
        data.append({
            "date": d,
            "open": open_price,
            "high": high,
            "low": low,
            "close": price,
            "volume": vol
        })
        
    df = pd.DataFrame(data)
    filename = f"mock_{symbol}.csv"
    df.to_csv(filename, index=False)
    print(f"✅ 生成模拟数据: {filename}")
    return filename

if __name__ == "__main__":
    generate_mock_data()
