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
        """批量获取价格 (优化版)"""
        prices = {}
        
        # 1. 提取所有需要批量获取的股票/ETF代码
        stock_etf_symbols = set()
        for asset in assets:
            if asset['asset_type'] in ['stock', 'etf']:
                stock_etf_symbols.add(asset['symbol'])
        
        # 2. 批量获取 A 股/ETF 行情
        if stock_etf_symbols:
            try:
                # 注意：这个接口比较慢，获取全市场数据
                df = ak.stock_zh_a_spot_em()
                
                # 优化匹配性能：将 DataFrame 转为字典或使用 isin
                # 这里我们只关心我们持有的代码
                # 假设 df 有 '代码' 和 '最新价' 列
                mask = df['代码'].isin(stock_etf_symbols)
                relevant_rows = df[mask]
                
                for _, row in relevant_rows.iterrows():
                    try:
                        val = float(row['最新价'])
                        prices[row['代码']] = val
                    except (ValueError, KeyError):
                        pass
                        
            except Exception as e:
                logging.error(f"Batch fetch error for stocks: {e}")

        # 3. 处理场外基金、现金和其他类型
        # 注意：不要对 stock/etf 类型进行重试，因为 get_current_price 也会调用全量接口，会导致性能灾难
        for asset in assets:
            symbol = asset['symbol']
            atype = asset['asset_type']
            
            # 如果已经获取到了，跳过
            if symbol in prices:
                continue
                
            # 现金直接设为 1
            if atype == 'cash':
                prices[symbol] = 1.0
                continue
                
            # 场外基金单独获取
            if atype == 'fund':
                try:
                    price = PriceService.get_current_price(symbol, atype)
                    if price is not None:
                        prices[symbol] = price
                except Exception:
                    pass
            
            # Stock/ETF 如果在步骤 2 没获取到，可能是代码错误或停牌，不再重试
                    
        return prices
