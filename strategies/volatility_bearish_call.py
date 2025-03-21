from .bearish_call_base import BearishCallStrategyBase
from .option_selector import VolatilityOptionSelector


class VolatilityBearishCallStrategy(BearishCallStrategyBase):
    """基于波动率的熊市看涨价差策略"""
    
    def __init__(self, context, option_data, etf_data):
        super().__init__(context, option_data, etf_data, VolatilityOptionSelector())

