import akshare as ak
import pandas as pd

def test_csindex_valuation():
    print("Testing stock_zh_index_value_csindex...")
    try:
        # 中证指数估值，symbol 通常是指数代码，如 000300
        df = ak.stock_zh_index_value_csindex(symbol="H00300") # 沪深300
        print(df.head())
    except Exception as e:
        print(f"csindex failed: {e}")

def test_legu_valuation():
    print("\nTesting stock_a_indicator_lg (Legu)...")
    try:
        # 乐咕看盘，通常用 stock_a_indicator_lg(symbol="000300")
        df = ak.stock_a_indicator_lg(symbol="000300")
        print(df.head())
    except Exception as e:
        print(f"legu failed: {e}")

if __name__ == "__main__":
    test_csindex_valuation()
    test_legu_valuation()
