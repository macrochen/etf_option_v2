from datetime import datetime, timedelta
import random
import sqlite3
import json
import logging
from typing import Optional

import pytz

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
        
        # 添加上一个交易日收盘价表
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS prev_close_prices (
                symbol VARCHAR(20),
                market VARCHAR(10),
                prev_close_date DATE,
                prev_close_price DECIMAL(10,4),
                update_time TIMESTAMP,
                PRIMARY KEY (symbol, market)
            )
        ''')
        
        # 添加期权delta缓存表
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS option_delta_cache (
                option_symbol VARCHAR(50) PRIMARY KEY,
                delta FLOAT,
                update_time TIMESTAMP,
                next_update_time TIMESTAMP
            )
        ''')

        # 添加模拟交易持仓表
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS sim_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(50) NOT NULL,        -- 股票代码或期权代码
                market VARCHAR(10) NOT NULL,        -- US/HK
                position_type VARCHAR(10) NOT NULL, -- stock/option
                direction VARCHAR(10) NOT NULL,     -- long/short
                quantity INTEGER NOT NULL,
                price DECIMAL(10,4) NOT NULL,
                open_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- 期权特有字段
                underlying VARCHAR(50),             -- 期权标的
                expiry DATE,                        -- 到期日
                strike DECIMAL(10,4),              -- 行权价
                option_type VARCHAR(10)             -- call/put
            )
        ''')

    def upsert_prev_close_price(self, symbol: str, market: str, prev_close_price: float) -> bool:
        """插入或更新股票前一交易日收盘价
        
        Args:
            symbol: 股票代码
            market: 市场类型(US/HK)
            prev_close_price: 前一交易日收盘价
            
        Returns:
            bool: 操作是否成功
        """
        try:
            prev_trading_day = self.get_prev_trading_day()
            
            # 检查是否已存在记录
            existing = self.db.fetch_one('''
                SELECT prev_close_price 
                FROM prev_close_prices 
                WHERE symbol = ? AND market = ? 
            ''', (symbol, market))
            
            if existing:
                result = self.db.execute('''
                    UPDATE prev_close_prices 
                    SET prev_close_price = ?, 
                        prev_close_date = ?,
                        update_time = datetime('now')
                    WHERE symbol = ? AND market = ?
                ''', (prev_close_price, prev_trading_day, symbol, market))
                if result.rowcount == 0:
                    logging.error(
                        f"更新前收价失败 - 股票: {symbol}, 市场: {market}\n"
                        f"前收价: {prev_close_price}\n"
                        f"交易日期: {prev_trading_day}\n"
                        f"当前记录: {existing}"
                    )
                    return False
            else:
                # 如果不存在，则插入新记录
                result = self.db.execute('''
                    INSERT INTO prev_close_prices 
                    (symbol, market, prev_close_date, prev_close_price, update_time)
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', (symbol, market, prev_trading_day, prev_close_price))
                if result.rowcount == 0:
                    logging.error(
                        f"插入前收价失败 - 股票: {symbol}, 市场: {market}\n"
                        f"前收价: {prev_close_price}\n"
                        f"交易日期: {prev_trading_day}"
                    )
                    return False
            return True
            
        except Exception as e:
            logging.error(f"更新{symbol}的前收价失败: {str(e)}")
            return False
            

    def get_prev_trading_day(self, date: datetime = None) -> datetime:
        """获取上一个交易日（基于美东时间）
        
        Args:
            date: 指定日期，默认为当前美东时间
            
        Returns:
            datetime: 上一个交易日
        """
        if date is None:
            # 获取当前美东时间
            eastern = pytz.timezone('US/Eastern')
            date = datetime.now(pytz.timezone('Asia/Shanghai')).astimezone(eastern)
            
        prev_day = date - timedelta(days=1)
        
        # 如果是周一或者前一天是周末，返回上周五
        if prev_day.weekday() >= 5:  # 5是周六，6是周日
            days_to_friday = prev_day.weekday() - 4  # 4是周五
            prev_day = prev_day - timedelta(days=days_to_friday)
            
        return prev_day.date()  # 只返回日期部分，不包含时间

    def get_symbols_without_prev_close(self, market_symbol_dict: dict) -> list[tuple[str, str]]:
        """获取没有前一交易日收盘价的股票列表
        
        Args:
            market_symbol_dict: 市场和股票代码的字典，格式为 {'US': ['AAPL', 'GOOGL'], 'HK': ['00700']}
            
        Returns:
            list[tuple]: 返回 (symbol, market) 元组的列表，表示需要获取前收价的股票
        """
        missing_symbols = []
        prev_trading_day = self.get_prev_trading_day()
        
        for market, symbols in market_symbol_dict.items():
            if not symbols:
                continue
                
            # 查询已有前收价的股票
            placeholders = ','.join(['?' for _ in symbols])
            query = f"""
                SELECT symbol 
                FROM prev_close_prices 
                WHERE market = ? 
                AND symbol IN ({placeholders})
                AND prev_close_date = ?
            """
            
            existing_symbols = set(row[0] for row in self.db.fetch_all(
                query, 
                (market, *symbols, prev_trading_day)
            ))
            
            # 找出没有前收价的股票
            missing_symbols.extend(
                (symbol, market) for symbol in symbols 
                if symbol not in existing_symbols
            )
            
        return missing_symbols

    def get_prev_close(self, symbol: str, market: str) -> float:
        """获取股票前一交易日收盘价
        
        Args:
            symbol: 股票代码
            market: 市场(US/HK)
            
        Returns:
            float: 前一交易日收盘价，如果不存在返回None
        """
        query = "SELECT prev_close FROM prev_close_prices WHERE symbol = ? AND market = ?"
        result = self.execute_query(query, (symbol, market))
        return result[0][0] if result else None
        

    def create_sim_position(self, position_data: dict) -> int:
        """创建模拟交易持仓
        
        Args:
            position_data: 持仓数据字典
        
        Returns:
            int: 新创建的持仓ID
        """
        if position_data['type'] == 'stock':
            query = '''
                INSERT INTO sim_positions 
                (symbol, market, position_type, direction, quantity, price)
                VALUES (?, ?, 'stock', ?, ?, ?)
            '''
            params = (
                position_data['symbol'],
                position_data['market'],
                position_data['direction'],
                position_data['quantity'],
                position_data['price']
            )
        else:  # option
            # 构建期权代码
            expiry = datetime.strptime(position_data['expiry'], '%Y-%m-%d')
            strike = float(position_data['strike'])
            option_symbol = f"{position_data['underlying']}{expiry.strftime('%y%m%d')}{position_data['optionType'][0].upper()}{int(strike*1000):08d}"
            
            query = '''
                INSERT INTO sim_positions 
                (symbol, market, position_type, direction, quantity, price,
                underlying, expiry, strike, option_type)
                VALUES (?, ?, 'option', ?, ?, ?, ?, ?, ?, ?)
            '''
            params = (
                option_symbol,
                position_data['market'],
                position_data['direction'],
                position_data['quantity'],
                position_data['price'],
                position_data['underlying'],
                position_data['expiry'],
                position_data['strike'],
                position_data['optionType']
            )
        
        cursor = self.db.execute(query, params)
        return cursor.lastrowid


    def close_sim_position(self, position_id: int) -> bool:
        """关闭模拟交易持仓
        
        Args:
            position_id: 持仓ID
        
        Returns:
            bool: 是否成功关闭
        """
        result = self.db.execute('''
            DELETE FROM sim_positions
            WHERE id = ?
        ''', (position_id,))
        
        return result.rowcount > 0

    def get_sim_positions(self) -> list:
        """获取所有模拟持仓"""
        return self.db.fetch_all('''
            SELECT * FROM sim_positions
            ORDER BY open_time DESC
        ''')

    def get_sim_position(self, position_id: int) -> Optional[dict]:
        """获取单个模拟持仓详情"""
        result = self.db.fetch_one('''
            SELECT * FROM sim_positions
            WHERE id = ?
        ''', (position_id,))
        
        if not result:
            return None
            
        columns = ['id', 'symbol', 'market', 'position_type', 'direction', 
                'quantity', 'price', 'open_time', 'underlying', 'expiry', 
                'strike', 'option_type']
        return dict(zip(columns, result))

    def get_cached_delta(self, option_symbol: str, ignore_expiry: bool = False) -> Optional[float]:
        """从缓存中获取期权delta值
        
        Args:
            option_symbol: 期权代码，例如 'NVDA250321C132000'
            ignore_expiry: 是否忽略过期时间，True表示即使缓存过期也返回值
            
        Returns:
            float: delta值，如果缓存不存在则返回None
        """
        result = self.db.fetch_one('''
            SELECT delta, next_update_time 
            FROM option_delta_cache 
            WHERE option_symbol = ?
        ''', (option_symbol,))
        
        if result:
            delta, next_update = result
            # 如果设置了忽略过期或者缓存未过期，返回delta值
            if ignore_expiry or datetime.now() < datetime.fromisoformat(next_update):
                return delta
            # 即使过期也返回缓存的值
            return delta
        return None

    def cache_delta(self, option_symbol: str, delta: float):
        """缓存期权delta值
        
        Args:
            option_symbol: 期权代码
            delta: delta值
        """
        # 随机延迟15-20分钟，避免所有期权同时更新
        next_update = datetime.now() + timedelta(minutes=15) + timedelta(seconds=random.randint(0, 300))
        
        self.db.execute('''
            INSERT OR REPLACE INTO option_delta_cache 
            (option_symbol, delta, update_time, next_update_time)
            VALUES (?, ?, datetime('now'), ?)
        ''', (option_symbol, delta, next_update.isoformat()))

    def get_expired_delta_options(self) -> list[str]:
        """获取需要更新delta值的期权列表
        
        Returns:
            list: 需要更新的期权代码列表
        """
        results = self.db.fetch_all('''
            SELECT option_symbol 
            FROM option_delta_cache 
            WHERE next_update_time < datetime('now')
        ''')
        
        return [row[0] for row in results]

    def batch_save_prev_close_prices(self, price_data_list: list):
        """批量保存上一个交易日收盘价
        
        Args:
            price_data_list: 价格数据列表，每个元素为字典，包含：
                           symbol: 股票代码
                           market: 市场类型
                           prev_close_date: 上一个交易日日期
                           prev_close_price: 上一个交易日收盘价
        """
        if not price_data_list:
            return
            
        self.db.execute_many('''
            INSERT OR REPLACE INTO prev_close_prices 
            (symbol, market, prev_close_date, prev_close_price, update_time)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', [(
            data['symbol'],
            data['market'],
            data['prev_close_date'],
            data['prev_close_price']
        ) for data in price_data_list])

    def batch_get_prev_close_prices(self, symbols: list, market: str) -> dict:
        """批量获取上一个交易日收盘价
        
        Args:
            symbols: 股票代码列表
            market: 市场类型（US/HK）
            
        Returns:
            dict: 以股票代码为key的字典，值为(prev_close_date, prev_close_price)元组
        """
        if not symbols:
            return {}
            
        results = self.db.fetch_all('''
            SELECT symbol, prev_close_date, prev_close_price
            FROM prev_close_prices
            WHERE symbol IN ({}) AND market = ?
        '''.format(','.join(['?'] * len(symbols))), (*symbols, market))
        
        return {row[0]: (row[1], row[2]) for row in results}

    def get_prev_close_price(self, symbol: str, market: str) -> tuple[str, float]:
        """获取单个股票的上一个交易日收盘价
        
        Args:
            symbol: 股票代码
            market: 市场类型（US/HK）
            
        Returns:
            tuple: (prev_close_date, prev_close_price)，如果没有数据返回(None, None)
        """
        result = self.db.fetch_one('''
            SELECT prev_close_date, prev_close_price
            FROM prev_close_prices
            WHERE symbol = ? AND market = ?
        ''', (symbol, market))
        
        return result if result else (None, None)

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
    
    def get_last_update_date(self, stock_code, market_type):
        """获取指定股票的最后更新日期"""
        try:
            result = self.db.fetch_one('''
                SELECT MAX(date) 
                FROM stock_prices 
                WHERE stock_code = ? AND market_type = ?
            ''', (stock_code, market_type))
            
            return datetime.strptime(result[0], '%Y-%m-%d').date() if result and result[0] else None
            
        except Exception as e:
            logging.error(f"获取最后更新日期时出错: {e}")
            return None
        
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