from datetime import datetime
import sqlite3
import json
from .config import US_STOCK_DB
from .database import Database  # 引入Database类

class USStockDatabase:
    def __init__(self, db_path: str = US_STOCK_DB):
        """初始化美股数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db = Database(db_path)  # 使用Database类
        self._init_table()

    def _init_table(self):
        """初始化数据表"""
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS stock_prices (
                stock_code VARCHAR(10),
                date DATE,
                open_price REAL,
                close_price REAL,
                PRIMARY KEY (stock_code, date)
            )
        ''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS stock_volatility_stats (
                stock_code VARCHAR(10),
                calc_date DATE,
                monthly_stats TEXT,
                weekly_stats TEXT,
                PRIMARY KEY (stock_code, calc_date)
            )
        ''')
        
    def save_stock_data(self, stock_code: str, date: str, open_price: float, close_price: float):
        """保存股票数据"""
        stock_code = stock_code.upper()  # 将股票代码转换为大写
        exists = self.db.fetch_one('SELECT COUNT(*) FROM stock_prices WHERE stock_code = ? AND date = ?', (stock_code, date))
        if exists and exists[0] > 0:
            print("数据已经存在")
            return
        
        self.db.execute('''
            INSERT INTO stock_prices (stock_code, date, open_price, close_price)
            VALUES (?, ?, ?, ?)
        ''', (stock_code, date, open_price, close_price))

    def save_volatility_stats(self, stock_code: str, calc_date: str, monthly_stats: dict, weekly_stats: dict):
        """保存波动率统计数据"""
        stock_code = stock_code.upper()  # 将股票代码转换为大写
        exists = self.db.fetch_one('SELECT COUNT(*) FROM stock_volatility_stats WHERE stock_code = ? AND calc_date = ?', (stock_code, calc_date))
        if exists and exists[0] > 0:
            print("波动率数据已经存在")
            return
        
        self.db.execute('''
            INSERT INTO stock_volatility_stats (stock_code, calc_date, monthly_stats, weekly_stats)
            VALUES (?, ?, ?, ?)
        ''', (stock_code, calc_date, json.dumps(monthly_stats), json.dumps(weekly_stats)))

    def get_stock_list(self):
        """获取已下载的股票列表"""
        stocks = self.db.fetch_all('SELECT DISTINCT stock_code FROM stock_prices')
        
        stock_list = []
        for stock in stocks:
            stock_code = stock[0]
            # 获取最新的下载时间
            latest_date = self.db.fetch_one('SELECT MAX(date) FROM stock_prices WHERE stock_code = ?', (stock_code,))
            download_time = latest_date[0] if latest_date else None
            
            # 获取波动率数据
            volatility_data = self.db.fetch_one('SELECT monthly_stats FROM stock_volatility_stats WHERE stock_code = ?', (stock_code,))
            volatility = json.loads(volatility_data[0]) if volatility_data else None
            
            stock_list.append({
                "stock_code": stock_code,
                "download_time": download_time,
                "volatility": volatility
            })
        
        return stock_list

    def get_volatility(self, stock_code):
        """获取指定股票的波动率数据"""
        volatility_data = self.db.fetch_one('SELECT monthly_stats, weekly_stats FROM stock_volatility_stats WHERE stock_code = ?', (stock_code,))
        if volatility_data:
            monthly_stats = json.loads(volatility_data[0])  # 解析月度波动数据
            weekly_stats = json.loads(volatility_data[1])   # 解析周度波动数据
            return {
                'monthly_stats': monthly_stats,
                'weekly_stats': weekly_stats
            }
        else:
            return None 