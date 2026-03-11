import yfinance as yf
import logging

logging.basicConfig(level=logging.INFO)

print("Testing Yahoo Finance...")

# Yahoo Finance 后缀规则：
# 上海: .SS (如 600519.SS)
# 深圳: .SZ (如 000001.SZ)

test_symbols = ['600519.SS', '510300.SS', '588000.SS', '00700.HK', 'AAPL']

try:
    print(f"Requesting: {test_symbols}")
    # 批量获取
    tickers = yf.Tickers(" ".join(test_symbols))
    
    for symbol in test_symbols:
        try:
            ticker = tickers.tickers[symbol]
            # 获取实时价格 (regularMarketPrice 或 currentPrice)
            # yfinance 的 info 字典包含大量信息
            price = ticker.info.get('regularMarketPrice') or ticker.info.get('currentPrice') or ticker.info.get('previousClose')
            print(f"Success {symbol}: {price}")
        except Exception as e:
            print(f"Failed {symbol}: {e}")

except Exception as e:
    print(f"Global Error: {e}")
