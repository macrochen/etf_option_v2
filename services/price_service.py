import akshare as ak
import pandas as pd
import logging
from typing import Dict, Optional

class PriceService:
    @staticmethod
    def get_current_price(symbol: str, asset_type: str) -> Optional[float]:
        """获取资产当前价格/净值"""
        try:
            if asset_type == 'cash':
                return 1.0
                
            elif asset_type in ['stock', 'etf']:
                # 使用 akshare 获取实时行情
                df = ak.stock_zh_a_spot_em()
                # 过滤出对应代码的行
                row = df[df['代码'] == symbol]
                if not row.empty:
                    return float(row.iloc[0]['最新价'])
                    
            elif asset_type == 'fund':
                # 获取场外基金净值
                df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
                if not df.empty:
                    # 获取最新日期的单位净值
                    return float(df.iloc[-1]['单位净值'])
                    
            return None
            
        except Exception as e:
            logging.error(f"Error fetching price for {symbol} ({asset_type}): {e}")
            return None

    @staticmethod
    def get_batch_prices(assets: list) -> Dict[str, float]:
        """批量获取价格 (简单实现，循环调用)"""
        prices = {}
        
        # 优化：对于股票/ETF，可以一次性获取所有行情再匹配
        stock_etf_symbols = [a['symbol'] for a in assets if a['asset_type'] in ['stock', 'etf']]
        if stock_etf_symbols:
            try:
                df = ak.stock_zh_a_spot_em()
                for symbol in stock_etf_symbols:
                    row = df[df['代码'] == symbol]
                    if not row.empty:
                        prices[symbol] = float(row.iloc[0]['最新价'])
            except Exception as e:
                logging.error(f"Batch fetch error for stocks: {e}")

        # 场外基金和现金单独处理
        for asset in assets:
            if asset['symbol'] not in prices: # 还没获取到
                price = PriceService.get_current_price(asset['symbol'], asset['asset_type'])
                if price is not None:
                    prices[asset['symbol']] = price
                    
        return prices
