import akshare as ak
import traceback

try:
    print("Testing 106.AAPL (invalid)...")
    df = ak.stock_us_hist(symbol="106.AAPL", period="daily", start_date="20230101", end_date="20230105", adjust="qfq")
    print(df)
except Exception:
    print("Caught expected error for 106.AAPL")
    # traceback.print_exc()

try:
    print("Testing 105.AAPL (valid)...")
    df = ak.stock_us_hist(symbol="105.AAPL", period="daily", start_date="20230101", end_date="20230105", adjust="qfq")
    print(f"Success: {len(df)} rows")
except Exception:
    traceback.print_exc()
