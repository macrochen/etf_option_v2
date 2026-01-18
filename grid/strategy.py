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
        atr_series = Indicators.calculate_atr(df, self.context.atr_period)
        mid, upper, lower = Indicators.calculate_bollinger(df, self.context.bollinger_period, self.context.bollinger_std)
        
        # 计算波动率评分指标
        amplitude = Indicators.calculate_amplitude_avg(df, window=30)
        beta = 0.0
        if benchmark_df is not None and not benchmark_df.empty:
            beta = Indicators.calculate_beta(df, benchmark_df, window=90)
            
        # 计算综合评分 (0-100)
        volatility_score = self._calculate_score(beta, amplitude)
        
        # 获取最新值 (使用最后一行)
        current_atr = atr_series.iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        current_price = self.context.current_price
        
        # 60日极值
        last_60_days = df.iloc[-60:]
        max_60d = last_60_days['high'].max()
        min_60d = last_60_days['low'].min()
        
        # 2. 模式判定
        mode = self._determine_mode()
        
        # 3. 区间计算
        # 上限 = min(布林上轨, 60日最高)
        # 下限 = max(布林下轨, 60日最低)
        # 并在 Accumulate/Trend 模式下微调 (PRD 未明确微调细节，暂按标准逻辑)
        
        p_max = min(current_upper, max_60d)
        p_min = max(current_lower, min_60d)
        
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
        # 可用资金 = 总资金 * (1 - 底仓比例)
        available_capital = self.context.total_capital * (1 - self.context.base_position_ratio)
        cash_per_grid = available_capital / n_grids
        
        # 单格股数 (向下取整到 100)
        vol_per_grid = math.floor(cash_per_grid / current_price / 100) * 100
        if vol_per_grid < 100:
            vol_per_grid = 100 # 至少 1 手
            
        # 6. 生成网格线 (等比数列)
        grid_lines = []
        
        # 系数调整
        buy_factor = 1.0
        sell_factor = 1.0
        
        if mode == StrategyMode.ACCUMULATE:
            buy_factor = 1.2
            sell_factor = 1.0
        elif mode == StrategyMode.TREND:
            buy_factor = 1.0
            sell_factor = 0.8 # 卖少点，防卖飞
            
        for i in range(n_grids + 1):
            # 等比公式: Price_i = p_min * (1 + step_ratio)^i
            price = p_min * math.pow(1 + step_ratio, i)
            price = round(price, 3)
            
            # 计算该档位的买卖量
            buy_vol = int(vol_per_grid * buy_factor)
            sell_vol = int(vol_per_grid * sell_factor)
            
            # 向下取整到100，但保证至少100 (除非系数为0)
            buy_vol = math.floor(buy_vol / 100) * 100
            if buy_vol == 0 and buy_factor > 0: buy_vol = 100
            
            sell_vol = math.floor(sell_vol / 100) * 100
            if sell_vol == 0 and sell_factor > 0: sell_vol = 100
            
            grid_lines.append(GridLine(
                price=price,
                buy_vol=buy_vol,
                sell_vol=sell_vol
            ))
            
        # 更新 p_max 为最后一格的价格
        p_max = grid_lines[-1].price
            
        return StrategyResult(
            symbol=self.context.symbol,
            mode=mode,
            price_min=p_min,
            price_max=p_max,
            step_price=round(current_atr, 3), # 显示参考 ATR
            step_percent=round(step_ratio * 100, 2),
            grid_count=n_grids,
            cash_per_grid=cash_per_grid,
            vol_per_grid=vol_per_grid,
            grid_lines=grid_lines,
            description=f"基于 {mode.value} 模式生成等比网格，步长约 {round(step_ratio * 100, 2)}%",
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
