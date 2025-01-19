#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
波动率数据生成工具

用途：
1. 创建或更新波动率统计表，增加起止时间字段
2. 计算ETF的历史波动率数据，包括：
   - 整体波动率
   - 上行波动率（上涨时的波动率）
   - 下行波动率（下跌时的波动率）
   - 各个分位数的统计值
3. 生成用于前端展示的图表数据

使用方法：
1. 生成所有股票的波动率数据：
   python tools/volatility_data_generator.py

2. 生成指定股票的波动率数据：
   python tools/volatility_data_generator.py --etf 510050 510300

注意事项：
1. 数据库路径为项目下的@db/us_stock.db
2. 波动率计算使用所有历史数据
3. 波动率为月度值，使用21个交易日（一个月）进行计算
4. 所有统计数据以JSON格式存储在数据库中
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from scipy import stats
from db.us_stock_db import USStockDatabase  # 引入USStockDatabase类
import traceback

class VolatilityDataGenerator:
    """波动率数据生成器"""

    def __init__(self, db:USStockDatabase):
        """初始化数据生成器"""
        self.stock_db = db  # 使用USStockDatabase类

    def calculate_volatility(self, returns, window):
        """计算给定窗口的波动率"""
        rolling_std = returns.rolling(window=window).std()
        return rolling_std * np.sqrt(window)  # 转换为月度波动率

    def calculate_volatility_stats(self, stock_code):
        """计算波动率统计数据"""
        try:
            # 定义不同时间长度
            periods = {
                '3个月': 63,
                '6个月': 126,
                '1年': 252,
                '3年': 756,
                '5年': 1260,
                '10年': 2520
            }

            monthly_stats_data = {}
            weekly_stats_data = {}
            for period, window in periods.items():
                # 获取最近对应窗口大小的历史数据
                historical_data = self.stock_db.db.fetch_all(
                    f'SELECT date, close_price FROM stock_prices WHERE stock_code = ? ORDER BY date DESC LIMIT {window}',
                    (stock_code,)
                )
                
                if not historical_data:
                    print(f"未找到{stock_code}的历史数据")
                    continue

                self.build_stats(historical_data, period, 21, monthly_stats_data)
                self.build_stats(historical_data, period, 5, weekly_stats_data)

            # 保存到数据库
            calc_date = pd.Timestamp.now().strftime('%Y-%m-%d')
            self.stock_db.save_volatility_stats(stock_code, calc_date, monthly_stats_data, weekly_stats_data)  # 这里可以根据需要调整

            return True

        except Exception as e:
            print(f"计算波动率统计数据失败: {str(e)}")
            traceback.print_exc()  # 打印堆栈信息
            raise

    def build_stats(self, historical_data, name, days, stats_data):
        try:
            # 转换为DataFrame
            df = pd.DataFrame(historical_data, columns=['date', 'close'])
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)

            # 计算日收益率
            df['returns'] = df['close'].pct_change()

            # 计算上涨和下跌的波动率
            up_returns = df['returns'][df['returns'] > 0]
            down_returns = df['returns'][df['returns'] < 0]

            # 计算上涨波动率
            up_volatility = self.calculate_volatility(up_returns, days)
            down_volatility = self.calculate_volatility(down_returns, days)

            # 统计分析
            stats_data[name] = {
                'up_volatility': {
                    'volatility': round(float(np.mean(up_volatility.dropna())), 3),
                    'std': round(float(np.std(up_volatility.dropna())), 3),
                    'min': round(float(np.min(up_volatility.dropna())), 3),
                    'max': round(float(np.max(up_volatility.dropna())), 3),
                    'percentiles': {
                        '25': round(float(np.percentile(up_volatility.dropna(), 25)), 3),
                        '50': round(float(np.percentile(up_volatility.dropna(), 50)), 3),
                        '75': round(float(np.percentile(up_volatility.dropna(), 75)), 3),
                    }
                },
                'down_volatility': {
                    'volatility': round(float(np.mean(down_volatility.dropna())), 3),
                    'std': round(float(np.std(down_volatility.dropna())), 3),
                    'min': round(float(np.min(down_volatility.dropna())), 3),
                    'max': round(float(np.max(down_volatility.dropna())), 3),
                    'percentiles': {
                        '25': round(float(np.percentile(down_volatility.dropna(), 25)), 3),
                        '50': round(float(np.percentile(down_volatility.dropna(), 50)), 3),
                        '75': round(float(np.percentile(down_volatility.dropna(), 75)), 3),
                    }
                }
            }
        except Exception as e:
            print(f"构建统计数据失败: {str(e)}")
            traceback.print_exc()  # 打印堆栈信息
            raise

    def generate_data(self, stock_codes=None):
        """生成波动率数据
        
        Args:
            stock_codes: 股票代码列表，如果为None则处理所有股票
        """
        try:
            if stock_codes is None:
                stock_codes = self.stock_db.db.fetch_all('SELECT DISTINCT stock_code FROM stock_prices')

            for stock_code in stock_codes:
                try:
                    print(f"正在处理 {stock_code}...")
                    self.calculate_volatility_stats(stock_code)
                    print(f"{stock_code} 处理完成")
                except Exception as e:
                    print(f"处理 {stock_code} 时出错: {str(e)}")
                    continue

        except Exception as e:
            print(f"生成波动率数据时出错: {str(e)}")
            traceback.print_exc()  # 打印堆栈信息
            raise

    def save_volatility_stats(self, stock_code: str, calc_date: str, monthly_stats: dict, weekly_stats: dict):
        """保存波动率统计数据"""
        exists = self.stock_db.fetch_one('SELECT COUNT(*) FROM stock_volatility_stats WHERE stock_code = ? AND calc_date = ?', (stock_code, calc_date))
        if exists and exists[0] > 0:
            print("波动率数据已经存在")
            return
        
        self.stock_db.execute('''
            INSERT INTO stock_volatility_stats (stock_code, calc_date, monthly_stats, weekly_stats)
            VALUES (?, ?, ?, ?)
        ''', (stock_code, calc_date, json.dumps(monthly_stats), json.dumps(weekly_stats)))

def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成ETF波动率统计数据')
    parser.add_argument('--etf', nargs='+', help='指定要处理的ETF代码列表')
    
    args = parser.parse_args()
    
    generator = VolatilityDataGenerator(USStockDatabase())
    
    if args.etf:
        print("正在生成波动率数据...")
        generator.generate_data(args.etf)
        print("数据生成完成")

if __name__ == '__main__':
    main()
