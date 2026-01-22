from db.market_db import MarketDatabase
from grid.etf818_client import Etf818Client
from datetime import datetime, timedelta
import pandas as pd
import logging
import numpy as np

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
        返回 DataFrame: index=date, columns=[pe, pb, pe_rank, pb_rank]
        """
        # 1. 检查数据库中是否有最近的数据
        # 简单策略：如果有今天的数据，就不更新。或者检查最大日期。
        last_date = self.db.db.fetch_one(
            "SELECT MAX(date) FROM index_valuation_history WHERE index_code = ?",
            (index_code,)
        )
        
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
            
        # 2. 读取数据 (包含 Rank)
        rows = self.db.db.fetch_all(
            "SELECT date, pe, pb, pe_rank, pb_rank FROM index_valuation_history WHERE index_code = ? ORDER BY date",
            (index_code,)
        )
        
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows, columns=['date', 'pe', 'pb', 'pe_rank', 'pb_rank'])
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date')

    def ensure_valuation_ranks(self, index_code: str):
        """
        计算并缓存 PE/PB 的历史 5 年分位数
        """
        # 1. 检查是否需要更新 (即是否存在 rank 为空的数据)
        row = self.db.db.fetch_one(
            "SELECT COUNT(*) FROM index_valuation_history WHERE index_code = ? AND (pe_rank IS NULL OR pb_rank IS NULL)",
            (index_code,)
        )
        if not row or row[0] == 0:
            return # 数据完整，无需计算

        logging.info(f"Calculating rolling ranks for {index_code}...")
        
        # 2. 加载全量数据 (此时 rank 可能是 None)
        df = self.get_valuation_history(index_code)
        if df.empty: return
        
        # 确保索引是 DatetimeIndex 以支持时间窗口 rolling
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # 3. 计算 Rolling Rank (时间窗口)
        # 使用 5 年 (1825天) 时间窗口，而非固定行数
        # 这确保了与 boundary_calc 中的日期切片逻辑一致
        for col in ['pe', 'pb']:
            series = df[col].where(df[col] > 0)
            # 计算 Rank (0-100)
            df[f'{col}_rank'] = series.rolling(window='1825D', min_periods=250).apply(
                lambda x: (x < x.iloc[-1]).mean() * 100 if len(x) > 0 else np.nan,
                raw=False
            )
            
        # 4. 更新回数据库
        to_update = []
        for date, row in df.iterrows():
            if pd.notna(row['pe_rank']) or pd.notna(row['pb_rank']):
                to_update.append((
                    row['pe_rank'] if pd.notna(row['pe_rank']) else None,
                    row['pb_rank'] if pd.notna(row['pb_rank']) else None,
                    index_code,
                    date.strftime('%Y-%m-%d')
                ))
        
        if to_update:
            logging.info(f"Updating {len(to_update)} ranks to DB...")
            self.db.db.execute_many(
                "UPDATE index_valuation_history SET pe_rank=?, pb_rank=? WHERE index_code=? AND date=?",
                to_update
            )
            self.db.db.commit()

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
