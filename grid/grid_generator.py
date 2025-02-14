from dataclasses import dataclass
from typing import List, Tuple
import numpy as np

@dataclass
class Grid:
    """网格数据类"""
    price: float       # 网格价格
    position: int = 0  # 每次交易的数量（必须是100的整数倍）
    grid_percent: float = 0.0  # 添加：网格间距百分比
    has_position: bool = False  # 是否持有该网格对应的仓位

class GridGenerator:
    """网格生成器"""
    
    def __init__(self, initial_capital: float = 100000.0, fee_rate: float = 0.0001):
        """初始化网格生成器
        
        Args:
            initial_capital: 初始资金，默认10万
            fee_rate: 交易费率，默认万分之一
        """
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        
    def generate_grids(self, current_price: float, atr: float, 
                      grid_count: int, atr_factor: float) -> tuple[list[Grid], float]:
        """生成网格
        
        Args:
            current_price: 当前价格（作为第一个网格）
            atr: ATR值
            grid_count: 网格数量
            atr_factor: ATR系数
            
        Returns:
            List[Grid]: 网格列表
        """
        # 计算网格间距
        grid_spacing = atr * atr_factor
        # 计算网格间距百分比
        grid_percent = (grid_spacing / current_price) * 100
        
        # 计算上下网格数量
        upper_count = (grid_count - 1) // 2
        lower_count = grid_count - 1 - upper_count
        
        # 生成网格价格
        grids = []
        
        # 生成下方网格
        for i in range(lower_count):
            price = current_price - (i + 1) * grid_spacing
            grids.insert(0, Grid(
                price=price,
                grid_percent=grid_percent
            ))
        
        # 添加当前价格网格
        grids.append(Grid(
            price=current_price,
            grid_percent=grid_percent
        ))
        
        # 生成上方网格
        for i in range(upper_count):
            price = current_price + (i + 1) * grid_spacing
            grids.append(Grid(
                price=price,
                grid_percent=grid_percent
            ))
            
        # 计算每个网格的交易量
        self._calculate_grid_positions(grids)
        
        return grids, grid_percent
    
    def _calculate_grid_positions(self, grids: List[Grid]) -> None:
        """计算每个网格的交易量，确保是100的整数倍
        
        Args:
            grids: 网格列表
        """
        # 计算每个网格的交易金额：总资金 / 网格数量，预留一部分用于手续费
        grid_capital = (self.initial_capital / len(grids)) / (1 + self.fee_rate)
        
        # 为每个网格计算交易数量
        for grid in grids:
            # 计算该网格价位可交易的数量
            position = grid_capital / grid.price
            # 向下取整到最接近的100的倍数
            grid.position = int(position // 100) * 100