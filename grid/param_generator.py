from dataclasses import dataclass
from typing import List, Dict, Iterator
import itertools

@dataclass
class GridParams:
    """网格参数数据类"""
    grid_count: int          # 网格数量
    atr_factor: float       # ATR系数
    
    def __str__(self) -> str:
        return (f"网格数量: {self.grid_count}, "
                f"ATR系数: {self.atr_factor:.1f}")

class ParamGenerator:
    """参数生成器
    
    ATR系数说明：
    - ATR (Average True Range) 用于衡量价格波动幅度
    - ATR系数用于调整网格间距：网格间距 = ATR × ATR系数
    - 系数越大，网格间距越大，交易频率越低，适合波动较大的市场
    - 系数越小，网格间距越小，交易频率越高，适合波动较小的市场
    - 0.5: 激进策略，适合低波动
    - 1.0: 均衡策略，适合中等波动
    - 1.5-2.0: 保守策略，适合高波动
    """
    def __init__(self):
        # 定义参数空间
        self.param_space = {
            'grid_count': [6, 8, 10, 12, 14, 16],
            'atr_factor': [0.5, 1.0, 1.5, 2.0]
        }
    
    def generate(self) -> Iterator[GridParams]:
        """生成所有可能的参数组合"""
        param_combinations = itertools.product(
            self.param_space['grid_count'],
            self.param_space['atr_factor']
        )
        
        for grid_count, atr_factor in param_combinations:
            yield GridParams(
                grid_count=grid_count,
                atr_factor=atr_factor
            )
    
    def get_param_count(self) -> int:
        """获取参数组合总数"""
        return (len(self.param_space['grid_count']) *
                len(self.param_space['atr_factor']))