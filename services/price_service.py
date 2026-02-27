import akshare as ak
import requests
import traceback
import logging # 使用标准日志库
from typing import Dict, Optional

# 获取当前模块的 logger
logger = logging.getLogger(__name__)

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
                    
                # 备用：akshare 东财
                try:
                    df = ak.stock_zh_a_spot_em()
                    row = df[df['代码'] == symbol]
                    if not row.empty:
                        return float(row.iloc[0]['最新价'])
                except:
                    pass
                    
            elif asset_type == 'fund':
                # 获取场外基金净值
                # logger.info(f"正在调取 Akshare 基金接口: {symbol}")
                df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
                if not df.empty:
                    return float(df.iloc[-1]['单位净值'])
                    
            return None
            
        except Exception as e:
            logger.error(f"Error fetching price for {symbol} ({asset_type}): {e}")
            return None

    @staticmethod
    def _get_tencent_prices(symbols: list) -> Dict[str, float]:
        """直接调用腾讯财经接口获取批量价格"""
        prices = {}
        if not symbols:
            return prices
            
        tencent_codes = []
        code_map = {} 
        
        for s in symbols:
            prefix = ''
            if s.startswith(('6', '5', '9')): # 上海
                prefix = 'sh'
            elif s.startswith(('0', '3', '1')): # 深圳
                prefix = 'sz'
            elif s.startswith(('4', '8')): # 北交所
                prefix = 'bj'
            
            if prefix:
                t_code = f"{prefix}{s}"
                tencent_codes.append(t_code)
                code_map[t_code] = s
        
        if not tencent_codes:
            return prices

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
                logger.error(f"Tencent batch fetch failed: {e}")
                
        return prices

    @staticmethod
    def get_batch_prices(assets: list) -> Dict[tuple, float]:
        """批量获取价格"""
        prices = {}
        
        # 1. 提取资产信息
        stock_etf_symbols = set()
        fund_assets = []
        skipped_custom_count = 0
        
        for asset in assets:
            atype = asset.get('asset_type')
            s = asset.get('symbol', '')
            
            # 核心过滤：如果代码包含非数字字符（如 TG_XXXX, CASH_XXXX），认为是自定义资产，跳过自动同步
            if not s.isdigit():
                skipped_custom_count += 1
                continue
                
            if atype in ['stock', 'etf']:
                stock_etf_symbols.add(s)
            elif atype == 'fund':
                fund_assets.append(asset)
        
        if skipped_custom_count > 0:
            logger.info(f"已跳过 {skipped_custom_count} 个自定义资产（代码含非数字字符），请手动维护其现价。")
        
        logger.info(f">>> [行情同步] 计划同步 {len(stock_etf_symbols)} 个上市标的，{len(fund_assets)} 个场外基金。")

        # 2. 同步股票/ETF (腾讯接口)
        if stock_etf_symbols:
            try:
                logger.info(f"正在调用腾讯财经接口批量获取 {len(stock_etf_symbols)} 个股票/ETF 价格...")
                t_prices = PriceService._get_tencent_prices(list(stock_etf_symbols))
                
                for asset in assets:
                    s, atype = asset['symbol'], asset['asset_type']
                    if atype in ['stock', 'etf'] and s in t_prices:
                        prices[(s, atype)] = t_prices[s]
                
                logger.info(f"腾讯接口同步完成，成功获取 {len([k for k in prices if k[1] in ['stock', 'etf']])} 个标的价格。")
            except Exception as e:
                logger.error(f"Tencent source failed: {e}")

        # 3. 基金逐个同步 (由于场外基金无批量实时接口，只能逐个调取净值)
        if fund_assets:
            logger.info(f"开始同步 {len(fund_assets)} 个场外基金净值...")
            for i, asset in enumerate(fund_assets):
                s, atype = asset['symbol'], asset['asset_type']
                try:
                    logger.info(f"[{i+1}/{len(fund_assets)}] 抓取基金净值: {asset['name']}({s})...")
                    price = PriceService.get_current_price(s, atype)
                    if price is not None:
                        prices[(s, atype)] = price
                        logger.info(f"   => 成功: {price}")
                    else:
                        logger.warning(f"   => 失败: 未能获取到净值")
                except Exception as e:
                    logger.error(f"   => 异常: {e}")
            
        return prices
