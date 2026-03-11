import glob
import logging
import os
import sqlite3

import akshare as ak
import pandas as pd


class MinDataLoader:
    def __init__(self, db_path='db/market_data_min.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
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
            '''
        )
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_time ON etf_min_1m (symbol, timestamp)')
        conn.commit()
        conn.close()

    def _upsert_minute_df(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0

        data_to_insert = df[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']].values.tolist()
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            '''
            INSERT OR REPLACE INTO etf_min_1m (symbol, timestamp, open, high, low, close, volume, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            data_to_insert,
        )
        conn.commit()
        conn.close()
        return len(data_to_insert)

    def _normalize_parquet_df(self, df: pd.DataFrame, symbol: str, file_path: str) -> pd.DataFrame:
        if df.empty:
            raise ValueError(f'Parquet file {file_path} is empty.')

        df = df.reset_index()

        if 'adj_factor' in df.columns:
            latest_adj = df['adj_factor'].iloc[-1]
            if latest_adj != 0:
                mult = df['adj_factor'] / latest_adj
                px_cols = ['open', 'high', 'low', 'close']
                df[px_cols] = df[px_cols].mul(mult, axis=0).round(3)

        if 'trade_time' not in df.columns:
            raise ValueError(f"Missing 'trade_time' column in {file_path}")

        df['timestamp'] = pd.to_datetime(df['trade_time']).dt.strftime('%Y-%m-%d %H:%M:%S')
        df['symbol'] = symbol

        if 'vol' in df.columns:
            df['volume'] = df['vol']

        required_cols = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f'Missing columns in {file_path}: {missing_cols}')

        return df[required_cols].sort_values('timestamp').drop_duplicates(subset=['symbol', 'timestamp'], keep='last')

    def _normalize_akshare_df(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if df.empty:
            raise ValueError(f'AKShare returned empty data for {symbol}.')

        df = df.rename(
            columns={
                '时间': 'timestamp',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume',
                '成交额': 'amount',
            }
        )
        df['symbol'] = symbol
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

        mask = (df['open'] <= 0) & (df['close'] > 0)
        if mask.any():
            df.loc[mask, 'open'] = df.loc[mask, 'close']
            df.loc[(df['high'] <= 0) & (df['close'] > 0), 'high'] = df.loc[(df['high'] <= 0) & (df['close'] > 0), 'close']
            df.loc[(df['low'] <= 0) & (df['close'] > 0), 'low'] = df.loc[(df['low'] <= 0) & (df['close'] > 0), 'close']

        required_cols = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']
        return df[required_cols].sort_values('timestamp').drop_duplicates(subset=['symbol', 'timestamp'], keep='last')

    def _filter_new_rows(self, df: pd.DataFrame, latest_timestamp: str | None) -> pd.DataFrame:
        if df.empty or not latest_timestamp:
            return df
        return df[df['timestamp'] > latest_timestamp].copy()

    def load_data(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        加载本地分钟数据。
        start_date, end_date format: 'YYYY-MM-DD'
        """
        conn = sqlite3.connect(self.db_path)
        query = 'SELECT * FROM etf_min_1m WHERE symbol = ?'
        params = [symbol]

        if start_date:
            query += ' AND timestamp >= ?'
            params.append(f'{start_date} 09:30:00')

        if end_date:
            query += ' AND timestamp <= ?'
            params.append(f'{end_date} 15:00:00')

        query += ' ORDER BY timestamp ASC'

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

            info_db_path = 'db/market_data.db'
            if os.path.exists(info_db_path):
                conn.execute(f"ATTACH DATABASE '{info_db_path}' AS info_db")
                query = '''
                    SELECT
                        t1.symbol,
                        COALESCE(t2.fund_name, t1.symbol) as name,
                        MIN(t1.timestamp) as start_date,
                        MAX(t1.timestamp) as end_date
                    FROM etf_min_1m t1
                    LEFT JOIN info_db.fund_info t2 ON t1.symbol = t2.fund_code
                    GROUP BY t1.symbol
                    ORDER BY t1.symbol
                '''
            else:
                query = '''
                    SELECT
                        symbol,
                        symbol as name,
                        MIN(timestamp) as start_date,
                        MAX(timestamp) as end_date
                    FROM etf_min_1m
                    GROUP BY symbol
                    ORDER BY symbol
                '''

            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            data = []
            for r in rows:
                start = r[2].split(' ')[0] if r[2] else ''
                end = r[3].split(' ')[0] if r[3] else ''
                data.append({'code': r[0], 'name': r[1], 'start_date': start, 'end_date': end})

            return data
        except Exception as e:
            print(f'Error getting ETF list: {e}')
            return []

    def import_from_local_parquet(self, symbol: str, parquet_dir='data/etf_1min') -> dict:
        """
        优先从本地 Parquet 文件导入分钟数据。
        返回导入明细，供 UI 展示和后续 AKShare 补齐逻辑使用。
        """
        result = {
            'success': False,
            'source': 'parquet',
            'file_path': None,
            'rows_read': 0,
            'rows_written': 0,
            'range': None,
            'error': None,
        }
        logging.info(f'Attempting to import local parquet for {symbol} from {parquet_dir}...')

        try:
            pattern = os.path.join(parquet_dir, f'*{symbol}*.parquet')
            files = glob.glob(pattern)
            if not files:
                result['error'] = f'No parquet file found for {symbol} matching {pattern}'
                logging.warning(result['error'])
                return result

            file_path = max(files, key=os.path.getmtime)
            result['file_path'] = file_path
            logging.info(f'Found parquet file: {file_path}')

            raw_df = pd.read_parquet(file_path)
            result['rows_read'] = len(raw_df)
            normalized = self._normalize_parquet_df(raw_df, symbol, file_path)
            result['rows_written'] = self._upsert_minute_df(normalized)
            result['range'] = {
                'start': normalized['timestamp'].min(),
                'end': normalized['timestamp'].max(),
            }
            result['success'] = True
            logging.info(f'Successfully imported {result["rows_written"]} records from {file_path}.')
            return result
        except Exception as e:
            result['error'] = str(e)
            logging.error(f'Error importing from local parquet for {symbol}: {e}', exc_info=True)
            return result

    def import_from_akshare(self, symbol: str, latest_timestamp: str | None = None) -> dict:
        result = {
            'success': False,
            'source': 'akshare',
            'rows_read': 0,
            'rows_written': 0,
            'rows_after_filter': 0,
            'range': None,
            'latest_timestamp_before_sync': latest_timestamp,
            'error': None,
        }
        logging.info(f'Fetching minute data for {symbol} from AKShare...')

        try:
            raw_df = ak.fund_etf_hist_min_em(symbol=symbol, period='1', adjust='qfq')
            result['rows_read'] = len(raw_df)
            normalized = self._normalize_akshare_df(raw_df, symbol)
            if not normalized.empty:
                result['range'] = {
                    'start': normalized['timestamp'].min(),
                    'end': normalized['timestamp'].max(),
                }

            filtered = self._filter_new_rows(normalized, latest_timestamp)
            result['rows_after_filter'] = len(filtered)
            result['rows_written'] = self._upsert_minute_df(filtered)
            result['success'] = True
            logging.info(
                'AKShare sync finished for %s: read=%s, after_filter=%s, written=%s',
                symbol,
                result['rows_read'],
                result['rows_after_filter'],
                result['rows_written'],
            )
            return result
        except Exception as e:
            result['error'] = str(e)
            logging.error(f'Error updating minute data for {symbol}: {e}', exc_info=True)
            return result

    def update_data(self, symbol: str) -> dict:
        """
        更新数据策略：
        1. 先导入本地 parquet 全量历史。
        2. 再基于本地最新时间戳使用 AKShare 补齐最新缺口。
        """
        logging.info(f'Start updating data for {symbol}...')
        parquet_result = self.import_from_local_parquet(symbol)

        latest_local_ts = None
        if parquet_result.get('success') and parquet_result.get('range'):
            latest_local_ts = parquet_result['range']['end']
        else:
            current_range = self.get_available_range(symbol)
            if current_range:
                latest_local_ts = current_range['end']

        akshare_result = self.import_from_akshare(symbol, latest_local_ts)
        final_range = self.get_available_range(symbol)

        success = bool((parquet_result.get('success') or akshare_result.get('success')) and final_range)
        used_sources = []
        if parquet_result.get('success'):
            used_sources.append('parquet')
        if akshare_result.get('success'):
            used_sources.append('akshare')

        warnings = []
        if parquet_result.get('error'):
            warnings.append(parquet_result['error'])
        if akshare_result.get('error'):
            warnings.append(akshare_result['error'])
        elif akshare_result.get('success') and akshare_result.get('rows_written', 0) == 0 and latest_local_ts:
            warnings.append('AKShare 未补到比本地更晚的数据，当前库中分钟数据已是 AKShare 可提供的最新范围。')

        return {
            'success': success,
            'symbol': symbol,
            'used_sources': used_sources,
            'parquet': parquet_result,
            'akshare': akshare_result,
            'info': final_range,
            'warnings': warnings,
            'message': self._build_sync_message(parquet_result, akshare_result, final_range),
        }

    def _build_sync_message(self, parquet_result: dict, akshare_result: dict, final_range: dict | None) -> str:
        parts = []
        if parquet_result.get('success'):
            parts.append(f"本地 parquet 导入 {parquet_result['rows_written']} 条")
        if akshare_result.get('success'):
            parts.append(f"AKShare 补充 {akshare_result['rows_written']} 条最新分钟数据")
        if final_range:
            parts.append(f"当前本地范围 {final_range['start']} ~ {final_range['end']}")
        return '；'.join(parts) if parts else '未能同步分钟数据'

    def get_available_range(self, symbol: str):
        """获取本地数据的可用时间范围"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM etf_min_1m WHERE symbol = ?', (symbol,))
        res = cursor.fetchone()
        conn.close()
        if res and res[0]:
            return {'start': res[0], 'end': res[1], 'count': res[2]}
        return None

    def load_daily_data(self, symbol: str) -> pd.DataFrame:
        """
        从分钟数据聚合出日线数据 (用于相似度搜索等)
        """
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query(
            'SELECT timestamp, open, high, low, close, volume FROM etf_min_1m WHERE symbol = ? ORDER BY timestamp',
            conn,
            params=(symbol,),
        )
        conn.close()

        if df.empty:
            return pd.DataFrame()

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date

        daily_df = df.groupby('date').agg(
            {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
            }
        ).reset_index()

        daily_df['date'] = pd.to_datetime(daily_df['date'])
        return daily_df
