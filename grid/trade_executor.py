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

class TradeExecutor:
    """交易执行器"""
    
    def __init__(self, grids: List[Grid], fee_rate: float = 0.0001, initial_capital: float = 100000):
        """初始化交易执行器"""
        self.grids = grids
        self.fee_rate = fee_rate
        self.last_price = None
        self.last_trade_grid_index = None  # 添加：记录上一次交易的网格索引
        self.position = 0  # 添加持仓跟踪
        self.cash = initial_capital
        
    def initialize_base_position(self, timestamp: datetime, current_price: float) -> Trade:
        """初始化底仓，记录买入交易"""
        base_grid_index = next(i for i, grid in enumerate(self.grids) 
                             if grid.price == current_price)
        
        # 初始化时，所有高于当前价格的网格都标记为有持仓（为未来的上涨做准备）
        for i in range(base_grid_index, len(self.grids)):
            self.grids[i].has_position = True
        
        # 计算初始持仓量：累加所有已标记持仓的网格的position
        base_amount = sum(grid.position for grid in self.grids if grid.has_position)
        
        # 记录底仓买入交易
        trade = Trade(
            timestamp=timestamp,
            price=current_price,
            amount=base_amount,
            direction="buy",
            grid_index=base_grid_index,
            grid_count=1
        )
        
        # 更新持仓和资金
        self.position = base_amount
        self.cash -= current_price * base_amount * (1 + self.fee_rate)
        self.last_price = current_price
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
        """执行网格交易"""
        total_amount = 0
        crossed_grid_index = None
        
        if current_price < last_price:  # 价格下跌
            for i, grid in enumerate(self.grids):
                if last_price > grid.price >= current_price:
                    # 执行下跌建仓操作
                    trade_amount = self._execute_downtrend_position(timestamp, i, current_price)
                    if trade_amount:
                        total_amount += trade_amount
                        if crossed_grid_index is None:
                            crossed_grid_index = i
        else:  # 价格上涨
            for i, grid in enumerate(self.grids):
                if last_price < grid.price <= current_price:
                    # 执行上涨清仓操作
                    trade_amount = self._execute_uptrend_position(timestamp, i, current_price)
                    if trade_amount:
                        total_amount += trade_amount
                        if crossed_grid_index is None:
                            crossed_grid_index = i
        
        # 如果有交易发生，生成交易记录
        if total_amount != 0 and crossed_grid_index is not None:
            return Trade(
                timestamp=timestamp,
                price=current_price,
                amount=total_amount,
                direction="buy" if current_price < last_price else "sell",
                grid_index=crossed_grid_index,
                grid_count=1
            )
        return None
        
    def _execute_downtrend_position(self, timestamp: datetime, current_grid_index: int, price: float) -> Optional[int]:
        """执行下跌趋势的建仓操作，返回交易数量"""
        needs_update = False
        update_amount = 0
        
        # 检查当前网格以上的所有网格（包含当前网格）
        for i in range(current_grid_index, len(self.grids)):
            if not self.grids[i].has_position:
                needs_update = True
                self.grids[i].has_position = True
                update_amount += self.grids[i].position
                
        if needs_update:
            # 更新持仓和资金
            self.position += update_amount
            self.cash -= price * update_amount * (1 + self.fee_rate)
            # logging.info(f"[{timestamp.strftime('%Y-%m-%d')}] 下跌建仓：在价格{price}处补充上方网格持仓{update_amount}股")
            return update_amount
        return None
            
    def _execute_uptrend_position(self, timestamp: datetime, current_grid_index: int, price: float) -> Optional[int]:
        """执行上涨趋势的清仓操作，返回交易数量（负数）"""
        needs_update = False
        update_amount = 0
        
        # 检查当前网格以下的所有网格（不包含当前网格）
        for i in range(0, current_grid_index):
            if self.grids[i].has_position:
                needs_update = True
                self.grids[i].has_position = False
                update_amount += self.grids[i].position
                
        if needs_update:
            # 更新持仓和资金
            self.position -= update_amount
            self.cash += price * update_amount * (1 - self.fee_rate)
            # logging.info(f"[{timestamp.strftime('%Y-%m-%d')}] 上涨清仓：在价格{price}处清除下方网格持仓{update_amount}股")
            return -update_amount  # 卖出返回负数
        return None