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
        寻找历史相似时刻 (Refactored)
        """
        # 1. 获取基础数据
        index_info = self.vm.get_index_for_etf(etf_code)
        if not index_info:
            return {"error": "未找到跟踪指数"}
        index_code = index_info['index_code']

        # 2. 更新并加载价格数据
        logging.info(f"Updating price data for {etf_code}...")
        self.dl.update_data(etf_code)
        df_price = self.dl.load_daily_data(etf_code)
        
        # 3. 更新估值数据并确保计算了分位
        logging.info(f"Updating and calculating valuation ranks for {index_code}...")
        self.vm.ensure_valuation_ranks(index_code)

        # 4. 加载最终的、包含分位的估值数据
        df_val = self.vm.get_valuation_history(index_code)

        if df_val.empty or df_price.empty:
            return {"error": "数据不足，无法进行匹配"}

        # 5. 数据处理与对齐
        df_price['date'] = pd.to_datetime(df_price['date'])
        df_price = df_price.set_index('date').sort_index()
        df_val.index = pd.to_datetime(df_val.index)
        
        logging.info(f"Price Range: {df_price.index[0].date()} -> {df_price.index[-1].date()} (Count: {len(df_price)})")
        logging.info(f"Valuation Range: {df_val.index[0].date()} -> {df_val.index[-1].date()} (Count: {len(df_val)})")

        # 6. 选择指标并使用缓存的 Rank
        use_pe = True
        if metric_preference == 'pb':
            use_pe = False
        elif metric_preference == 'auto':
            if not df_val['pe'].notnull().any():
                use_pe = False
        
        val_col = 'pe' if use_pe else 'pb'
        rank_col = f'{val_col}_rank'
        df_val['val_pct'] = df_val[rank_col]
        logging.info(f"Using Metric for Similarity: {val_col.upper()} (Pre-calculated)")

        # --- TEMPORARY DEBUGGING ---
        logging.info("--- Start: Data Snapshot BEFORE JOIN ---")
        logging.info("--- df_price (last 15) ---")
        logging.info(df_price.tail(15).to_string())
        logging.info("--- df_val (last 15) ---")
        logging.info(df_val.tail(15).to_string())
        logging.info("--- End: Data Snapshot BEFORE JOIN ---")
        # --- END TEMP DEBUGGING ---

        # 7. 合并估值分位到价格数据
        df = df_price[['close']].join(df_val[['pe', 'pb', 'val_pct']], how='inner')
        if df.empty:
            return {"error": "价格与估值数据无法对齐"}
            
        # 8. 计算趋势因子
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['trend_factor'] = (df['ma20'] - df['ma60']) / df['ma60']
        
        def get_trend_type(f):
            if pd.isna(f): return None
            if f > 0.02: return "上涨 (Bull)"
            if f < -0.02: return "下跌 (Bear)"
            return "横盘 (Sideways)"
        
        df['trend_type'] = df['trend_factor'].apply(get_trend_type)

        # 9. 获取当前状态
        if df.empty:
            return {"error": "数据对齐后为空，无法获取当前状态"}
            
        current_state = df.iloc[-1]
        c_val_pct = current_state['val_pct']
        c_trend_type = current_state['trend_type']
        
        logging.info(f"--- Similarity Search for {etf_code} ({index_info['index_name']}) ---")
        
        if pd.isna(c_val_pct) or c_trend_type is None:
            # 提供更详细的调试信息
            logging.error(f"Failed to determine current state. Val Pct: {c_val_pct}, Trend: {c_trend_type}")
            logging.error(f"Last available date in joined data: {current_state.name.date()}")
            logging.error(f"Last PE: {current_state.get('pe')}, Last PB: {current_state.get('pb')}")
            return {"error": "当前状态尚未稳定 (数据预热不足或历史分位无法计算)"}

        logging.info(f"Current State: Val={c_val_pct:.1f}%, Trend={c_trend_type}")
        logging.info(f"Manual check for current date: Metric={val_col.upper()}, Value={current_state[val_col]}, Rank={c_val_pct:.2f}%")

        # 10. 历史扫描匹配
        search_df = df.iloc[:-120].copy()
        
        matches = search_df[
            (search_df['val_pct'].sub(c_val_pct).abs() < 7.5) &
            (search_df['trend_type'] == c_trend_type)
        ].copy()
        
        logging.info(f"Search Range: {search_df.index[0].date()} -> {search_df.index[-1].date()}")
        logging.info(f"Matches Found: {len(matches)}")

        kline_data = []
        for d, row in df.iterrows():
            kline_data.append({
                "date": d.strftime('%Y-%m-%d'),
                "price": row['close'],
                "pe": row['pe'] if pd.notna(row['pe']) else None,
                "pb": row['pb'] if pd.notna(row['pb']) else None
            })

        current_data = {
            "val_pct": round(c_val_pct, 1), 
            "val_value": round(current_state[val_col], 2),
            "trend": c_trend_type,
            "index_name": index_info['index_name'],
            "metric": val_col.upper()
        }

        if matches.empty:
            return {"current": current_data, "matches": [], "kline": kline_data}

        # 11. 后验分析
        results = []
        last_added_date = None
        
        for date, row in matches.sort_index(ascending=False).iterrows():
            if last_added_date and (last_added_date - date).days < 90:
                continue
            
            future_data = df_price[df_price.index > date].head(120)
            if len(future_data) < 60: continue
            
            start_p = row['close']
            end_p = future_data['close'].iloc[-1]
            future_ret = (end_p - start_p) / start_p * 100
            
            if future_ret > 10: label = "上涨 (Bull)"
            elif future_ret < -10: label = "下跌 (Bear)"
            else: label = "横盘 (Sideways)"
            
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
            "current": current_data,
            "matches": results,
            "kline": kline_data
        }

