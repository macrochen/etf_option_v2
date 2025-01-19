# tools/signal_data_generator.py
import sqlite3
import pandas as pd
import json
from pathlib import Path

class SignalDataGenerator:
    """买卖点数据生成器"""

    def __init__(self, db_path):
        """初始化数据生成器"""
        self.db_path = db_path

    def create_table(self):
        """创建买卖点数据表"""
        with sqlite3.connect(self.db_path) as conn:
            # 先删除已有的表
            conn.execute("DROP TABLE IF EXISTS combined_signals")
            
            # 创建新表
            conn.execute("""
                    CREATE TABLE combined_signals (
                        etf_code VARCHAR(10) NOT NULL,
                        trend_indicator VARCHAR(50) NOT NULL,  -- 存储趋势指标名称
                        Buy_Signal TEXT NOT NULL,  -- 存储买点日期的逗号分隔字符串
                        Sell_Signal TEXT NOT NULL,  -- 存储卖点日期的逗号分隔字符串
                        PRIMARY KEY (etf_code, trend_indicator)  -- 更新主键
                    )
            """)
            conn.commit()

    def generate_signals(self, etf_code):
        """生成买卖点数据"""
        df = self.fetch_etf_data(etf_code)
        
        # 计算综合买卖点数据并存储到数据库
        combined_signals = self.calculate_combined_signals(df, etf_code)
        
        # 存储每个指标的买卖点数据
        ma_signals = self.moving_average_crossover(df)
        rsi_signals = self.rsi_strategy(df)
        macd_signals = self.macd_strategy(df)
        bb_signals = self.bollinger_band_strategy(df)

        # 提取买点和卖点日期
        def get_alternate_signals(signals):
            buy_dates = []
            sell_dates = []
            last_signal = None  # 用于跟踪上一个信号

            for index, row in signals.iterrows():
                if row['Buy_Signal'] and last_signal != 'buy':
                    buy_dates.append(row['date'])
                    last_signal = 'buy'
                elif row['Sell_Signal'] and last_signal != 'sell':
                    sell_dates.append(row['date'])
                    last_signal = 'sell'

            return buy_dates, sell_dates

        ma_buy_dates, ma_sell_dates = get_alternate_signals(ma_signals)
        rsi_buy_dates, rsi_sell_dates = get_alternate_signals(rsi_signals)
        macd_buy_dates, macd_sell_dates = get_alternate_signals(macd_signals)
        bb_buy_dates, bb_sell_dates = get_alternate_signals(bb_signals)

        # 存储买卖点数据
        self.store_signals(ma_buy_dates, ma_sell_dates, etf_code, 'Moving Average')
        self.store_signals(rsi_buy_dates, rsi_sell_dates, etf_code, 'RSI')
        self.store_signals(macd_buy_dates, macd_sell_dates, etf_code, 'MACD')
        self.store_signals(bb_buy_dates, bb_sell_dates, etf_code, 'Bollinger Bands')

    def fetch_etf_data(self, etf_code):
        """从数据库中获取ETF历史数据"""
        with sqlite3.connect(self.db_path) as conn:
            query = f"SELECT date, close_price FROM etf_daily WHERE etf_code = '{etf_code}' ORDER BY date"
            df = pd.read_sql_query(query, conn)
        return df

    def calculate_combined_signals(self, df, etf_code):
        """计算综合买卖点数据并存储到数据库"""
        # 生成各个策略的信号
        ma_signals = self.moving_average_crossover(df)
        rsi_signals = self.rsi_strategy(df)
        macd_signals = self.macd_strategy(df)
        bb_signals = self.bollinger_band_strategy(df)

        # 合并所有信号，使用交集
        combined_signals = pd.merge(ma_signals, rsi_signals, on='date', suffixes=('_ma', '_rsi'), how='inner')
        combined_signals = pd.merge(combined_signals, macd_signals, on='date', suffixes=('', '_macd'), how='inner')
        combined_signals = pd.merge(combined_signals, bb_signals, on='date', suffixes=('', '_bb'), how='inner')

        # 综合买卖信号
        combined_signals['Buy_Signal'] = combined_signals[['Buy_Signal_ma', 'Buy_Signal_rsi', 'Buy_Signal', 'Buy_Signal_bb']].all(axis=1)
        combined_signals['Sell_Signal'] = combined_signals[['Sell_Signal_ma', 'Sell_Signal_rsi', 'Sell_Signal', 'Sell_Signal_bb']].all(axis=1)

        # 提取买点和卖点日期
        buy_dates = combined_signals[combined_signals['Buy_Signal']].date.tolist()
        sell_dates = combined_signals[combined_signals['Sell_Signal']].date.tolist()

        # 存储综合买卖点数据
        self.store_combined_signals(buy_dates, sell_dates, etf_code)

        return combined_signals[['date', 'Buy_Signal', 'Sell_Signal']]

    def store_signals(self, buy_signals, sell_signals, etf_code, trend_indicator):
        """将买卖点数据存储到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            buy_signals_str = ','.join(buy_signals)  # 将买点日期转换为逗号分隔字符串
            sell_signals_str = ','.join(sell_signals)  # 将卖点日期转换为逗号分隔字符串
            
            conn.execute("""
                INSERT INTO combined_signals (etf_code, trend_indicator, Buy_Signal, Sell_Signal)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(etf_code, trend_indicator) DO UPDATE SET
                    Buy_Signal = excluded.Buy_Signal,
                    Sell_Signal = excluded.Sell_Signal
            """, (etf_code, trend_indicator, buy_signals_str, sell_signals_str))
            conn.commit()

    def store_combined_signals(self, buy_signals, sell_signals, etf_code):
        """将综合买卖点数据存储到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            buy_signals_str = ','.join(buy_signals)  # 将买点日期转换为逗号分隔字符串
            sell_signals_str = ','.join(sell_signals)  # 将卖点日期转换为逗号分隔字符串
            
            conn.execute("""
                INSERT INTO combined_signals (etf_code, trend_indicator, Buy_Signal, Sell_Signal)
                VALUES (?, 'Combined', ?, ?)
                ON CONFLICT(etf_code, trend_indicator) DO UPDATE SET
                    Buy_Signal = excluded.Buy_Signal,
                    Sell_Signal = excluded.Sell_Signal
            """, (etf_code, buy_signals_str, sell_signals_str))
            conn.commit()

    # 以下是各个策略的实现
    def moving_average_crossover(self, df):
        df['MA20'] = df['close_price'].rolling(window=20).mean()
        df['MA50'] = df['close_price'].rolling(window=50).mean()
        df['Buy_Signal'] = (df['MA20'] > df['MA50']) & (df['MA20'].shift(1) <= df['MA50'].shift(1))
        df['Sell_Signal'] = (df['MA20'] < df['MA50']) & (df['MA20'].shift(1) >= df['MA50'].shift(1))
        return df[['date', 'Buy_Signal', 'Sell_Signal']]

    def rsi_strategy(self, df):
        df['RSI'] = self.compute_rsi(df['close_price'])
        df['Buy_Signal'] = (df['RSI'] < 30) & (df['RSI'].shift(1) >= 30)
        df['Sell_Signal'] = (df['RSI'] > 70) & (df['RSI'].shift(1) <= 70)
        return df[['date', 'Buy_Signal', 'Sell_Signal']]

    def macd_strategy(self, df):
        df = self.compute_macd(df)
        df['Buy_Signal'] = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
        df['Sell_Signal'] = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
        return df[['date', 'Buy_Signal', 'Sell_Signal']]

    def bollinger_band_strategy(self, df):
        df = self.bollinger_bands(df)
        df['Buy_Signal'] = (df['close_price'] < df['Lower_Band'])
        df['Sell_Signal'] = (df['close_price'] > df['Upper_Band'])
        return df[['date', 'Buy_Signal', 'Sell_Signal']]

    # 计算RSI的函数
    def compute_rsi(self, series, window=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    # 计算MACD的函数
    def compute_macd(self, df):
        df['EMA12'] = df['close_price'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['close_price'].ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        return df

    # 计算布林带的函数
    def bollinger_bands(self, df, window=20, num_std_dev=2):
        df['MA'] = df['close_price'].rolling(window=window).mean()
        df['Upper_Band'] = df['MA'] + (df['close_price'].rolling(window=window).std() * num_std_dev)
        df['Lower_Band'] = df['MA'] - (df['close_price'].rolling(window=window).std() * num_std_dev)
        return df

def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成买卖点数据')
    parser.add_argument('--init', action='store_true', help='初始化数据库表')
    parser.add_argument('--etf', nargs='+', help='指定要处理的ETF代码列表', default=None)
    
    args = parser.parse_args()
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    db_path = project_root / 'db' / 'market_data.db'
    
    generator = SignalDataGenerator(db_path)
    
    if args.init:
        print("正在初始化数据库表...")
        generator.create_table()
        print("表初始化完成")
        
    if args.etf is None:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT etf_code FROM etf_daily")
            args.etf = [row[0] for row in cursor.fetchall()]

    if args.etf:
        print("正在生成买卖点数据...")
        for etf_code in args.etf:
            generator.generate_signals(etf_code)
            print(f"{etf_code} 买卖点数据生成完成")
        print("数据生成完成")
    else:
        print("未提供ETF代码，无法生成买卖点数据。")

if __name__ == '__main__':
    main()