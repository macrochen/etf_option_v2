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
        
    def check_and_trade(self, timestamp: datetime, price: float) -> Optional[Trade]:
        """检查并执行交易"""
        if self.last_price is None:
            self.last_price = price
            return None
            
        # 查找并执行网格交易
        trade = self._execute_grid_trades(timestamp, self.last_price, price)
        self.last_price = price
        return trade
    
    def _execute_grid_trades(self, timestamp: datetime, last_price: float, current_price: float) -> Optional[Trade]:
        """执行网格交易
        
        完全重构的逻辑：
        1. 废弃累积检查，改为对每个穿越的网格独立判断。
        2. 增加浮点数容差 (EPSILON)。
        """
        EPSILON = 1e-6
        total_amount = 0
        crossed_grid_index = None
        trade_direction = ""

        # 价格下跌：寻找跌破的网格线 -> 买入
        if current_price < last_price:
            for i, grid in enumerate(self.grids):
                # 穿越判断：上次在上方(> grid.price)，这次在下方(<= grid.price)
                # 加上 EPSILON 防止在边界反复触发
                # 这里的逻辑是：跌破 grid.price，应该买入 grid 对应的持仓
                if last_price > grid.price + EPSILON and current_price <= grid.price + EPSILON:
                    if not grid.has_position:
                        # 执行买入
                        grid.has_position = True
                        buy_amount = grid.position
                        
                        # 更新账户
                        self.position += buy_amount
                        cost = buy_amount * current_price * (1 + self.fee_rate)
                        self.cash -= cost
                        
                        total_amount += buy_amount
                        crossed_grid_index = i
                        trade_direction = "buy"

        # 价格上涨：寻找涨破的网格线 -> 卖出下方网格的持仓
        elif current_price > last_price:
            for i, grid in enumerate(self.grids):
                # 穿越判断：上次在下方(< grid.price)，这次在上方(>= grid.price)
                if last_price < grid.price - EPSILON and current_price >= grid.price - EPSILON:
                    # 涨破了 Grid[i]。
                    # 在等比网格中，Grid[i] 是 Grid[i-1] 的卖出目标位。
                    # 所以如果涨破了 Grid[i]，我们应该检查并卖出 Grid[i-1] 的持仓。
                    
                    target_sell_idx = i - 1
                    if target_sell_idx >= 0:
                        target_grid = self.grids[target_sell_idx]
                        if target_grid.has_position:
                            # 执行卖出
                            target_grid.has_position = False
                            sell_amount = target_grid.position
                            
                            # 更新账户
                            self.position -= sell_amount
                            revenue = sell_amount * current_price * (1 - self.fee_rate)
                            self.cash += revenue
                            
                            total_amount -= sell_amount # 卖出为负
                            crossed_grid_index = i # 记录触发网格（是哪个价格线触发的）
                            trade_direction = "sell"
        
        if total_amount != 0:
            return Trade(
                timestamp=timestamp,
                price=current_price,
                amount=total_amount,
                direction=trade_direction,
                grid_index=crossed_grid_index,
                grid_count=abs(total_amount) // self.grids[0].position if self.grids else 1, # 估算格数
                current_position=self.position,
                position_value=self.position * current_price,
                total_value=self.cash + (self.position * current_price),
                cash=self.cash
            )
        return None