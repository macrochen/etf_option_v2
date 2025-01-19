#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
US Stock Database Builder

用途：
1. 创建一个SQLite数据库us_stock.db
2. 创建表格以存放美股股票的历史价格数据
3. 创建表格以分析美股股票的历史波动率

使用方法：
python tools/us_stock_db_builder.py
"""

import sqlite3
from pathlib import Path

class USStockDBBuilder:
    """美股数据库构建器"""

    def __init__(self, db_path):
        """初始化数据库构建器"""
        self.db_path = db_path

    def create_tables(self):
        """创建表格"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建历史价格数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_prices (
                    stock_code VARCHAR(10),
                    date DATE,
                    open_price REAL,
                    close_price REAL,
                    PRIMARY KEY (stock_code, date)
                )
            """)

            # 创建波动率统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_volatility_stats (
                    stock_code VARCHAR(10),
                    calc_date DATE,
                    monthly_stats TEXT,
                    weekly_stats TEXT,
                    PRIMARY KEY (stock_code, calc_date)
                )
            """)
            conn.commit()

def main():
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    db_path = project_root / 'db' / 'us_stock.db'
    
    builder = USStockDBBuilder(db_path)
    print("正在创建数据库表...")
    builder.create_tables()
    print("数据库表创建完成")

if __name__ == '__main__':
    main() 