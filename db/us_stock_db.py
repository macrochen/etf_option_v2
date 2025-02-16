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
                market_type VARCHAR(10),
                stock_name VARCHAR(100),  
                date DATE,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                adj_close REAL,
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
        
    def save_stock_data(self, stock_code: str, date: str, open_price: float, high_price: float, 
                       low_price: float, close_price: float, adj_close: float, market_type: str = 'US',
                       stock_name: str = None):  # 新增股票名称参数
        """保存股票数据
        
        Args:
            stock_code: 股票代码
            date: 日期
            open_price: 开盘价
            high_price: 最高价
            low_price: 最低价
            close_price: 收盘价
            adj_close: 复权收盘价
            market_type: 市场类型（US:美股, HK:港股），默认为US
            stock_name: 股票名称，默认为None
        """
        stock_code = stock_code.upper()
        exists = self.db.fetch_one(
            'SELECT COUNT(*) FROM stock_prices WHERE stock_code = ? AND market_type = ? AND date = ?', 
            (stock_code, market_type, date)
        )
        if exists and exists[0] > 0:
            print(f"{market_type} 市场的 {stock_code} 在 {date} 的数据已经存在")
            return
        
        self.db.execute('''
            INSERT INTO stock_prices (stock_code, market_type, stock_name, date, open_price, high_price, 
                                    low_price, close_price, adj_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (stock_code, market_type, stock_name, date, open_price, high_price, low_price, close_price, adj_close))

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

    def get_stock_prices(self, stock_code: str, market_type: str = 'US'):
        """获取指定股票的所有价格数据
        
        Args:
            stock_code: 股票代码
            market_type: 市场类型（US:美股, HK:港股），默认为US
            
        Returns:
            list: 包含日期和价格数据的列表，按日期升序排序
        """
        stock_code = stock_code.upper()
        return self.db.fetch_all('''
            SELECT date, close_price
            FROM stock_prices 
            WHERE stock_code = ? AND market_type = ?
            AND date >= date('now', '-3 years')
            ORDER BY date ASC
        ''', (stock_code, market_type))
    

    def get_stock_list(self):
        """获取已下载的股票列表"""
        stocks = self.db.fetch_all('''
            SELECT DISTINCT stock_code, market_type, stock_name 
            FROM stock_prices 
            ORDER BY stock_code
        ''')
        
        stock_list = []
        for stock in stocks:
            stock_code = stock[0]
            market_type = stock[1]
            stock_name = stock[2]
            
            # 获取最新的下载时间
            latest_date = self.db.fetch_one(
                'SELECT MAX(date) FROM stock_prices WHERE stock_code = ? AND market_type = ?', 
                (stock_code, market_type)
            )
            download_time = latest_date[0] if latest_date else None
            
            # 获取波动率数据
            volatility_data = self.db.fetch_one('SELECT monthly_stats FROM stock_volatility_stats WHERE stock_code = ?', (stock_code,))
            volatility = json.loads(volatility_data[0]) if volatility_data else None
            
            stock_list.append({
                "stock_code": stock_code,
                "market_type": market_type,
                "stock_name": stock_name,
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