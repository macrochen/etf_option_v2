import akshare as ak
import requests
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
                # 优先尝试腾讯直连
                try:
                    res = PriceService._get_tencent_prices([symbol])
                    if symbol in res:
                        return res[symbol]
                except:
                    pass
                    
                # 备用：akshare 东财 (单只获取效率低，且可能被墙)
                try:
                    df = ak.stock_zh_a_spot_em()
                    row = df[df['代码'] == symbol]
                    if not row.empty:
                        return float(row.iloc[0]['最新价'])
                except:
                    pass
                    
            elif asset_type == 'fund':
                # 获取场外基金净值 (天天基金源，通常比较稳)
                df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
                if not df.empty:
                    return float(df.iloc[-1]['单位净值'])
                    
            return None
            
        except Exception as e:
            logging.error(f"Error fetching price for {symbol} ({asset_type}): {e}")
            return None

    @staticmethod
    def _get_tencent_prices(symbols: list) -> Dict[str, float]:
        """直接调用腾讯财经接口获取批量价格"""
        prices = {}
        if not symbols:
            return prices
            
        # 转换代码格式：6开头->sh, 5/9->sh, 0/3/1->sz, 4/8->bj
        # 腾讯接口对bj支持不一定好，主要处理sh/sz
        tencent_codes = []
        code_map = {} # tencent_code -> original_symbol
        
        for s in symbols:
            prefix = ''
            if s.startswith(('6', '5')): # 上海
                prefix = 'sh'
            elif s.startswith(('0', '3', '1')): # 深圳
                prefix = 'sz'
            elif s.startswith(('4', '8')): # 北交所通常腾讯用 bj? 或者 sz? 暂且跳过或试bj
                prefix = 'bj'
            
            if prefix:
                t_code = f"{prefix}{s}"
                tencent_codes.append(t_code)
                code_map[t_code] = s
        
        if not tencent_codes:
            return prices

        # 分批请求，腾讯接口URL长度有限制
        chunk_size = 50
        for i in range(0, len(tencent_codes), chunk_size):
            chunk = tencent_codes[i:i+chunk_size]
            url = f"http://qt.gtimg.cn/q={','.join(chunk)}"
            
            try:
                resp = requests.get(url, timeout=3)
                if resp.status_code == 200:
                    lines = resp.text.split(';')
                    for line in lines:
                        if '="' in line:
                            parts = line.split('="')
                            # parts[0] 格式 v_sh600519
                            t_code = parts[0].split('_')[-1]
                            data_str = parts[1].strip('"')
                            data = data_str.split('~')
                            
                            if len(data) > 3:
                                try:
                                    price = float(data[3])
                                    original_symbol = code_map.get(t_code)
                                    if original_symbol:
                                        prices[original_symbol] = price
                                except (ValueError, IndexError):
                                    pass
            except Exception as e:
                logging.error(f"Tencent batch fetch failed: {e}")
                
        return prices

    @staticmethod
    def get_batch_prices(assets: list) -> Dict[str, float]:
        """批量获取价格 (优化版：优先腾讯直连)"""
        prices = {}
        
        # 1. 提取所有需要批量获取的股票/ETF代码
        stock_etf_symbols = set()
        for asset in assets:
            if asset['asset_type'] in ['stock', 'etf']:
                stock_etf_symbols.add(asset['symbol'])
        
        # 2. 优先尝试腾讯直连接口 (最快最稳)
        if stock_etf_symbols:
            try:
                t_prices = PriceService._get_tencent_prices(list(stock_etf_symbols))
                prices.update(t_prices)
            except Exception as e:
                logging.error(f"Tencent source failed: {e}")

        # 3. 检查是否有漏网之鱼，尝试 Akshare (EastMoney/Sina)
        missing_symbols = stock_etf_symbols - set(prices.keys())
        if missing_symbols:
            # ... (Existing akshare fallback logic)
            # 为了简化代码，这里仅作为最后的备选，或者如果腾讯覆盖了就不跑了
            try:
                # 只有当缺失时才尝试 akshare，避免重复请求
                df = ak.stock_zh_a_spot_em()
                mask = df['代码'].isin(missing_symbols)
                relevant_rows = df[mask]
                for _, row in relevant_rows.iterrows():
                    try:
                        val = float(row['最新价'])
                        prices[row['代码']] = val
                    except: pass
            except Exception:
                pass # Ignore backup errors

        # 4. 处理场外基金、现金和其他类型
        for asset in assets:
            symbol = asset['symbol']
            atype = asset['asset_type']
            
            if symbol in prices: continue
            if atype == 'cash':
                prices[symbol] = 1.0
                continue
            
            if atype == 'fund':
                try:
                    price = PriceService.get_current_price(symbol, atype)
                    if price is not None:
                        prices[symbol] = price
                except: pass
            
        return prices
