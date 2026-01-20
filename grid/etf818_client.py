import requests
import time
import logging
from typing import Dict, List, Optional

class Etf818Client:
    BASE_URL = "https://etf818.com/fundex-quote"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://etf818.com/",
        "Accept": "application/json, text/plain, */*"
    }

    def _get_ts(self) -> int:
        return int(time.time() * 1000)

    def get_tracking_index(self, etf_code: str) -> Optional[Dict[str, str]]:
        """
        获取 ETF 对应的跟踪指数
        API: /security/component/trackingIndex?securityCode=510300.SH&ts=...
        """
        # 确保代码格式为 510300.SH
        if not etf_code.endswith(('.SH', '.SZ')):
            # 简单推断：5开头是SH，1开头是SZ
            if etf_code.startswith('5'):
                etf_code += '.SH'
            elif etf_code.startswith('1'):
                etf_code += '.SZ'
        
        url = f"{self.BASE_URL}/security/component/trackingIndex"
        params = {
            "securityCode": etf_code,
            "ts": self._get_ts()
        }
        
        try:
            logging.info(f"Fetching tracking index for {etf_code}...")
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            logging.info(f"API Response for {etf_code}: {data}")
            
            # 响应结构推测: {"data": {"securityCode": "000300.SH", "securityName": "沪深300"}}
            # 需根据实际响应调整
            if str(data.get("code")) == "200" and data.get("data"):
                return {
                    "index_code": data["data"].get("securityCode"),
                    "index_name": data["data"].get("securityName")
                }
            return None
            
        except Exception as e:
            logging.error(f"Error fetching tracking index for {etf_code}: {e}")
            return None

    def get_valuation_history(self, index_code: str, valuation_type: str = 'PE') -> List[Dict]:
        """
        获取指数历史估值
        API: /index/valuation?securityCode=000300.SH&valuationType=PE&timeInterval=max&ts=...
        """
        url = f"{self.BASE_URL}/index/valuation"
        params = {
            "securityCode": index_code,
            "valuationType": valuation_type, # PE or PB
            "timeInterval": "max",
            "ts": self._get_ts()
        }
        
        try:
            logging.info(f"Fetching {valuation_type} history for {index_code}...")
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            # 响应结构需验证
            if str(data.get("code")) == "200" and data.get("data"):
                # data["data"] 是字典，历史数据在 items 列表中
                # items: [{'tradeDate': '20230101', 'valuationValue': 12.3}, ...]
                return data["data"].get("items", [])
            return []
            
        except Exception as e:
            logging.error(f"Error fetching valuation for {index_code}: {e}")
            return []
