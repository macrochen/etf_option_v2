from typing import Dict, Any, Tuple, Optional, List
import pandas as pd
from datetime import datetime

from pandas import DataFrame

from .base import OptionStrategy, SpreadDirection
from .option_selector import DeltaOptionSelector
from .types import OptionType, StrategyType, PortfolioValue, TradeResult, TradeRecord, OptionPosition, PriceConditions

class IronCondorStrategy(OptionStrategy):
    """铁鹰策略（Iron Condor）
    
    策略构成：
    1. 卖出看跌期权（较高行权价）
    2. 买入看跌期权（较低行权价）
    3. 卖出看涨期权（较低行权价）
    4. 买入看涨期权（较高行权价）
    
    基础策略逻辑：
    1. 开仓条件：
        - 无持仓时开仓
        - 有足够现金支付保证金
    2. 平仓条件：
        - 到期日自动平仓
        - 触及止损线平仓
    """
    
    def __init__(self, context, option_data, etf_data):
        super().__init__(context, option_data, etf_data, DeltaOptionSelector())
    
    def _select_options(self, current_options: pd.DataFrame, current_price: float, expiry: datetime) -> Tuple[
        Optional[DataFrame], Optional[DataFrame], Optional[DataFrame], Optional[DataFrame]]:
        """选择合适的期权合约"""
        # 选择PUT组合
        put_sell, put_buy = self._select_spread_options(
            current_options=current_options,
            current_etf_price=current_price,
            expiry=expiry,
            sell_delta=self.context.put_sell_delta,
            buy_delta=self.context.put_buy_delta,
            option_type=OptionType.PUT,
            higher_buy=False  # 看跌价差买入更低行权价
        )
        
        # 选择CALL组合
        call_sell, call_buy = self._select_spread_options(
            current_options=current_options,
            current_etf_price=current_price,
            expiry=expiry,
            sell_delta=self.context.call_sell_delta,
            buy_delta=self.context.call_buy_delta,
            option_type=OptionType.CALL,
            higher_buy=True  # 看涨价差买入更高行权价
        )
        
        if any(x is None for x in [put_sell, put_buy, call_sell, call_buy]):
            return None, None, None, None
        
        return put_sell, put_buy, call_sell, call_buy

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
        
        # 选择期权合约
        put_sell, put_buy, call_sell, call_buy = self._select_options(option_data, current_etf_price, expiry)
        if any(x is None for x in [put_sell, put_buy, call_sell, call_buy]):
            return None
        
        # 创建铁鹰持仓
        positions = self._create_spread_position(
            current_date=current_date,
            options=[put_sell.iloc[0], put_buy.iloc[0],call_sell.iloc[0], call_buy.iloc[0]],
            option_types=[OptionType.PUT, OptionType.PUT, OptionType.CALL, OptionType.CALL],
            spread_type=SpreadDirection.IRON_CONDOR,
            expiry=expiry
        )

        if any(pos is None for pos in positions):
            return None
        
        # 记录持仓和创建交易记录
        records = []
        total_cost = 0

        for pos in positions:
            # 使用基类方法创建开仓记录
            record = self._create_open_record(
                current_date=current_date,
                position=pos,
                etf_price=current_etf_price
            )
            records.append(record)
            total_cost += record.cost
            
            # 添加到持仓
            self.positions[pos.contract_code] = pos
        
        # 更新现金
        self.cash -= total_cost

        return TradeResult(
            records=records,
            total_cost=total_cost,
            total_pnl=0,  # 开仓时盈亏为0
            etf_price=current_etf_price
        )

    def _calculate_position_size(self, options: pd.DataFrame, contract_codes: list) -> int:
        """计算可开仓数量
        
        铁鹰策略的资金要求：
        1. 买入期权支付权利金
        2. 交易成本
        3. 卖出期权的行权价 * 合约乘数（确保有足够资金接货）
        
        解方程计算逻辑：
        设最大合约数量为x，需要满足：
        总资金 >= x * (
            buy_puts_cost +           # 买入PUT成本
            buy_calls_cost +          # 买入CALL成本
            transaction_costs +        # 交易成本
            put_sell_strike * multiplier +   # PUT接货资金
            call_sell_strike * multiplier    # CALL接货资金
        )
        """
        if len(contract_codes) != 4:
            return 0
        
        # 获取各个期权数据
        put_sell = options[options['交易代码'] == contract_codes[0]].iloc[0]
        put_buy = options[options['交易代码'] == contract_codes[1]].iloc[0]
        call_sell = options[options['交易代码'] == contract_codes[2]].iloc[0]
        call_buy = options[options['交易代码'] == contract_codes[3]].iloc[0]
        
        # 计算买入期权的成本
        put_buy_cost = put_buy['收盘价'] * self.context.contract_multiplier
        call_buy_cost = call_buy['收盘价'] * self.context.contract_multiplier
        
        # 计算交易成本（4个合约）
        transaction_cost = self.context.transaction_cost * 4
        
        # 计算接货资金需求
        put_exercise_cost = put_sell['行权价'] * self.context.contract_multiplier
        call_exercise_cost = call_sell['行权价'] * self.context.contract_multiplier
        
        # 计算每组合约的总成本
        cost_per_combo = (
            put_buy_cost +        # 买入PUT成本
            call_buy_cost +       # 买入CALL成本
            transaction_cost +     # 交易成本
            put_exercise_cost +   # PUT接货资金
            call_exercise_cost    # CALL接货资金
        )
        
        # 计算最大可开仓数量
        max_contracts = int(self.cash / cost_per_combo)
        
        return max_contracts if max_contracts > 0 else 0

    def close_position(self, current_date: datetime, 
                      market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult]:
        """平仓逻辑
        
        铁鹰策略平仓分为两大类情况：
        1. ETF价格在中间区域（put_sell.strike < price <= call_sell.strike）
           - 所有期权作废
           
        2. ETF价格在区间外
           2.1 PUT区间（price <= put_sell.strike）
               - PUT需要平仓
               - CALL作废
           2.2 CALL区间（price > call_sell.strike）
               - CALL需要平仓
               - PUT作废
        """
        if not self.positions:
            return None
        
        # 获取四个期权持仓
        put_sell, put_buy, call_sell, call_buy = self._get_positions()
        if not all([put_sell, put_buy, call_sell, call_buy]):
            return None
        
        option_data = market_data['option']
        etf_data = market_data['etf']
        current_etf_price = self._get_current_etf_price(current_date, etf_data)
        if current_etf_price is None:
            return None
        
        records = []
        total_pnl = 0
        total_cost = 0
        
        # PUT价差的价格条件
        put_conditions = PriceConditions(
            expire_below=put_buy.strike,
            expire_above=put_sell.strike,
            partial_below=put_buy.strike,
            partial_above=put_sell.strike
        )
        
        # CALL价差的价格条件
        call_conditions = PriceConditions(
            expire_below=call_sell.strike,
            expire_above=call_buy.strike,
            partial_below=call_sell.strike,
            partial_above=call_buy.strike
        )
        
        # 处理PUT价差
        put_result = self._handle_close_by_price(
            current_date=current_date,
            market_data=market_data,
            sell_position=put_sell,
            buy_position=put_buy,
            price_conditions=put_conditions,
            option_type=OptionType.PUT
        )
        
        # 处理CALL价差
        call_result = self._handle_close_by_price(
            current_date=current_date,
            market_data=market_data,
            sell_position=call_sell,
            buy_position=call_buy,
            price_conditions=call_conditions,
            option_type=OptionType.CALL
        )
        
        if put_result is None or call_result is None:
            return None
        
        # 合并结果
        records = put_result.records + call_result.records
        total_pnl = put_result.total_pnl + call_result.total_pnl
        total_cost = put_result.total_cost + call_result.total_cost
        

        return TradeResult(
            records=records,
            etf_price=current_etf_price,
            total_pnl=total_pnl,
            total_cost=total_cost
        )


    def _get_positions(self) -> Tuple[Optional[OptionPosition], ...]:
        """获取四个期权持仓"""
        put_sell, put_buy = self._get_positions_by_type(OptionType.PUT)
        call_sell, call_buy = self._get_positions_by_type(OptionType.CALL)
        return put_sell, put_buy, call_sell, call_buy 