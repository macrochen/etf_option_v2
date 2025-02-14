#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Grid Trade Data Importer

用途：
1. 读取grid_trade目录下的CSV文件
2. 创建market_data.db数据库中的grid_trade表
3. 导入数据到数据库中

使用方法：
python tools/grid_data_importer.py
"""

import sqlite3
import pandas as pd
from pathlib import Path
import os

class GridDataImporter:
    """网格交易数据导入器"""

    def __init__(self, db_path):
        """初始化数据导入器"""
        self.db_path = db_path

    def create_table(self):
        """创建网格交易数据表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS grid_trade (
                    etf_code VARCHAR(10),
                    date DATE,
                    open_price REAL,
                    close_price REAL,
                    low_price REAL,
                    high_price REAL,
                    volume REAL,
                    money REAL,
                    factor REAL,
                    high_limit REAL,
                    low_limit REAL,
                    avg_price REAL,
                    pre_close REAL,
                    paused REAL,
                    PRIMARY KEY (etf_code, date)
                )
            """)
            conn.commit()

    def import_csv_file(self, file_path):
        """导入单个CSV文件的数据"""
        try:
            # 从文件名中提取ETF代码
            file_name = Path(file_path).stem
            etf_code = file_name.split('_')[0]
            
            # 读取CSV文件
            df = pd.read_csv(file_path)
            
            # 重命名列以匹配数据库表结构
            column_mapping = {
                '日期': 'date',
                'open': 'open_price',
                'close': 'close_price',
                'low': 'low_price',
                'high': 'high_price',
                'volume': 'volume',
                'money': 'money',
                'factor': 'factor',
                'high_limit': 'high_limit',
                'low_limit': 'low_limit',
                'avg': 'avg_price',
                'pre_close': 'pre_close',
                'paused': 'paused'
            }
            df = df.rename(columns=column_mapping)
            
            # 添加ETF代码列
            df['etf_code'] = etf_code
            
            # 连接数据库并导入数据
            with sqlite3.connect(self.db_path) as conn:
                df.to_sql('grid_trade', conn, if_exists='append', index=False)
                
            print(f"成功导入文件: {file_path}")
            return True
            
        except Exception as e:
            print(f"导入文件 {file_path} 时出错: {str(e)}")
            return False

    def process_directory(self, data_dir):
        """处理目录中的所有CSV文件"""
        # 获取所有CSV文件
        csv_files = list(Path(data_dir).glob('*.csv'))
        
        if not csv_files:
            print(f"在 {data_dir} 目录中没有找到CSV文件")
            return
        
        total_files = len(csv_files)
        success_count = 0
        
        print(f"开始处理 {total_files} 个文件...")
        
        # 处理每个文件
        for file_path in csv_files:
            if self.import_csv_file(file_path):
                success_count += 1
                
        print(f"\n处理完成:")
        print(f"总文件数: {total_files}")
        print(f"成功导入: {success_count}")
        print(f"失败数量: {total_files - success_count}")

def main():
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    db_path = project_root / 'db' / 'market_data.db'
    data_dir = project_root / 'data' / 'grid_trade'
    
    # 确保db目录存在
    db_dir = db_path.parent
    if not db_dir.exists():
        print(f"创建数据库目录: {db_dir}")
        db_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 创建导入器实例
        importer = GridDataImporter(db_path)
        
        # 创建数据表
        print("正在创建数据表...")
        importer.create_table()
        print("数据表创建完成")
        
        # 导入数据
        print("\n开始导入数据...")
        importer.process_directory(data_dir)
        
    except sqlite3.OperationalError as e:
        print(f"数据库操作错误: {str(e)}")
        print("请检查数据库文件权限和目录权限")
    except Exception as e:
        print(f"发生错误: {str(e)}")

if __name__ == '__main__':
    main()