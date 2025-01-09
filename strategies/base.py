from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
from datetime import datetime
import numpy as np
from .types import OptionType, PositionConfig, OptionPosition, TradeResult, PortfolioValue, TradeRecord
from utils import get_monthly_expiry, get_next_monthly_expiry
import logging

class OptionStrategy(ABC):
    """期权策略抽象基类"""
    
    def __init__(self, config: PositionConfig, option_data, etf_data):
        self.config = config
        self.positions: Dict[str, OptionPosition] = {}  # 当前持仓
        self.trades: Dict[datetime, List[TradeRecord]] = {}  # 交易记录
        self.cash: float = 0                           # 现金余额
        self.option_data = option_data                 # 期权数据，将在加载数据时设置
        self.etf_data = etf_data                      # ETF数据，将在加载数据时设置
        
        # 初始化logger
        self.logger = logging.getLogger(self.__class__.__name__)
        # 如果还没有处理程序，添加一个默认的控制台处理程序
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def set_option_data(self, option_data: pd.DataFrame):
        """设置期权数据"""
        self.option_data = option_data
        # 如果没有指定结束日期，使用数据集的最后日期
        if self.config.end_date is None:
            self.config.end_date = self.option_data['日期'].max()
            
    def set_etf_data(self, etf_data: pd.DataFrame):
        """设置ETF数据"""
        self.etf_data = etf_data

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
            - 如果到期日超过了回测结束日期，则使用结束日期
        """
        # 获取当月到期日
        current_expiry = get_monthly_expiry(current_date, self.option_data)
        
        # 如果是首次开仓且当前日期不是到期日，使用当月到期日
        if not self.trades and current_date < current_expiry:
            target_expiry = current_expiry
        else:
            # 其他情况（当日是到期日或非首次开仓）使用下月到期日
            target_expiry = get_next_monthly_expiry(current_date, self.option_data)
            
        # 如果目标到期日超过了回测结束日期，则使用结束日期
        if not target_expiry or target_expiry > self.config.end_date:
            target_expiry = self.config.end_date
            
        return target_expiry

    def should_open_position(self, current_date: datetime,
                           market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该开仓"""
        # 默认实现：只在没有持仓且当前日期不是回测结束日时开仓
        return not bool(self.positions) and current_date.date() < self.config.end_date.date()
    
    def should_close_position(self, current_date: datetime,
                            market_data: Dict[str, pd.DataFrame]) -> bool:
        """判断是否应该平仓"""
        if not self.positions:
            return False

        # 获取任意一个持仓（两个期权的到期日相同）
        position = next(iter(self.positions.values()))

        # 到期平仓
        return position.expiry <= current_date
    
    @abstractmethod
    def open_position(self, current_date: datetime, 
                     market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult] :
        """开仓逻辑"""
        pass
    
    @abstractmethod
    def close_position(self, current_date: datetime, 
                      market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult]:
        """平仓逻辑"""
        pass
    
    def execute(self, current_date: datetime, 
                market_data: Dict[str, pd.DataFrame]):
        """执行策略（模板方法）"""
    
        if self.should_close_position(current_date, market_data):
            result = self.close_position(current_date, market_data)
            self.record_trade(current_date, result)
            
            
        # 平仓后立即检查是否可以开仓
        if self.should_open_position(current_date, market_data):
            result = self.open_position(current_date, market_data)
            self.record_trade(current_date, result)
    

    def record_trade(self, date: datetime, details: TradeResult):
        """记录交易详细信息
        
        Args:
            date: 交易日期
            details: 交易结果对象
        """
        if not details:
            return
            
        # 确保交易日期存在
        if date not in self.trades:
            self.trades[date] = []
            
        # 记录每个期权的交易信息
        for i, record in enumerate(details.records):
            if i == len(details.records) - 1:  # 最后一条记录
                record.total_pnl = details.total_pnl
                record.total_cost = details.total_cost
            self.trades[date].append(record)
    
    def find_best_strike(self, options: pd.DataFrame, 
                        target_delta: float, 
                        option_type: OptionType) -> Tuple[float, str]:
        """找到最接近目标Delta的期权
        
        Args:
            options: 期权数据
            target_delta: 目标Delta值
            option_type: 期权类型
            
        Returns:
            Tuple[float, str]: (行权价, 合约代码)
            
        Raises:
            ValueError: 如果找不到合适的期权
        """
        # 首先移除Delta为NaN的行
        orgin_options = options
        options = options.dropna(subset=['Delta'])
        
        if options.empty:
            error_msg = (
                f"没有找到有效的期权:\n"
                f"目标Delta: {target_delta}\n"
                f"期权类型: {option_type.name}\n"
                f"原始数据行数: {len(orgin_options)}\n"
                f"筛选条件: Delta不为NaN\n"
            )
            raise ValueError(error_msg)
            
        if option_type == OptionType.CALL:
            delta_diff = (options['Delta'] - target_delta).abs()
        else:  # PUT
            delta_diff = (options['Delta'] + target_delta).abs()
            
        # 找到差异最小的期权
        best_idx = delta_diff.idxmin()
        if pd.isna(best_idx):
            raise ValueError("无法找到合适的期权（Delta差异计算结果为NaN）")
            
        best_option = options.loc[best_idx]
        best_delta = best_option['Delta']
        
        # 验证找到的期权是否合理
        if pd.isna(best_delta):
            raise ValueError("找到的期权Delta值为NaN")
            
        if option_type == OptionType.CALL and not (0 < best_delta < 1):
            raise ValueError(f"找到的CALL期权Delta值（{best_delta}）不在有效范围内")
        elif option_type == OptionType.PUT and not (-1 < best_delta < 0):
            raise ValueError(f"找到的PUT期权Delta值（{best_delta}）不在有效范围内")
        
        return best_option['行权价'], best_option['交易代码']
    
    def calculate_transaction_cost(self, quantity: int) -> float:
        """计算交易成本"""
        return abs(quantity) * self.config.transaction_cost
    
    def _get_current_option_price(self, contract_code: str,
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
    
    @abstractmethod
    def _calculate_position_size(self, options: pd.DataFrame, contract_codes: list) -> int:
        """计算可开仓数量，具体实现由子类完成"""
        pass
    
    def _create_position(self, contract_code: str, strike: float, 
                        option_type: OptionType, quantity: int,
                        current_date: datetime, options: pd.DataFrame, expiry: datetime) -> OptionPosition:
        """创建期权持仓"""
        option_data = options[options['交易代码'] == contract_code].iloc[0]
        
        position = OptionPosition(
            contract_code=contract_code,
            option_type=option_type,
            expiry=expiry,
            strike=strike,
            delta=option_data['Delta'] * (-1 if quantity < 0 else 1),
            quantity=quantity,
            open_price=option_data['收盘价'],
            open_date=current_date
        )
        
        # 更新资金
        cost = self.calculate_transaction_cost(quantity)
        premium = option_data['收盘价'] * abs(quantity) * self.config.contract_multiplier
        
        self.cash -= cost
        if quantity < 0:  # 卖出期权收取权利金
            # 卖出期权获得的权利金在开仓时不应该直接计入现金，因为这部分收益还不能确定，需要等到期权到期或平仓时才能最终确认。让
            # self.cash += premium
            pass
        else:  # 买入期权支付权利金
            self.cash -= premium
        
        return position 
    
    @abstractmethod
    def calculate_portfolio_value(self, current_date: datetime) -> PortfolioValue:
        """计算当前投资组合价值
        
        Args:
            current_date: 当前交易日期
            
        Returns:
            float: 投资组合总价值
        """
        pass 