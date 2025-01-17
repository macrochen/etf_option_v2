from typing import Dict, Any, Tuple, Optional
import pandas as pd
from datetime import datetime
from pandas import DataFrame

from .bearish_call_base import BearishCallStrategyBase
from .types import OptionType
from .option_selector import VolatilityOptionSelector


class VolatilityBearishCallStrategy(BearishCallStrategyBase):
    """基于波动率的熊市看涨价差策略"""
    
    def __init__(self, config, option_data, etf_data):
        super().__init__(config, option_data, etf_data, VolatilityOptionSelector())

