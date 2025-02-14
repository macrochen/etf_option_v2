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
import requests
import time
import logging

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

    def update_hk_stock_names(self, stock_codes):
        """更新港股股票名称
        
        Args:
            stock_codes: 需要更新名称的港股代码列表
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for stock_code in stock_codes:
                try:
                    # 构建API URL
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_code}.HK"
                    
                    # 发送请求
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()
                    
                    # 解析响应获取股票名称
                    data = response.json()
                    if data and 'chart' in data and data['chart']['result']:
                        meta = data['chart']['result'][0].get('meta', {})
                        stock_name = meta.get('longName') or meta.get('shortName')
                        
                        if stock_name:
                            # 更新数据库中的股票名称
                            cursor.execute('''
                                UPDATE stock_prices 
                                SET stock_name = ? 
                                WHERE stock_code = ? AND market_type = 'HK'
                            ''', (stock_name, stock_code))
                            print(f"已更新 {stock_code} 的股票名称为: {stock_name}")
                        else:
                            print(f"无法获取 {stock_code} 的股票名称")
                    
                    # 添加延时避免请求过于频繁
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"更新 {stock_code} 的股票名称时出错: {str(e)}")
                    continue
            
            conn.commit()

    def update_us_stock_names(self, stock_codes):
        """更新美股股票名称
        
        Args:
            stock_codes: 需要更新名称的美股代码列表
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for stock_code in stock_codes:
                try:
                    # 构建API URL
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_code}"
                    
                    # 发送请求
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()
                    
                    # 解析响应获取股票名称
                    data = response.json()
                    if data and 'chart' in data and data['chart']['result']:
                        meta = data['chart']['result'][0].get('meta', {})
                        stock_name = meta.get('longName') or meta.get('shortName')
                        
                        if stock_name:
                            # 更新数据库中的股票名称
                            cursor.execute('''
                                UPDATE stock_prices 
                                SET stock_name = ? 
                                WHERE stock_code = ? AND market_type = 'US'
                            ''', (stock_name, stock_code))
                            print(f"已更新 {stock_code} 的股票名称为: {stock_name}")
                        else:
                            print(f"无法获取 {stock_code} 的股票名称")
                    
                    # 添加延时避免请求过于频繁
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"更新 {stock_code} 的股票名称时出错: {str(e)}")
                    continue
            
            conn.commit()

def main():
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    db_path = project_root / 'db' / 'us_stock.db'
    
    builder = USStockDBBuilder(db_path)
    
    # 更新美股名称
    us_unnamed_stocks = ['AAPL', 'ABBV', 'ASML', 'AXP', 'BABA', 'BLK', 'CAT', 
                        'COST', 'CVX', 'ELV', 'ETN', 'GS', 'IBM', 'ISRG', 'MA', 
                        'META', 'MSFT', 'NFLX', 'NVDA', 'QQQ', 'SBUX', 'SPY', 
                        'TEAM', 'TSLA', 'UPS', 'URI', 'V', 'WM', 'XOM']
    
    if us_unnamed_stocks:
        print(f"发现 {len(us_unnamed_stocks)} 个没有名称的美股，开始更新...")
        builder.update_us_stock_names(us_unnamed_stocks)
        print("更新完成")
    
    # # 更新港股名称
    # hk_unnamed_stocks = ['0016', '0700', '1211', '2020', '2318', '2382', 
    #                   '2800', '3690', '9961', '9988', '9999']
    
    # if hk_unnamed_stocks:
    #     print(f"发现 {len(hk_unnamed_stocks)} 个没有名称的港股，开始更新...")
    #     builder.update_hk_stock_names(hk_unnamed_stocks)
    #     print("更新完成")
    # else:
    #     print("没有发现需要更新名称的港股")

if __name__ == '__main__':
    main()