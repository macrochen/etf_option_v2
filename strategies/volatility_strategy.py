from typing import Dict, Any, List
from datetime import datetime
from strategies.base import OptionStrategy
from utils.option_utils import find_strike_price_by_volatility
from strategies.types import OptionType, PositionConfig

class VolatilityStrategy(OptionStrategy):
    """基于波动率的期权策略"""
    
    def __init__(self, params: Dict[str, Any]):
        """
        初始化波动率策略
        
        Args:
            params: 策略参数字典，包含：
                - put_volatility: float或List[float] PUT期权的目标波动率
                - call_volatility: float或List[float] CALL期权的目标波动率
                - 其他基类参数
        """
        super().__init__(params)
        self.put_volatility = params['put_volatility']
        self.call_volatility = params['call_volatility']
        
    def get_positions(self, current_price: float, expiry_date: datetime) -> List[PositionConfig]:
        """
        根据波动率计算期权持仓
        
        Args:
            current_price: 当前价格
            expiry_date: 到期日期
            
        Returns:
            期权持仓配置列表
        """
        positions = []
        
        # 处理PUT期权
        for i, vol in enumerate(self.put_volatility):
            strike = find_strike_price_by_volatility(
                self.symbol,
                current_price,
                vol,
                expiry_date,
                OptionType.PUT
            )
            # 如果是价差策略，第一个是买入，第二个是卖出
            quantity = 1 if i == 0 else -1
            positions.append(PositionConfig(
                option_type=OptionType.PUT,
                strike_price=strike,
                quantity=quantity
            ))
            
        # 处理CALL期权
        for i, vol in enumerate(self.call_volatility):
            strike = find_strike_price_by_volatility(
                self.symbol,
                current_price,
                vol,
                expiry_date,
                OptionType.CALL
            )
            # 如果是价差策略，第一个是买入，第二个是卖出
            quantity = 1 if i == 0 else -1
            positions.append(PositionConfig(
                option_type=OptionType.CALL,
                strike_price=strike,
                quantity=quantity
            ))
            
        return positions
