from datetime import datetime
from typing import Dict, Tuple, Optional

import pandas as pd
from pandas import DataFrame

from backtest_params import BacktestParam
from .base import OptionStrategy, SpreadDirection
from .option_selector import OptionSelector
from .types import OptionType, TradeResult, OptionPosition, PriceConditions


class BearishCallStrategyBase(OptionStrategy):
    """熊市看涨价差策略基类
    
    策略构成：
    1. 卖出较低行权价的看涨期权
    2. 买入较高行权价的看涨期权
    
    基础策略逻辑：
    1. 开仓条件：
        - 无持仓时开仓
    2. 平仓条件：
        - 到期日自动平仓
    """
    
    def __init__(self, param: BacktestParam, option_data, etf_data, option_selector: OptionSelector):
        super().__init__(param, option_data, etf_data, option_selector)

    def _select_options(self, current_options: pd.DataFrame, current_etf_price: float, expiry: datetime) -> Tuple[
        Optional[DataFrame], Optional[DataFrame]]:
        """选择合适的期权合约"""
        return self._select_spread_options(
            current_options=current_options,
            current_etf_price=current_etf_price,
            expiry=expiry,
            sell_delta=self.param.sell_value,
            buy_delta=self.param.buy_value,
            option_type=OptionType.CALL,
            higher_buy=True  # 看涨价差买入更高行权价
        )

    def open_position(self, current_date: datetime,
                      market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult]:
        """开仓逻辑"""
        # 获取目标到期日
        expiry = self.get_target_expiry(current_date)
        if expiry is None:
            return None

        option_data = market_data['option']
        etf_data = market_data['etf']

        # 获取当前ETF价格
        current_etf_price = self._get_current_etf_price(current_date, etf_data)
        if current_etf_price is None:
            return None

        # 获取当日期权数据
        # todo 参考 etf_data改成索引的访问方式
        current_options = option_data[option_data['日期'] == current_date]

        # 选择合适的期权对
        sell_option, buy_option = self._select_options(current_options, current_etf_price, expiry)
        if sell_option is None or buy_option is None:
            return None

        # 创建期权价差持仓
        sell_position, buy_position = self._create_spread_position(
            current_date=current_date,
            options=[sell_option.iloc[0], buy_option.iloc[0]],
            option_types=[OptionType.CALL, OptionType.CALL],
            spread_type=SpreadDirection.VERTICAL_SPREAD,
            expiry=expiry
        )
        if sell_position is None or buy_position is None:
            return None

        # 记录持仓
        self.positions[sell_position.contract_code] = sell_position
        self.positions[buy_position.contract_code] = buy_position

        # 创建开仓记录
        records = []
        total_cost = 0

        # 卖出期权的开仓记录
        sell_record = self._create_open_record(
            current_date=current_date,
            position=sell_position,
            etf_price=current_etf_price
        )
        records.append(sell_record)
        total_cost += sell_record.cost

        # 买入期权的开仓记录
        buy_record = self._create_open_record(
            current_date=current_date,
            position=buy_position,
            etf_price=current_etf_price
        )
        records.append(buy_record)
        total_cost += buy_record.cost

        # 返回开仓结果
        return TradeResult(
            records=records,
            etf_price=current_etf_price,
            total_pnl=None,  # 开仓时没有盈亏
            total_cost=total_cost
        )

    def close_position(self, current_date: datetime,
                       market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult]:
        """平仓逻辑"""
        if not self.positions:
            return None

        # 获取卖出和买入的期权持仓
        sell_position, buy_position = self._get_positions()

        # 设置价格条件
        price_conditions = PriceConditions(
            expire_below=sell_position.strike,
            expire_above=buy_position.strike,
            partial_below=sell_position.strike,
            partial_above=buy_position.strike
        )

        return self._handle_close_by_price(
            current_date=current_date,
            market_data=market_data,
            sell_position=sell_position,
            buy_position=buy_position,
            price_conditions=price_conditions,
            option_type=OptionType.CALL
        )

    def _calculate_position_size(self, options: pd.DataFrame, contract_codes: list) -> int:
        """计算可开仓数量"""
        if len(contract_codes) != 2:
            return 0
        return self._calculate_spread_position_size(options, contract_codes[0], contract_codes[1])

    def _get_positions(self) -> Tuple[Optional[OptionPosition], Optional[OptionPosition]]:
        """获取看涨期权持仓"""
        return self._get_positions_by_type(OptionType.CALL)
