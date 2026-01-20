import akshare as ak
import pandas as pd

def test_csindex_variants():
    symbols = ["000300", "H00300", "000905", "000001"]
    print("Testing stock_zh_index_value_csindex with various symbols...")
    
    for s in symbols:
        try:
            print(f"Trying symbol: {s}")
            df = ak.stock_zh_index_value_csindex(symbol=s)
            if df is not None and not df.empty:
                print(f"Success! Symbol {s} returned {len(df)} rows.")
                print(df.head())
                print(df.columns.tolist())
                return # 找到一个成功的就停止
            else:
                print(f"Symbol {s} returned empty dataframe.")
        except Exception as e:
            print(f"Symbol {s} failed: {e}")

if __name__ == "__main__":
    test_csindex_variants()
