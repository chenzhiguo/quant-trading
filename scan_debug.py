
import os
import sys
from datetime import datetime
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.data import get_fetcher, Period
from config.watchlist import get_watchlist

def debug_scan():
    print("Starting debug scan...")
    symbols = get_watchlist("all")
    print(f"Total symbols: {len(symbols)}")
    
    fetcher = get_fetcher()
    print("Fetcher initialized.")
    
    print("Testing get_realtime_quotes for all symbols...")
    try:
        quotes = fetcher.get_realtime_quotes(symbols)
        print(f"Successfully got {len(quotes)} quotes.")
    except Exception as e:
        print(f"Failed to get quotes: {e}")
        return

    print("Testing get_candlesticks for each symbol...")
    for i, symbol in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] Fetching candles for {symbol}...", end="", flush=True)
        try:
            start_time = time.time()
            candles = fetcher.get_candlesticks(symbol, Period.Day, 10) # reduced count for speed
            duration = time.time() - start_time
            print(f" Done ({len(candles)} candles) in {duration:.2f}s")
        except Exception as e:
            print(f" Failed: {e}")

if __name__ == "__main__":
    debug_scan()
