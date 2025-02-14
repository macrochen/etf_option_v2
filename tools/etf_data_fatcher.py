import tushare as ts
import pandas as pd
import numpy as np
from typing import Optional


class ETFDataFetcher:
    def __init__(self, token: str):
        ts.set_token('fb3d7d272effcf44f7bc0fb4e2c0ab80d612576105a13a8d442d0e4a')
        self.pro = ts.pro_api()

    def fetch_etf_daily(self, etf_code: str,
                        start_date: str,
                        end_date: str) -> Optional[pd.DataFrame]:
        try:
            # 获取原始数据
            df = self.pro.fund_daily(
                ts_code=etf_code,
                start_date=start_date,
                end_date=end_date
            )

            if df.empty:
                return None

            # 计算ATR
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    abs(df['high'] - df['pre_close']),
                    abs(df['low'] - df['pre_close'])
                )
            )
            df['atr'] = df['tr'].rolling(window=14).mean()

            # 格式化数据
            result_df = df[[
                'trade_date', 'ts_code', 'open', 'high', 'low',
                'close', 'vol', 'amount', 'pre_close',
                'pct_chg', 'atr'
            ]].rename(columns={
                'trade_date': 'date',
                'ts_code': 'etf_code',
                'vol': 'volume',
                'pct_chg': 'change_rate'
            })

            return result_df

        except Exception as e:
            print(f"Error fetching data: {str(e)}")
            return None


# 初始化数据获取器
fetcher = ETFDataFetcher('your_tushare_token')

# 获取数据
df = fetcher.fetch_etf_daily(
    etf_code='510050.SH',
    start_date='20230101',
    end_date='20231231'
)

# 保存到数据库
if df is not None:
    # TODO: 实现数据库保存逻辑
    pass