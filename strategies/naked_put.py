from typing import Dict, Any, Tuple, Optional
import pandas as pd
from datetime import datetime

from . import TradeResult
from .base import OptionStrategy
from .option_selector import DeltaOptionSelector
from .types import OptionType, StrategyType, PortfolioValue, TradeResult, TradeRecord, OptionPosition, PriceConditions


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
        super().__init__(config, option_data, etf_data, DeltaOptionSelector())
    
    def _select_options(self, current_options: pd.DataFrame, current_price: float, expiry: datetime) -> Tuple[Dict, None]:
        """选择合适的期权合约
        
        策略逻辑：
        1. 卖出目标Delta的看跌期权（例如：-0.3）
        """
        # 选择PUT
        sell_options = self.find_best_options(
            current_options,
            current_price,
            self.config.sell_delta,
            OptionType.PUT,
            expiry
        )
        self._check_options_selection(sell_options, expiry, "看跌")
        
        if sell_options.empty:
            return None, None
            
        return sell_options.iloc[[0]], None

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
        current_options = option_data[option_data['日期'] == current_date]
        
        # 选择合适的期权
        sell_option, _ = self._select_options(current_options, current_etf_price, expiry)
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
        
        # 使用基类方法创建开仓记录
        record = self._create_open_record(
            current_date=current_date,
            position=sell_position,
            etf_price=current_etf_price
        )
        
        # 返回开仓结果
        return TradeResult(
            records=[record],
            etf_price=current_etf_price,
            total_pnl=0,
            total_cost=record.cost,
        )

    def close_position(self, current_date: datetime, 
                      market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult]:
        """平仓逻辑"""
        if not self.positions:
            return None
    
        # 获取卖出期权持仓
        sell_position, _ = self._get_positions()
        
        # 设置价格条件
        price_conditions = PriceConditions(
            expire_below=0,  # 单腿策略不需要这个条件
            expire_above=sell_position.strike,
            partial_below=0,  # 单腿策略不需要这个条件
            partial_above=sell_position.strike
        )
        
        return self._handle_single_close_by_price(
            current_date=current_date,
            market_data=market_data,
            sell_position=sell_position,
            price_conditions=price_conditions,
            option_type=OptionType.PUT
        )

    def _calculate_position_size(self, options: pd.DataFrame, contract_codes: list) -> int:
        """计算可开仓数量"""
        if len(contract_codes) != 1:
            return 0
        return self._calculate_single_position_size(options, contract_codes[0])
    
    def _get_positions(self) -> Tuple[Optional[OptionPosition], None]:
        """获取看跌期权持仓"""
        sell_pos, _ = self._get_positions_by_type(OptionType.PUT)
        return sell_pos, None 