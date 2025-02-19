#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Previous Close Price Manager

用途：
1. 创建和管理上一个交易日价格数据表
2. 提供接口用于保存和查询价格数据

使用方法：
python tools/prev_close_price_manager.py
"""

import sqlite3
from pathlib import Path
import logging
import traceback
from datetime import datetime

class PrevClosePriceManager:
    """上一个交易日价格数据管理器"""
    
    def __init__(self, db_path=None):
        """初始化管理器"""
        if db_path is None:
            # 默认数据库路径
            self.db_path = Path(__file__).parent.parent / 'db' / 'us_stock.db'
        else:
            self.db_path = db_path
            
    def create_table(self):
        """创建价格数据表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prev_close_prices (
                    symbol VARCHAR(20),           -- 股票代码
                    market VARCHAR(10),           -- 市场（US/HK）
                    prev_close_date DATE,         -- 上一个交易日日期
                    prev_close_price DECIMAL(10,4), -- 上一个交易日收盘价
                    update_time TIMESTAMP,        -- 数据更新时间
                    PRIMARY KEY (symbol, market)
                )
            """)
            conn.commit()
            
    def save_price(self, symbol: str, market: str, prev_close_date: str, prev_close_price: float):
        """保存价格数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO prev_close_prices 
                    (symbol, market, prev_close_date, prev_close_price, update_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (symbol, market, prev_close_date, prev_close_price, datetime.now()))
                
                conn.commit()
                return True
        except Exception as e:
            logging.error(
                f"保存价格数据失败. Context: {{'symbol': '{symbol}', 'market': '{market}'}}\n"
                f"Error message: {str(e)}\n"
                f"Stacktrace:\n{traceback.format_exc()}"
            )
            return False
            
    def get_price(self, symbol: str, market: str) -> tuple[str, float]:
        """获取价格数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT prev_close_date, prev_close_price
                    FROM prev_close_prices
                    WHERE symbol = ? AND market = ?
                """, (symbol, market))
                
                result = cursor.fetchone()
                return result if result else (None, None)
                
        except Exception as e:
            logging.error(
                f"获取价格数据失败. Context: {{'symbol': '{symbol}', 'market': '{market}'}}\n"
                f"Error message: {str(e)}\n"
                f"Stacktrace:\n{traceback.format_exc()}"
            )
            return None, None

def main():
    """主函数"""
    manager = PrevClosePriceManager()
    manager.create_table()
    print("价格数据表创建成功")

if __name__ == "__main__":
    main()