from dataclasses import dataclass
from typing import Dict, List
import numpy as np
import pandas as pd

@dataclass
class EvaluationResult:
    """回测评估结果"""
    total_return: float     # 总收益率
    annual_return: float    # 年化收益率
    max_drawdown: float    # 最大回撤
    sharpe_ratio: float    # 夏普比率
    trade_count: int       # 交易次数
    capital_utilization: float  # 资金利用率
    total_score: float     # 综合评分
    
    def __str__(self) -> str:
        return (
            f"总收益率: {self.total_return:.2%}\n"
            f"年化收益率: {self.annual_return:.2%}\n"
            f"最大回撤: {self.max_drawdown:.2%}\n"
            f"夏普比率: {self.sharpe_ratio:.2f}\n"
            f"交易次数: {self.trade_count}\n"
            f"资金利用率: {self.capital_utilization:.2%}\n"
            f"综合评分: {self.total_score:.2f}"
        )

class BacktestEvaluator:
    """回测评估器"""
    
    def __init__(self):
        # 定义指标权重
        self.weights = {
            'annual_return': 0.35,
            'max_drawdown': 0.25,
            'sharpe_ratio': 0.20,
            'trade_frequency': 0.10,
            'capital_utilization': 0.10

            # 'annual_return': 1,
            # 'max_drawdown': 0.0,
            # 'sharpe_ratio': 0.0,
            # 'trade_frequency': 0.0,
            # 'capital_utilization': 0
        }
    
    def calculate_metrics(self, daily_returns: pd.Series, trade_records: List[dict], 
                         capital: float) -> EvaluationResult:
        """计算评估指标
        
        Args:
            daily_returns: 每日收益率序列
            trade_records: 交易记录列表
            capital: 初始资金
        """
        # 计算总收益率
        total_return = self._calculate_total_return(daily_returns)
        
        # 计算年化收益率
        annual_return = self._calculate_annual_return(daily_returns)
        
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
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'trade_frequency': trade_count,
            'capital_utilization': capital_utilization}
        )
        
        return EvaluationResult(
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trade_count=trade_count,
            capital_utilization=capital_utilization,
            total_score=total_score,
        )
    
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
            
        # 将日收益率转换为累积收益
        cumulative_returns = (1 + daily_returns).cumprod()
        total_return = cumulative_returns.iloc[-1] - 1
        
        # 计算年化收益率
        days = len(daily_returns)
        if days == 0:
            return 0.0
            
        years = days / 252
        return (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1

    def _calculate_max_drawdown(self, daily_returns: pd.Series) -> float:
        """计算最大回撤"""
        if daily_returns.empty:
            return 0.0
            
        # 计算累积收益
        cumulative = (1 + daily_returns).cumprod()
        # 计算历史最高点
        rolling_max = cumulative.expanding().max()
        # 计算回撤
        drawdowns = cumulative / rolling_max - 1
        return abs(drawdowns.min())  # 返回正值
    
    def _calculate_sharpe_ratio(self, daily_returns: pd.Series) -> float:
        """计算夏普比率"""
        annual_return = self._calculate_annual_return(daily_returns)
        annual_volatility = daily_returns.std() * np.sqrt(252)
        risk_free_rate = 0.03  # 假设无风险利率为3%
        return (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0
    
    def _calculate_capital_utilization(self, trade_records: List[dict], capital: float) -> float:
        """计算资金利用率（加权平均占用资金法）
        
        Args:
            trade_records: 交易记录列表
            capital: 初始资金
            
        Returns:
            float: 资金利用率（0-1之间的小数）
        """
        if not trade_records:
            return 0.0
            
        # 计算每笔交易的金额作为权重
        occupied_capitals = []
        current_occupied = 0  # 当前占用资金
        
        for trade in trade_records:
            trade_value = abs(trade['amount'] * trade['price'])
            
            # 根据交易方向更新资金占用
            if trade['direction'] == 'buy':
                current_occupied += trade_value
            else:  # sell
                current_occupied -= trade_value
            
            occupied_capitals.append(current_occupied)
            
        # 计算权重（每笔交易金额占总交易金额的比例）
        total_trade_amount = sum(occupied_capitals)
        if total_trade_amount == 0:
            return 0.0
            
        weights = [amount / total_trade_amount for amount in occupied_capitals]
        
        # 计算加权平均占用资金
        weighted_capital = sum(occupied * weight for occupied, weight in zip(occupied_capitals, weights))
        
        # 计算资金利用率（加权平均占用资金 / 初始资金）
        utilization_rate = weighted_capital / capital
        
        # 确保返回值在0-1之间
        return max(min(utilization_rate, 1.0), 0.0)
    

    def _calculate_score(self, evaluation: Dict[str, float]) -> float:
        """计算综合评分
        
        Args:
            evaluation: 评估指标字典
            
        Returns:
            float: 综合评分
        """
        # 对最大回撤取反，因为回撤越小越好
        evaluation = evaluation.copy()
        evaluation['max_drawdown'] = -evaluation['max_drawdown']
        
        # 对各指标进行标准化（转换到0-1之间）
        normalized = {}
        for key in self.weights:
            value = evaluation[key]
            if key == 'max_drawdown':
                # 回撤已经在-1到0之间，转换到0-1
                normalized[key] = 1 + value
            else:
                # 其他指标使用sigmoid函数归一化
                normalized[key] = 1 / (1 + np.exp(-value))
        
        # 计算加权得分
        score = sum(normalized[key] * self.weights[key] for key in self.weights)
        
        return score