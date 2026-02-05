from core.data import get_fetcher
from core.regime import RegimeDetector

fetcher = get_fetcher()
symbol = "MSFT.US"
print(f"Fetching {symbol}...")
df = fetcher.get_kline_df(symbol, days=200)
print(f"Data length: {len(df) if df is not None else 'None'}")
if df is not None and not df.empty:
    print(df.tail())
    detector = RegimeDetector()
    regime = detector.analyze(symbol, df)
    print(f"Regime: {regime}")
