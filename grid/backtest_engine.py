from dataclasses import dataclass
from typing import List, Dict, Any
import numpy as np
import pandas as pd
import logging
from datetime import datetime
from .grid_generator import GridGenerator, Grid
from .trade_executor import TradeExecutor, Trade
from .evaluator import BacktestEvaluator

@dataclass
class BacktestResult:
    """回测结果"""
    params: Dict[str, Any]          # 回测参数
    trades: List[Trade]             # 交易记录
    daily_returns: pd.Series        # 每日收益率
    evaluation: Dict[str, float]    # 评估指标
    grids: List[Grid]              # 改为网格列表类型

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, initial_capital: float = 100000.0, fee_rate: float = 0.0001):
        """初始化回测引擎
        
        Args:
            initial_capital: 初始资金
            fee_rate: 交易费率
        """
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.grid_generator = GridGenerator(initial_capital, fee_rate)
        self.evaluator = BacktestEvaluator()  # 添加评估器实例
        
    def run_backtest(self, hist_data: Dict[str, List], atr: float,
                    grid_count: int, atr_factor: float, benchmark_annual_return: float) -> BacktestResult:
        """运行回测
        
        Args:
            hist_data: 历史数据，包含 dates, open, high, low, close
            atr: ATR值
            grid_count: 网格数量
            atr_factor: ATR系数
            benchmark_annual_return: 基准年化收益率
            
        Returns:
            BacktestResult: 回测结果
        """
        # 生成网格
        grids, grid_percent = self.grid_generator.generate_grids(
            current_price=hist_data['close'][0], # 使用收盘价
            atr=atr,
            grid_count=grid_count,
            atr_factor=atr_factor
        )
        
        # 初始化交易执行器
        executor = TradeExecutor(grids, self.fee_rate, self.initial_capital)
        
        # 记录所有交易
        trades = []
        
        # 建立底仓
        initial_trade = executor.initialize_base_position(
            timestamp=datetime.strptime(hist_data['dates'][0], '%Y-%m-%d'),
            current_price=hist_data['close'][0] # 使用收盘价
        )
        trades.append(initial_trade)
        
        try:
            # 从第二天开始遍历历史数据
            for i in range(1, len(hist_data['dates'])):
                timestamp = datetime.strptime(hist_data['dates'][i], '%Y-%m-%d')
                open_price = hist_data['open'][i]
                high_price = hist_data['high'][i]
                low_price = hist_data['low'][i]
                close_price = hist_data['close'][i]
                
                # 检查并执行交易
                new_trades = executor.check_and_trade(timestamp, open_price, high_price, low_price, close_price)
                if new_trades:
                    trades.extend(new_trades)
        except Exception as e:
            import traceback
            logging.error(f"Backtest failed at index {i} date {timestamp}: {str(e)}\n{traceback.format_exc()}")
            raise e
        
        # 记录每日资产状况
        daily_portfolio = self._calculate_daily_portfolio(hist_data, trades)
        
        # 计算每日收益率
        daily_returns = self._calculate_daily_returns(daily_portfolio)
        
        # 使用评估器计算评估指标
        evaluation_result = self.evaluator.calculate_metrics(
            daily_returns=daily_returns,
            trade_records=[{
                'direction': trade.direction,
                'timestamp': trade.timestamp,
                'amount': trade.amount,
                'price': trade.price,
                'grid_index': trade.grid_index
            } for trade in trades],
            capital=self.initial_capital,
            benchmark_annual_return=benchmark_annual_return # 传递基准收益率
        )
        
        return BacktestResult(
            params={
                'grid_count': grid_count,
                'atr_factor': atr_factor,
                'initial_capital': self.initial_capital,
                'fee_rate': self.fee_rate,
                'grid_percent': grid_percent
            },
            trades=trades,
            daily_returns=daily_returns,
            grids=grids,
            evaluation=evaluation_result.__dict__  # 直接使用 dataclass 的 __dict__ 属性
        )

    def run_manual_backtest(self, hist_data: Dict[str, List], grid_percent: float,
                          grid_count: int, benchmark_annual_return: float,
                          initial_base_price: float = None,
                          trade_size: int = None) -> BacktestResult:
        """运行手动回测（指定网格百分比）
        
        Args:
            hist_data: 历史数据
            grid_percent: 网格间距百分比
            grid_count: 网格数量
            benchmark_annual_return: 基准年化收益率
            initial_base_price: 初始基准价格，如果为None则使用开始日期的收盘价
            trade_size: 每格交易数量，如果为None则自动计算
            
        Returns:
            BacktestResult: 回测结果
        """
        # 确定基准价格
        base_price = initial_base_price if initial_base_price is not None else hist_data['close'][0]
        
        # 生成网格
        grids = self.grid_generator.generate_grids_by_percent(
            current_price=base_price,
            grid_percent=grid_percent,
            grid_count=grid_count,
            trade_size=trade_size
        )
        
        # 初始化交易执行器
        executor = TradeExecutor(grids, self.fee_rate, self.initial_capital)
        
        # 记录所有交易
        trades = []
        
        # 建立底仓
        initial_trade = executor.initialize_base_position(
            timestamp=datetime.strptime(hist_data['dates'][0], '%Y-%m-%d'),
            current_price=hist_data['close'][0]
        )
        trades.append(initial_trade)
        
        # 从第二天开始遍历历史数据
        for i in range(1, len(hist_data['dates'])):
            timestamp = datetime.strptime(hist_data['dates'][i], '%Y-%m-%d')
            open_price = hist_data['open'][i]
            high_price = hist_data['high'][i]
            low_price = hist_data['low'][i]
            close_price = hist_data['close'][i]
            
            # 检查并执行交易
            new_trades = executor.check_and_trade(timestamp, open_price, high_price, low_price, close_price)
            if new_trades:
                for trade in new_trades:
                    logging.info(f"Trade Triggered: Date={timestamp}, Price={trade.price}, Direction={trade.direction}")
                trades.extend(new_trades)
        
        # 记录每日资产状况
        daily_portfolio = self._calculate_daily_portfolio(hist_data, trades)
        
        # 计算每日收益率
        daily_returns = self._calculate_daily_returns(daily_portfolio)
        
        # 使用评估器计算评估指标
        evaluation_result = self.evaluator.calculate_metrics(
            daily_returns=daily_returns,
            trade_records=[{
                'direction': trade.direction,
                'timestamp': trade.timestamp,
                'amount': trade.amount,
                'price': trade.price,
                'grid_index': trade.grid_index
            } for trade in trades],
            capital=self.initial_capital,
            benchmark_annual_return=benchmark_annual_return
        )
        
        return BacktestResult(
            params={
                'grid_count': grid_count,
                'grid_percent': grid_percent,
                'initial_capital': self.initial_capital,
                'fee_rate': self.fee_rate,
                'initial_base_price': base_price,
                'trade_size': trade_size
            },
            trades=trades,
            daily_returns=daily_returns,
            grids=grids,
            evaluation=evaluation_result.__dict__
        )
    
    def _calculate_daily_portfolio(self, hist_data: Dict[str, List], trades: List[Trade]) -> pd.DataFrame:
        """计算每日投资组合价值"""
        dates = pd.to_datetime(hist_data['dates'])
        prices = pd.Series(hist_data['close'], index=dates)
        
        # 创建每日资产记录DataFrame
        portfolio = pd.DataFrame(index=dates, columns=['cash', 'position', 'position_value', 'total_value'])
        
        # 初始化
        cash = self.initial_capital
        position = 0
        
        # 按日期遍历
        for date in dates:
            # 处理当日交易
            day_trades = [t for t in trades if t.timestamp == date]
            for trade in day_trades:
                trade_value = trade.price * abs(trade.amount)
                if trade.direction == 'buy':
                    cost = trade_value * (1 + self.fee_rate)
                    cash -= cost
                    position += trade.amount
                else:  # sell
                    revenue = trade_value * (1 - self.fee_rate)
                    cash += revenue
                    position -= abs(trade.amount)
            
            # 重要：即使没有交易，也要每日更新持仓市值
            current_price = prices[date]
            position_value = position * current_price
            total_value = cash + position_value
            
            # 记录当日资产状况
            portfolio.loc[date] = {
                'cash': cash,
                'position': position,
                'position_value': position_value,
                'total_value': total_value
            }
        
        return portfolio
        
    def _calculate_daily_returns(self, portfolio: pd.DataFrame) -> pd.Series:
        """根据每日总资产计算收益率"""
        # 确保 total_value 列的数据类型为 float
        portfolio['total_value'] = portfolio['total_value'].astype(float)
        # 计算每日收益率
        daily_returns = portfolio['total_value'].pct_change()
        # 使用 infer_objects() 让 Pandas 自动推断合适的数据类型
        return daily_returns.fillna(0).infer_objects(copy=False)
        
    def _calculate_benchmark_returns(self, hist_data: Dict[str, List]) -> pd.Series:
        """计算标的持有收益率"""
        prices = pd.Series(hist_data['close'])
        # 计算每日收益率
        daily_returns = prices.pct_change().fillna(0)
        return daily_returns
