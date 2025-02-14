from typing import Dict, List, Any
import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime
import logging


@dataclass
class GridPosition:
    """初始建仓位置信息"""
    price: float
    quantity: float
    amount: float

@dataclass
class GridParams:
    """网格交易参数"""
    upper_price: float  # 上限价格
    lower_price: float  # 下限价格
    grid_interval: float  # 网格间距
    grid_capital: float  # 每格资金
    initial_position: GridPosition  # 初始建仓信息
    actual_grid_count: int  # 实际网格数量
    start_date: datetime = None  # 回测开始日期

@dataclass
class TradeRecord:
    """交易记录"""
    date: datetime
    type: str  # 'buy' 或 'sell'
    price: float
    quantity: float
    amount: float
    profit: float = 0.0

@dataclass
class BacktestResult:
    """回测结果"""
    total_return: float  # 总收益率
    annual_return: float  # 年化收益率
    max_drawdown: float  # 最大回撤
    sharpe_ratio: float  # 夏普比率
    grid_return: float   # 网格策略收益
    hold_return: float   # 持有策略收益
    excess_return: float # 超额收益
    trades: List[TradeRecord]  # 交易记录
    daily_returns: List[float]  # 每日收益率
    dates: List[datetime]  # 对应的日期
    prices: List[float]   # 价格序列
    grid_prices: List[float]  # 网格价格线

class GridBacktester:
    def __init__(self, grid_count: int, initial_capital: float, initial_position_ratio: float = 0.5):
        """初始化网格回测器
        
        Args:
            grid_count: 网格数量
            initial_capital: 初始资金
            initial_position_ratio: 初始建仓比例，默认50%
        """
        self.grid_count = grid_count * 2  # 单边网格数量
        self.initial_capital = initial_capital
        self.initial_position_ratio = initial_position_ratio
        self.trades: List[TradeRecord] = []
        self.positions: Dict[float, Dict] = {}  # 价格 -> {quantity: 数量, price: 买入价格}
        self.cash = initial_capital
        # 计算每个网格的固定购买金额
        self.grid_capital = (initial_capital * (1 - initial_position_ratio)) / (grid_count // 2)  # 只用下半部分网格买入
        
    
    def calculate_grid_params(self, df: pd.DataFrame) -> GridParams:
        """计算网格参数"""
        current_price = round(df['close'].iloc[0], 2)  # 当前价格保留两位小数
        # 添加起始日期到网格参数
        start_date = df['date'].iloc[0]
        
        # 计算每格资金和数量
        grid_capital = round((self.initial_capital * (1 - self.initial_position_ratio)) / self.grid_count, 2)
        quantity_per_grid = int(grid_capital / current_price / 100) * 100
        
        # 如果每格数量小于100，调整网格数量
        if quantity_per_grid < 100:
            quantity_per_grid = 100
            actual_grid_count = int((self.initial_capital * (1 - self.initial_position_ratio)) / (current_price * 100))
            self.grid_count = min(self.grid_count, actual_grid_count)
        
        # 计算实际每格资金
        actual_grid_capital = round(quantity_per_grid * current_price, 2)
        
        # 计算网格间距
        grid_interval = round(current_price / self.grid_count, 2)
        
        # 计算上下限价格
        lower_price = round(current_price - (self.grid_count // 2) * grid_interval, 2)
        upper_price = round(current_price + (self.grid_count // 2) * grid_interval, 2)
        
        # 计算初始建仓数量和金额
        initial_quantity = int((self.initial_capital * self.initial_position_ratio) / current_price / 100) * 100
        initial_amount = round(current_price * initial_quantity, 2)
        
        # 创建初始建仓信息
        initial_position = GridPosition(
            price=current_price,
            quantity=float(initial_quantity),
            amount=initial_amount
        )
        
        # 返回GridParams对象
        return GridParams(
            upper_price=upper_price,
            lower_price=lower_price,
            grid_interval=grid_interval,
            grid_capital=actual_grid_capital,
            initial_position=initial_position,
            actual_grid_count=self.grid_count,
            start_date = start_date
        )
    
    def _initialize_positions(self, grid_prices: List[float], current_price: float, grid_params: GridParams):
        """初始化持仓"""
        logging.info(f"初始化网格交易，初始价格: {current_price:.2f}, 网格数量: {self.grid_count}, 初始资金: {self.initial_capital:.2f}")
        
        # 初始建仓
        initial_position = grid_params.initial_position
        initial_quantity_per_grid = initial_position.quantity // (self.grid_count // 2)  # 每个网格分配的数量
        
        # 在初始价格及以上的网格点设置初始持仓
        for price in grid_prices:
            if price >= current_price:
                self.positions[price] = {
                    'quantity': initial_quantity_per_grid,
                    'buy_price': initial_position.price  # 使用 .price 访问
                }
        
        # 更新剩余现金
        self.cash -= initial_position.amount
        
        logging.info(f"初始建仓完成 - 价格: {initial_position.price:.2f}, 每格数量: {initial_quantity_per_grid}, "
                    f"总金额: {initial_position.amount:.2f}")
        
        # 记录初始建仓交易
        self.trades.append(TradeRecord(
            date=grid_params.start_date,
            type='buy',
            price=initial_position.price,
            quantity=initial_position.quantity,
            amount=initial_position.amount
        ))
        
        # 设置当前价格以下的网格买入点
        for price in grid_prices:
            if price < current_price:
                self.positions[price] = {'quantity': 0, 'buy_price': price}  # 等待价格下跌时买入
    
    def run_backtest(self, history_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行网格交易回测
        
        Args:
            history_data: 历史数据
            grid_count: 网格数量
            initial_capital: 初始资金
            
        Returns:
            Dict[str, Any]: 回测结果
        """
        
        result = self._run_backtest(history_data)
        
        
        # 转换回测结果为字典格式
        return {
            'total_return': round(result.total_return * 100, 2),
            'annual_return': round(result.annual_return * 100, 2),
            'max_drawdown': round(result.max_drawdown * 100, 2),
            'sharpe_ratio': round(result.sharpe_ratio, 2),
            'grid_return': round(result.grid_return * 100, 2),
            'hold_return': round(result.hold_return * 100, 2),
            'excess_return': round(result.excess_return * 100, 2),
            'trades': [
                {
                    'date': trade.date.strftime('%Y-%m-%d'),
                    'type': trade.type,
                    'price': round(trade.price, 2),
                    'quantity': round(trade.quantity, 2),
                    'amount': round(trade.amount, 2),
                    'profit': round(trade.profit, 2)
                }
                for trade in result.trades
            ],
            'daily_returns': [round(r * 100, 2) for r in result.daily_returns],
            'dates': [date.strftime('%Y-%m-%d') for date in result.dates],
            'prices': result.prices,  # 直接使用 BacktestResult 中的价格数据
            'grid_prices': result.grid_prices  # 直接使用 BacktestResult 中的网格价格数据
        }


    def _run_backtest(self, history_data: Dict[str, Any]) -> BacktestResult:
        """执行回测"""
        # 转换为DataFrame
        df = pd.DataFrame({
            'date': pd.to_datetime(history_data['dates']),
            'close': history_data['close']
        })

        # 计算网格参数
        grid_params = self.calculate_grid_params(df)
        
        
        # 计算网格价格
        grid_prices = self._calculate_grid_prices(
            grid_params.lower_price,
            grid_params.upper_price
        )
        
        # 初始化持仓
        self._initialize_positions(grid_prices, df['close'].iloc[0], grid_params)
        
        # 执行回测
        daily_returns = []
        portfolio_values = []
        
        # 计算初始投资组合价值
        initial_portfolio_value = self._calculate_portfolio_value(df['close'].iloc[0])
        portfolio_values.append(initial_portfolio_value)
        
        for i in range(1, len(df)):
            current_price = df['close'].iloc[i]
            prev_price = df['close'].iloc[i-1]
            current_date = df['date'].iloc[i]
            
            # 检查是否触发网格交易
            self._execute_grid_trades(current_price, prev_price, current_date, grid_params)
            
            # 计算当日组合价值
            portfolio_value = self._calculate_portfolio_value(current_price)
            portfolio_values.append(portfolio_value)
            
            # 计算日收益率
            daily_return = (portfolio_value - portfolio_values[-2]) / portfolio_values[-2]
            daily_returns.append(daily_return)
        
        # 计算回测指标
        total_days = len(df)
        total_return = (portfolio_values[-1] - self.initial_capital) / self.initial_capital
        annual_return = (1 + total_return) ** (252 / total_days) - 1
        
        # 计算最大回撤
        max_drawdown = self._calculate_max_drawdown(portfolio_values)
        
        # 计算夏普比率
        sharpe_ratio = self._calculate_sharpe_ratio(daily_returns)
        
        # 计算持有策略收益
        hold_return = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]
        
        # 计算超额收益
        excess_return = total_return - hold_return
        
        # 在回测结束时输出汇总信息
        logging.info(f"回测完成 - 总收益率: {total_return*100:.2f}%, 年化收益: {annual_return*100:.2f}%, 最大回撤: {max_drawdown*100:.2f}%")
        logging.info(f"交易统计 - 总交易次数: {len(self.trades)}, 夏普比率: {sharpe_ratio:.2f}")
        
        return BacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            grid_return=total_return,
            hold_return=hold_return,
            excess_return=excess_return,
            trades=self.trades,
            daily_returns=daily_returns,
            dates=df['date'].tolist(),  # 修改为包含所有日期
            prices=df['close'].tolist(),  # 添加价格序列
            grid_prices=grid_prices  # 添加网格价格线
        )
    
    def _calculate_grid_prices(self, lower_price: float, upper_price: float) -> List[float]:
        """计算网格价格"""
        return [
            round(lower_price + i * (upper_price - lower_price) / (self.grid_count - 1), 2)
            for i in range(self.grid_count)
        ]
    
    
    def _execute_grid_trades(self, current_price: float, prev_price: float, current_date: datetime, grid_params: GridParams):
        """检查并执行网格交易"""
        # 向上突破，卖出
        for price in sorted(self.positions.keys()):
            if prev_price <= price < current_price and self.positions[price]['quantity'] > 0:
                position = self.positions[price]
                quantity = position['quantity']
                buy_price = position['buy_price']
                # 使用网格价格（price）作为卖出价格，买入价格（buy_price）计算利润
                profit = quantity * (price - buy_price)
                self.cash += quantity * price
                self.positions[price]['quantity'] = 0
                
                logging.info(f"网格卖出 - 日期: {current_date}, 卖出价: {price:.2f}, 买入价: {buy_price:.2f}, "
                           f"数量: {quantity}, 利润: {profit:.2f}")
                self.trades.append(TradeRecord(
                    date=current_date,
                    type='sell',
                    price=price,  # 使用网格价格作为卖出价格
                    quantity=quantity,
                    amount=quantity * price,
                    profit=profit
                ))
        
        # 向下突破，买入
        for price in sorted(self.positions.keys(), reverse=True):
            if prev_price >= price > current_price:
                # 使用每格固定金额计算可买入数量
                grid_capital = grid_params.grid_capital
                quantity = int(grid_capital / current_price / 100) * 100  # 确保买入数量是100的整数倍
                if quantity > 0:
                    amount = quantity * current_price
                    # 如果买入金额超过了每格固定金额，调整数量
                    if amount > grid_capital:
                        quantity = int(grid_capital / current_price / 100) * 100
                        amount = quantity * current_price
                    
                    if self.cash >= amount:  # 确保有足够的现金
                        self.positions[price] = {
                            'quantity': quantity,
                            'buy_price': current_price
                        }
                        self.cash -= amount
                        
                        logging.info(f"网格买入 - 日期: {current_date}, 网格价: {price:.2f}, "
                                   f"买入价: {current_price:.2f}, 数量: {quantity}, 金额: {amount:.2f}")
                        self.trades.append(TradeRecord(
                            date=current_date,
                            type='buy',
                            price=current_price,
                            quantity=quantity,
                            amount=amount
                        ))
    
    def _calculate_portfolio_value(self, current_price: float) -> float:
        """计算当前组合价值"""
        position_value = sum(
            position['quantity'] * current_price 
            for position in self.positions.values()
        )
        return self.cash + position_value
    
    def _calculate_max_drawdown(self, portfolio_values: List[float]) -> float:
        """计算最大回撤"""
        max_so_far = portfolio_values[0]
        max_drawdown = 0
        
        for value in portfolio_values:
            if value > max_so_far:
                max_so_far = value
            drawdown = (max_so_far - value) / max_so_far
            max_drawdown = max(max_drawdown, drawdown)
            
        return max_drawdown
    
    def _calculate_sharpe_ratio(self, daily_returns: List[float]) -> float:
        """计算夏普比率"""
        if not daily_returns:
            return 0
        
        # 假设无风险利率为3%
        risk_free_rate = 0.03
        daily_rf = (1 + risk_free_rate) ** (1/252) - 1
        
        excess_returns = np.array(daily_returns) - daily_rf
        if len(excess_returns) < 2:
            return 0
            
        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)