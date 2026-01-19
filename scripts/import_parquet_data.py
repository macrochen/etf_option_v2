import os
import pandas as pd
import sqlite3
import glob
from tqdm import tqdm

DB_PATH = 'db/market_data_min.db'
DATA_DIR = 'data/etf_1min'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 确保表结构存在
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

def process_file(file_path):
    filename = os.path.basename(file_path)
    # 文件名格式: 510300.SH.parquet -> 提取 510300
    symbol = filename.split('.')[0]
    
    try:
        df = pd.read_parquet(file_path)
        if df.empty:
            return None
            
        # Parquet 可能使用 MultiIndex (trade_date, trade_time)
        df = df.reset_index()
            
        # 1. 前复权处理 (Forward Adjust)
        # 逻辑参考: mult = adj_factor / latest_adj
        # px = px * mult
        if 'adj_factor' in df.columns:
            latest_adj = df['adj_factor'].iloc[-1]
            if latest_adj != 0:
                mult = df['adj_factor'] / latest_adj
                px_cols = ['open', 'high', 'low', 'close']
                df[px_cols] = df[px_cols].mul(mult, axis=0).round(3) # 保留3位小数更精确
        
        # 2. 格式转换
        # trade_time 是 datetime64[ns]，需要转为 YYYY-MM-DD HH:MM:00 字符串
        if 'trade_time' in df.columns:
            df['timestamp'] = df['trade_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # 调试：打印列名
            print(f"Columns in {filename}: {df.columns.tolist()}")
            return None
        
        # 构造插入数据
        # 目标列: symbol, timestamp, open, high, low, close, volume, amount
        df['symbol'] = symbol
        
        # 选取并重命名列 (volume 对应 vol)
        data = df[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'vol', 'amount']].values.tolist()
        return data
        
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return None

def main():
    init_db()
    
    # 测试阶段：只导入 510300
    target_file = os.path.join(DATA_DIR, '510300.SH.parquet')
    if not os.path.exists(target_file):
        print(f"File not found: {target_file}")
        return

    parquet_files = [target_file]
    print(f"Found {len(parquet_files)} parquet files.")
    
    conn = sqlite3.connect(DB_PATH)
    
    for file_path in tqdm(parquet_files):
        data = process_file(file_path)
        if data:
            # 批量插入
            conn.executemany('''
                INSERT OR REPLACE INTO etf_min_1m 
                (symbol, timestamp, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
            conn.commit()
            
    conn.close()
    print("All data imported successfully!")

if __name__ == "__main__":
    main()
