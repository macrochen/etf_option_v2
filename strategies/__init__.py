from strategies.delta_bullish_put import DeltaBullishPutStrategy
from strategies.volatility_bearish_call import VolatilityBearishCallStrategy
from strategies.volatility_bullish_put import VolatilityBullishPutStrategy
from .base import OptionStrategy, SpreadDirection
from .bullish_put_base import BullishPutStrategyBase
from .delta_bearish_call import DeltaBearishCallStrategy
from .factory import StrategyFactory
from .iron_condor import IronCondorStrategy
from .naked_put import NakedPutStrategy
from .types import OptionType, StrategyType, OptionPosition, PortfolioValue, TradeResult, BacktestResult
from .volatility_bearish_call import VolatilityBearishCallStrategy
from .wheel import WheelStrategy
from strategies.strategy_context import StrategyContext, BacktestConfig, StrategyContextFactory

# 注册策略
StrategyFactory.register(StrategyType.BEARISH_CALL, DeltaBearishCallStrategy)
StrategyFactory.register(StrategyType.BULLISH_PUT, DeltaBullishPutStrategy)
StrategyFactory.register(StrategyType.IRON_CONDOR, IronCondorStrategy)
StrategyFactory.register(StrategyType.NAKED_PUT, NakedPutStrategy)
StrategyFactory.register(StrategyType.WHEEL, WheelStrategy)
StrategyFactory.register(StrategyType.VOLATILITY_BEARISH_CALL, VolatilityBearishCallStrategy)
StrategyFactory.register(StrategyType.VOLATILITY_BULLISH_PUT, VolatilityBullishPutStrategy)

__all__ = [
    'OptionType',
    'StrategyType',
    'SpreadDirection',
    'OptionPosition',
    'PortfolioValue',
    'TradeResult',
    'BacktestResult',
    'OptionStrategy',
    'StrategyFactory',
    'DeltaBearishCallStrategy',
    'DeltaBullishPutStrategy',
    'IronCondorStrategy',
    'NakedPutStrategy',
    'WheelStrategy',
    'VolatilityBearishCallStrategy',
    'VolatilityBullishPutStrategy',
]
