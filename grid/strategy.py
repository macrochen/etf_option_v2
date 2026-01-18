import pandas as pd
import numpy as np
import math
from .models import GridContext, StrategyMode, StrategyResult, GridLine
from .indicators import Indicators

class SmartGridStrategy:
    def __init__(self, context: GridContext):
        self.context = context

    def generate(self, df: pd.DataFrame, benchmark_df: pd.DataFrame = None) -> StrategyResult:
        """
        生成网格策略参数
        :param df: 日线行情数据
        :param benchmark_df: 基准指数数据 (用于计算 Beta)
        :return: StrategyResult
        """
        if df.empty:
            raise ValueError("Historical data is empty")

        # 1. 计算指标
        if len(df) < self.context.bollinger_period:
            # 数据不足以计算布林带，回退到使用最高最低价
            current_atr = df['close'].mean() * 0.01 # 估算
            current_upper = df['high'].max()
            current_lower = df['low'].min()
        else:
            atr_series = Indicators.calculate_atr(df, self.context.atr_period)
            mid, upper, lower = Indicators.calculate_bollinger(df, self.context.bollinger_period, self.context.bollinger_std)
            
            # 获取最新值 (使用最后一行)
            current_atr = atr_series.iloc[-1]
            current_upper = upper.iloc[-1]
            current_lower = lower.iloc[-1]
            
        # 计算波动率评分指标
        amplitude = Indicators.calculate_amplitude_avg(df, window=30)
        beta = 0.0
        if benchmark_df is not None and not benchmark_df.empty:
            beta = Indicators.calculate_beta(df, benchmark_df, window=90)
            
        # 计算综合评分 (0-100)
        volatility_score = self._calculate_score(beta, amplitude)
            
        # 检查是否为 NaN (可能因为停牌或其他原因)
        if pd.isna(current_upper) or pd.isna(current_lower) or pd.isna(current_atr):
             current_upper = df['high'].max()
             current_lower = df['low'].min()
             current_atr = df['close'].iloc[-1] * 0.01

        current_price = self.context.current_price
        
        # 60日极值
        last_60_days = df.iloc[-60:] if len(df) > 60 else df
        max_60d = last_60_days['high'].max()
        min_60d = last_60_days['low'].min()
        
        # 2. 模式判定
        mode = self._determine_mode()
        
        # 3. 区间计算
        # 上限 = min(布林上轨, 60日最高)
        # 下限 = max(布林下轨, 60日最低)
        
        p_max = min(current_upper, max_60d)
        p_min = max(current_lower, min_60d)
        
        # 安全检查: p_max 和 p_min 不能相等或为 NaN
        if pd.isna(p_max) or pd.isna(p_min) or p_max <= p_min:
             # 兜底：使用当前价格 +/- 10%
             p_max = current_price * 1.1
             p_min = current_price * 0.9
        
        # 兜底逻辑：如果当前价格不在区间内，强制扩展区间
        if current_price >= p_max:
            p_max = current_price * 1.05
        if current_price <= p_min:
            p_min = current_price * 0.95
            
        # 4. 步长计算 (等比网格)
        # 基准步长比率 = ATR / 当前价
        step_ratio = current_atr / current_price
        if step_ratio <= 0:
            step_ratio = 0.01 # 默认 1%
            
        # 计算从 p_min 到 p_max 需要多少个等比格
        # 公式: p_max = p_min * (1 + step_ratio)^n
        # => n = log(p_max / p_min) / log(1 + step_ratio)
        n_grids = int(math.log(p_max / p_min) / math.log(1 + step_ratio))
        
        # 约束：至少 10 格
        if n_grids < self.context.min_grid_count:
            n_grids = self.context.min_grid_count
            # 重新计算适应 10 格的等比步长
            # step_ratio = (p_max / p_min)^(1/n) - 1
            step_ratio = math.pow(p_max / p_min, 1/n_grids) - 1
            
        # 5. 资金分配
        # 可用资金 = 总资金 * (1 - 底仓比例 - 预留现金比例)
        # 注意: base_position_ratio 对应的是"锁定底仓"，不参与网格分格资金计算
        # cash_reserve_ratio 对应的是"下方安全垫"，用于生成额外网格
        active_ratio = 1 - self.context.base_position_ratio - self.context.cash_reserve_ratio
        if active_ratio < 0: active_ratio = 0
        
        available_capital = self.context.total_capital * active_ratio
        
        # 避免除零
        if n_grids <= 0: n_grids = 1
        
        cash_per_grid = available_capital / n_grids
        
        # 单格股数 (向下取整到 100)
        vol_per_grid = math.floor(cash_per_grid / current_price / 100) * 100
        if vol_per_grid < 100:
            vol_per_grid = 100 # 至少 1 手
            
        # 6. 生成主网格线 (等比数列)
        grid_lines = []
        
        # 系数调整
        buy_factor = 1.0
        sell_factor = 1.0
        
        if mode == StrategyMode.ACCUMULATE:
            buy_factor = 1.2
            sell_factor = 1.0
        elif mode == StrategyMode.TREND:
            buy_factor = 1.0
            sell_factor = 0.8 
            
        # 计算具体买卖量
        buy_vol = int(vol_per_grid * buy_factor)
        sell_vol = int(vol_per_grid * sell_factor)
        
        buy_vol = math.floor(buy_vol / 100) * 100
        if buy_vol == 0 and buy_factor > 0: buy_vol = 100
        
        sell_vol = math.floor(sell_vol / 100) * 100
        if sell_vol == 0 and sell_factor > 0: sell_vol = 100
            
        for i in range(n_grids + 1):
            # 等比公式: Price_i = p_min * (1 + step_ratio)^i
            price = p_min * math.pow(1 + step_ratio, i)
            price = round(price, 3)
            
            grid_lines.append(GridLine(
                price=price,
                buy_vol=buy_vol,
                sell_vol=sell_vol
            ))
            
        # 7. 生成预留现金安全网格 (Safety Extension)
        # 利用预留资金，在 p_min 下方继续生成网格，防止破网
        if self.context.cash_reserve_ratio > 0:
            reserved_capital = self.context.total_capital * self.context.cash_reserve_ratio
            current_low_p = p_min
            
            # 向下扩展循环
            while reserved_capital > 0:
                # 逆推下一格价格
                next_p = current_low_p / (1 + step_ratio)
                next_p = round(next_p, 3)
                
                # 计算这一格需要的资金 (按买入量计算)
                cost = next_p * buy_vol
                
                # 价格太低或资金不足时停止
                if next_p <= 0.01 or reserved_capital < cost:
                    break
                    
                # 插入到列表头部
                grid_lines.insert(0, GridLine(
                    price=next_p,
                    buy_vol=buy_vol,
                    sell_vol=sell_vol
                ))
                
                reserved_capital -= cost
                current_low_p = next_p
                
            # 更新 p_min 为新的下限
            p_min = grid_lines[0].price
            
        # 更新 p_max 为最后一格的价格 (主网格逻辑未变)
        p_max = grid_lines[-1].price
        
        # 更新实际格数
        final_grid_count = len(grid_lines) - 1
            
        return StrategyResult(
            symbol=self.context.symbol,
            mode=mode,
            price_min=p_min,
            price_max=p_max,
            step_price=round(current_atr, 3), 
            step_percent=round(step_ratio * 100, 2),
            grid_count=final_grid_count,
            cash_per_grid=cash_per_grid,
            vol_per_grid=vol_per_grid,
            grid_lines=grid_lines,
            description=f"基于 {mode.value} 模式生成，预留 {round(self.context.cash_reserve_ratio*100)}% 现金扩展下限至 {p_min}元",
            beta=round(beta, 2),
            amplitude=round(amplitude * 100, 2),
            volatility_score=volatility_score
        )

    def _calculate_score(self, beta: float, amplitude: float) -> float:
        """
        计算波动率综合评分 (0-100)
        Beta (50分): 弹性越高越好 (>1.2)
        Amplitude (50分): 振幅越高越好 (>2%)
        """
        score = 0
        
        # Beta 评分
        if beta > 1.5: score += 50
        elif beta > 1.2: score += 40
        elif beta > 1.0: score += 30
        elif beta > 0.8: score += 20
        else: score += 10
        
        # Amplitude 评分 (输入是小数，如 0.02)
        if amplitude > 0.025: score += 50
        elif amplitude > 0.020: score += 40
        elif amplitude > 0.015: score += 30
        elif amplitude > 0.010: score += 20
        else: score += 10
        
        return float(score)

    def _determine_mode(self) -> StrategyMode:
        """根据估值判定策略模式"""
        if self.context.force_mode:
            return self.context.force_mode
            
        # 简单加权：PE 和 PB 各占 50% ? 
        # 或者只要有一个低就低？ 
        # PRD: "估值 < 20%"，通常指综合估值。
        # 这里采用平均值判断
        avg_percentile = (self.context.pe_percentile + self.context.pb_percentile) / 2
        
        if avg_percentile < 20:
            return StrategyMode.ACCUMULATE
        elif avg_percentile > 70:
            return StrategyMode.TREND
        else:
            return StrategyMode.NEUTRAL
