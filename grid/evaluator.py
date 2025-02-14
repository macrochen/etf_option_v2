from dataclasses import dataclass
from typing import List
import numpy as np
import pandas as pd

@dataclass
class EvaluationResult:
    """回测评估结果"""
    annual_return: float    # 年化收益率
    max_drawdown: float    # 最大回撤
    sharpe_ratio: float    # 夏普比率
    trade_count: int       # 交易次数
    capital_utilization: float  # 资金利用率
    total_score: float     # 综合评分
    
    def __str__(self) -> str:
        return (
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
            'annual_return': 1,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'trade_frequency': 0.0,
            'capital_utilization': 0
        }
    
    def calculate_metrics(self, daily_returns: pd.Series, trade_records: List[dict], 
                         capital: float) -> EvaluationResult:
        """计算评估指标
        
        Args:
            daily_returns: 每日收益率序列
            trade_records: 交易记录列表
            capital: 初始资金
        """
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
        total_score = self._calculate_total_score(
            annual_return, max_drawdown, sharpe_ratio,
            trade_count, capital_utilization
        )
        
        return EvaluationResult(
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trade_count=trade_count,
            capital_utilization=capital_utilization,
            total_score=total_score,
        )
    
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
        """计算资金利用率"""
        # if not trade_records:
        #     return 0.0
            
        # # 按时间排序交易记录
        # sorted_trades = sorted(trade_records, key=lambda x: x['timestamp'])
        
        # # 计算每个时点的资金使用情况
        # cash = capital          # 可用现金
        # total_cost = 0         # 累计购买成本
        # utilization_records = []
        
        # for trade in sorted_trades:
        #     if trade['direction'] == 'buy':
        #         # 买入时减少现金，增加成本
        #         trade_value = trade['amount'] * trade['price']
        #         cash -= trade_value
        #         total_cost += trade_value
        #     else:
        #         # 卖出时增加现金，减少成本（按比例）
        #         trade_value = trade['amount'] * trade['price']
        #         if total_cost > 0:  # 避免除以零
        #             cost_ratio = trade_value / (total_cost + cash)  # 卖出部分占总资产的比例
        #             total_cost -= total_cost * cost_ratio  # 按比例减少成本
        #         cash += trade_value
                
        #     # 计算当前时点的资金利用率（已投入资金占总资金的比例）
        #     current_utilization = total_cost / capital
        #     utilization_records.append(current_utilization)
            
        # # 计算平均资金利用率
        # if not utilization_records:
        #     return 0.0
            
        # avg_utilization = sum(utilization_records) / len(utilization_records)
        # return max(min(avg_utilization, 1.0), 0.0)
        return 1.0
    
    def _calculate_total_score(self, annual_return: float, max_drawdown: float,
                             sharpe_ratio: float, trade_count: int,
                             capital_utilization: float) -> float:
        """计算综合评分"""
        # 对交易次数进行归一化处理，假设理想交易次数为每月1-2次
        ideal_annual_trades = 18  # 每月1.5次
        trade_score = 1 - abs(trade_count - ideal_annual_trades) / ideal_annual_trades
        
        return (
            self.weights['annual_return'] * annual_return
        )