import akshare as ak
import traceback

print(f"Akshare version: {ak.__version__}")

try:
    print("\nTesting stock_zh_a_hist for 600519 (Moutai)...")
    df = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20230101", end_date="20230110", adjust="qfq")
    print(f"Success! Shape: {df.shape}")
except Exception:
    traceback.print_exc()

try:
    print("\nTesting stock_hk_hist for 00700 (Tencent)...")
    # akshare usually expects '00700' for HK stocks
    df = ak.stock_hk_hist(symbol="00700", period="daily", start_date="20230101", end_date="20230110", adjust="qfq")
    print(f"Success! Shape: {df.shape}")
except Exception:
    traceback.print_exc()

try:
    print("\nTesting stock_us_hist for 105.AAPL (Apple)...")
    # Using the symbol '105.AAPL' as is common for EastMoney source in akshare, or just 'AAPL'
    # Let's try 'AAPL' first, as my code uses that.
    # If it fails, I might need to adjust the code.
    try:
        df = ak.stock_us_hist(symbol="105.AAPL", period="daily", start_date="20230101", end_date="20230110", adjust="qfq")
        print(f"Success with '105.AAPL'! Shape: {df.shape}")
    except:
        print("Failed with '105.AAPL', trying 'AAPL'...")
        df = ak.stock_us_hist(symbol="AAPL", period="daily", start_date="20230101", end_date="20230110", adjust="qfq")
        print(f"Success with 'AAPL'! Shape: {df.shape}")

except Exception:
    traceback.print_exc()
