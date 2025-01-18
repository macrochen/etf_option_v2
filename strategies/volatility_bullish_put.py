from .bullish_put_base import BullishPutStrategyBase
from .option_selector import VolatilityOptionSelector


class VolatilityBullishPutStrategy(BullishPutStrategyBase):
    """基于波动率的牛市看跌价差策略"""
    
    def __init__(self, context, option_data, etf_data):
        super().__init__(context, option_data, etf_data, VolatilityOptionSelector())

