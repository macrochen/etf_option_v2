from backtest_params import BacktestParam
from .bearish_call_base import BearishCallStrategyBase
from .option_selector import DeltaOptionSelector


class DeltaBearishCallStrategy(BearishCallStrategyBase):
    """基于Delta的熊市看涨价差策略"""
    
    def __init__(self, param: BacktestParam, option_data, etf_data):
        super().__init__(param, option_data, etf_data, DeltaOptionSelector())
