import os
import sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.data import get_fetcher
print("Attempting to get fetcher...")
fetcher = get_fetcher()
print("Fetcher obtained.")
print("Attempting to get quote for AAPL...")
quote = fetcher.get_realtime_quotes(["AAPL.US"])
print(f"Quote: {quote}")
