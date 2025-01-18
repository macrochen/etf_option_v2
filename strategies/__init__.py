from strategies.delta_bullish_put import DeltaBullishPutStrategy
from strategies.volatility_bearish_call import VolatilityBearishCallStrategy
from strategies.volatility_bullish_put import VolatilityBullishPutStrategy
from .base import OptionStrategy, SpreadDirection
from .bullish_put_base import BullishPutStrategyBase
from .delta_bearish_call import DeltaBearishCallStrategy
from .delta_iron_condor import DeltaIronCondorStrategy
from .delta_naked_put import DeltaNakedPutStrategy
from .factory import StrategyFactory
from .iron_condor_base import IronCondorStrategyBase
from .naked_put_base import NakedPutStrategyBase
from .types import OptionType, StrategyType, OptionPosition, PortfolioValue, TradeResult, BacktestResult
from .volatility_bearish_call import VolatilityBearishCallStrategy
from .volatility_iron_condor import VolatilityIronCondorStrategy
from .volatility_naked_put import VolatilityNakedPutStrategy
from .wheel import WheelStrategy
from strategies.strategy_context import StrategyContext, BacktestConfig, StrategyContextFactory

# 注册策略
StrategyFactory.register(StrategyType.BEARISH_CALL, DeltaBearishCallStrategy)
StrategyFactory.register(StrategyType.BULLISH_PUT, DeltaBullishPutStrategy)
StrategyFactory.register(StrategyType.IRON_CONDOR, DeltaIronCondorStrategy)
StrategyFactory.register(StrategyType.NAKED_PUT, DeltaNakedPutStrategy)

StrategyFactory.register(StrategyType.WHEEL, WheelStrategy)

StrategyFactory.register(StrategyType.VOLATILITY_BEARISH_CALL, VolatilityBearishCallStrategy)
StrategyFactory.register(StrategyType.VOLATILITY_BULLISH_PUT, VolatilityBullishPutStrategy)
StrategyFactory.register(StrategyType.VOLATILITY_IRON_CONDOR, VolatilityIronCondorStrategy)
StrategyFactory.register(StrategyType.VOLATILITY_NAKED_PUT, VolatilityNakedPutStrategy)

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
    'DeltaIronCondorStrategy',
    'DeltaNakedPutStrategy',
    'WheelStrategy',
    'VolatilityBearishCallStrategy',
    'VolatilityBullishPutStrategy',
    'VolatilityIronCondorStrategy',
    'VolatilityNakedPutStrategy',
]
