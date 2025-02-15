from typing import List, Dict, Any
from itertools import product
import numpy as np
from .backtest_engine import BacktestEngine, BacktestResult
from .param_generator import ParamGenerator, GridParams

class ParameterAnalyzer:
    """参数分析器"""
    
    def __init__(self, initial_capital: float = 100000.0, fee_rate: float = 0.0001):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.backtest_engine = BacktestEngine(initial_capital, fee_rate)
        self.param_generator = ParamGenerator()
        
        
    def analyze(self, hist_data: Dict[str, List], atr: float, top_n: int = 10) -> List[BacktestResult]:
        """执行参数分析
        
        Args:
            hist_data: 历史数据
            atr: ATR值
            top_n: 返回最优的前N个结果
            
        Returns:
            List[BacktestResult]: 最优的N个回测结果
        """
        results = []
        
        # 使用参数生成器遍历所有参数组合
        for params in self.param_generator.generate():
            # 运行回测
            result = self.backtest_engine.run_backtest(
                hist_data=hist_data,
                atr=atr,
                grid_count=params.grid_count,
                atr_factor=params.atr_factor
            )
            
            # 计算综合评分
            results.append(result)
        
        # 按评分排序并返回前N个结果
        return sorted(results, key=lambda x: x.evaluation['total_score'], reverse=True)[:top_n]
    