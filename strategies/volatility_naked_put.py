from . import NakedPutStrategyBase
from .option_selector import VolatilityOptionSelector
from .strategy_context import StrategyContext


class VolatilityNakedPutStrategy(NakedPutStrategyBase):
    """基于volatility的熊市看涨价差策略"""
    
    def __init__(self, context: StrategyContext, option_data, etf_data):
        super().__init__(context, option_data, etf_data, VolatilityOptionSelector())
