from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import pandas as pd
from datetime import datetime
import numpy as np
from .types import OptionType, PositionConfig, OptionPosition
from .utils import get_monthly_expiry, get_next_monthly_expiry

class OptionStrategy(ABC):
    """期权策略抽象基类"""
    
    def __init__(self, config: PositionConfig):
        self.config = config
        self.positions: Dict[str, OptionPosition] = {}  # 当前持仓
        self.trades: Dict[datetime, Dict] = {}          # 交易记录
        self.cash: float = 0                           # 现金余额
        self.margin: float = 0                         # 保证金
        self.initial_margin: float = 0                 # 初始保证金
        self.option_data = None                        # 期权数据，将在加载数据时设置

    def set_option_data(self, option_data: pd.DataFrame):
        """设置期权数据"""
        self.option_data = option_data

    def get_target_expiry(self, current_date: datetime) -> Optional[datetime]:
        """获取目标到期日
        
        Args:
            current_date: 当前交易日期
            
        Returns:
            Optional[datetime]: 目标到期日。如果无法获取则返回None
            
        说明：
            - 如果是首次开仓（没有交易记录），使用当月到期日
            - 如果当前日期正好是当月到期日，使用下月到期日
            - 如果是平仓后再开仓，使用下月到期日
        """
        # 获取当月到期日
        current_expiry = get_monthly_expiry(current_date, self.option_data)
        
        # 如果是首次开仓且当前日期不是到期日，使用当月到期日
        if not self.trades and current_date < current_expiry:
            return current_expiry
            
        # 其他情况（当日是到期日或非首次开仓）使用下月到期日
        return get_next_monthly_expiry(current_date, self.option_data)

    @abstractmethod
    def should_open_position(self, current_date: datetime, 
                           market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该开仓"""
        pass
    
    @abstractmethod
    def should_close_position(self, current_date: datetime, 
                            market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该平仓"""
        pass
    
    @abstractmethod
    def open_position(self, current_date: datetime, 
                     market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """开仓逻辑"""
        pass
    
    @abstractmethod
    def close_position(self, current_date: datetime, 
                      market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """平仓逻辑"""
        pass
    
    def execute(self, current_date: datetime, 
                market_data: Dict[str, pd.DataFrame]) -> Optional[Dict[str, Any]]:
        """执行策略（模板方法）"""
        if self.should_close_position(current_date, market_data):
            result = self.close_position(current_date, market_data)
            self.record_trade(current_date, "close", result)
            return result
            
        if self.should_open_position(current_date, market_data):
            result = self.open_position(current_date, market_data)
            self.record_trade(current_date, "open", result)
            return result
            
        return None
    
    def record_trade(self, date: datetime, action: str, details: Dict[str, Any]):
        """记录交易"""
        self.trades[date] = {
            "action": action,
            "details": details,
            "cash": self.cash,
            "margin": self.margin
        }
    
    def find_best_strike(self, options: pd.DataFrame, 
                        target_delta: float, 
                        option_type: OptionType) -> Tuple[float, str]:
        """找到最接近目标Delta的期权"""
        if option_type == OptionType.CALL:
            delta_diff = (options['Delta'] - target_delta).abs()
        else:  # PUT
            delta_diff = (options['Delta'] + target_delta).abs()
            
        best_idx = delta_diff.idxmin()
        best_option = options.loc[best_idx]
        
        return best_option['行权价'], best_option['交易代码']
    
    def calculate_margin(self, strike: float, quantity: int) -> float:
        """计算保证金"""
        return strike * abs(quantity) * self.config.contract_multiplier * self.config.margin_ratio
    
    def calculate_transaction_cost(self, quantity: int) -> float:
        """计算交易成本"""
        return abs(quantity) * self.config.transaction_cost
    
    def _get_current_price(self, contract_code: str, 
                          current_date: datetime, 
                          option_data: pd.DataFrame) -> Optional[float]:
        """获取当前价格"""
        current_data = option_data[
            (option_data['日期'] == current_date) & 
            (option_data['交易代码'] == contract_code)
        ]
        
        if current_data.empty:
            return None
            
        return current_data.iloc[0]['收盘价']
    
    def _get_expiry_from_code(self, contract_code: str) -> datetime:
        """从合约代码解析到期日"""
        # 示例：510300P2309M03950
        # 提取年月：2309 -> 2023年9月
        year = int('20' + contract_code[6:8])
        month = int(contract_code[8:10])
        # 使用第一天作为参考日期来获取当月到期日
        reference_date = datetime(year, month, 1)
        return get_monthly_expiry(reference_date, self.option_data)
    
    def _calculate_position_size(self, options: pd.DataFrame, 
                               contract_codes: list) -> int:
        """计算可开仓数量"""
        total_margin = 0
        total_cost = 0
        
        for code in contract_codes:
            option_data = options[options['交易代码'] == code].iloc[0]
            strike = option_data['行权价']
            margin = self.calculate_margin(strike, 1)
            total_margin += margin
            total_cost += self.config.transaction_cost
        
        max_contracts = int(self.cash / (total_margin + total_cost))
        return max_contracts if max_contracts > 0 else 0
    
    def _create_position(self, contract_code: str, strike: float, 
                        option_type: OptionType, quantity: int,
                        current_date: datetime, options: pd.DataFrame) -> OptionPosition:
        """创建期权持仓"""
        option_data = options[options['交易代码'] == contract_code].iloc[0]
        
        position = OptionPosition(
            contract_code=contract_code,
            option_type=option_type,
            expiry=self._get_expiry_from_code(contract_code),
            strike=strike,
            delta=option_data['Delta'] * (-1 if quantity < 0 else 1),
            quantity=quantity,
            open_price=option_data['收盘价'],
            open_date=current_date
        )
        
        # 更新资金
        cost = self.calculate_transaction_cost(quantity)
        margin = self.calculate_margin(strike, quantity)
        premium = option_data['收盘价'] * abs(quantity) * self.config.contract_multiplier
        
        self.cash -= cost
        if quantity < 0:  # 卖出期权收取权利金
            self.cash += premium
        else:  # 买入期权支付权利金
            self.cash -= premium
            
        self.margin += margin
        
        return position 