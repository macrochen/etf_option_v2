import sys
import os
# 添加项目根目录到 path 以便导入模块
sys.path.append(os.getcwd())

from db.market_db import MarketDatabase
import logging

logging.basicConfig(level=logging.INFO)

def migrate():
    print("Checking database schema for index_valuation_history...")
    db = MarketDatabase()
    
    # 检查列是否存在
    # pragma table_info(table_name)
    rows = db.db.fetch_all("PRAGMA table_info(index_valuation_history)")
    columns = [row[1] for row in rows]
    print(f"Current columns: {columns}")
    
    if 'pe_rank' not in columns:
        print("Adding pe_rank column...")
        try:
            db.db.execute("ALTER TABLE index_valuation_history ADD COLUMN pe_rank REAL")
            print("pe_rank added.")
        except Exception as e:
            print(f"Error adding pe_rank: {e}")
            
    if 'pb_rank' not in columns:
        print("Adding pb_rank column...")
        try:
            db.db.execute("ALTER TABLE index_valuation_history ADD COLUMN pb_rank REAL")
            print("pb_rank added.")
        except Exception as e:
            print(f"Error adding pb_rank: {e}")
            
    print("Migration check complete.")

if __name__ == "__main__":
    migrate()
