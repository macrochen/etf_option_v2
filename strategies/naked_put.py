from typing import Dict, Any, Tuple, Optional
import pandas as pd
from datetime import datetime

from . import TradeResult
from .base import OptionStrategy
from .types import OptionType, StrategyType, PortfolioValue, TradeResult, TradeRecord

class NakedPutStrategy(OptionStrategy):
    """单腿卖出看跌策略（Naked Put / Cash Secured Put）
    
    策略构成：
    1. 卖出看跌期权
    
    基础策略逻辑：
    1. 开仓条件：
        - 无持仓时开仓
        - 有足够现金支付行权成本
    2. 平仓条件：
        - 到期日自动平仓
    """
    
    def __init__(self, config, option_data, etf_data):
        super().__init__(config, option_data, etf_data)
    
    def _select_options(self, current_options: pd.DataFrame, expiry: datetime) -> Tuple[Dict, None]:
        """选择合适的期权合约
        
        策略逻辑：
        1. 卖出目标Delta的看跌期权（例如：-0.3）
        """
        # 获取目标月份的看跌期权
        target_puts = current_options[
            (current_options['交易代码'].str.contains('P' + expiry.strftime('%y%m'))) & 
            (current_options['Delta'].notna())
        ]
        
        if target_puts.empty:
            self.logger.warning(
                f"未找到符合条件的看跌期权:\n"
                f"到期日: {expiry.strftime('%Y-%m-%d')}\n"
                f"期权代码模式: P{expiry.strftime('%y%m')}\n"
                f"当前期权数量: {len(current_options)}\n"
                f"Delta有效期权数量: {current_options['Delta'].notna().sum()}"
            )
            return None, None
            
        # 找到Delta最接近目标值的期权
        sell_strike, sell_code = self.find_best_strike(
            target_puts,
            self.config.sell_delta,
            OptionType.PUT
        )
        
        if not sell_code:
            return None, None
            
        return (
            target_puts[target_puts['交易代码'] == sell_code],
            None
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
        if current_date in etf_data.index:
            current_etf_price = etf_data.loc[current_date]['收盘价']
        else:
            self.logger.warning(f"在 {current_date} 没有找到 ETF 数据，无法开仓")
            return None
        
        # 获取当日期权数据
        current_options = option_data[option_data['日期'] == current_date]
        
        # 选择合适的期权
        sell_option, _ = self._select_options(current_options, expiry)
        if sell_option is None:
            return None
            
        # 计算可开仓数量
        quantity = self._calculate_position_size(
            current_options, 
            [sell_option.iloc[0]['交易代码']]
        )
        if quantity <= 0:
            return None
            
        # 创建卖出期权持仓
        sell_position = self._create_position(
            contract_code=sell_option.iloc[0]['交易代码'],
            strike=sell_option.iloc[0]['行权价'],
            option_type=OptionType.PUT,
            quantity=-quantity,  # 负数表示卖出
            current_date=current_date,
            options=sell_option,
            expiry=expiry
        )
        
        # 记录持仓
        self.positions[sell_position.contract_code] = sell_position
        
        # 计算开仓成本
        sell_open_cost = self.calculate_transaction_cost(abs(sell_position.quantity))
        sell_open_value = sell_position.open_price * abs(sell_position.quantity) * self.config.contract_multiplier
        
        # 构建开仓记录
        records = [
            TradeRecord(
                date=current_date,
                action='卖出开仓',
                etf_price=current_etf_price,
                strike=sell_position.strike,
                price=sell_position.open_price,
                quantity=abs(sell_position.quantity),
                premium=sell_open_value,
                cost=sell_open_cost,
                delta=sell_position.delta,
                pnl=None
            )
        ]
        
        # 返回开仓结果
        return TradeResult(
            records=records,
            etf_price=current_etf_price,
            total_pnl=None,
            total_cost=sell_open_cost,
        )

    def close_position(self, current_date: datetime, 
                      market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult]:
        """平仓逻辑"""
        if not self.positions:
            return None
            
        sell_position = list(self.positions.values())[0]  # 获取卖出期权持仓
        option_data = market_data['option']
        etf_data = market_data['etf']
        current_etf_price = etf_data.loc[current_date]['收盘价']
        
        # 获取卖出期权持仓
        sell_position = next(iter(self.positions.values()))
        
        # 初始化变量
        sell_close_price = 0
        sell_close_cost = 0
        sell_close_value = 0
        
        # 情况1：期权作废
        if current_etf_price > sell_position.strike:
            sell_close_type = '到期作废'
            # 直接获得权利金收益
            sell_pnl = sell_close_value = sell_position.open_price * abs(sell_position.quantity) * self.config.contract_multiplier

            # 更新现金：确认卖出期权收取的权利金
            self.cash += sell_close_value
            
        # 情况2：期权被行权
        else:
            sell_close_type = '被行权'
            # 获取卖出期权的当前价格
            sell_options = option_data[
                (option_data['日期'] == current_date) & 
                (option_data['交易代码'] == sell_position.contract_code)
            ]
            
            if sell_options.empty:
                return None
                
            sell_close_price = sell_options.iloc[0]['收盘价']
            sell_close_cost = self.calculate_transaction_cost(abs(sell_position.quantity))
            sell_close_value = sell_close_price * abs(sell_position.quantity) * self.config.contract_multiplier
            
            # 更新现金：
            # 1. 确认卖出期权收取的权利金
            self.cash += sell_position.open_price * abs(sell_position.quantity) * self.config.contract_multiplier
            # 2. 支付平仓成本（买入期权的市场价格）
            self.cash -= sell_close_value
            # 3. 扣除交易成本
            self.cash -= sell_close_cost
            
            # 计算盈亏（权利金收益 - 平仓成本）
            sell_pnl = (sell_position.open_price - sell_close_price) * \
                       abs(sell_position.quantity) * self.config.contract_multiplier - \
                       sell_close_cost
        
        # 记录平仓信息
        records = [
            TradeRecord(
                date=current_date,
                action=sell_close_type,
                etf_price=current_etf_price,
                strike=sell_position.strike,
                price=sell_close_price,
                quantity=abs(sell_position.quantity),
                premium=sell_close_value,
                cost=sell_close_cost,
                delta=sell_position.delta,
                pnl=sell_pnl,
            )
        ]
        
        # 清除持仓
        self.positions.clear()
        
        # 返回平仓结果
        return TradeResult(
            records=records,
            etf_price=current_etf_price,
            total_pnl=sell_pnl,
            total_cost=sell_close_cost,
        )

    def _calculate_position_size(self, options: pd.DataFrame, contract_codes: list) -> int:
        """计算可开仓数量
        
        解方程计算逻辑：
        设最大合约数量为x，需要满足：
        总资金 >= x * transaction_costs + x * strike * multiplier
        
        其中：
        - x * transaction_costs 是交易成本
        - x * strike * multiplier 是行权资金准备
        """
        if len(contract_codes) != 1:
            return 0
            
        # 获取卖出期权数据
        sell_option = options[options['交易代码'] == contract_codes[0]].iloc[0]
        
        # 每份合约的成本因子
        transaction_cost = self.config.transaction_cost  # 每个合约的交易成本
        exercise_cost = sell_option['行权价'] * self.config.contract_multiplier  # 行权资金准备
        
        # 解方程：cash >= x * (transaction_cost + exercise_cost)
        cost_per_contract = transaction_cost + exercise_cost
        max_contracts = int(self.cash / cost_per_contract)
        
        return max_contracts if max_contracts > 0 else 0
    
    def calculate_portfolio_value(self, current_date: datetime) -> PortfolioValue:
        """计算当前投资组合价值
        
        对于单腿看跌策略：
        1. 现金
        2. 卖出期权的价值：
           - 开仓时收取的权利金 - 当前市场价值（负值，因为是卖出）
        """
        portfolio_value = self.cash
        option_value = 0
        
        for code, position in self.positions.items():
            current_option_price = self._get_current_option_price(code, current_date, self.option_data)
            if current_option_price is not None:
                contract_value = current_option_price * abs(position.quantity) * self.config.contract_multiplier
                # 卖出期权
                initial_premium = position.open_price * abs(position.quantity) * self.config.contract_multiplier
                option_value += initial_premium - contract_value
        
        total_value = portfolio_value + option_value
        
        # 计算日收益率
        if hasattr(self, 'last_total_value') and self.last_total_value is not None:
            daily_return = (total_value - self.last_total_value) / self.last_total_value * 100
        else:
            daily_return = 0.0
            
        # 更新上一日总市值
        self.last_total_value = total_value
        
        return PortfolioValue(
            cash=portfolio_value,
            option_value=option_value,
            total_value=total_value,
            daily_return=daily_return
        ) 