import akshare as ak
import logging

logging.basicConfig(level=logging.INFO)

print("Testing Tencent Interface...")

def get_prefix(symbol):
    """简单推断前缀"""
    if symbol.startswith('6') or symbol.startswith('5') or symbol.startswith('9'):
        return f"sh{symbol}"
    else:
        return f"sz{symbol}"

test_codes = ['600519', '510300'] # 茅台, 300ETF

try:
    for code in test_codes:
        symbol = get_prefix(code)
        print(f"Requesting {symbol}...")
        # akshare 的腾讯接口通常是 stock_zh_a_spot_tx(symbol="sh600519")
        # 注意：不同版本 akshare 函数名可能不同，这里尝试标准名称
        df = ak.stock_zh_a_spot_tx(symbol=symbol)
        print(f"Success {symbol}: Latest Price = {df['最新价'].values[0]}")
        
    print("\nTest Finished.")
except Exception as e:
    print(f"\nTencent Failed: {e}")
