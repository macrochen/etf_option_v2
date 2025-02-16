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

from abc import abstractmethod
import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from scipy import stats
from db.market_db import MarketDatabase
from db.us_stock_db import USStockDatabase  # 引入USStockDatabase类
import traceback

class VolatilityDataGenerator:
    """波动率数据生成器基类"""

    def __init__(self, db):
        """初始化数据生成器"""
        self.stock_db = db  # 使用数据库类

    def calculate_volatility(self, returns, window_days):
        """计算给定窗口的波动率"""
        rolling_std = returns.rolling(window=window_days).std()
        return rolling_std * np.sqrt(window_days)  # 转换为月度波动率

    def calculate_volatility_stats(self, stock_code, window_days=21):
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
                # 检查window是否为window_days的整数倍
                if window % window_days != 0 or window == window_days:
                    print(f"跳过 {period}：{window} 不是 {window_days} 的整数倍")
                    continue

                # 获取最近对应窗口大小的历史数据
                historical_data = self.get_historical_data(stock_code, window)
                
                if not historical_data:
                    print(f"未找到{stock_code}的历史数据")
                    continue

                self.build_monthly_stats(monthly_stats_data, period, historical_data, window_days)
                self.build_weekly_stats(weekly_stats_data, period, historical_data)
                
                # 检查历史数据的数量是否小于窗口大小
                if len(historical_data) < window:
                    print(f"获取的历史数据数量{len(historical_data)}少于 {window}，跳过 {stock_code} 的 {period} 计算")
                    break

            return monthly_stats_data, weekly_stats_data

        except Exception as e:
            print(f"计算波动率统计数据失败: {str(e)}")
            traceback.print_exc()  # 打印堆栈信息
            raise

    def build_monthly_stats(self, monthly_stats_data, period, historical_data, window_days=21):
        self.build_stats(historical_data, period, window_days, monthly_stats_data)

    def build_weekly_stats(self, weekly_stats_data, period, historical_data):
        """构建周度统计数据"""
        pass

    @abstractmethod
    def get_historical_data(self, stock_code, window):
        """获取历史数据"""
        pass

    def build_stats(self, historical_data, name, window_days, stats_data):
        try:
            # 转换为DataFrame
            df = pd.DataFrame(historical_data, columns=['date', 'close'])
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)

            # 计算日收益率
            # df['returns'] = df['close'].pct_change()
            df['returns'] = np.log(df['close'] / df['close'].shift(1))

            # 计算上涨和下跌的波动率
            up_returns = df['returns'][df['returns'] > 0]
            down_returns = df['returns'][df['returns'] < 0]

            # 计算上涨波动率
            up_volatility = self.calculate_volatility(up_returns, window_days)
            down_volatility = self.calculate_volatility(down_returns, window_days)

            # 去除 NaN 值
            up_vol_clean = up_volatility.dropna()
            down_vol_clean = down_volatility.dropna()

            # 统计分析，只在有数据时才添加统计结果
            result = {}
            if len(up_vol_clean) > 0:
                result['up_volatility'] = self._calculate_stats(up_vol_clean)
            else:
                print(f"警告: {name} 期间没有上涨波动率数据")
                
            if len(down_vol_clean) > 0:
                result['down_volatility'] = self._calculate_stats(down_vol_clean)
            else:
                print(f"警告: {name} 期间没有下跌波动率数据")

            # 只在有统计结果时才添加到stats_data中
            if result:
                stats_data[name] = result

        except Exception as e:
            print(f"构建统计数据失败: {str(e)}")
            print(f"参数信息: historical_data长度={len(historical_data)}, name={name}, window_days={window_days}")
            print(f"上涨样本数={len(up_returns)}, 下跌样本数={len(down_returns)}")
            traceback.print_exc()
            raise

    def _calculate_stats(self, volatility_series):
        """计算波动率统计数据"""
        return {
            'volatility': round(float(np.mean(volatility_series)), 3),
            'std': round(float(np.std(volatility_series)), 3),
            'min': round(float(np.min(volatility_series)), 3),
            'max': round(float(np.max(volatility_series)), 3),
            'percentiles': {
                '90': round(float(np.percentile(volatility_series, 90)), 3), 
                '25': round(float(np.percentile(volatility_series, 25)), 3),
                '50': round(float(np.percentile(volatility_series, 50)), 3),
                '75': round(float(np.percentile(volatility_series, 75)), 3),
            }
        }

    def generate_data(self, stock_codes=None):
        """生成波动率数据
        
        Args:
            stock_codes: 股票代码列表，如果为None则处理所有股票
        """
        try:
            if stock_codes is None:
                stock_codes = self.get_codes()

            for stock_code in stock_codes:
                try:
                    print(f"正在处理 {stock_code}...")
                    monthly_stats_data, weekly_stats_data = self.calculate_volatility_stats(stock_code,window_days=21)

                    # 保存到数据库
                    calc_date = pd.Timestamp.now().strftime('%Y-%m-%d')
                    self.save_volatility_stats(stock_code, calc_date, monthly_stats_data, weekly_stats_data)  # 这里可以根据需要调整

                    print(f"{stock_code} 处理完成")
                except Exception as e:
                    print(f"处理 {stock_code} 时出错: {str(e)}")
                    continue

        except Exception as e:
            print(f"生成波动率数据时出错: {str(e)}")
            traceback.print_exc()  # 打印堆栈信息
            raise
    @abstractmethod
    def get_codes(self):
        """获取股票代码"""
        pass
        
    def save_volatility_stats(self, stock_code: str, calc_date: str, monthly_stats: dict, weekly_stats: dict):
        """保存波动率统计数据"""
        exists = self.stock_db.db.fetch_one('SELECT COUNT(*) FROM stock_volatility_stats WHERE stock_code = ?',
                                            (stock_code,))
        if exists and exists[0] > 0:
            print("波动率数据已经存在")
            return

        self.stock_db.db.execute('''
                    INSERT INTO stock_volatility_stats (stock_code, calc_date, monthly_stats, weekly_stats)
                    VALUES (?, ?, ?, ?)
                ''', (stock_code, calc_date, json.dumps(monthly_stats), json.dumps(weekly_stats)))

class USVolatilityDataGenerator(VolatilityDataGenerator):
    """美股波动率数据生成器"""

    def get_codes(self):
        stock_codes = self.stock_db.db.fetch_all('SELECT DISTINCT stock_code FROM stock_prices')
        return stock_codes
    
    def get_historical_data(self, stock_code, window):
        historical_data = self.stock_db.db.fetch_all(
                    f'SELECT date, close_price FROM stock_prices WHERE stock_code = ? ORDER BY date DESC LIMIT {window}',
                    (stock_code,)
                )
        
        return historical_data
    
    def build_weekly_stats(self, weekly_stats_data, period, historical_data):
        self.build_stats(historical_data, period, 5, weekly_stats_data)


class AStockVolatilityDataGenerator(VolatilityDataGenerator):
    """A股波动率数据生成器"""

    def get_codes(self):
        codes = self.stock_db.db.fetch_all('SELECT DISTINCT etf_code FROM etf_daily')
        return [str(code[0]) for code in codes]
    
    def get_historical_data(self, etf_code, window):
        historical_data = self.stock_db.db.fetch_all(
            query=f'SELECT date, close_price FROM etf_daily WHERE etf_code = ? ORDER BY date DESC LIMIT {window}',
            params=(etf_code,)
        )
        
        return historical_data

    def get_price_date_range(self, etf_code):
        """获取指定ETF的价格数据的起止时间"""
        date_range = self.stock_db.db.fetch_one(
            'SELECT MIN(date), MAX(date) FROM etf_daily WHERE etf_code = ?',
            (etf_code,)
        )
        return date_range  # 返回 (最早日期, 最晚日期)

    def save_volatility_stats(self, stock_code: str, calc_date: str, monthly_stats: dict, weekly_stats: dict):
        """保存波动率统计数据"""
        exists = self.stock_db.db.fetch_one('SELECT COUNT(*) FROM volatility_stats WHERE etf_code = ?', (stock_code,))
        if exists and exists[0] > 0:
            print("波动率数据已经存在")
            return
        
        # 获取价格数据的起止时间
        date_range = self.get_price_date_range(stock_code)
        start_date = date_range[0]
        end_date = date_range[1]

        self.stock_db.db.execute('''
            INSERT INTO volatility_stats (etf_code, calc_date, stats_data, start_date, end_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (stock_code, calc_date, json.dumps(monthly_stats), start_date, end_date))

class HKVolatilityDataGenerator(VolatilityDataGenerator):
    """港股波动率数据生成器"""

    def get_historical_data(self, stock_code, window):
        historical_data = self.stock_db.db.fetch_all(
                    f'SELECT date, close_price FROM stock_prices WHERE stock_code = ? ORDER BY date DESC LIMIT {window}',
                    (stock_code,)
                )
        
        return historical_data
    
    # def build_weekly_stats(self, weekly_stats_data, period, historical_data):
        # self.build_stats(historical_data, period, 5, weekly_stats_data)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成ETF波动率统计数据')
    parser.add_argument('--etf', nargs='+', help='指定要处理的ETF代码列表')
    
    args = parser.parse_args()
    
    # generator = VolatilityDataGenerator(USStockDatabase())
    generator = AStockVolatilityDataGenerator(MarketDatabase())
    # if args.etf:
    print("正在生成波动率数据...")
    generator.generate_data(args.etf)
    print("数据生成完成")

if __name__ == '__main__':
    main()
