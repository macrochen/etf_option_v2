import pandas as pd
import numpy as np

class Indicators:
    @staticmethod
    def calculate_tr(df: pd.DataFrame) -> pd.Series:
        """
        计算真实波幅 TR (True Range)
        TR = Max(High - Low, |High - PreClose|, |Low - PreClose|)
        """
        high = df['high']
        low = df['low']
        close = df['close']
        # shift(1) 获取前一天的收盘价
        pre_close = close.shift(1)
        
        # 三个组件
        hl = high - low
        hc = (high - pre_close).abs()
        lc = (low - pre_close).abs()
        
        # 取最大值
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        计算平均真实波幅 ATR
        """
        tr = Indicators.calculate_tr(df)
        # 简单移动平均 (SMA) 还是 Wilder's Smoothing? 
        # PRD 提到 MA(TR, N)，通常使用 SMA 或 EMA。这里使用 SMA 保持简单，也可配置
        atr = tr.rolling(window=period).mean()
        return atr

    @staticmethod
    def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0):
        """
        计算布林带
        Returns: (mid, upper, lower)
        """
        close = df['close']
        mid = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        
        upper = mid + std_dev * std
        lower = mid - std_dev * std
        
        return mid, upper, lower

    @staticmethod
    def calculate_ma(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """计算移动平均线"""
        return df['close'].rolling(window=period).mean()

    @staticmethod
    def calculate_amplitude_avg(df: pd.DataFrame, window: int = 30) -> float:
        """
        计算过去 N 天的平均振幅
        振幅 = (High - Low) / PreClose
        """
        if len(df) < 2:
            return 0.0
            
        high = df['high']
        low = df['low']
        close = df['close']
        pre_close = close.shift(1)
        
        amplitude = (high - low) / pre_close
        
        # 取最近 window 天 (去除头部 NaN)
        recent_amp = amplitude.tail(window).dropna()
        
        if recent_amp.empty:
            return 0.0
            
        return float(recent_amp.mean())

    @staticmethod
    def calculate_beta(etf_df: pd.DataFrame, benchmark_df: pd.DataFrame, window: int = 90) -> float:
        """
        计算 Beta 系数
        """
        if etf_df.empty or benchmark_df.empty:
            return 0.0
            
        # 1. 数据合并 (按日期对齐)
        # 确保日期格式一致 (字符串或 datetime)
        # 假设 df['date'] 是字符串，直接 merge
        try:
            merged = pd.merge(etf_df[['date', 'close']], 
                            benchmark_df[['date', 'close']], 
                            on='date', suffixes=('_etf', '_mkt'), how='inner')
        except Exception:
            return 0.0
        
        if len(merged) < window * 0.5:
            return 0.0
            
        # 2. 计算日收益率
        merged['pct_etf'] = merged['close_etf'].pct_change()
        merged['pct_mkt'] = merged['close_mkt'].pct_change()
        
        # 3. 截取最近 window 天
        recent_data = merged.dropna().tail(window)
        
        if len(recent_data) < 2:
            return 0.0

        # 4. 计算协方差
        cov_matrix = np.cov(recent_data['pct_etf'], recent_data['pct_mkt'])
        
        covariance = cov_matrix[0][1]
        variance_mkt = cov_matrix[1][1]
        
        if variance_mkt == 0:
            return 0.0
            
        # 5. 计算 Beta
        beta = covariance / variance_mkt
        return float(beta)
