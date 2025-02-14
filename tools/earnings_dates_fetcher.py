#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Earnings Dates Fetcher

用途：
1. 创建market_data.db数据库中的earnings_dates表
2. 从Alpha Vantage获取美股财报日期数据
3. 将数据保存到数据库中

使用方法：
python tools/earnings_dates_fetcher.py
"""

import sqlite3
from pathlib import Path
import pandas as pd
import requests
from datetime import datetime
import logging
import traceback

class EarningsDatesFetcher:
    """财报日期获取器"""
    
    def __init__(self, db_path=None):
        """初始化获取器"""
        if db_path is None:
            # 默认数据库路径
            self.db_path = Path(__file__).parent.parent / 'db' / 'us_stock.db'
        else:
            self.db_path = db_path
        self.api_key = "OZE4L077PH84CBU7"

    @classmethod
    def create(cls):
        """工厂方法，创建一个默认配置的获取器"""
        return cls()

    def download_earnings(self, stock_code: str, market_type: str = 'US') -> tuple[bool, str, int]:
        """
        下载并保存股票的财报数据
        
        Args:
            stock_code: 股票代码
            market_type: 市场类型（目前只支持US）
            
        Returns:
            tuple: (是否成功, 消息, 数据条数)
        """
        if market_type != 'US':
            return False, '目前只支持美股财报数据下载', 0
            
        try:
            # 获取财报数据
            earnings_df = self.get_earnings_dates(stock_code)
            
            if earnings_df is None:
                return False, f'未找到 {stock_code} 的财报数据', 0
                
            # 保存财报数据
            self.save_earnings_dates(stock_code, earnings_df)
            
            return True, f'成功下载并保存 {stock_code} 的财报数据', len(earnings_df)
            
        except Exception as e:
            logging.error(f"下载财报数据时出错: {e}\n{traceback.format_exc()}")
            return False, f'下载财报数据失败: {str(e)}', 0

    def create_tables(self):
        """创建earnings_dates表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS earnings_dates (
                    stock_code VARCHAR(10),
                    fiscal_date_ending DATE,
                    reported_date DATE,
                    reported_eps REAL,
                    estimated_eps REAL,
                    surprise REAL,
                    surprise_percentage REAL,
                    report_time VARCHAR(20),
                    create_date DATE,
                    PRIMARY KEY (stock_code, fiscal_date_ending)
                )
            """)
            conn.commit()

    def get_earnings_dates(self, symbol):
        """从Alpha Vantage获取财报日期"""
        url = f"https://www.alphavantage.co/query?function=EARNINGS&symbol={symbol}&apikey={self.api_key}"
        try:
            response = requests.get(url)
            data = response.json()
            
            if 'quarterlyEarnings' not in data:
                print(f"未找到 {symbol} 的财报数据")
                return None
            
            # 将季度财报数据转换为DataFrame
            quarterly_earnings = pd.DataFrame(data['quarterlyEarnings'])
            quarterly_earnings['fiscalDateEnding'] = pd.to_datetime(quarterly_earnings['fiscalDateEnding'])
            quarterly_earnings['reportedDate'] = pd.to_datetime(quarterly_earnings['reportedDate'])
            
            # 转换数值类型的列
            numeric_columns = ['reportedEPS', 'estimatedEPS', 'surprise', 'surprisePercentage']
            for col in numeric_columns:
                quarterly_earnings[col] = pd.to_numeric(quarterly_earnings[col], errors='coerce')
            
            # 只保留最近10年的数据
            filtered_df = quarterly_earnings[
                quarterly_earnings['fiscalDateEnding'] >= pd.Timestamp.now() - pd.DateOffset(years=10)
            ]
            
            if filtered_df.empty:
                print(f"{symbol} 没有最近10年的财报数据")
                return None
                
            return filtered_df
            
        except Exception as e:
            import traceback
            print(f"获取 {symbol} 的财报数据时出错:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            print("详细堆栈:")
            print(traceback.format_exc())
            return None

    def save_earnings_dates(self, symbol, earnings_df):
        """保存财报日期到数据库"""
        if earnings_df is None or earnings_df.empty:
            return
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                today = datetime.now().date()
                data = [(
                    symbol,
                    row['fiscalDateEnding'].date(),
                    row['reportedDate'].date(),
                    row['reportedEPS'],
                    row['estimatedEPS'],
                    row['surprise'],
                    row['surprisePercentage'],
                    row['reportTime'],
                    today
                ) for _, row in earnings_df.iterrows()]
                
                cursor.executemany("""
                    REPLACE INTO earnings_dates (
                        stock_code, fiscal_date_ending, reported_date,
                        reported_eps, estimated_eps, surprise,
                        surprise_percentage, report_time, create_date
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, data)
                
                conn.commit()
                print(f"已保存 {symbol} 的 {len(data)} 条财报数据")
        except Exception as e:
            import traceback
            print(f"保存 {symbol} 的财报数据时出错:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            print("详细堆栈:")
            print(traceback.format_exc())

    def get_earnings_volatility(self, stock_code: str) -> list:
        """获取股票财报日期前后的价格波动数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            list: 包含财报日期和价格数据的列表，格式为：
                 [(fiscal_date_ending, reported_date, report_time, 
                   pre_close, trade_date, open_price, close_price), ...]
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 对于盘前公布的财报，使用当天作为交易日
                # 对于盘后公布的财报，使用下一个交易日作为交易日
                cursor.execute("""
                    WITH trade_dates AS (
                        -- 获取每个财报日期后的第一个有效交易日
                        SELECT e.stock_code, e.reported_date, e.report_time,
                               MIN(s.date) as trade_date
                        FROM earnings_dates e
                        LEFT JOIN stock_prices s ON s.stock_code = e.stock_code 
                            AND s.market_type = 'US'
                            AND (
                                (e.report_time = 'pre-market' AND s.date = e.reported_date)
                                OR 
                                (e.report_time = 'post-market' AND s.date > e.reported_date)
                            )
                        WHERE e.stock_code = ?
                        GROUP BY e.stock_code, e.reported_date, e.report_time
                    )
                    SELECT 
                        e.fiscal_date_ending,
                        e.reported_date,
                        e.report_time,
                        pre.close_price as pre_close,
                        td.trade_date,
                        curr.open_price as open_price,
                        curr.close_price as close_price,
                        e.reported_eps,
                        e.estimated_eps
                    FROM earnings_dates e
                    JOIN trade_dates td ON e.stock_code = td.stock_code 
                        AND e.reported_date = td.reported_date
                        AND e.report_time = td.report_time
                    -- 获取交易日前一个交易日的收盘价
                    LEFT JOIN stock_prices pre ON e.stock_code = pre.stock_code
                        AND pre.market_type = 'US'
                        AND pre.date = (
                            SELECT MAX(date) 
                            FROM stock_prices 
                            WHERE stock_code = e.stock_code
                                AND market_type = 'US'
                                AND date < td.trade_date
                        )
                    -- 获取交易日的开盘价和收盘价
                    LEFT JOIN stock_prices curr ON e.stock_code = curr.stock_code
                        AND curr.market_type = 'US'
                        AND curr.date = td.trade_date
                    WHERE e.stock_code = ?
                        AND pre.close_price IS NOT NULL
                        AND curr.open_price IS NOT NULL
                        AND curr.close_price IS NOT NULL
                    ORDER BY e.reported_date DESC
                """, (stock_code, stock_code))
                
                return cursor.fetchall()
                
        except Exception as e:
            logging.error(f"获取财报波动数据时出错: {e}\n{traceback.format_exc()}")
            return []

def main():
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    db_path = project_root / 'db' / 'us_stock.db'  # 修改数据库路径
    
    # 确保db目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    fetcher = EarningsDatesFetcher(db_path)
    print("正在创建数据库表...")
    fetcher.create_tables()
    print("数据库表创建完成")
    
    # 这里可以添加你要获取的股票代码列表
    # symbols = ['AAPL', 'MSFT', 'GOOGL']  # 示例股票
    symbols = ['AAPL']  # 示例股票
    
    for symbol in symbols:
        print(f"正在获取 {symbol} 的财报日期...")
        earnings_df = fetcher.get_earnings_dates(symbol)
        fetcher.save_earnings_dates(symbol, earnings_df)

if __name__ == '__main__':
    main()