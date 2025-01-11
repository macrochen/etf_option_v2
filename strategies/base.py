from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
from datetime import datetime
import numpy as np
from .types import OptionType, PositionConfig, OptionPosition, TradeResult, PortfolioValue, TradeRecord, PriceConditions
from utils import get_monthly_expiry, get_next_monthly_expiry
import logging
from enum import Enum, auto

class SpreadDirection(Enum):
    VERTICAL_SPREAD = (-1, 1)         # 垂直价差
    IRON_CONDOR = (-1, 1, -1, 1)      # 铁蝶
    BUTTERFLY = (-1, 2, -1)           # 蝶式
    # 可以继续添加其他组合策略的方向 

class CloseType(Enum):
    ALL_EXPIRE = auto()      # 全部作废
    PARTIAL_EXPIRE = auto()  # 部分作废部分平仓
    ALL_CLOSE = auto()       # 全部平仓


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
        options = options.dropna(subset=['Delta'])
        
        if options.empty:
            error_msg = (
                f"没有找到有效的期权:\n"
                f"目标Delta: {target_delta}\n"
                f"期权类型: {option_type.name}\n"
                f"筛选条件: Delta不为NaN\n"
            )
            self.logger.warning(error_msg)
            return None, None
        
        # 确保Delta是数值类型
        options['Delta'] = pd.to_numeric(options['Delta'], errors='coerce')
        options = options.dropna(subset=['Delta'])
        
        if options.empty:
            self.logger.warning("转换Delta为数值类型后没有有效数据")
            return None, None
        
        if option_type == OptionType.CALL:
            # CALL期权的Delta为正值
            delta_diff = (options['Delta'] - target_delta).abs()
        else:  # PUT
            # PUT期权的Delta为负值，但target_delta已经是负值，所以直接相减
            delta_diff = (options['Delta'] - target_delta).abs()
            
        # 找到差异最小的期权
        best_idx = delta_diff.idxmin()
        if pd.isna(best_idx):
            self.logger.warning("无法找到合适的期权（Delta差异计算结果为NaN）")
            return None, None
            
        best_option = options.loc[best_idx]
        
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
                        current_date: datetime, options: pd.DataFrame, 
                        expiry: datetime) -> OptionPosition:
        """创建期权持仓
        
        Args:
            contract_code: 合约代码
            strike: 行权价
            option_type: 期权类型
            quantity: 持仓数量（正数为买入，负数为卖出）
            current_date: 当前日期
            options: 期权数据
            expiry: 到期日
            
        Returns:
            OptionPosition: 期权持仓对象，包含考虑合约乘数的权利金
        """
        if isinstance(options, pd.Series):
            option_data = options if options['交易代码'] == contract_code else None
        else:
            option_data = options[options['交易代码'] == contract_code].iloc[0] if not options[options['交易代码'] == contract_code].empty else None
        
        position = OptionPosition(
            contract_code=contract_code,
            option_type=option_type,
            expiry=expiry,
            strike=strike,
            delta=option_data['Delta'] * (-1 if quantity < 0 else 1),
            quantity=quantity,
            open_price=option_data['收盘价'],
            open_date=current_date,
            contract_multiplier=self.config.contract_multiplier,
            transaction_cost=self.config.transaction_cost
        )

        # 卖出虽然收到的权利金，但是要到期才能最终确认，这里不能直接加到现金中，买入则需要立即确认
        if quantity > 0:
            self.cash += position.premium
        
        return position
    
    def calculate_portfolio_value(self, current_date: datetime) -> PortfolioValue:
        """计算当前投资组合价值的通用方法
        
        计算逻辑：
        1. 现金价值
        2. 期权价值：
           - 卖出期权：开仓收取的权利金 - 当前市场价值
           - 买入期权：当前市场价值
        """
        portfolio_value = self.cash
        option_value = 0
        
        for code, position in self.positions.items():
            current_option_price = self._get_current_option_price(code, current_date, self.option_data)
            if current_option_price is not None:
                contract_value = current_option_price * abs(position.quantity) * self.config.contract_multiplier
                if position.quantity < 0:  # 卖出期权
                    # 开仓收取的权利金 - 当前需要支付的价值
                    option_value += position.premium - contract_value
                else:  # 买入期权
                    option_value += contract_value
        
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

    def _create_close_record(self, current_date: datetime, position: OptionPosition, 
                            close_price: float, etf_price: float, 
                            is_expire: bool = False) -> Tuple[TradeRecord, float, float]:
        """创建平仓记录
        
        Args:
            current_date: 当前日期
            position: 期权持仓
            close_price: 平仓价格
            etf_price: ETF价格
            is_expire: 是否为到期作废
            
        Returns:
            (交易记录, 盈亏, 成本)
        """
        action = '到期作废' if is_expire else ('买入平仓' if position.quantity < 0 else '卖出平仓')
        close_cost = 0 if is_expire else self.calculate_transaction_cost(abs(position.quantity))
        close_value = close_price * abs(position.quantity) * position.contract_multiplier
        
        # 计算盈亏
        if position.quantity < 0:  # 卖出期权
            pnl = position.premium - (0 if is_expire else close_value)
        else:  # 买入期权
            pnl = (close_value if not is_expire else 0) + position.premium
            
        record = TradeRecord(
            date=current_date,
            action=action,
            etf_price=etf_price,
            strike=position.strike,
            price=close_price,
            quantity=abs(position.quantity),
            premium=close_value,
            cost=close_cost,
            delta=position.delta,
            pnl=pnl
        )
        
        return record, pnl, close_cost 

    def find_options_by_delta(self, 
                             options: pd.DataFrame,
                             target_delta: float,
                             option_type: OptionType,
                             expiry: datetime) -> pd.DataFrame:
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
    
    def _create_open_record(self, current_date: datetime, position: OptionPosition, 
                           etf_price: float) -> TradeRecord:
        """创建开仓记录
        
        Args:
            current_date: 当前日期
            position: 期权持仓
            etf_price: ETF价格
            
        Returns:
            (交易记录, 交易成本)
        """

        # 确定开仓动作
        action = '卖出开仓' if position.quantity < 0 else '买入开仓'
        
        record = TradeRecord(
            date=current_date,
            action=action,
            etf_price=etf_price,
            strike=position.strike,
            price=position.open_price,
            quantity=abs(position.quantity),
            premium=position.premium,
            cost=position.open_cost,
            delta=position.delta,
            pnl=None  # 开仓时没有盈亏
        )
        
        return record

    def _get_current_etf_price(self, current_date: datetime, etf_data: pd.DataFrame) -> Optional[float]:
        """获取当前ETF价格
        
        Args:
            current_date: 当前日期
            etf_data: ETF数据
            
        Returns:
            当前ETF价格，如果找不到数据则返回None
        """
        if current_date in etf_data.index:
            return etf_data.loc[current_date]['收盘价']
        else:
            self.logger.warning(f"在 {current_date} 没有找到 ETF 数据")
            return None 

    def _get_positions_by_type(self, option_type: OptionType) -> Tuple[Optional[OptionPosition], Optional[OptionPosition]]:
        """获取指定类型的期权持仓
        
        Args:
            option_type: 期权类型（PUT/CALL）
            
        Returns:
            (卖出持仓, 买入持仓)
        """
        sell_pos = buy_pos = None
        
        for position in self.positions.values():
            if position.option_type == option_type:
                if position.quantity < 0:
                    sell_pos = position
                else:
                    buy_pos = position
                    
        return sell_pos, buy_pos 

    def _handle_option_expiry(self, position: OptionPosition) -> Tuple[str, float, float, float]:
        """处理期权作废的通用方法
        
        Returns:
            Tuple[str, float, float, float]: 
            (作废类型, 盈亏, 作废价格, 作废成本)
        """
        close_type = '到期作废'
        pnl = position.premium
        close_price = 0
        close_cost = 0
        
        # 更新现金
        if position.quantity < 0:  # 卖出期权
            self.cash += position.premium
        
        return close_type, pnl, close_price, close_cost

    def _create_spread_position(self, 
                              current_date: datetime,
                              options: List[pd.Series],
                              option_types: List[OptionType],
                              spread_type: SpreadDirection,
                              expiry: datetime) -> List[Optional[OptionPosition]]:
        """
        创建期权组合持仓的通用方法
        
        Args:
            current_date: 当前日期
            options: 期权数据列表，可以是任意数量的期权
            option_types: 对应的期权类型列表（PUT/CALL）
            spread_type: 期权组合策略类型
            expiry: 到期日
        """
        # 验证期权数量与策略方向的匹配性
        if len(options) != len(spread_type.value):
            raise ValueError(f"{spread_type.name} 策略需要 {len(spread_type.value)} 个期权，"
                            f"但提供了 {len(options)} 个")

        quantity = self._calculate_position_size(
            pd.DataFrame(options),
            [option['交易代码'] for option in options]
        )
        
        if quantity == 0:
            return [None] * len(options)
        
        positions = []
        for option, option_type, direction in zip(options, option_types, spread_type.value):
            position = self._create_position(
                current_date=current_date,
                contract_code=option['交易代码'],
                quantity=quantity * direction,
                strike=option['行权价'],
                option_type=option_type,
                options=option,
                expiry=expiry
            )
            positions.append(position)
        
        return positions

    def _handle_spread_close(self, 
                            current_date: datetime,
                            sell_position: OptionPosition,
                            buy_position: OptionPosition,
                            current_etf_price: float,
                            option_data: pd.DataFrame,
                            close_type: CloseType) -> Tuple[List[TradeRecord], float, float]:
        """处理期权价差平仓的通用方法"""
        records = []
        total_pnl = 0
        total_cost = 0

        if close_type == CloseType.ALL_EXPIRE:
            # 处理到期作废
            sell_close_type, sell_pnl, sell_close_price, sell_close_cost = \
                self._handle_option_expiry(sell_position)
            buy_close_type, buy_pnl, buy_close_price, buy_close_cost = \
                self._handle_option_expiry(buy_position)
            
            sell_is_expire = buy_is_expire = True
            total_pnl = sell_pnl + buy_pnl
            total_cost = sell_close_cost + buy_close_cost
            
        elif close_type == CloseType.PARTIAL_EXPIRE:
            # sell 平仓
            sell_close_type, sell_pnl, sell_close_price, sell_close_cost, sell_close_value = \
                self._handle_option_close(sell_position, current_date, option_data)
            # buy 作废
            buy_close_type, buy_pnl, buy_close_price, buy_close_cost = \
                self._handle_option_expiry(buy_position)
            
            sell_is_expire = False
            buy_is_expire =True
            total_pnl = sell_pnl + buy_pnl
            total_cost = sell_close_cost + buy_close_cost
            
        else:  # CloseType.ALL_CLOSE
            # 全部平仓
            sell_close_type, sell_pnl, sell_close_price, sell_close_cost, sell_close_value = \
                self._handle_option_close(sell_position, current_date, option_data)
            buy_close_type, buy_pnl, buy_close_price, buy_close_cost, buy_close_value = \
                self._handle_option_close(buy_position, current_date, option_data)
            
            sell_is_expire = buy_is_expire = False
            total_pnl = sell_pnl + buy_pnl
            total_cost = sell_close_cost + buy_close_cost
            
        # 创建平仓记录
        positions_info = [
            (sell_position, sell_close_price, sell_is_expire),
            (buy_position, buy_close_price, buy_is_expire)
        ]
        
        for pos, price, is_expire in positions_info:
            record, pnl, cost = self._create_close_record(
                current_date=current_date,
                position=pos,
                close_price=price,
                etf_price=current_etf_price,
                is_expire=is_expire
            )
            records.append(record)
        
        # 清除指定的持仓
        if sell_position:
            self.positions.pop(sell_position.contract_code, None)
        if buy_position:
            self.positions.pop(buy_position.contract_code, None)
        
        return records, total_pnl, total_cost

    def _handle_close_by_price(self,
                              current_date: datetime,
                              market_data: Dict[str, pd.DataFrame],
                              sell_position: OptionPosition,
                              buy_position: OptionPosition,
                              price_conditions: PriceConditions,
                              option_type: OptionType) -> Optional[TradeResult]:
        """基于价格条件处理平仓的通用方法"""
        if not sell_position or not buy_position:
            return None
        
        if not price_conditions.validate():
            self.logger.error("无效的价格条件")
            return None
        
        option_data = market_data['option']
        etf_data = market_data['etf']
        current_etf_price = self._get_current_etf_price(current_date, etf_data)
        if current_etf_price is None:
            return None
        
        # 根据期权类型和价格判断平仓方式
        close_type = self._determine_spread_close_type(
            option_type=option_type,
            current_etf_price=current_etf_price,
            price_conditions=price_conditions
        )
        
        # 处理平仓
        records, total_pnl, total_cost = self._handle_spread_close(
            current_date=current_date,
            sell_position=sell_position,
            buy_position=buy_position,
            current_etf_price=current_etf_price,
            option_data=option_data,
            close_type=close_type
        )
        
        if records is None:
            return None
        

        # 返回平仓结果
        return TradeResult(
            records=records,
            etf_price=current_etf_price,
            total_pnl=total_pnl,
            total_cost=total_cost
        ) 

    def _handle_single_close_by_price(self,
                                    current_date: datetime,
                                    market_data: Dict[str, pd.DataFrame],
                                    sell_position: OptionPosition,
                                    price_conditions: PriceConditions,
                                    option_type: OptionType) -> Optional[TradeResult]:
        """基于价格条件处理单腿策略平仓的通用方法"""
        if not sell_position:
            return None
        
        if not price_conditions.validate():
            self.logger.error("无效的价格条件")
            return None
        
        option_data = market_data['option']
        etf_data = market_data['etf']
        current_etf_price = self._get_current_etf_price(current_date, etf_data)
        if current_etf_price is None:
            return None
        
        # 根据期权类型和价格判断平仓方式
        if option_type == OptionType.PUT:
            is_expire = current_etf_price > price_conditions.expire_above
        else:  # CALL
            is_expire = current_etf_price <= price_conditions.expire_below

        close_price = 0
        if is_expire:
            close_type, pnl, close_price, close_cost = self._handle_option_expiry(sell_position)
        else:
            close_type, pnl, close_price, close_cost, close_value = self._handle_option_close(sell_position,current_date,option_data)

        # 创建平仓记录
        record, pnl, cost = self._create_close_record(
            current_date=current_date,
            position=sell_position,
            close_price= close_price,
            etf_price=current_etf_price,
            is_expire=is_expire
        )
        
        if record is None:
            return None
        
        # 清除指定的持仓
        if sell_position:
            self.positions.pop(sell_position.contract_code, None)

        
        return TradeResult(
            records=[record],
            etf_price=current_etf_price,
            total_pnl=pnl,
            total_cost=cost
        ) 

    def _calculate_spread_position_size(self, 
                                      options: pd.DataFrame, 
                                      sell_code: str,
                                      buy_code: str) -> int:
        """计算期权价差策略的可开仓数量
        
        解方程计算逻辑：
        设最大合约数量为x，需要满足：
        总资金 >= x * buy_premium * multiplier + x * transaction_costs + x * sell_strike * multiplier
        
        其中：
        - x * buy_premium * multiplier 是买入期权的总成本
        - x * transaction_costs 是交易成本
        - x * sell_strike * multiplier 是准备接货的资金
        """
        if not sell_code or not buy_code:
            return 0
        
        # 获取卖出期权和买入期权的数据
        sell_option = options[options['交易代码'] == sell_code].iloc[0]
        buy_option = options[options['交易代码'] == buy_code].iloc[0]
        
        # 每份合约的成本因子
        buy_cost = buy_option['收盘价'] * self.config.contract_multiplier  # 买入期权成本
        transaction_cost = self.config.transaction_cost * 2  # 每组合约的交易成本
        exercise_cost = sell_option['行权价'] * self.config.contract_multiplier  # 行权资金准备
        
        # 解方程：cash >= x * (buy_cost + transaction_cost + exercise_cost)
        cost_per_contract = buy_cost + transaction_cost + exercise_cost
        max_contracts = int(self.cash / cost_per_contract)
        
        return max_contracts if max_contracts > 0 else 0

    def _calculate_single_position_size(self,
                                      options: pd.DataFrame,
                                      contract_code: str) -> int:
        """计算单腿期权策略的可开仓数量
        
        解方程计算逻辑：
        设最大合约数量为x，需要满足：
        总资金 >= x * transaction_costs + x * strike * multiplier
        
        其中：
        - x * transaction_costs 是交易成本
        - x * strike * multiplier 是行权资金准备
        """
        if not contract_code:
            return 0
        
        # 获取期权数据
        option = options[options['交易代码'] == contract_code].iloc[0]
        
        # 每份合约的成本因子
        transaction_cost = self.config.transaction_cost  # 每个合约的交易成本
        exercise_cost = option['行权价'] * self.config.contract_multiplier  # 行权资金准备
        
        # 解方程：cash >= x * (transaction_cost + exercise_cost)
        cost_per_contract = transaction_cost + exercise_cost
        max_contracts = int(self.cash / cost_per_contract)
        
        return max_contracts if max_contracts > 0 else 0 

    def _check_options_selection(self,
                               options: pd.DataFrame, 
                               expiry: datetime,
                               option_type: str) -> None:
        """检查期权选择结果的通用方法"""
        if options.empty:
            self.logger.warning(
                f"未找到符合条件的{option_type}期权:\n"
                f"到期日: {expiry.strftime('%Y-%m-%d')}\n"
                f"期权代码模式: {option_type[0]}{expiry.strftime('%y%m')}\n"
                f"当前期权数量: {len(options)}\n"
                f"Delta有效期权数量: {options['Delta'].notna().sum()}"
            ) 

    def _handle_option_close(self, position: OptionPosition, current_date: datetime, 
                            option_data: pd.DataFrame) -> Tuple[str, float, float, float, float]:
        """处理期权平仓的通用方法
        
        Returns:
            Tuple[str, float, float, float, float]: 
            (平仓类型, 盈亏, 平仓价格, 平仓成本, 平仓价值)
        """
        close_type = '买入平仓' if position.quantity < 0 else '卖出平仓'
        
        # 获取期权的当前价格
        close_price = self._get_current_option_price(position.contract_code,current_date,option_data)
        close_cost = self.calculate_transaction_cost(abs(position.quantity))
        close_value = close_price * abs(position.quantity) * self.config.contract_multiplier

        self.cash -= close_cost

        # 计算盈亏
        if position.quantity < 0:  # 卖出期权
            # 更新现金
            self.cash += position.premium  # 确认卖出期权收取的权利金
            if close_value:
                self.cash -= close_value
            pnl = -(close_value - position.premium)
        else:  # 买入期权
            pnl = close_value + position.premium
            if close_value:
                self.cash += close_value
        
        return close_type, pnl, close_price, close_cost, close_value 


    def _determine_spread_close_type(self, 
                                   option_type: OptionType,
                                   current_etf_price: float,
                                   price_conditions: PriceConditions) -> CloseType:
        """
        判断价差策略的平仓方式
        
        Args:
            option_type: 期权类型（看涨/看跌）
            current_etf_price: 当前ETF价格
            sell_strike: 卖出期权行权价
            buy_strike: 买入期权行权价（对于看涨期权，大于sell_strike；对于看跌期权，小于sell_strike）
            
        Returns:
            CloseType: 平仓方式
        """
        if option_type == OptionType.CALL:
            if current_etf_price < price_conditions.expire_below:
                return CloseType.ALL_EXPIRE
            elif price_conditions.expire_below < current_etf_price < price_conditions.partial_below:
                return CloseType.PARTIAL_EXPIRE
            else:  # current_etf_price > price_conditions.partial_below
                return CloseType.ALL_CLOSE
        else:  # PUT
            if current_etf_price > price_conditions.expire_above:
                return CloseType.ALL_EXPIRE
            elif price_conditions.partial_below < current_etf_price < price_conditions.expire_above:
                return CloseType.PARTIAL_EXPIRE
            else:  # current_etf_price < price_conditions.partial_below
                return CloseType.ALL_CLOSE

    def _select_spread_options(self,
                             current_options: pd.DataFrame,
                             expiry: datetime,
                             sell_delta: float,
                             buy_delta: float,
                             option_type: OptionType,
                             higher_buy: bool = True) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """
        选择价差策略的期权组合
        
        Args:
            current_options: 当前可用的期权数据
            expiry: 到期日
            sell_delta: 卖出期权的目标delta
            buy_delta: 买入期权的目标delta
            option_type: 期权类型（看涨/看跌）
            higher_buy: 买入期权是否需要更高行权价（看涨价差为True，看跌价差为False）
            
        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: 卖出期权和买入期权
        """
        # 选择卖出期权
        sell_options = self.find_options_by_delta(
            current_options,
            sell_delta,
            option_type,
            expiry
        )
        self._check_options_selection(sell_options, expiry, 
                                    "看涨" if option_type == OptionType.CALL else "看跌")
        
        if sell_options.empty:
            return None, None
        
        sell_option = sell_options.iloc[0]
        
        # 根据策略类型筛选行权价
        if higher_buy:
            filtered_options = current_options[current_options['行权价'] > sell_option['行权价']]
        else:
            filtered_options = current_options[current_options['行权价'] < sell_option['行权价']]
        
        # 选择买入期权
        buy_options = self.find_options_by_delta(
            filtered_options,
            buy_delta,
            option_type,
            expiry
        )
        self._check_options_selection(buy_options, expiry,
                                    "看涨" if option_type == OptionType.CALL else "看跌")
        
        if buy_options.empty:
            return None, None
        
        return sell_options.iloc[[0]], buy_options.iloc[[0]]
