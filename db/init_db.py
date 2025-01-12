from database import Database
from config import DB_CONFIG
import os

def init_database():
    """初始化数据库"""
    db = Database(DB_CONFIG['backtest_schemes']['path'])
    
    # 执行建表SQL
    db.execute('''
        CREATE TABLE IF NOT EXISTS backtest_schemes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE,
            params TEXT NOT NULL,
            results TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    ''')
    
    print(f"数据库初始化完成: {DB_CONFIG['backtest_schemes']['path']}")

if __name__ == '__main__':
    init_database() 