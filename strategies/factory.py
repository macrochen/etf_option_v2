from typing import Type
from .types import StrategyType, PositionConfig
from .base import OptionStrategy

class StrategyFactory:
    """策略工厂"""
    
    _strategies = {}  # 将在注册具体策略时填充
    
    @classmethod
    def register(cls, strategy_type: StrategyType, strategy_class: Type[OptionStrategy]):
        """注册策略"""
        cls._strategies[strategy_type] = strategy_class
    
    @classmethod
    def create_strategy(cls, strategy_type: StrategyType, config: PositionConfig) -> OptionStrategy:
        """创建策略实例"""
        if strategy_type not in cls._strategies:
            raise ValueError(f"不支持的策略类型: {strategy_type.value}")
            
        strategy_class = cls._strategies[strategy_type]
        return strategy_class(config) 