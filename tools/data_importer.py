import os
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

class DataImporter:
    def __init__(self, db_path='market_data.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def connect(self):
        """连接到SQLite数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()

    def create_tables(self):
        """创建数据表"""
        # ETF日行情表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS etf_daily (
            etf_code VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            open_price DECIMAL(10,4),
            close_price DECIMAL(10,4),
            PRIMARY KEY (etf_code, date)
        )
        ''')

        # 期权日行情表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS option_daily (
            etf_code VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            contract_code VARCHAR(20),
            change_rate DECIMAL(10,4),
            open_price DECIMAL(10,4),
            close_price DECIMAL(10,4),
            strike_price DECIMAL(10,4),
            delta DECIMAL(10,4),
            settlement_price DECIMAL(10,4),
            PRIMARY KEY (etf_code, date, contract_code),
            FOREIGN KEY (etf_code, date) REFERENCES etf_daily(etf_code, date)
        )
        ''')
        
        self.conn.commit()

    def import_etf_data(self, etf_code):
        """导入ETF数据"""
        etf_dir = f'data/{etf_code}'
        if not os.path.exists(etf_dir):
            print(f"找不到ETF数据目录: {etf_dir}")
            return
            
        # 获取目录下所有的CSV文件
        csv_files = [f for f in os.listdir(etf_dir) if f.endswith('.csv')]
        if not csv_files:
            print(f"目录 {etf_dir} 中没有找到CSV文件")
            return
            
        for csv_file in csv_files:
            csv_path = os.path.join(etf_dir, csv_file)
            try:
                df = pd.read_csv(csv_path)
                df['etf_code'] = etf_code
                
                # 准备数据
                records = df.apply(lambda row: (
                    row['etf_code'],
                    row['日期'],
                    row['开盘价'],
                    row['收盘价']
                ), axis=1).tolist()

                # 批量插入数据
                self.cursor.executemany(
                    'INSERT OR REPLACE INTO etf_daily (etf_code, date, open_price, close_price) VALUES (?, ?, ?, ?)',
                    records
                )
                self.conn.commit()
                print(f"已导入ETF {etf_code}的数据文件: {csv_file}")
                
            except Exception as e:
                print(f"处理文件 {csv_file} 时发生错误: {str(e)}")
                continue

    def clean_excel_data(self, df):
        """清理Excel数据，移除非数据行"""
        # 确保所有必需的列都存在
        required_columns = ['日期', '交易代码', '涨跌幅(%)', '开盘价', '收盘价', '行权价', 'Delta', '结算价']
        if not all(col in df.columns for col in required_columns):
            return pd.DataFrame()  # 返回空DataFrame

        # 确保日期列是datetime类型
        if not pd.api.types.is_datetime64_any_dtype(df['日期']):
            try:
                df['日期'] = pd.to_datetime(df['日期'])
            except:
                return pd.DataFrame()

        # 删除日期为空的行
        df = df.dropna(subset=['日期'])
        
        # 删除包含"数据来源"的行
        df = df[~df['交易代码'].astype(str).str.contains('数据来源', na=False)]
        
        return df

    def import_option_data(self, etf_code):
        """导入期权数据"""
        option_dir = f'data/{etf_code}'
        if not os.path.exists(option_dir):
            print(f"找不到期权数据目录: {option_dir}")
            return

        # 获取所有xlsx文件
        xlsx_files = [f for f in os.listdir(option_dir) if f.endswith('.xlsx') and '日行情' in f]
        
        for file in xlsx_files:
            file_path = os.path.join(option_dir, file)
            print(f"正在处理文件: {file}")
            
            try:
                # 读取Excel文件，跳过最后几行
                df = pd.read_excel(file_path)
                
                # 清理数据
                df = self.clean_excel_data(df)
                if df.empty:
                    print(f"文件 {file} 中没有有效数据")
                    continue

                df['etf_code'] = etf_code
                
                # 准备数据
                records = []
                for _, row in df.iterrows():
                    try:
                        # 转换日期格式
                        date_str = row['日期'].strftime('%Y-%m-%d')
                        
                        record = (
                            row['etf_code'],
                            date_str,
                            str(row['交易代码']),
                            float(row['涨跌幅(%)']),
                            float(row['开盘价']),
                            float(row['收盘价']),
                            float(row['行权价']),
                            float(row['Delta']),
                            float(row['结算价'])
                        )
                        records.append(record)
                    except (ValueError, KeyError, AttributeError) as e:
                        print(f"跳过无效数据行: {str(e)}")
                        continue

                if records:
                    # 批量插入数据
                    self.cursor.executemany('''
                        INSERT OR REPLACE INTO option_daily 
                        (etf_code, date, contract_code, change_rate, open_price, close_price, 
                        strike_price, delta, settlement_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', records)
                    self.conn.commit()
                    print(f"已导入文件 {file} 的数据，共 {len(records)} 条记录")
                else:
                    print(f"文件 {file} 中没有有效数据")
                    
            except Exception as e:
                print(f"处理文件 {file} 时发生错误: {str(e)}")
                continue

def main():
    importer = DataImporter()
    try:
        importer.connect()
        importer.create_tables()
        
        # 处理所有ETF数据目录
        etf_codes = ['510300', '510500', '510050', '588000', '588080', 
                    '159901', '159915', '159919', '159922']
        
        for etf_code in etf_codes:
            print(f"\n开始处理 {etf_code} 的数据...")
            importer.import_etf_data(etf_code)
            importer.import_option_data(etf_code)
            
    except Exception as e:
        print(f"发生错误: {str(e)}")
    finally:
        importer.close()

if __name__ == '__main__':
    main() 