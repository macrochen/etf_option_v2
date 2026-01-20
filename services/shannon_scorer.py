import numpy as np
import pandas as pd

class ShannonGridScorer:
    def __init__(self, df_history):
        """
        初始化评分器
        :param df_history: 包含 'date', 'open', 'high', 'low', 'close' 的 DataFrame (日线数据)
                           数据长度建议至少 3-5 年 (约 750-1200 行)
        """
        # 确保按时间排序
        if 'date' in df_history.columns:
            self.df = df_history.sort_values('date').reset_index(drop=True)
        else:
            self.df = df_history.reset_index(drop=True)
            
        self.close = self.df['close'].values
        self.high = self.df['high'].values
        self.low = self.df['low'].values
        self.total_len = len(self.df)

    def _calc_ma_crossings(self, prices, window=250):
        """核心算法：计算均线穿越频率 (Mean Reversion Capability)"""
        if len(prices) < window: return 0
        
        # 计算 MA
        ma = pd.Series(prices).rolling(window).mean()
        # 填充 NaN 以防报错
        ma = ma.bfill().values 
        
        crossings = 0
        # 从 window 开始统计
        for i in range(window, len(prices)):
            # 穿越逻辑：(前一天 < MA and 今天 > MA) or (前一天 > MA and 今天 < MA)
            if (prices[i-1] < ma[i-1] and prices[i] > ma[i]) or \
               (prices[i-1] > ma[i-1] and prices[i] < ma[i]):
                crossings += 1
                
        # 归一化：每 100 天穿越多少次
        valid_days = len(prices) - window
        if valid_days <= 0: return 0
        
        frequency = (crossings / valid_days) * 100
        return frequency

    def _calc_volatility_energy(self, high, low, close, pre_close):
        """
        V2.0 优化版：短期热度计算 (Amplitude Energy)
        1. 使用 True Range (TR) 捕捉跳空缺口
        2. 使用 Median (中位数) 剔除极端值干扰
        """
        # 确保数据对齐，长度一致
        n = len(close)
        if n < 1: return 0
        
        tr_list = []
        for i in range(n):
            h = high[i]
            l = low[i]
            c = close[i]
            pc = pre_close[i] # 对应日期的昨收
            
            # 核心修正：计算真实波幅 TR
            # TR = max(H-L, |H-PC|, |L-PC|)
            tr = max(h - l, abs(h - pc), abs(l - pc))
            
            # 归一化为百分比 (相对于当前价格)
            # 注意：原代码是用 c 分母，合理。
            if c == 0: continue
            tr_pct = tr / c * 100
            tr_list.append(tr_pct)
            
        if not tr_list: return 0
        
        # 核心修正：使用中位数 (Median) 代替平均值 (Mean)
        median_tr = np.median(tr_list)
        
        return median_tr

    def _calc_price_rank(self, current_p, history_p):
        """核心算法：计算价格分位数 (Safety Rank)"""
        if len(history_p) == 0: return 50
        # 0% 是历史最低（最安全），100% 是历史最高（最危险）
        min_p = np.min(history_p)
        max_p = np.max(history_p)
        if max_p == min_p: return 50
        rank = (current_p - min_p) / (max_p - min_p) * 100
        return rank

    def calculate_score(self):
        """
        执行评分逻辑 (V2.0 修正版：适配牛市与强趋势)
        """
        if self.total_len < 30:
            return {
                "total_score": 0,
                "error": "数据不足 (需至少30天)",
                "details": {"long_term_gene": 0, "mid_term_safety": 0, "short_term_heat": 0},
                "raw_metrics": {"cross_frequency": 0, "price_rank": 0, "recent_amplitude": 0}
            }

        # ------------------------------------------------------
        # 1. 长期基因 (Long Term) - 改用 MA20 穿越
        # ------------------------------------------------------
        # 逻辑：MA20 是布林带中轨，反映“中频震荡”属性。
        lookback_long = 750 # 3年
        if self.total_len > lookback_long:
            data_long_close = self.close[-lookback_long:]
        else:
            data_long_close = self.close
        
        # 【关键修改】使用 MA20 (window=20) 而非 MA250
        cross_freq = self._calc_ma_crossings(data_long_close, window=20) 
        
        # 评分标准调整：MA20 穿越非常频繁，阈值提高
        # > 15次/100天 (极度活跃) = 100分
        # < 5次/100天 (单边逼空或阴跌) = 0分
        score_long = np.interp(cross_freq, [5, 15], [0, 100])
        
        # ------------------------------------------------------
        # 2. 中期安全 (Medium Term) - 扩大窗口至 4-5 年
        # ------------------------------------------------------
        # 逻辑：拉长历史视野，避免牛市初期因短期涨幅过大而误判高估。
        lookback_mid = 1000 # 约 4 年，覆盖一个完整的牛熊周期
        if self.total_len > lookback_mid:
            data_mid = self.close[-lookback_mid:]
        else:
            data_mid = self.close # 数据不够就用全部
            
        current_price = self.close[-1]
        rank = self._calc_price_rank(current_price, data_mid)
        
        # 评分标准：Rank 越低分越高
        # 20% 分位以下满分，80% 分位以上零分
        score_mid = np.interp(rank, [20, 80], [100, 0])

        # ------------------------------------------------------
        # 3. 短期热度 (Short Term) - V2.0 真实波幅 & 中位数
        # ------------------------------------------------------
        # 逻辑：使用 True Range 捕捉跳空，使用 Median 过滤噪音。
        lookback_short = 60
        
        # 准备数据：需要过去 60 天的数据，以及每一天对应的"昨收"
        # 所以我们需要取过去 61 天的数据，前 60 天作为 pre_close
        
        if self.total_len > lookback_short + 1:
            # 取最后 60 天
            s_idx = -lookback_short
            high_short = self.high[s_idx:]
            low_short = self.low[s_idx:]
            close_short = self.close[s_idx:]
            
            # 昨收：从 -61 到 -1
            pre_close_short = self.close[-(lookback_short+1):-1]
        else:
            # 数据不足 61 天，只能尽力而为
            # 第一天没有昨收，忽略
            high_short = self.high[1:]
            low_short = self.low[1:]
            close_short = self.close[1:]
            pre_close_short = self.close[:-1]
        
        recent_amp = self._calc_volatility_energy(high_short, low_short, close_short, pre_close_short)
        
        # 评分标准：日均真实波幅 > 2.5% 满分 (TR通常比Amplitude大，稍微提高标准)
        score_short = np.interp(recent_amp, [0.5, 2.5], [0, 100])

        # 4. 加权汇总
        # 原逻辑：40% 基因 + 30% 安全 + 30% 热度
        total_score = (score_long * 0.4) + (score_mid * 0.3) + (score_short * 0.3)
        is_bull_exemption = False

        # 【V2.1 补丁：牛市特赦 (Momentum Exemption)】
        # 逻辑：如果短期热度极高(>85)，说明处于主升浪/风口。
        # 此时允许牺牲安全性，大幅提高热度权重，防止踏空。
        if score_short > 85:
            # 特赦权重：30% 基因 + 10% 安全 + 60% 热度
            # 这种配置下，即使安全分很低，只要热度够高，总分也能及格
            bull_score = (score_long * 0.3) + (score_mid * 0.1) + (score_short * 0.6)
            
            if bull_score > total_score:
                total_score = bull_score
                is_bull_exemption = True

        # 生成评语
        if total_score >= 75:
            verdict = "强力推荐 (Perfect)"
            color = "success" # Green
        elif total_score >= 60:
            verdict = "适格 (Good)"
            color = "primary" # Blue
        elif total_score >= 40:
            verdict = "谨慎 (Caution)"
            color = "warning" # Yellow
        else:
            verdict = "放弃 (Avoid)"
            color = "danger" # Red
            
        # 如果触发了特赦，虽然分数高了，但本质是激进策略，颜色和评语微调
        if is_bull_exemption:
            verdict += " [趋势特赦]"
            # 如果原来是 danger/warning，现在变成了 primary/success，
            # 我们可以保留高分颜色，但一定要在 UI 上加火苗标记

        return {
            "total_score": round(total_score, 1),
            "verdict": verdict,
            "color": color,
            "is_bull_exemption": is_bull_exemption,
            "details": {
                "long_term_gene": round(score_long, 1),   # 基因分 (MA20穿越)
                "mid_term_safety": round(score_mid, 1),   # 安全分 (4年分位)
                "short_term_heat": round(score_short, 1)  # 热度分 (TR中位数)
            },
            "raw_metrics": {
                "cross_frequency": round(cross_freq, 2),
                "price_rank": round(rank, 2),
                "recent_amplitude": round(recent_amp, 2)
            }
        }
