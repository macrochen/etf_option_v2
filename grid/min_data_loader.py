import sqlite3
import pandas as pd
import akshare as ak
import os
from datetime import datetime

class MinDataLoader:
    def __init__(self, db_path='db/market_data_min.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS etf_min_1m (
                symbol TEXT,
                timestamp TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                amount REAL,
                PRIMARY KEY (symbol, timestamp)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_time ON etf_min_1m (symbol, timestamp)')
        conn.commit()
        conn.close()

    def load_data(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        加载本地分钟数据。
        start_date, end_date format: 'YYYY-MM-DD'
        """
        conn = sqlite3.connect(self.db_path)
        query = "SELECT * FROM etf_min_1m WHERE symbol = ?"
        params = [symbol]
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(f"{start_date} 09:30:00")
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(f"{end_date} 15:00:00")
            
        query += " ORDER BY timestamp ASC"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

    def update_data(self, symbol: str) -> bool:
        """
        从 AKShare 下载最新分钟数据并更新到数据库。
        注意：fund_etf_hist_min_em 通常返回最近一段时间的数据（如最近几千条）。
        """
        try:
            # period='1' 代表 1分钟线
            df = ak.fund_etf_hist_min_em(symbol=symbol, period='1', adjust='qfq')
            
            if df.empty:
                return False

            # 重命名列
            # 原始列: 时间, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 均价
            df = df.rename(columns={
                '时间': 'timestamp',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume',
                '成交额': 'amount'
            })
            
            # 增加 symbol 列
            df['symbol'] = symbol
            
            # 数据清洗：修复 Open=0 的脏数据
            # 如果 Open <= 0 且 Close > 0，用 Close 填充 Open
            mask = (df['open'] <= 0) & (df['close'] > 0)
            if mask.any():
                df.loc[mask, 'open'] = df.loc[mask, 'close']
                # 同步修复 High/Low 如果也为0
                df.loc[(df['high'] <= 0) & (df['close'] > 0), 'high'] = df.loc[(df['high'] <= 0) & (df['close'] > 0), 'close']
                df.loc[(df['low'] <= 0) & (df['close'] > 0), 'low'] = df.loc[(df['low'] <= 0) & (df['close'] > 0), 'close']
            
            # 存入数据库 (Upsert)
            conn = sqlite3.connect(self.db_path)
            
            # 使用 executemany 进行批量插入/更新
            # SQLite 的 INSERT OR REPLACE
            data_to_insert = df[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']].values.tolist()
            
            conn.executemany('''
                INSERT OR REPLACE INTO etf_min_1m (symbol, timestamp, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error updating minute data for {symbol}: {e}")
            return False

    def get_available_range(self, symbol: str):
        """获取本地数据的可用时间范围"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM etf_min_1m WHERE symbol = ?", (symbol,))
        res = cursor.fetchone()
        conn.close()
        if res and res[0]:
            return {
                'start': res[0],
                'end': res[1],
                'count': res[2]
            }
        return None
