from strategies.strategy_context import StrategyContext
from .bullish_put_base import BullishPutStrategyBase
from .option_selector import DeltaOptionSelector


class DeltaBullishPutStrategy(BullishPutStrategyBase):
    """基于Delta的牛市看跌价差策略"""
    
    def __init__(self, context: StrategyContext, option_data, etf_data):
        super().__init__(context, option_data, etf_data, DeltaOptionSelector())
