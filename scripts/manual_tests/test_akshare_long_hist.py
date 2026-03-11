import akshare as ak
import pandas as pd

def test_long_history_valuation():
    # 尝试 funddb 接口，这个接口通常返回很长的历史数据
    print("Testing index_value_hist_funddb for long history...")
    try:
        # symbol="000300", indicator="市盈率"
        df = ak.index_value_hist_funddb(symbol="000300", indicator="市盈率")
        if not df.empty:
            print(f"Success! Found {len(df)} rows of historical PE.")
            print(df.tail())
            return
    except Exception as e:
        print(f"funddb (市盈率) failed: {e}")

    try:
        df = ak.index_value_hist_funddb(symbol="000300", indicator="市净率")
        if not df.empty:
            print(f"Success! Found {len(df)} rows of historical PB.")
            print(df.tail())
            return
    except Exception as e:
        print(f"funddb (市净率) failed: {e}")

if __name__ == "__main__":
    test_long_history_valuation()
