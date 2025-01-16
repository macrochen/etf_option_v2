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
1. 初始化/更新数据库表结构：
   python tools/volatility_data_generator.py --init

2. 生成所有ETF的波动率数据：
   python tools/volatility_data_generator.py

3. 生成指定ETF的波动率数据：
   python tools/volatility_data_generator.py --etf 510050 510300

注意事项：
1. 数据库路径为项目下的@db/market_data.db
2. 波动率计算使用所有历史数据
3. 波动率为月度值，使用21个交易日（一个月）进行计算
4. 所有统计数据以JSON格式存储在数据库中
"""

import sqlite3
import json
import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta
from pathlib import Path
from scipy import stats

class VolatilityDataGenerator:
    """波动率数据生成器"""

    def __init__(self, db_path):
        """初始化数据生成器"""
        self.db_path = db_path

    def create_table(self):
        """创建或更新波动率统计表"""
        with sqlite3.connect(self.db_path) as conn:
            # 先删除已有的表
            conn.execute("DROP TABLE IF EXISTS volatility_stats")
            
            # 创建新表
            conn.execute("""
                CREATE TABLE volatility_stats (
                    etf_code VARCHAR(10),
                    calc_date DATE,
                    stats_data TEXT,
                    display_data TEXT,
                    start_date DATE,
                    end_date DATE,
                    PRIMARY KEY (etf_code, calc_date)
                )
            """)
            conn.commit()

    def calculate_monthly_volatility(self, returns):
        """计算月度波动率统计数据
        Args:
            returns: 日收益率序列
        Returns:
            dict: 包含波动率统计数据的字典
        """
        # 使用21个交易日作为一个月
        window = 21
        rolling_std = returns.rolling(window=window).std()
        monthly_volatility = rolling_std * np.sqrt(window)  # 转换为月度波动率
        
        # 计算分位数和统计值
        valid_data = monthly_volatility.dropna()
        mean = round(float(np.mean(valid_data)), 3)
        std = round(float(np.std(valid_data)), 3)
        min_val = round(float(np.min(valid_data)), 3)
        max_val = round(float(np.max(valid_data)), 3)
        
        percentiles = {
            '25': round(float(np.percentile(valid_data, 25)), 3),
            '50': round(float(np.percentile(valid_data, 50)), 3),
            '75': round(float(np.percentile(valid_data, 75)), 3),
            '90': round(float(np.percentile(valid_data, 90)), 3)
        }
        
        return {
            'volatility': mean,
            'std': std,
            'min': min_val,
            'max': max_val,
            'percentiles': percentiles,
            'std_ranges': {
                'minus_2std': round(max(0, mean - 2 * std), 3),
                'minus_1std': round(max(0, mean - std), 3),
                'plus_1std': round(mean + std, 3),
                'plus_2std': round(mean + 2 * std, 3)
            }
        }

    def calculate_volatility_stats(self, symbol):
        """计算波动率统计数据"""
        try:
            # 获取历史数据
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date, close_price 
                    FROM etf_daily 
                    WHERE etf_code = ? 
                    ORDER BY date
                """, (symbol,))
                data = cursor.fetchall()

            if not data:
                raise ValueError(f"未找到{symbol}的历史数据")

            # 转换为DataFrame
            df = pd.DataFrame(data, columns=['date', 'close'])
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)

            # 计算日收益率
            df['returns'] = df['close'].pct_change()
            
            # 分离上涨和下跌
            df['up_returns'] = df['returns'].apply(lambda x: x if x > 0 else np.nan)
            df['down_returns'] = df['returns'].apply(lambda x: abs(x) if x < 0 else np.nan)

            # 计算整体波动率
            window = 21
            up_volatility = df['up_returns'].rolling(window=window, min_periods=1).std() * np.sqrt(window)
            down_volatility = df['down_returns'].rolling(window=window, min_periods=1).std() * np.sqrt(window)

            # 去除无效数据
            up_volatility = up_volatility.replace([np.inf, -np.inf], np.nan).dropna()
            down_volatility = down_volatility.replace([np.inf, -np.inf], np.nan).dropna()

            # 准备箱线图数据
            def prepare_boxplot_data(volatility_series):
                if len(volatility_series) == 0:
                    return [0, 0, 0, 0, 0]  # 返回默认值
                    
                data = volatility_series
                return [
                    round(float(np.min(data)), 3),  # 最小值
                    round(float(np.percentile(data, 25)), 3),  # Q1
                    round(float(np.percentile(data, 50)), 3),  # 中位数
                    round(float(np.percentile(data, 75)), 3),  # Q3
                    round(float(np.max(data)), 3)  # 最大值
                ]

            # 准备正态分布数据
            def prepare_distribution_data(data, is_upward=True):
                if len(data) == 0:
                    return {
                        'x': [0],
                        'y': [0],
                        'mean': 0,
                        'std': 0,
                        'ranges': {'1std': [0, 0], '2std': [0, 0]}
                    }
                    
                mean = np.mean(data)
                std = np.std(data)
                
                # 生成x轴数据点，确保覆盖±3个标准差
                x = np.linspace(mean - 3*std, mean + 3*std, 100)
                
                # 计算正态分布曲线
                y = stats.norm.pdf(x, mean, std)
                
                return {
                    'x': list(x),
                    'y': list(y),
                    'mean': round(float(mean), 3),
                    'std': round(float(std), 3),
                    'ranges': {
                        '1std': [round(float(mean - std), 3), round(float(mean + std), 3)],
                        '2std': [round(float(mean - 2*std), 3), round(float(mean + 2*std), 3)]
                    }
                }

            # 生成显示数据
            display_data = {
                'boxplot': {
                    'upward': prepare_boxplot_data(up_volatility),
                    'downward': prepare_boxplot_data(down_volatility)
                },
                'distribution': {
                    'upward': prepare_distribution_data(up_volatility, True),
                    'downward': prepare_distribution_data(down_volatility, False)
                }
            }

            # 生成统计数据
            def calculate_stats(volatility_series):
                if len(volatility_series) == 0:
                    return {
                        'min': 0,
                        'max': 0,
                        'volatility': 0,
                        'std': 0,
                        'percentiles': {'25': 0, '50': 0, '75': 0, '90': 0}
                    }
                    
                data = volatility_series
                return {
                    'min': round(float(np.min(data)), 3),
                    'max': round(float(np.max(data)), 3),
                    'volatility': round(float(np.mean(data)), 3),
                    'std': round(float(np.std(data)), 3),
                    'percentiles': {
                        '25': round(float(np.percentile(data, 25)), 3),
                        '50': round(float(np.percentile(data, 50)), 3),
                        '75': round(float(np.percentile(data, 75)), 3),
                        '90': round(float(np.percentile(data, 90)), 3)
                    }
                }

            stats_data = {
                'upward': calculate_stats(up_volatility),
                'downward': calculate_stats(down_volatility)
            }

            # 保存到数据库
            calc_date = df.index[-1].strftime('%Y-%m-%d')
            stats_json = json.dumps(stats_data)
            display_json = json.dumps(display_data)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO volatility_stats 
                    (etf_code, calc_date, stats_data, display_data, start_date, end_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    symbol,
                    calc_date,
                    stats_json,
                    display_json,
                    df.index[0].strftime('%Y-%m-%d'),
                    df.index[-1].strftime('%Y-%m-%d')
                ))
                conn.commit()

            return True

        except Exception as e:
            print(f"计算波动率统计数据失败: {str(e)}")
            raise

    def generate_data(self, etf_codes=None):
        """生成波动率数据
        
        Args:
            etf_codes: ETF代码列表，如果为None则处理所有ETF
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 清除已有数据
                if etf_codes:
                    placeholders = ','.join(['?' for _ in etf_codes])
                    conn.execute(f"DELETE FROM volatility_stats WHERE etf_code IN ({placeholders})", etf_codes)
                else:
                    conn.execute("DELETE FROM volatility_stats")
                conn.commit()

                # 如果没有指定ETF代码，获取所有ETF代码
                if not etf_codes:
                    cursor = conn.cursor()
                    cursor.execute("SELECT DISTINCT etf_code FROM etf_daily")
                    etf_codes = [row[0] for row in cursor.fetchall()]

            # 生成新数据
            for etf_code in etf_codes:
                try:
                    print(f"正在处理 {etf_code}...")
                    self.calculate_volatility_stats(etf_code)
                    print(f"{etf_code} 处理完成")
                except Exception as e:
                    print(f"处理 {etf_code} 时出错: {str(e)}")
                    continue

        except Exception as e:
            print(f"生成波动率数据时出错: {str(e)}")
            raise

def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成ETF波动率统计数据')
    parser.add_argument('--init', action='store_true', help='初始化数据库表')
    parser.add_argument('--etf', nargs='+', help='指定要处理的ETF代码列表')
    
    args = parser.parse_args()
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    db_path = project_root / 'db' / 'market_data.db'
    
    generator = VolatilityDataGenerator(db_path)
    
    if args.init:
        print("正在初始化数据库表...")
        generator.create_table()
        print("表初始化完成")
        
    if args.etf or not args.init:
        print("正在生成波动率数据...")
        generator.generate_data(args.etf)
        print("数据生成完成")

if __name__ == '__main__':
    main()
