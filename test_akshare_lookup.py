import akshare as ak
import pandas as pd

try:
    print("Fetching US stock spot data...")
    df = ak.stock_us_spot_em()
    print(df.head())
    
    # Check if AAPL is in there
    aapl = df[df['名称'] == '苹果']
    if not aapl.empty:
        print("Found Apple by Name:")
        print(aapl)
        
    aapl_code = df[df['代码'] == '105.AAPL']
    if not aapl_code.empty:
         print("Found Apple by Code 105.AAPL:")
         print(aapl_code)
         
    aapl_short = df[df['代码'] == 'AAPL']
    if not aapl_short.empty:
         print("Found Apple by Code AAPL:")
         print(aapl_short)
         
except Exception as e:
    print(e)
