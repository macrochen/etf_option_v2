import logging
import numpy as np
import pandas as pd
from grid.valuation_manager import ValuationManager

class DynamicGridBoundary:
    def __init__(self):
        self.vm = ValuationManager()

    def calculate_limits(self, etf_code: str, current_price: float, current_date: str = None, metric_preference: str = 'auto'):
        """
        计算动态上下限
        :param metric_preference: 'auto', 'pe', 'pb'
        """
        # 1. 获取对应指数
        index_info = self.vm.get_index_for_etf(etf_code)
        if not index_info:
            return self._fallback_default(current_price, "未找到跟踪指数")
            
        index_code = index_info['index_code']
        index_name = index_info['index_name']
        
        # 2. 获取估值历史
        df_val = self.vm.get_valuation_history(index_code)
        
        if df_val.empty:
            return self._fallback_default(current_price, "暂无估值数据")
            
    def _get_valuation_window(self, df, min_years=3, max_years=5):
        """
        智能截取估值计算的时间窗口 (参考香农策略)
        """
        if df.empty:
            return df, "无数据"
            
        # 1. 计算数据总时长
        start_date = df.index[0]
        end_date = df.index[-1]
        total_days = (end_date - start_date).days
        total_years = total_days / 365.25
        
        logging.info(f"Data Duration: {total_years:.2f} years ({start_date.date()} -> {end_date.date()})")

        # 2. 决策逻辑
        if total_years >= max_years:
            # 情况 A: 数据充足 -> 截取最近 5 年
            # 使用日期切片而非行数切片，以应对数据稀疏的情况
            cutoff_date = end_date - pd.DateOffset(years=max_years)
            valid_df = df[df.index >= cutoff_date]
            return valid_df, f"Level A: 截取最近{max_years}年 ({cutoff_date.date()}之后)"
            
        elif total_years >= min_years:
            # 情况 B: 数据尚可 -> 使用全部历史
            return df, f"Level B: 数据不足{max_years}年，使用全部"
            
        else:
            # 情况 C: 数据太少 -> 报警
            return df, f"Level C: 数据不足{min_years}年 (警告:样本失效)"

    def calculate_limits(self, etf_code: str, current_price: float, current_date: str = None, metric_preference: str = 'auto'):
        """
        计算动态上下限
        :param metric_preference: 'auto', 'pe', 'pb'
        """
        # 1. 获取对应指数
        index_info = self.vm.get_index_for_etf(etf_code)
        if not index_info:
            return self._fallback_default(current_price, "未找到跟踪指数")
            
        index_code = index_info['index_code']
        index_name = index_info['index_name']
        
        # 2. 获取估值历史
        df_val = self.vm.get_valuation_history(index_code)
        
        if df_val.empty:
            return self._fallback_default(current_price, "暂无估值数据")
            
        # 3. 截取历史窗口 (截止到当前日期)
        if current_date:
            target_dt = pd.to_datetime(current_date)
            # 先切掉未来数据
            df_available = df_val[df_val.index <= target_dt]
        else:
            df_available = df_val
            
        # 4. 应用智能窗口选择策略
        df_hist, strategy_msg = self._get_valuation_window(df_available)
        
        # Logging Debug Info
        start_dt_log = df_hist.index[0] if not df_hist.empty else "N/A"
        end_dt_log = df_hist.index[-1] if not df_hist.empty else "N/A"
        count_log = len(df_hist)
        
        # 至少要有 1 年数据 (250条)
        # 注意：Level C 虽然报警但也会返回数据，这里做最终兜底
        if len(df_hist) < 20: 
             logging.warning(f"Insufficient valuation history for {etf_code}: {count_log} records.")
             return self._fallback_default(current_price, "历史数据不足")

        # 5. 计算百分位 (根据偏好选择)
        metric = 'pe' # 默认
        series = pd.Series(dtype=float)
        
        # 辅助函数：获取有效序列
        def get_series(m):
            s = df_hist[m].dropna()
            if m == 'pe':
                s = s[s > 0] # 去除亏损
            return s

        if metric_preference == 'pe':
            series = get_series('pe')
            metric = 'pe'
            # 如果强制指定但无数据，尝试回退 PB? 或者直接报错?
            # 策略：如果无数据，降级回 auto 逻辑并标记
            if series.empty:
                metric_preference = 'auto' # Fallback
                
        if metric_preference == 'pb':
            series = get_series('pb')
            metric = 'pb'
            if series.empty:
                metric_preference = 'auto'

        # Auto 逻辑 (或 Fallback)
        if metric_preference == 'auto':
            # 优先 PE
            series = get_series('pe')
            metric = 'pe'
            if series.empty:
                series = get_series('pb')
                metric = 'pb'
            
        if series.empty:
             return self._fallback_default(current_price, "有效估值数据不足")
             
        current_val = series.iloc[-1]
        val_min = series.min()
        val_max = series.max()
        val_min_date = series.idxmin()
        val_max_date = series.idxmax()
        
        # 历史极值锚点
        val_low_10 = np.percentile(series, 10)
        val_high_85 = np.percentile(series, 85)
        
        # 当前百分位
        rank_pct = (series < current_val).mean() * 100
        
        # DEBUG LOGGING
        logging.info(f"--- Valuation Calc Debug for {etf_code} ---")
        logging.info(f"Metric: {metric.upper()}")
        logging.info(f"Strategy: {strategy_msg}")
        logging.info(f"Window: {start_dt_log} -> {end_dt_log} (Count: {count_log})")
        logging.info(f"Values: Min={val_min:.2f} (on {val_min_date}), Max={val_max:.2f} (on {val_max_date}), Current={current_val:.2f}")
        logging.info(f"Percentiles: 10%={val_low_10:.2f}, 85%={val_high_85:.2f}")
        logging.info(f"Calculated Rank: {rank_pct:.2f}%")
        
        # 5. 映射回价格 (Price Mapping)
        # Price_Target = Price_Current * (Val_Target / Val_Current)
        if current_val <= 0:
             return self._fallback_default(current_price)
             
        limit_lower = current_price * (val_low_10 / current_val)
        limit_upper = current_price * (val_high_85 / current_val)
        
        # 6. 香农安全边际修正
        # A: 下限防护 - 至少跌 15%
        max_lower = current_price * 0.85
        limit_lower = min(limit_lower, max_lower)
        
        # B: 上限空间 - 至少涨 20%，至多涨 150% (2.5倍)
        min_upper = current_price * 1.2
        max_upper = current_price * 2.5
        limit_upper = max(limit_upper, min_upper)
        limit_upper = min(limit_upper, max_upper)
        
        # 状态文案
        if rank_pct < 20: status = "低估 (Undervalued)"
        elif rank_pct > 80: status = "高估 (Overvalued)"
        else: status = "适中 (Fair)"
        
        return {
            "lower": round(limit_lower, 3),
            "upper": round(limit_upper, 3),
            "valuation": {
                "index_code": index_code,
                "index_name": index_name,
                "metric": metric.upper(),
                "current_val": round(current_val, 2),
                "percentile": round(rank_pct, 1),
                "status": status,
                "history_low_10": round(val_low_10, 2),
                "history_high_85": round(val_high_85, 2)
            }
        }

    def calculate_rolling_limits(self, etf_code: str, start_date: str = None, metric_preference: str = 'auto'):
        """
        批量计算滚动估值分位序列 (用于回测)
        返回: DataFrame (index=date, cols=[limit_lower_val, limit_upper_val])
        注意：这里返回的是"估值指标"的上下限(如PE值)，而非价格。
        价格上下限需要在回测时结合当时的 Close Price 动态计算：
        Price_Lower = Current_Price * (Limit_Lower_Val / Current_Val)
        """
        # 1. 获取对应指数
        index_info = self.vm.get_index_for_etf(etf_code)
        if not index_info:
            return pd.DataFrame()
            
        index_code = index_info['index_code']
        df_val = self.vm.get_valuation_history(index_code)
        
        if df_val.empty:
            return pd.DataFrame()
            
        # 2. 确定指标 (PE vs PB)
        # 简单策略：如果 PE 数据质量好就用 PE，否则 PB
        # 为了回测一致性，我们需要在全时段使用同一个指标，或者分段？
        # 简单起见，检测最近的非空值来决定
        use_pe = True
        if metric_preference == 'pb':
            use_pe = False
        elif metric_preference == 'auto':
            # 检查 PE 是否有太多缺失或负值
            valid_pe = df_val['pe'][df_val['pe'] > 0].count()
            valid_pb = df_val['pb'][df_val['pb'] > 0].count()
            if valid_pe < valid_pb * 0.5: # PE 质量太差
                use_pe = False
        
        col = 'pe' if use_pe else 'pb'
        series = df_val[col]
        # 过滤负值干扰 (PE<0 通常无意义)
        series = series.where(series > 0)
        
        # 3. 滚动计算分位数
        # 窗口：5年 (1250天)
        # 最小样本：1年 (250天)
        roll = series.rolling(window=1250, min_periods=250)
        
        df_res = pd.DataFrame(index=df_val.index)
        df_res['val_low'] = roll.quantile(0.10)
        df_res['val_high'] = roll.quantile(0.85)
        df_res['current_val'] = series
        
        # 4. 关键：Shift(1) 防未来函数
        # 今天的阈值，只能由昨天及以前的数据算出
        df_res = df_res.shift(1)
        
        # 5. 截取回测区间
        # 如果提供了 start_date，我们只需要 start_date 之后的数据
        # 但必须保留 start_date 之前的数据用于 rolling 计算 (上面已经算完了)
        if start_date:
            df_res = df_res[df_res.index >= pd.to_datetime(start_date)]
            
        return df_res

    def _fallback_default(self, price, reason="暂无估值数据"):
        return {
            "lower": round(price * 0.7, 3),
            "upper": round(price * 1.3, 3),
            "valuation": {
                "status": f"默认 ({reason})",
                "percentile": 50.0, # Dummy
                "index_name": "-"
            }
        }