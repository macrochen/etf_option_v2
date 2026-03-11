import akshare as ak
import traceback

print(f"Akshare version: {ak.__version__}")

try:
    print("Testing stock_zh_a_hist for 600519...")
    df = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20230101", end_date="20230110", adjust="qfq")
    print("Success!")
    print(df.head())
except Exception:
    traceback.print_exc()
