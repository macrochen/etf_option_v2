from strategies.volatility_bearish_call import VolatilityBearishCallStrategy
from .delta_bearish_call import DeltaBearishCallStrategy
from .types import OptionType, StrategyType, PositionConfig, OptionPosition,PortfolioValue,TradeResult,BacktestResult
from .base import OptionStrategy, SpreadDirection
from .factory import StrategyFactory
from .bullish_put import BullishPutStrategy
from .iron_condor import IronCondorStrategy
from .naked_put import NakedPutStrategy
from .wheel import WheelStrategy
from .volatility_bearish_call import VolatilityBearishCallStrategy

# 注册策略
StrategyFactory.register(StrategyType.BEARISH_CALL, DeltaBearishCallStrategy)
StrategyFactory.register(StrategyType.BULLISH_PUT, BullishPutStrategy)
StrategyFactory.register(StrategyType.IRON_CONDOR, IronCondorStrategy)
StrategyFactory.register(StrategyType.NAKED_PUT, NakedPutStrategy)
StrategyFactory.register(StrategyType.WHEEL, WheelStrategy)
StrategyFactory.register(StrategyType.VOLATILITY_BEARISH_CALL, VolatilityBearishCallStrategy)

__all__ = [
    'OptionType',
    'StrategyType',
    'SpreadDirection',
    'PositionConfig',
    'OptionPosition',
    'PortfolioValue',
    'TradeResult',
    'BacktestResult',
    'OptionStrategy',
    'StrategyFactory',
    'DeltaBearishCallStrategy',
    'BullishPutStrategy',
    'IronCondorStrategy',
    'NakedPutStrategy',
    'WheelStrategy',
    'VolatilityBearishCallStrategy'
]