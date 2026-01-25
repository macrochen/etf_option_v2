import akshare as ak
import logging

logging.basicConfig(level=logging.INFO)

print("Trying Sina interface...")
try:
    # 尝试获取新浪行情 (个股)
    df = ak.stock_zh_a_spot()
    print("Sina Success!")
    print(df.head(2))
except Exception as e:
    print(f"Sina Failed: {e}")
