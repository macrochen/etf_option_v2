from .types import OptionType, StrategyType, PositionConfig, OptionPosition,PortfolioValue,TradeResult,BacktestResult
from .base import OptionStrategy
from .factory import StrategyFactory
from .bearish_call import BearishCallStrategy
from .bullish_put import BullishPutStrategy
# from .iron_condor import IronCondorStrategy
from .naked_put import NakedPutStrategy

# 注册策略
StrategyFactory.register(StrategyType.BEARISH_CALL, BearishCallStrategy)
StrategyFactory.register(StrategyType.BULLISH_PUT, BullishPutStrategy)
# StrategyFactory.register(StrategyType.IRON_CONDOR, IronCondorStrategy)
StrategyFactory.register(StrategyType.NAKED_PUT, NakedPutStrategy)

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
    'BearishCallStrategy',
    'BullishPutStrategy',
    # 'IronCondorStrategy',
    'NakedPutStrategy'
] 