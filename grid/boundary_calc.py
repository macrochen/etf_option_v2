import numpy as np
import pandas as pd
from grid.valuation_manager import ValuationManager

class DynamicGridBoundary:
    def __init__(self):
        self.vm = ValuationManager()

    def calculate_limits(self, etf_code: str, current_price: float, current_date: str = None):
        """
        计算动态上下限
        Returns: {
            "lower": float,
            "upper": float,
            "valuation": {
                "index_name": "沪深300",
                "metric": "PE",
                "current_val": 12.5,
                "percentile": 25.0,
                "status": "低估",
                ...
            }
        }
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
            
        # 3. 截取历史窗口 (过去 5 年)
        if current_date:
            target_dt = pd.to_datetime(current_date)
            df_hist = df_val[df_val.index <= target_dt]
        else:
            df_hist = df_val
            
        # 至少要有 1 年数据 (250条)
        if len(df_hist) < 20: 
             return self._fallback_default(current_price, "历史数据不足")

        # 4. 计算百分位 (优先 PE, 其次 PB)
        metric = 'pe'
        series = df_hist['pe'].dropna()
        # 简单清洗：去除 <= 0 的 PE (亏损)
        series = series[series > 0]
        
        if series.empty:
            metric = 'pb'
            series = df_hist['pb'].dropna()
            
        if series.empty:
             return self._fallback_default(current_price, "有效估值数据不足")
             
        current_val = series.iloc[-1]
        
        # 历史极值锚点
        val_low_10 = np.percentile(series, 10)
        val_high_85 = np.percentile(series, 85)
        
        # 当前百分位
        rank_pct = (series < current_val).mean() * 100
        
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
                "index_name": index_name,
                "metric": metric.upper(),
                "current_val": round(current_val, 2),
                "percentile": round(rank_pct, 1),
                "status": status,
                "history_low_10": round(val_low_10, 2),
                "history_high_85": round(val_high_85, 2)
            }
        }

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
