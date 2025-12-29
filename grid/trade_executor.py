from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import logging
from .grid_generator import Grid

@dataclass
class Trade:
    """交易记录"""
    timestamp: datetime      # 交易时间
    price: float            # 成交价格
    amount: int             # 成交数量（正数买入，负数卖出）
    direction: str          # 买入/卖出
    grid_index: int         # 触发网格索引
    grid_count: int = 1     # 跨越网格数量
    current_position: int = 0   # 交易后持仓
    position_value: float = 0.0 # 交易后市值
    total_value: float = 0.0      # 交易后总资产
    cash: float = 0.0             # 交易后现金

class TradeExecutor:
    """交易执行器"""
    
    def __init__(self, grids: List[Grid], fee_rate: float = 0.0001, initial_capital: float = 100000):
        """初始化交易执行器"""
        self.grids = grids
        self.fee_rate = fee_rate
        self.last_price = None
        self.last_trade_grid_index = None
        self.position = 0
        self.cash = initial_capital
        
    def initialize_base_position(self, timestamp: datetime, current_price: float) -> Trade:
        """初始化底仓，记录买入交易
        
        Args:
            timestamp: 交易时间
            current_price: 当前价格
        """
        # 找到最近的网格
        base_grid_index = min(range(len(self.grids)), key=lambda i: abs(self.grids[i].price - current_price))
        
        # 初始化时，所有高于当前价格的网格（包含当前格）都标记为有持仓
        for i, grid in enumerate(self.grids):
            if grid.price >= current_price:
                grid.has_position = True
            else:
                grid.has_position = False
        
        # 计算初始持仓量：累加所有已标记持仓的网格的position
        base_amount = sum(grid.position for grid in self.grids if grid.has_position)
        
        # 更新持仓和资金
        self.position = base_amount
        cost = current_price * base_amount * (1 + self.fee_rate)
        self.cash -= cost
        self.last_price = current_price

        # 记录底仓买入交易
        trade = Trade(
            timestamp=timestamp,
            price=current_price,
            amount=base_amount,
            direction="buy",
            grid_index=base_grid_index,
            grid_count=1,
            current_position=self.position,
            position_value=self.position * current_price,
            total_value=self.cash + (self.position * current_price),
            cash=self.cash
        )
        return trade
        
    def check_and_trade(self, timestamp: datetime, open_price: float, high_price: float, low_price: float, close_price: float) -> List[Trade]:
        """检查并执行交易 (OHLC版本)
        
        Returns:
            List[Trade]: 生成的交易列表（可能包含多笔买卖）
        """
        if self.last_price is None:
            self.last_price = close_price
            return []
            
        trades = self._execute_grid_trades_ohlc(timestamp, open_price, high_price, low_price, close_price)
        self.last_price = close_price
        return trades
    
    def _execute_grid_trades_ohlc(self, timestamp: datetime, open_price: float, high_price: float, low_price: float, close_price: float) -> List[Trade]:
        """执行网格交易 (OHLC逻辑)"""
        trades = []
        
        # 1. 卖出循环 (High)
        # 优先执行卖出，释放资金和仓位
        for i, grid in enumerate(self.grids):
            if grid.has_position:
                # 如果是最后一个网格，没有上一档，通常不卖出或者无限持有
                if i + 1 < len(self.grids):
                    target_price = self.grids[i+1].price
                    if high_price >= target_price:
                        # 确定成交价：如果是跳空高开，则以 Open 价卖出
                        exec_price = max(open_price, target_price)
                        
                        # 执行卖出
                        grid.has_position = False
                        amount = grid.position
                        
                        self.position -= amount
                        revenue = amount * exec_price * (1 - self.fee_rate)
                        self.cash += revenue
                        
                        trades.append(Trade(
                            timestamp=timestamp,
                            price=exec_price,
                            amount=-amount, # 卖出为负
                            direction="sell",
                            grid_index=self.grids.index(grid),
                            grid_count=1,
                            current_position=self.position,
                            position_value=self.position * close_price, # 使用收盘价计算市值
                            total_value=self.cash + (self.position * close_price),
                            cash=self.cash
                        ))

        # 2. 买入循环 (Low)
        # 遍历所有网格，检查是否触发买入
        # 按价格从高到低遍历 (reversed)，在资金不足时优先成交价格较高的网格（通常是刚跌破的）
        for i, grid in reversed(list(enumerate(self.grids))):
            if not grid.has_position:
                buy_price = grid.price
                if low_price <= buy_price:
                    # 确定成交价：如果是跳空低开，则以 Open 价买入
                    exec_price = min(open_price, buy_price)
                    
                    # 检查资金
                    cost = grid.position * exec_price * (1 + self.fee_rate)
                    if self.cash >= cost:
                        # 执行买入
                        grid.has_position = True
                        amount = grid.position
                        
                        self.position += amount
                        self.cash -= cost
                        
                        trades.append(Trade(
                            timestamp=timestamp,
                            price=exec_price,
                            amount=amount,
                            direction="buy",
                            grid_index=self.grids.index(grid),
                            grid_count=1,
                            current_position=self.position,
                            position_value=self.position * close_price,
                            total_value=self.cash + (self.position * close_price),
                            cash=self.cash
                        ))
                    else:
                        # 资金不足日志可以记录，但为了不刷屏，可以考虑 debug 级别
                        # logging.debug(...)
                        pass

        return trades