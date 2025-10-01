from dataclasses import dataclass
from typing import Dict, List
import numpy as np
import pandas as pd

@dataclass
class EvaluationResult:
    """回测评估结果"""
    total_return: float         # 总收益率
    annual_return: float        # 年化收益率
    relative_return: float      # 相对表现（对比基准）
    max_drawdown: float         # 最大回撤
    sharpe_ratio: float         # 夏普比率
    trade_count: int            # 交易次数
    capital_utilization: float  # 资金利用率
    total_score: float          # 综合评分
    
    def __str__(self) -> str:
        return (
            f"总收益率: {self.total_return:.2%}\n"
            f"年化收益率: {self.annual_return:.2%}\n"
            f"相对表现: {self.relative_return:.2f}\n"
            f"最大回撤: {self.max_drawdown:.2%}\n"
            f"夏普比率: {self.sharpe_ratio:.2f}\n"
            f"交易次数: {self.trade_count}\n"
            f"资金利用率: {self.capital_utilization:.2%}\n"
            f"综合评分: {self.total_score:.2f}"
        )

class BacktestEvaluator:
    """回测评估器"""
    
    def __init__(self):
        # 定义指标权重，引入相对表现
        self.weights = {
            'annual_return': 0.40,       # 提高年化收益权重
            'relative_return': 0.30,     # 新增：相对表现，权重很高
            'max_drawdown': 0.15,        # 降低最大回撤权重
            'sharpe_ratio': 0.10,        # 降低夏普比率权重
            'capital_utilization': 0.05, # 资金利用率作为次要指标
            'trade_frequency': 0.0       # 交易频率不作为评分项
        }
    
    def calculate_metrics(self, daily_returns: pd.Series, trade_records: List[dict], 
                         capital: float, benchmark_annual_return: float) -> EvaluationResult:
        """计算评估指标
        
        Args:
            daily_returns: 每日收益率序列
            trade_records: 交易记录列表
            capital: 初始资金
            benchmark_annual_return: 基准年化收益率
        """
        # 计算总收益率
        total_return = self._calculate_total_return(daily_returns)
        
        # 计算年化收益率
        annual_return = self._calculate_annual_return(daily_returns)
        
        # 新增：计算相对表现
        relative_return = self._calculate_relative_return(annual_return, benchmark_annual_return)

        # 计算最大回撤
        max_drawdown = self._calculate_max_drawdown(daily_returns)
        
        # 计算夏普比率
        sharpe_ratio = self._calculate_sharpe_ratio(daily_returns)
        
        # 计算交易频率相关指标
        trade_count = len(trade_records)
        
        # 计算资金利用率
        capital_utilization = self._calculate_capital_utilization(trade_records, capital)
        
        # 计算综合评分
        total_score = self._calculate_score({
            'annual_return': annual_return,
            'relative_return': relative_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'trade_frequency': trade_count,
            'capital_utilization': capital_utilization
        })
        
        return EvaluationResult(
            total_return=total_return,
            annual_return=annual_return,
            relative_return=relative_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trade_count=trade_count,
            capital_utilization=capital_utilization,
            total_score=total_score,
        )

    def _calculate_relative_return(self, strategy_return: float, benchmark_return: float) -> float:
        """计算相对表现"""
        if benchmark_return <= 0:
            # 如果基准不赚钱，策略只要不亏太多就是好的
            return 1.0 + (strategy_return - benchmark_return)
        return strategy_return / benchmark_return

    def _calculate_total_return(self, daily_returns: pd.Series) -> float:
        """计算总收益率"""
        if daily_returns.empty:
            return 0.0
        
        cumulative_returns = (1 + daily_returns).cumprod()
        total_return = cumulative_returns.iloc[-1] - 1
        return total_return

    def _calculate_annual_return(self, daily_returns: pd.Series) -> float:
        """计算年化收益率"""
        if daily_returns.empty:
            return 0.0
            
        total_return = self._calculate_total_return(daily_returns)
        
        days = len(daily_returns)
        if days == 0:
            return 0.0
            
        years = days / 252
        return (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1

    def _calculate_max_drawdown(self, daily_returns: pd.Series) -> float:
        """计算最大回撤"""
        if daily_returns.empty:
            return 0.0
            
        cumulative = (1 + daily_returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = cumulative / rolling_max - 1
        return abs(drawdowns.min())
    
    def _calculate_sharpe_ratio(self, daily_returns: pd.Series) -> float:
        """计算夏普比率"""
        if daily_returns.empty:
            return 0.0
        annual_return = self._calculate_annual_return(daily_returns)
        annual_volatility = daily_returns.std() * np.sqrt(252)
        risk_free_rate = 0.03
        return (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0
    
    def _calculate_capital_utilization(self, trade_records: List[dict], capital: float) -> float:
        """计算资金利用率"""
        if not trade_records:
            return 0.0
        
        occupied_capitals = []
        current_occupied = 0
        
        for trade in trade_records:
            trade_value = abs(trade['amount'] * trade['price'])
            if trade['direction'] == 'buy':
                current_occupied += trade_value
            else:
                current_occupied -= trade_value
            occupied_capitals.append(current_occupied)
            
        if not occupied_capitals:
            return 0.0
            
        avg_occupied_capital = sum(occupied_capitals) / len(occupied_capitals)
        return avg_occupied_capital / capital
    
    def _calculate_score(self, evaluation: Dict[str, float]) -> float:
        """计算综合评分"""
        evaluation = evaluation.copy()
        evaluation['max_drawdown'] = -evaluation['max_drawdown']
        
        normalized = {}
        for key in self.weights:
            if self.weights[key] == 0:
                continue
            value = evaluation[key]
            if key == 'max_drawdown':
                normalized[key] = 1 + value
            elif key == 'relative_return':
                # 相对表现分数做一些限制，避免极端值
                normalized[key] = 1 / (1 + np.exp(-(value - 1) * 2)) # 中心在1, 范围大约0.2-1.8
            else:
                normalized[key] = 1 / (1 + np.exp(-value))
        
        score = sum(normalized[key] * self.weights[key] for key in normalized)
        return score