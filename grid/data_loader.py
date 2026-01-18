import pandas as pd
from db.market_db import MarketDatabase
from typing import Optional

class GridDataLoader:
    def __init__(self):
        self.db = MarketDatabase()

    def load_daily_data(self, symbol: str, start_date: str = None) -> pd.DataFrame:
        """
        加载日线数据 (前复权)
        注意：假设数据库中的 etf_daily 已经是复权数据，或者忽略复权差异（根据用户确认）
        """
        # 从 db 获取
        # MarketDatabase.get_price_data 返回的是 (prices, dates) tuple
        # 我们直接查库可能更灵活，或者扩展 MarketDatabase
        # 这里直接用 SQL 查询以构造 DataFrame
        
        sql = """
            SELECT date, open_price, high_price, low_price, close_price, volume
            FROM grid_trade
            WHERE etf_code = ?
        """
        params = [symbol]
        
        if start_date:
            sql += " AND date >= ?"
            params.append(start_date)
            
        sql += " ORDER BY date ASC"
        
        rows = self.db.db.fetch_all(sql, tuple(params))
        
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        
        # 确保数值类型
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col])
            
        return df

    def get_latest_price(self, symbol: str) -> float:
        """获取最新收盘价"""
        sql = "SELECT close_price FROM grid_trade WHERE etf_code = ? ORDER BY date DESC LIMIT 1"
        row = self.db.db.fetch_one(sql, (symbol,))
        return float(row[0]) if row else 0.0
