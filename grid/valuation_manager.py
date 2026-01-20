from db.market_db import MarketDatabase
from grid.etf818_client import Etf818Client
from datetime import datetime, timedelta
import pandas as pd
import logging

class ValuationManager:
    def __init__(self):
        self.db = MarketDatabase()
        self.client = Etf818Client()

    def get_index_for_etf(self, etf_code: str):
        """
        获取 ETF 对应的指数信息
        Returns: {'index_code': '000300.SH', 'index_name': '沪深300'} or None
        """
        # 1. 查库
        row = self.db.db.fetch_one(
            "SELECT index_code, index_name FROM etf_index_mapping WHERE etf_code = ?", 
            (etf_code,)
        )
        if row and row[0]:
            return {'index_code': row[0], 'index_name': row[1]}
            
        # 2. 查 API
        info = self.client.get_tracking_index(etf_code)
        if info:
            # 3. 入库
            self.db.db.execute(
                "INSERT OR REPLACE INTO etf_index_mapping (etf_code, index_code, index_name) VALUES (?, ?, ?)",
                (etf_code, info['index_code'], info['index_name'])
            )
            self.db.db.commit()
            return info
            
        return None

    def get_valuation_history(self, index_code: str) -> pd.DataFrame:
        """
        获取指数估值历史 (PE & PB)
        返回 DataFrame: index=date, columns=[pe, pb]
        """
        # 1. 检查数据库中是否有最近的数据
        # 简单策略：如果有今天的数据，就不更新。或者检查最大日期。
        last_date = self.db.db.fetch_one(
            "SELECT MAX(date) FROM index_valuation_history WHERE index_code = ?",
            (index_code,)
        )
        
        today = datetime.now().strftime('%Y-%m-%d')
        need_update = True
        
        if last_date and last_date[0]:
            last_dt = datetime.strptime(last_date[0], '%Y-%m-%d')
            # 如果数据在一个月内，暂时认为够用 (历史分位不需要天天刷，除非是实盘监控)
            # 但为了准确，最好是一周更新一次。
            # 这里简单起见：如果最后日期 < 昨天，尝试更新
            if (datetime.now() - last_dt).days < 2:
                need_update = False
        
        if need_update:
            self._update_valuation_from_api(index_code)
            
        # 2. 读取数据
        rows = self.db.db.fetch_all(
            "SELECT date, pe, pb FROM index_valuation_history WHERE index_code = ? ORDER BY date",
            (index_code,)
        )
        
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows, columns=['date', 'pe', 'pb'])
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date')

    def _update_valuation_from_api(self, index_code: str):
        """从 API 拉取 PE 和 PB 并合并入库"""
        # 1. 拉取 PE
        pe_list = self.client.get_valuation_history(index_code, 'PE')
        # 2. 拉取 PB
        pb_list = self.client.get_valuation_history(index_code, 'PB')
        
        if not pe_list and not pb_list:
            return
            
        # 转换为 Dict: date -> {pe, pb}
        data_map = {}
        
        def parse_date(d_str):
            # API 返回的是 YYYYMMDD
            if len(str(d_str)) == 8:
                return f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            return str(d_str)[:10]

        # 处理 PE
        for item in pe_list:
            d_raw = item.get('tradeDate')
            v = item.get('valuationValue')
            if d_raw:
                d = parse_date(d_raw)
                if d not in data_map: data_map[d] = {}
                data_map[d]['pe'] = v
                
        # 处理 PB
        for item in pb_list:
            d_raw = item.get('tradeDate')
            v = item.get('valuationValue')
            if d_raw:
                d = parse_date(d_raw)
                if d not in data_map: data_map[d] = {}
                data_map[d]['pb'] = v
                
        # 入库
        # 使用 executemany 优化
        to_insert = []
        for d, vals in data_map.items():
            to_insert.append((
                index_code, 
                d, 
                vals.get('pe'), 
                vals.get('pb')
            ))
            
        self.db.db.execute_many(
            "INSERT OR REPLACE INTO index_valuation_history (index_code, date, pe, pb) VALUES (?, ?, ?, ?)",
            to_insert
        )
        self.db.db.commit()
