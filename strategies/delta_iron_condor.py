from datetime import datetime
from typing import Dict

import pandas as pd

from .iron_condor_base import IronCondorStrategyBase
from .option_selector import DeltaOptionSelector
from .strategy_context import StrategyContext


class DeltaIronCondorStrategy(IronCondorStrategyBase):
    """基于Delta的熊市看涨价差策略"""
    
    def __init__(self, context: StrategyContext, option_data, etf_data):
        super().__init__(context, option_data, etf_data, DeltaOptionSelector())


    def should_open_position(self, current_date: datetime,
                           market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该开仓"""
        # 默认实现：只在没有持仓且当前日期不是回测结束日时开仓
        return not bool(self.positions) and current_date.date() < self.context.end_date.date()

    def should_close_position(self, current_date: datetime,
                            market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该平仓"""
        if not self.positions:
            return False

        # 获取任意一个持仓（两个期权的到期日相同）
        position = next(iter(self.positions.values()))

        # 到期平仓
        return position.expiry <= current_date
