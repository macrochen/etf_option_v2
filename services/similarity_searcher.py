import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from grid.min_data_loader import MinDataLoader
from grid.valuation_manager import ValuationManager


class SimilaritySearcher:
    def __init__(self):
        self.vm = ValuationManager()
        self.dl = MinDataLoader()

    def _build_atr_snapshot(self, df_price: pd.DataFrame, window_start_date=None):
        """基于日线价格计算当前 ATR20 百分比与历史分位。"""
        if df_price.empty:
            return None

        df = df_price[['open', 'high', 'low', 'close']].copy().sort_index()
        df['prev_close'] = df['close'].shift(1)
        tr_components = pd.concat([
            (df['high'] - df['low']).abs(),
            (df['high'] - df['prev_close']).abs(),
            (df['low'] - df['prev_close']).abs(),
        ], axis=1)
        df['tr'] = tr_components.max(axis=1)
        df['atr20'] = df['tr'].rolling(20).mean()
        df['atr20_pct'] = np.where(df['close'] > 0, df['atr20'] / df['close'], np.nan)

        hist = df.dropna(subset=['atr20_pct']).copy()
        if window_start_date:
            start_dt = pd.to_datetime(window_start_date)
            hist = hist[hist.index >= start_dt]

        if hist.empty:
            return None

        current_row = hist.iloc[-1]
        current_atr_pct = float(current_row['atr20_pct'])
        rank_pct = float((hist['atr20_pct'] < current_atr_pct).mean() * 100)

        if rank_pct < 20:
            status = '低波动'
        elif rank_pct > 80:
            status = '高波动'
        else:
            status = '适中'

        return {
            'atr20_pct': round(current_atr_pct * 100, 2),
            'percentile': round(rank_pct, 1),
            'status': status,
            'window_start': hist.index[0].strftime('%Y-%m-%d'),
            'window_end': hist.index[-1].strftime('%Y-%m-%d'),
            'actual_date': hist.index[-1].strftime('%Y-%m-%d')
        }

    def _prepare_similarity_context(self, etf_code: str, metric_preference: str = 'auto', sync_price_data: bool = False, as_of_date: str | None = None):
        index_info = self.vm.get_index_for_etf(etf_code, allow_api_update=False)
        if not index_info:
            logging.info(f"ETF mapping for {etf_code} missing in local DB, falling back to API...")
            index_info = self.vm.get_index_for_etf(etf_code, allow_api_update=True)
        if not index_info:
            return {'error': '未找到 ETF 对应指数映射'}
        index_code = index_info['index_code']

        if sync_price_data:
            logging.info(f"Updating price data for {etf_code}...")
            self.dl.update_data(etf_code)
        else:
            logging.info(f"Loading cached price data for {etf_code} from local DB...")
        df_price = self.dl.load_daily_data(etf_code)

        logging.info(f"Loading cached valuation history for {index_code} from local DB...")
        self.vm.ensure_valuation_ranks(index_code)
        df_val = self.vm.get_valuation_history(index_code, allow_api_update=False)
        if df_val.empty:
            logging.info(f"Valuation history for {index_code} missing in local DB, falling back to API...")
            df_val = self.vm.get_valuation_history(index_code, allow_api_update=True)
            self.vm.ensure_valuation_ranks(index_code)

        if df_val.empty or df_price.empty:
            return {'error': '数据不足，无法进行匹配'}

        df_price = df_price.copy()
        df_price['date'] = pd.to_datetime(df_price['date'])
        df_price = df_price.set_index('date').sort_index()
        df_val = df_val.copy()
        df_val.index = pd.to_datetime(df_val.index)

        if as_of_date:
            as_of_dt = pd.to_datetime(as_of_date)
            df_price = df_price[df_price.index <= as_of_dt]
            df_val = df_val[df_val.index <= as_of_dt]

        use_pe = True
        if metric_preference == 'pb':
            use_pe = False
        elif metric_preference == 'auto' and not df_val['pe'].notnull().any():
            use_pe = False

        val_col = 'pe' if use_pe else 'pb'
        rank_col = f'{val_col}_rank'
        df_val['val_pct'] = df_val[rank_col]

        df = df_price[['open', 'high', 'low', 'close']].join(df_val[['pe', 'pb', 'val_pct']], how='inner')
        if df.empty:
            return {'error': '价格与估值数据无法对齐'}

        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['trend_factor'] = (df['ma20'] - df['ma60']) / df['ma60']

        def get_trend_type(f):
            if pd.isna(f):
                return None
            if f > 0.02:
                return '上涨 (Bull)'
            if f < -0.02:
                return '下跌 (Bear)'
            return '横盘 (Sideways)'

        df['trend_type'] = df['trend_factor'].apply(get_trend_type)
        if df.empty:
            return {'error': '数据对齐后为空，无法获取当前状态'}

        current_state = df.iloc[-1]
        c_val_pct = current_state['val_pct']
        c_trend_type = current_state['trend_type']
        if pd.isna(c_val_pct) or c_trend_type is None:
            logging.error(f"Failed to determine current state. Val Pct: {c_val_pct}, Trend: {c_trend_type}")
            return {'error': '当前状态尚未稳定 (数据预热不足或历史分位无法计算)'}

        current_data = {
            'val_pct': round(float(c_val_pct), 1),
            'val_value': round(float(current_state[val_col]), 2),
            'trend': c_trend_type,
            'index_name': index_info['index_name'],
            'metric': val_col.upper(),
            'volatility': self._build_atr_snapshot(df_price)
        }

        kline_data = []
        for d, row in df.iterrows():
            kline_data.append({
                'date': d.strftime('%Y-%m-%d'),
                'price': row['close'],
                'pe': row['pe'] if pd.notna(row['pe']) else None,
                'pb': row['pb'] if pd.notna(row['pb']) else None
            })

        return {
            'index_info': index_info,
            'df_price': df_price,
            'df': df,
            'val_col': val_col,
            'current_state': current_state,
            'current_data': current_data,
            'kline_data': kline_data,
        }

    def _find_match_rows(self, df: pd.DataFrame, current_state: pd.Series):
        c_val_pct = current_state['val_pct']
        c_trend_type = current_state['trend_type']
        search_df = df.iloc[:-120].copy()
        matches = search_df[
            (search_df['val_pct'].sub(c_val_pct).abs() < 7.5) &
            (search_df['trend_type'] == c_trend_type)
        ].copy()
        return matches.sort_index(ascending=False)

    def find_similar_moments(self, etf_code: str, top_n=5, metric_preference: str = 'auto'):
        """寻找历史相似时刻。"""
        ctx = self._prepare_similarity_context(etf_code, metric_preference=metric_preference)
        if ctx.get('error'):
            return {'error': ctx['error']}

        df = ctx['df']
        df_price = ctx['df_price']
        current_state = ctx['current_state']
        current_data = ctx['current_data']
        kline_data = ctx['kline_data']

        matches = self._find_match_rows(df, current_state)
        if matches.empty:
            return {'current': current_data, 'matches': [], 'kline': kline_data}

        results = []
        last_added_date = None
        c_val_pct = current_state['val_pct']

        for date, row in matches.iterrows():
            if last_added_date and (last_added_date - date).days < 90:
                continue

            future_data = df_price[df_price.index > date].head(120)
            if len(future_data) < 60:
                continue

            start_p = float(row['close'])
            end_p = float(future_data['close'].iloc[-1])
            future_ret = (end_p - start_p) / start_p * 100

            if future_ret > 10:
                label = '上涨 (Bull)'
            elif future_ret < -10:
                label = '下跌 (Bear)'
            else:
                label = '横盘 (Sideways)'

            similarity = 100 - abs(float(row['val_pct']) - float(c_val_pct)) * 2
            results.append({
                'date': date.strftime('%Y-%m-%d'),
                'similarity': round(similarity, 1),
                'val_pct': round(float(row['val_pct']), 1),
                'future_ret': round(future_ret, 2),
                'future_label': label
            })
            last_added_date = date
            if len(results) >= max(top_n, 10):
                break

        return {
            'current': current_data,
            'matches': results[:top_n] if top_n else results,
            'kline': kline_data
        }

    def estimate_planner_edge(self, etf_code: str, current_price: float, lower: float, upper: float,
                              metric_preference: str = 'auto', horizon: int = 120, max_matches: int = 10,
                              as_of_date: str | None = None):
        """基于历史相似样本估算当前规划先到上限/先到下限的经验概率。"""
        if current_price <= 0 or lower <= 0 or upper <= current_price or lower >= current_price:
            return {'error': '规划参数无效，需满足 lower < current_price < upper'}

        ctx = self._prepare_similarity_context(
            etf_code,
            metric_preference=metric_preference,
            as_of_date=as_of_date,
        )
        if ctx.get('error'):
            return {'error': ctx['error']}

        df = ctx['df']
        df_price = ctx['df_price']
        current_state = ctx['current_state']
        matches = self._find_match_rows(df, current_state)
        if matches.empty:
            return {
                'sample_count': 0,
                'resolved_count': 0,
                'up_count': 0,
                'down_count': 0,
                'tie_count': 0,
                'no_hit_count': 0,
                'win_rate': None,
                'samples': []
            }

        upper_mult = upper / current_price
        lower_mult = lower / current_price
        results = []
        last_added_date = None

        for date, row in matches.iterrows():
            if last_added_date and (last_added_date - date).days < 90:
                continue

            future_data = df_price[df_price.index > date].head(horizon)
            if len(future_data) < 20:
                continue

            start_price = float(row['close'])
            hit_upper = start_price * upper_mult
            hit_lower = start_price * lower_mult
            outcome = 'no_hit'
            hit_date = None

            for future_date, future_row in future_data.iterrows():
                up_hit = float(future_row['high']) >= hit_upper
                down_hit = float(future_row['low']) <= hit_lower
                if up_hit and down_hit:
                    outcome = 'tie'
                    hit_date = future_date
                    break
                if up_hit:
                    outcome = 'up'
                    hit_date = future_date
                    break
                if down_hit:
                    outcome = 'down'
                    hit_date = future_date
                    break

            similarity = 100 - abs(float(row['val_pct']) - float(current_state['val_pct'])) * 2
            results.append({
                'date': date.strftime('%Y-%m-%d'),
                'similarity': round(similarity, 1),
                'start_price': round(start_price, 4),
                'mapped_upper': round(hit_upper, 4),
                'mapped_lower': round(hit_lower, 4),
                'outcome': outcome,
                'hit_date': hit_date.strftime('%Y-%m-%d') if hit_date is not None else None
            })
            last_added_date = date
            if len(results) >= max_matches:
                break

        up_count = sum(1 for item in results if item['outcome'] == 'up')
        down_count = sum(1 for item in results if item['outcome'] == 'down')
        tie_count = sum(1 for item in results if item['outcome'] == 'tie')
        no_hit_count = sum(1 for item in results if item['outcome'] == 'no_hit')
        resolved_count = up_count + down_count
        win_rate = (up_count / resolved_count) if resolved_count > 0 else None

        return {
            'sample_count': len(results),
            'resolved_count': resolved_count,
            'up_count': up_count,
            'down_count': down_count,
            'tie_count': tie_count,
            'no_hit_count': no_hit_count,
            'win_rate': round(win_rate * 100, 1) if win_rate is not None else None,
            'samples': results
        }
