from core.data import get_fetcher
from core.regime import RegimeDetector
import pandas as pd

fetcher = get_fetcher()
symbol = "NVDA.US"
print(f"Fetching {symbol}...")
data = fetcher.get_kline_df(symbol, days=200)

if data:
    df = pd.DataFrame(data)
    print(f"Latest date: {df.iloc[-1]['date']}")
    print(f"Latest price: {df.iloc[-1]['close']}")
    
    detector = RegimeDetector()
    regime = detector.analyze(symbol, df)
    print(f"Regime: {regime}")
else:
    print("No data fetched")
