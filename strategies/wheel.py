from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import pandas as pd
from .base import OptionStrategy
from .option_selector import DeltaOptionSelector
from .types import OptionType, OptionPosition, TradeResult, PortfolioValue, PriceConditions
import traceback


class WheelStrategy(OptionStrategy):
    """轮转型现金担保看跌期权+备兑看涨期权策略（Wheel Strategy）
    
    策略构成：
    1. 第一阶段：卖出现金担保看跌期权(Cash Secured Put)
       - 选择delta=0.5的看跌期权
       - 到期作废则继续开仓新的看跌期权
       - 到期被行权则进入第二阶段
       
    2. 第二阶段：卖出备兑看涨期权(Covered Call)
       - 选择delta=0.5的看涨期权
       - 到期作废则继续开仓新的看涨期权
       - 到期被行权则回到第一阶段

    策略特点：
    1. 不使用杠杆，完全现金担保
    2. PUT期权阶段需要足够现金支付行权
    3. CALL期权阶段需要持有足够的标的资产
    """
    
    def __init__(self, context, option_data, etf_data):
        super().__init__(context, option_data, etf_data, DeltaOptionSelector())
        self.has_stock = False  # 是否持有标的资产
        self.stock_position = 0  # 持有的标的数量
        self.stock_cost = 0     # 标的持仓成本
    
    def _select_options(self, current_options: pd.DataFrame, current_price: float, expiry: datetime) -> Tuple[Optional[pd.DataFrame], None]:
        """选择合适的期权合约"""
        # 根据当前阶段选择期权类型
        option_type = OptionType.CALL if self.has_stock else OptionType.PUT
        
        # 选择delta=0.5的期权
        selected_options = self.find_best_options(
            current_options,
            current_price,
            0.5 if self.has_stock else -0.5,  # 应该配置为0.5
            option_type,
            expiry
        )
        
        self._check_options_selection(selected_options, expiry, 
                                    "看涨" if option_type == OptionType.CALL else "看跌")
        
        if selected_options.empty:
            return None, None
            
        return selected_options.iloc[[0]], None
    
    def _calculate_position_size(self, current_options: pd.DataFrame, 
                               contract_codes: List[str]) -> int:
        """计算可开仓数量
        
        轮动策略的特点：
        1. PUT阶段：复用基类的现金担保计算逻辑
        2. CALL阶段：根据持有的ETF数量计算可开仓数量
        
        Args:
            current_options: 当日期权数据
            contract_codes: 期权合约代码列表
            
        Returns:
            int: 可开仓数量
        """
        if len(contract_codes) != 1:
            return 0
        
        if self.has_stock:
            # CALL阶段：根据持有的ETF数量计算
            quantity = self.stock_position // self.context.contract_multiplier
            self.logger.debug(
                f"CALL阶段计算开仓数量:\n"
                f"持有ETF数量: {self.stock_position}\n"
                f"合约乘数: {self.context.contract_multiplier}\n"
                f"可开仓数量: {quantity}"
            )
            return quantity
        else:
            # PUT阶段：复用基类的现金担保计算逻辑
            return self._calculate_single_position_size(current_options, contract_codes[0])
    
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
            self.logger.debug(
                f"可用资金不足，无法开仓\n"
                f"当前现金: {self.cash}\n"
                f"所需保证金: {sell_option.iloc[0]['行权价'] * self.context.contract_multiplier}"
            )
            return None
        
        # 创建卖出期权持仓
        sell_position = self._create_position(
            contract_code=sell_option.iloc[0]['交易代码'],
            strike=sell_option.iloc[0]['行权价'],
            option_type=OptionType.CALL if self.has_stock else OptionType.PUT,
            quantity=-quantity,  # 负数表示卖出
            current_date=current_date,
            options=sell_option,
            expiry=expiry
        )
        
        # 记录持仓
        self.positions[sell_position.contract_code] = sell_position
        
        # 创建开仓记录
        record = self._create_open_record(
            current_date=current_date,
            position=sell_position,
            etf_price=current_etf_price
        )
        
        return TradeResult(
            records=[record],
            etf_price=current_etf_price,
            total_pnl=0,
            total_cost=record.cost,
        )

    def close_position(self, current_date: datetime, 
                      market_data: Dict[str, pd.DataFrame]) -> Optional[TradeResult]:
        """平仓逻辑
        
        轮动策略的特点：
        1. 不管期权是否作废，都按作废处理
        2. PUT被行权时买入标的，进入CALL阶段
        3. CALL被行权时卖出标的，回到PUT阶段

        Returns:
            Optional[TradeResult]: 平仓结果，如果平仓失败则返回None
        """
        try:

            position = next(iter(self.positions.values()))
            
            # 获取当前ETF价格
            current_etf_price = self._get_current_etf_price(current_date, market_data['etf'])
            if current_etf_price is None:
                return None
            
            close_type, close_record = self._handle_option_expiry(current_date, current_etf_price, position)
            

            # 标的资产交易产生的盈亏
            stock_pnl, commission, is_exercise = self._handle_exercise_transaction(position, current_etf_price)
            close_record.action = "到期行权" if is_exercise else "到期作废"
            close_record.pnl = close_record.pnl + stock_pnl 
            close_record.cost += commission
            # 移除持仓
            self.positions.pop(position.contract_code, None)
            
            # 返回平仓结果
            return TradeResult(
                records=[close_record],
                etf_price=current_etf_price,
                total_pnl=close_record.pnl,
                total_cost=close_record.cost
            )
            
        except Exception as e:
            self.logger.error(f"轮动策略平仓时发生错误: {str(e)}")
            self.logger.error(f"错误堆栈:\n{traceback.format_exc()}")
            return None 

    def _handle_exercise_transaction(self, position: OptionPosition, current_etf_price: float) -> Tuple[float, float, bool]:
        """处理期权行权时的标的资产交易
        
        Args:
            position: 期权持仓
            current_etf_price: 当前ETF价格
            
        Returns:
            Tuple[float, float]: (标的资产交易产生的盈亏, 总手续费)
        """
        pnl = 0.0
        total_commission = 0.0
        quantity = abs(position.quantity)
        total_quantity = quantity * self.context.contract_multiplier
        

        is_exercise = False
        
        # 处理行权情况
        if current_etf_price <= position.strike and position.option_type == OptionType.PUT:
            # PUT被行权，买入标的
            # 计算买入成本和手续费
            trade_amount = position.strike * total_quantity
            etf_commission = trade_amount * self.context.etf_commission_rate
            total_commission += etf_commission

            # 盈亏 = (行权价 - 当前价格) * 数量 + 总手续费
            pnl = (position.strike - current_etf_price) * total_quantity * -1 - etf_commission
            
            self.has_stock = True
            self.stock_position = total_quantity
            self.stock_cost = position.strike
            # 减少现金（包含所有费用）
            self.cash += pnl

            is_exercise = True
            
            self.logger.debug(
                f"PUT期权被行权，买入标的:\n"
                f"数量: {self.stock_position}\n"
                f"成本: {self.stock_cost}\n"
                f"当前价格: {current_etf_price}\n"
                f"交易金额: {trade_amount:.2f}\n"
                f"ETF手续费: {etf_commission:.2f}\n"
                f"总手续费: {total_commission:.2f}\n"
                f"盈亏: {pnl:.2f}\n"
                f"剩余现金: {self.cash}"
            )
            
        elif current_etf_price >= position.strike and position.option_type == OptionType.CALL:
            # CALL被行权，卖出标的
            # 计算卖出收入和手续费
            trade_amount = position.strike * total_quantity
            etf_commission = trade_amount * self.context.etf_commission_rate
            total_commission += etf_commission

            # 盈亏 = (当前价格 - 行权价) * 数量 - 总手续费
            pnl = (current_etf_price - position.strike) * total_quantity * -1 - etf_commission
            
            # 更新现金和持仓状态（扣除所有费用）
            self.cash += pnl
            self.has_stock = False
            self.stock_position = 0
            self.stock_cost = 0

            is_exercise = True
            
            self.logger.debug(
                f"CALL期权被行权，卖出标的:\n"
                f"行权价: {position.strike}\n"
                f"当前价格: {current_etf_price}\n"
                f"交易金额: {trade_amount:.2f}\n"
                f"ETF手续费: {etf_commission:.2f}\n"
                f"总手续费: {total_commission:.2f}\n"
                f"盈亏: {pnl:.2f}\n"
                f"剩余现金: {self.cash}"
            )
            
        else:
            self.logger.debug(
                f"期权到期作废:\n"
                f"类型: {'看涨' if position.option_type == OptionType.CALL else '看跌'}\n"
                f"行权价: {position.strike}\n"
                f"当前价格: {current_etf_price}"
            )
        
        return pnl, total_commission, is_exercise
