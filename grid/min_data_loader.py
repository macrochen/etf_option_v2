import sqlite3
import pandas as pd
import akshare as ak
import os
import glob
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

    def get_etf_list(self) -> list:
        """
        获取已有分钟线数据的 ETF 列表。
        逻辑：
        1. 从 etf_min_1m 表提取所有 symbol 及其起止时间。
        2. 关联 fund_info 表获取名称。
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 关联 market_data.db 获取基金名称
            info_db_path = 'db/market_data.db'
            if os.path.exists(info_db_path):
                conn.execute(f"ATTACH DATABASE '{info_db_path}' AS info_db")
                query = """
                    SELECT 
                        t1.symbol, 
                        COALESCE(t2.fund_name, t1.symbol) as name,
                        MIN(t1.timestamp) as start_date,
                        MAX(t1.timestamp) as end_date
                    FROM etf_min_1m t1
                    LEFT JOIN info_db.fund_info t2 ON t1.symbol = t2.fund_code
                    GROUP BY t1.symbol
                    ORDER BY t1.symbol
                """
            else:
                query = """
                    SELECT 
                        symbol, 
                        symbol as name,
                        MIN(timestamp) as start_date,
                        MAX(timestamp) as end_date
                    FROM etf_min_1m
                    GROUP BY symbol
                    ORDER BY symbol
                """
            
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            data = []
            for r in rows:
                # 仅保留日期部分
                start = r[2].split(' ')[0] if r[2] else ''
                end = r[3].split(' ')[0] if r[3] else ''
                
                data.append({
                    'code': r[0],
                    'name': r[1],
                    'start_date': start,
                    'end_date': end
                })
                
            return data
            
        except Exception as e:
            print(f"Error getting ETF list: {e}")
            return []

    def import_from_local_parquet(self, symbol: str, parquet_dir='data/etf_1min') -> bool:
        """
        优先从本地 Parquet 文件增量导入数据。
        参考 scripts/import_parquet_data.py 的处理逻辑 (含复权和格式转换)。
        """
        try:
            # 查找文件
            pattern = os.path.join(parquet_dir, f"*{symbol}*.parquet")
            files = glob.glob(pattern)
            
            if not files:
                return False
                
            file_path = files[0]
            df = pd.read_parquet(file_path)
            
            if df.empty:
                return False

            # Parquet 可能使用 MultiIndex (trade_date, trade_time)
            df = df.reset_index()

            # 1. 前复权处理 (Forward Adjust)
            if 'adj_factor' in df.columns:
                latest_adj = df['adj_factor'].iloc[-1]
                if latest_adj != 0:
                    mult = df['adj_factor'] / latest_adj
                    px_cols = ['open', 'high', 'low', 'close']
                    df[px_cols] = df[px_cols].mul(mult, axis=0).round(3)
            
            # 2. 格式转换 trade_time -> timestamp
            if 'trade_time' in df.columns:
                df['timestamp'] = df['trade_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                print(f"Missing 'trade_time' column in {file_path}")
                return False

            df['symbol'] = symbol
            
            # 映射 volume 字段 (parquet 中通常是 vol)
            if 'vol' in df.columns:
                df['volume'] = df['vol']
            
            # 检查必要列
            required_cols = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"Missing columns in {file_path}: {missing_cols}")
                return False
                
            data_to_insert = df[required_cols].values.tolist()
            
            conn = sqlite3.connect(self.db_path)
            conn.executemany('''
                INSERT OR REPLACE INTO etf_min_1m (symbol, timestamp, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)
            
            conn.commit()
            conn.close()
            print(f"Successfully imported {len(df)} records from {file_path}")
            
            return True
            
        except Exception as e:
            print(f"Error importing from local parquet for {symbol}: {e}")
            return False


    def update_data(self, symbol: str) -> bool:
        """
        更新数据策略：
        1. 优先尝试从本地 data/etf_1min/ 下的 parquet 文件导入。
        2. 如果本地无文件，则从 AKShare 下载。
        """
        # 1. 尝试本地导入
        if self.import_from_local_parquet(symbol):
            return True
            
        # 2. 降级到 AKShare 在线下载
        print(f"Fallback to AKShare download for {symbol}...")
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

    def load_daily_data(self, symbol: str) -> pd.DataFrame:
        """
        从分钟数据聚合出日线数据 (用于相似度搜索等)
        """
        # 1. 加载所有分钟数据 (只取需要的列以加速)
        conn = sqlite3.connect(self.db_path)
        # 假设 timestamp 格式 YYYY-MM-DD HH:MM:SS
        # 我们可以直接在 SQL 里做部分聚合，或者加载后 Pandas 聚合
        # Pandas 聚合通常更灵活
        df = pd.read_sql_query(
            "SELECT timestamp, open, high, low, close, volume FROM etf_min_1m WHERE symbol = ? ORDER BY timestamp", 
            conn, 
            params=(symbol,)
        )
        conn.close()
        
        if df.empty:
            return pd.DataFrame()
            
        # 2. 转换时间
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
        
        # 3. 聚合
        daily_df = df.groupby('date').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()
        
        # date 转 datetime (为了后续索引统一)
        daily_df['date'] = pd.to_datetime(daily_df['date'])
        
        return daily_df
