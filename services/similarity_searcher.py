import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from grid.valuation_manager import ValuationManager
from grid.min_data_loader import MinDataLoader

class SimilaritySearcher:
    def __init__(self):
        self.vm = ValuationManager()
        self.dl = MinDataLoader()

    def find_similar_moments(self, etf_code: str, top_n=5, metric_preference: str = 'auto'):
        """
        寻找历史相似时刻
        """
        # 1. 获取基础数据
        index_info = self.vm.get_index_for_etf(etf_code)
        if not index_info:
            return {"error": "未找到跟踪指数"}
            
        index_code = index_info['index_code']
        # 获取全量估值历史
        df_val = self.vm.get_valuation_history(index_code)
        # 获取全量价格历史 (日线)
        df_price = self.dl.load_daily_data(etf_code)
        
        if df_val.empty or df_price.empty:
            return {"error": "数据不足，无法进行匹配"}

        # 2. 数据对齐与预处理
        df_price['date'] = pd.to_datetime(df_price['date'])
        df_price = df_price.set_index('date').sort_index()
        
        logging.info(f"Price Range: {df_price.index[0].date()} -> {df_price.index[-1].date()} (Count: {len(df_price)})")
        logging.info(f"Valuation Range: {df_val.index[0].date()} -> {df_val.index[-1].date()} (Count: {len(df_val)})")
        
        # 合并估值与价格
        df = df_price[['close']].join(df_val[['pe', 'pb']], how='inner')
        if df.empty:
            return {"error": "价格与估值数据无法对齐"}

        # 3. 计算特征指标
        # A. 估值分位 (5年滑动窗口)
        # 根据偏好选择指标
        use_pe = True
        if metric_preference == 'pb':
            use_pe = False
        elif metric_preference == 'auto':
            # 默认逻辑：如果有 PE 且有效则用 PE，否则 PB
            if not df['pe'].notnull().any():
                use_pe = False
        
        val_col = 'pe' if use_pe else 'pb'
        series_val = df[val_col].where(df[val_col] > 0)
        
        # 记录一下计算前的状态
        logging.info(f"Using Metric for Similarity: {val_col.upper()}")
        logging.info(f"Data Length: {len(series_val)}")
        
        df['val_pct'] = series_val.rolling(window=1250, min_periods=250).apply(
            lambda x: (x < x.iloc[-1]).mean() * 100 if len(x) > 0 else np.nan
        )
        
        # 检查最后一日的计算详情
        if len(series_val) > 0:
            last_window = series_val.iloc[-1250:]
            last_val = last_window.iloc[-1]
            calc_rank = (last_window < last_val).mean() * 100
            logging.info(f"Manual check for last date: Value={last_val}, Window Size={len(last_window)}, Calculated Rank={calc_rank:.2f}%")

        # B. 趋势因子 (MA20/MA60 乖离)
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['trend_factor'] = (df['ma20'] - df['ma60']) / df['ma60']
        
        def get_trend_type(f):
            if pd.isna(f): return None
            if f > 0.02: return "上涨 (Bull)"
            if f < -0.02: return "下跌 (Bear)"
            return "横盘 (Sideways)"
        
        df['trend_type'] = df['trend_factor'].apply(get_trend_type)

        # 4. 获取当前状态
        current_state = df.iloc[-1]
        c_val_pct = current_state['val_pct']
        c_trend_type = current_state['trend_type']
        
        logging.info(f"--- Similarity Search for {etf_code} ({index_info['index_name']}) ---")
        logging.info(f"Current State: Val={c_val_pct:.1f}%, Trend={c_trend_type}")
        
        if pd.isna(c_val_pct) or c_trend_type is None:
            return {"error": "当前状态尚未稳定 (数据预热不足)"}

        # 5. 历史扫描匹配
        # 排除最近半年的数据，避免匹配到自己
        search_df = df.iloc[:-120].copy()
        
        # 匹配条件：
        # 1. 估值分位差异 < 7.5%
        # 2. 趋势类型一致
        matches = search_df[
            (search_df['val_pct'].sub(c_val_pct).abs() < 7.5) &
            (search_df['trend_type'] == c_trend_type)
        ].copy()
        
        logging.info(f"Search Range: {search_df.index[0].date()} -> {search_df.index[-1].date()}")
        logging.info(f"Matches Found: {len(matches)}")

        if matches.empty:
            return {
                "current": {
                    "val_pct": round(c_val_pct, 1), 
                    "trend": c_trend_type,
                    "index_name": index_info['index_name'],
                    "metric": val_col.upper()
                }, 
                "matches": []
            }

        # 6. 后验分析 (观察之后 120 个交易日的走势)
        results = []
        # 去重：如果两个匹配点靠得太近（比如在同一个月），只取一个
        last_added_date = None
        
        # 按日期倒序看（先看近期的相似点）
        for date, row in matches.sort_index(ascending=False).iterrows():
            if last_added_date and (last_added_date - date).days < 90:
                continue
            
            # 计算未来收益
            future_data = df_price[df_price.index > date].head(120)
            if len(future_data) < 60: continue # 数据不够观察
            
            start_p = row['close']
            end_p = future_data['close'].iloc[-1]
            future_ret = (end_p - start_p) / start_p * 100
            
            if future_ret > 10: label = "上涨 (Bull)"
            elif future_ret < -10: label = "下跌 (Bear)"
            else: label = "横盘 (Sideways)"
            
            # 计算相似度得分 (简单反比)
            similarity = 100 - abs(row['val_pct'] - c_val_pct) * 2
            
            results.append({
                "date": date.strftime('%Y-%m-%d'),
                "similarity": round(similarity, 1),
                "val_pct": round(row['val_pct'], 1),
                "future_ret": round(future_ret, 2),
                "future_label": label
            })
            
            last_added_date = date
            if len(results) >= 10: break

        return {
            "current": {
                "val_pct": round(c_val_pct, 1),
                "trend": c_trend_type,
                "index_name": index_info['index_name'],
                "metric": val_col.upper()
            },
            "matches": results,
            "kline": [
                {"date": d.strftime('%Y-%m-%d'), "price": p} 
                for d, p in df_price['close'].items()
            ]
        }
