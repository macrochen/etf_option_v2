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

        # 2. 数据处理与对齐
        df_price['date'] = pd.to_datetime(df_price['date'])
        df_price = df_price.set_index('date').sort_index()
        
        # 确保估值数据也是 datetime 索引
        df_val.index = pd.to_datetime(df_val.index)
        
        logging.info(f"Price Range: {df_price.index[0].date()} -> {df_price.index[-1].date()} (Count: {len(df_price)})")
        logging.info(f"Valuation Range: {df_val.index[0].date()} -> {df_val.index[-1].date()} (Count: {len(df_val)})")

        # 3. 在全量估值历史(指数)上计算特征指标 (参考香农策略：先算分位，再对齐价格)
        # 根据偏好选择指标
        use_pe = True
        if metric_preference == 'pb':
            use_pe = False
        elif metric_preference == 'auto':
            if not df_val['pe'].notnull().any():
                use_pe = False
        
        index_code = index_info['index_code']
        
        # 确保估值 Rank 已缓存
        self.vm.ensure_valuation_ranks(index_code)
        
        # 获取全量估值历史
        df_val = self.vm.get_valuation_history(index_code)
        # 获取全量价格历史 (日线)
        df_price = self.dl.load_daily_data(etf_code)
        
        if df_val.empty or df_price.empty:
            return {"error": "数据不足，无法进行匹配"}

        # 2. 数据处理与对齐
        df_price['date'] = pd.to_datetime(df_price['date'])
        df_price = df_price.set_index('date').sort_index()
        
        # 确保估值数据也是 datetime 索引
        df_val.index = pd.to_datetime(df_val.index)
        
        logging.info(f"Price Range: {df_price.index[0].date()} -> {df_price.index[-1].date()} (Count: {len(df_price)})")
        logging.info(f"Valuation Range: {df_val.index[0].date()} -> {df_val.index[-1].date()} (Count: {len(df_val)})")

        # 3. 选择指标并使用缓存的 Rank
        # 根据偏好选择指标
        use_pe = True
        if metric_preference == 'pb':
            use_pe = False
        elif metric_preference == 'auto':
            if not df_val['pe'].notnull().any():
                use_pe = False
        
        val_col = 'pe' if use_pe else 'pb'
        rank_col = f'{val_col}_rank'
        
        logging.info(f"Using Metric for Similarity: {val_col.upper()} (Pre-calculated)")
        
        # 直接使用数据库中的 Rank (val_pct)
        # 过滤掉 Rank 为空的数据 (比如前 1 年的预热期)
        # 注意：这里我们给 df_val 赋值一个新的列名 'val_pct' 以便后续合并
        df_val['val_pct'] = df_val[rank_col]

        # 4. 合并估值分位到价格数据
        # 此时得到的 df 的 val_pct 是基于指数完整历史背景的
        df = df_price[['close']].join(df_val[['pe', 'pb', 'val_pct']], how='inner')
        if df.empty:
            return {"error": "价格与估值数据无法对齐"}
            
        # 5. 计算趋势因子 (在对齐后的数据上计算)
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['trend_factor'] = (df['ma20'] - df['ma60']) / df['ma60']
        
        def get_trend_type(f):
            if pd.isna(f): return None
            if f > 0.02: return "上涨 (Bull)"
            if f < -0.02: return "下跌 (Bear)"
            return "横盘 (Sideways)"
        
        df['trend_type'] = df['trend_factor'].apply(get_trend_type)

        # 6. 获取当前状态
        current_state = df.iloc[-1]
        c_val_pct = current_state['val_pct']
        c_trend_type = current_state['trend_type']
        
        logging.info(f"--- Similarity Search for {etf_code} ({index_info['index_name']}) ---")
        logging.info(f"Current State: Val={c_val_pct:.1f}%, Trend={c_trend_type}")
        
        # 检查最后一日的计算详情
        logging.info(f"Manual check for current date: Metric={val_col.upper()}, Value={current_state[val_col]}, Rank={c_val_pct:.2f}%")
        
        if pd.isna(c_val_pct) or c_trend_type is None:
            return {"error": "当前状态尚未稳定 (数据预热不足或历史分位无法计算)"}

        # 7. 历史扫描匹配
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

        # 构造 K 线数据 (含估值)
        kline_data = []
        for d, row in df.iterrows():
            kline_data.append({
                "date": d.strftime('%Y-%m-%d'),
                "price": row['close'],
                "pe": row['pe'] if pd.notna(row['pe']) else None,
                "pb": row['pb'] if pd.notna(row['pb']) else None
            })

        if matches.empty:
            return {
                "current": {
                    "val_pct": round(c_val_pct, 1), 
                    "val_value": round(current_state[val_col], 2),
                    "trend": c_trend_type,
                    "index_name": index_info['index_name'],
                    "metric": val_col.upper()
                }, 
                "matches": [],
                "kline": kline_data
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
                "val_value": round(current_state[val_col], 2),
                "trend": c_trend_type,
                "index_name": index_info['index_name'],
                "metric": val_col.upper()
            },
            "matches": results,
            "kline": kline_data
        }
