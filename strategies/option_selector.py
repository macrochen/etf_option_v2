from abc import ABC, abstractmethod
from typing import Optional, Tuple
import pandas as pd
from datetime import datetime
from .types import OptionType

import logging

class OptionSelector(ABC):
    """期权选择器抽象类
    
    用于根据不同的选择策略（如delta、波动率等）选择合适的期权合约
    """
    def __init__(self):

        # 初始化logger
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def find_best_options(self,
                              options: pd.DataFrame,
                              current_price: float,
                              target_value: float,
                              option_type: OptionType,
                              expiry: datetime) -> pd.DataFrame:
        """查找最佳的期权组合
        
        Args:
            options: 当前可用的期权数据
            sell_value: 卖出期权的目标值（delta或波动率）
            buy_value: 买入期权的目标值（delta或波动率）
            option_type: 期权类型（看涨/看跌）
            expiry: 到期日
            
        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: 卖出期权和买入期权
        """
        pass
    


class DeltaOptionSelector(OptionSelector):
    """基于Delta的期权选择器"""


    def find_best_options(self,
                              options: pd.DataFrame,
                              current_price: float,
                              target_delta: float,
                              option_type: OptionType,
                              expiry: datetime) -> pd.DataFrame:
        """查找最佳的期权组合"""
        """查找目标Delta的期权"""
        # 创建数据副本而不是视图
        # 根据期权类型选择代码前缀
        code_prefix = 'P' if option_type == OptionType.PUT else 'C'
        expiry_code = expiry.strftime('%y%m')

        # 筛选目标月份的期权
        target_options = options[
            (options['交易代码'].str.contains(f"{code_prefix}{expiry_code}")) &
            (options['Delta'].notna())
            ].copy()

        if target_options.empty:
            return target_options

        # 使用 loc 赋值
        target_options.loc[:, 'Delta_Diff'] = abs(target_options['Delta'] - target_delta)

        # 按Delta差值排序并返回最接近的
        return target_options.sort_values('Delta_Diff')
    

class VolatilityOptionSelector(OptionSelector):
    """基于波动率的期权选择器"""

    def find_best_options(self,
                          options: pd.DataFrame,
                          current_price: float,
                          target_value: float,
                          option_type: OptionType,
                          expiry: datetime) -> pd.DataFrame:
        """查找最佳的期权组合"""
        # 选择卖出期权
        pass
