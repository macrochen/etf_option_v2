from typing import Dict, Any, Tuple
import pandas as pd
from datetime import datetime
from .base import OptionStrategy
from .types import OptionType, StrategyType

class BearishCallStrategy(OptionStrategy):
    """熊市看涨价差策略（Bear Call Spread / Call Credit Spread）
    
    策略构成：
    1. 卖出较低行权价的看涨期权
    2. 买入较高行权价的看涨期权
    
    基础策略逻辑：
    1. 开仓条件：
        - 无持仓时开仓
    2. 平仓条件：
        - 到期日自动平仓
    """
    
    def should_open_position(self, current_date: datetime, 
                           market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该开仓"""
        # 只在没有持仓时开仓
        return not bool(self.positions)
    
    def should_close_position(self, current_date: datetime, 
                            market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该平仓"""
        if not self.positions:
            return False
            
        # 获取任意一个持仓（两个期权的到期日相同）
        position = next(iter(self.positions.values()))
        
        # 到期平仓
        return position.expiry <= current_date
    
    def _select_options(self, current_options: pd.DataFrame, expiry: datetime) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """选择合适的期权对
        
        策略逻辑：
        1. 卖出高Delta的看涨期权（例如：0.3）
        2. 买入低Delta的看涨期权（例如：0.2）
        """
        # 获取目标月份的看涨期权
        target_calls = current_options[
            current_options['认购认沽'] == '认购'
        ]
        
        if target_calls.empty:
            return None, None
            
        # 找到Delta最接近卖出目标值的期权
        sell_strike, sell_code = self.find_best_strike(
            target_calls,
            self.config.sell_delta,  # 使用较高的Delta值
            OptionType.CALL
        )
        
        if not sell_code:
            return None, None
            
        # 找到Delta最接近买入目标值的期权
        buy_strike, buy_code = self.find_best_strike(
            target_calls,
            self.config.buy_delta,  # 使用较低的Delta值
            OptionType.CALL
        )
        
        if not buy_code:
            return None, None
            
        # 确保买入期权的行权价高于卖出期权
        sell_option = target_calls[target_calls['交易代码'] == sell_code].iloc[0]
        buy_option = target_calls[target_calls['交易代码'] == buy_code].iloc[0]
        
        if buy_option['行权价'] <= sell_option['行权价']:
            return None, None
            
        return (
            target_calls[target_calls['交易代码'] == sell_code],
            target_calls[target_calls['交易代码'] == buy_code]
        )
    
    def open_position(self, current_date: datetime, 
                     market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """开仓逻辑"""
        # 获取目标到期日
        expiry = self.get_target_expiry(current_date)
        if expiry is None:
            return None
            
        option_data = market_data['option']
        
        # 获取当日期权数据
        current_options = option_data[option_data['日期'] == current_date]
        
        # 选择合适的期权对
        sell_option, buy_option = self._select_options(current_options, expiry)
        if sell_option is None or buy_option is None:
            return None
            
        # 计算可开仓数量（考虑两个期权）
        quantity = self._calculate_position_size(
            current_options, 
            [sell_option.iloc[0]['交易代码'], buy_option.iloc[0]['交易代码']]
        )
        if quantity <= 0:
            return None
            
        # 创建卖出期权持仓
        sell_position = self._create_position(
            contract_code=sell_option.iloc[0]['交易代码'],
            strike=sell_option.iloc[0]['行权价'],
            option_type=OptionType.CALL,
            quantity=-quantity,  # 负数表示卖出
            current_date=current_date,
            options=sell_option
        )
        
        # 创建买入期权持仓
        buy_position = self._create_position(
            contract_code=buy_option.iloc[0]['交易代码'],
            strike=buy_option.iloc[0]['行权价'],
            option_type=OptionType.CALL,
            quantity=quantity,  # 正数表示买入
            current_date=current_date,
            options=buy_option
        )
        
        # 记录持仓
        self.positions[sell_position.contract_code] = sell_position
        self.positions[buy_position.contract_code] = buy_position
        
        return {
            "action": "open",
            "sell_position": sell_position,
            "buy_position": buy_position,
            "cash": self.cash,
            "margin": self.margin
        }
    
    def close_position(self, current_date: datetime, 
                      market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """平仓逻辑
        
        熊市看涨价差策略平仓时：
        1. 买入平仓之前卖出的低行权价看涨期权
        2. 卖出平仓之前买入的高行权价看涨期权
        """
        if not self.positions:
            return None
            
        option_data = market_data['option']
        total_cost = 0
        positions_info = []
        
        # 找到卖出和买入的期权持仓
        sell_position = None
        buy_position = None
        for position in self.positions.values():
            if position.quantity < 0:
                sell_position = position
            else:
                buy_position = position
                
        if not sell_position or not buy_position:
            return None
            
        # 获取卖出期权的当前价格（用于买入平仓）
        sell_options = option_data[
            (option_data['日期'] == current_date) & 
            (option_data['交易代码'] == sell_position.contract_code)
        ]
        
        if sell_options.empty:
            return None
            
        sell_close_price = sell_options.iloc[0]['收盘价']
        
        # 获取买入期权的当前价格（用于卖出平仓）
        buy_options = option_data[
            (option_data['日期'] == current_date) & 
            (option_data['交易代码'] == buy_position.contract_code)
        ]
        
        if buy_options.empty:
            return None
            
        buy_close_price = buy_options.iloc[0]['收盘价']
        
        # 计算平仓成本
        sell_close_cost = self.calculate_transaction_cost(abs(sell_position.quantity))
        buy_close_cost = self.calculate_transaction_cost(abs(buy_position.quantity))
        total_cost = sell_close_cost + buy_close_cost
        
        # 计算平仓价值
        # 买入平仓之前卖出的期权
        sell_close_value = sell_close_price * abs(sell_position.quantity) * self.config.contract_multiplier
        # 卖出平仓之前买入的期权
        buy_close_value = buy_close_price * abs(buy_position.quantity) * self.config.contract_multiplier
        
        # 更新资金
        self.cash -= total_cost
        self.cash -= sell_close_value  # 买入平仓支付权利金
        self.cash += buy_close_value   # 卖出平仓收取权利金
        self.margin = 0  # 释放保证金
        
        # 记录平仓信息
        positions_info = [
            {
                "position": sell_position,
                "close_price": sell_close_price,
                "close_cost": sell_close_cost,
                "close_value": sell_close_value,
                "action": "买入平仓"
            },
            {
                "position": buy_position,
                "close_price": buy_close_price,
                "close_cost": buy_close_cost,
                "close_value": buy_close_value,
                "action": "卖出平仓"
            }
        ]
        
        result = {
            "action": "close",
            "positions": positions_info,
            "total_cost": total_cost,
            "cash": self.cash,
            "margin": self.margin
        }
        
        # 清除持仓
        self.positions.clear()
        
        return result 