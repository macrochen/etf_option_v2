import akshare as ak
import traceback

print(f"Akshare version: {ak.__version__}")

try:
    print("\nTesting stock_us_hist for AAPL (Apple) without prefix...")
    df = ak.stock_us_hist(symbol="AAPL", period="daily", start_date="20230101", end_date="20230110", adjust="qfq")
    print(f"Success with 'AAPL'! Shape: {df.shape}")
except Exception:
    print("Failed with 'AAPL'")
    traceback.print_exc()
