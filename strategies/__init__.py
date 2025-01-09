from .types import OptionType, StrategyType, PositionConfig, OptionPosition,PortfolioValue,TradeResult,BacktestResult
from .base import OptionStrategy
from .factory import StrategyFactory
from .bearish_call import BearishCallStrategy

# 注册策略
StrategyFactory.register(StrategyType.BEARISH_CALL, BearishCallStrategy)

__all__ = [
    'OptionType',
    'StrategyType',
    'PositionConfig',
    'OptionPosition',
    'PortfolioValue',
    'TradeResult',
    'BacktestResult',
    'OptionStrategy',
    'StrategyFactory',
    'BearishCallStrategy'
] 