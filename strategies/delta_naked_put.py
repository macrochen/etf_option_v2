from .naked_put_base import NakedPutStrategyBase
from .option_selector import DeltaOptionSelector
from .strategy_context import StrategyContext


class DeltaNakedPutStrategy(NakedPutStrategyBase):
    """基于Delta的熊市看涨价差策略"""
    
    def __init__(self, context: StrategyContext, option_data, etf_data):
        super().__init__(context, option_data, etf_data, DeltaOptionSelector())
