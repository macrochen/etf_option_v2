from typing import Type, Optional
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
    def create_strategy(cls, strategy_type: StrategyType, 
                       config: PositionConfig, option_data, etf_data) -> Optional[OptionStrategy]:
        """创建策略实例
        
        Args:
            strategy_type: 策略类型
            config: 持仓配置，包含回测结束日期
            option_data: 期权数据，必传
            etf_data: ETF数据，必传
            
        Returns:
            Optional[OptionStrategy]: 策略实例，如果策略类型不存在则返回None
            
        Raises:
            ValueError: 当策略类型不存在或必要参数未传入时抛出
        """
        if strategy_type not in cls._strategies:
            raise ValueError(f"不支持的策略类型: {strategy_type}")
            
        strategy_class = cls._strategies[strategy_type]
        return strategy_class(config, option_data, etf_data)