from typing import Optional, List
from datetime import datetime
import pandas as pd
from models import OptionPosition
from logger import TradeLogger
from utils import calculate_margin_requirement

class OptionTrader:
    def __init__(self, portfolio_manager, target_delta: float, stop_loss_ratio: Optional[float] = None):
        """
        期权交易执行器
        
        Args:
            portfolio_manager: 投资组合管理器实例
            target_delta: 目标delta值
            stop_loss_ratio: 止损比例，None表示不止损
        """
        self.pm = portfolio_manager
        self.target_delta = target_delta
        self.stop_loss_ratio = stop_loss_ratio
        self.logger = TradeLogger()

    def sell_put(self, current_date: datetime, expiry: datetime, 
                option_data: pd.DataFrame, etf_price: float) -> bool:
        """卖出PUT期权
        
        Args:
            current_date: 当前交易日
            expiry: 到期日
            option_data: 期权数据
            etf_price: 当前ETF价格
        
        Returns:
            bool: 交易是否成功
        """
        # 获取符合条件的PUT期权
        eligible_puts = self._get_eligible_options(current_date, expiry, 'P', option_data)
        if eligible_puts.empty:
            self.logger.log_warning(f"{current_date} 没有找到合适的PUT期权")
            return False
        
        # 获取Delta值最接近目标值的期权
        selected_put = self._get_closest_option(eligible_puts, self.target_delta)
        if selected_put.empty:
            self.logger.log_warning(f"{current_date} 没有找到目标Delta的PUT期权")
            return False
            
        # 执行交易
        return self._execute_put_trade(current_date, expiry, selected_put, etf_price)

    def handle_option_expiry(self, current_date: datetime, etf_data: pd.DataFrame, 
                           option_data: pd.DataFrame) -> None:
        """处理期权到期或平仓"""
        if not self.pm.put_position:
            return
            
        # 获取当前ETF价格
        etf_price = etf_data.at[current_date, '收盘价'] if current_date in etf_data.index else None
        if etf_price is None:
            self.logger.log_error(f"{current_date} 无法获取ETF价格")
            return
            
        # 获取当前期权价格
        current_options = option_data[
            (option_data['日期'] == current_date) & 
            (option_data['交易代码'] == self.pm.put_position.trade_code)
        ]
        if current_options.empty:
            self.logger.log_error(f"{current_date} 无法获取期权价格")
            return
            
        current_option_price = current_options['收盘价'].iloc[0]
        
        # 如果是到期日
        if self.pm.put_position.expiry <= current_date:
            self.pm.handle_put_expiry(current_date, etf_price)
        else:
            # 非到期日，检查亏损情况
            unrealized_loss = (current_option_price - self.pm.put_position.premium) * \
                            self.pm.contract_multiplier * self.pm.put_position.num_contracts
            loss_ratio = abs(unrealized_loss) / (self.pm.put_position.premium * \
                          self.pm.contract_multiplier * self.pm.put_position.num_contracts)
            
            # 记录警告日志
            if loss_ratio > 0.5:  # 始终在亏损超过50%时记录警告
                self.logger.log_warning(
                    f"{current_date} 浮动亏损率达到 {loss_ratio:.2%}\n"
                    f"浮动亏损: {unrealized_loss:.2f}"
                )
                
                # 只有在设置了止损比例且达到止损条件时才平仓
                if self.stop_loss_ratio is not None and loss_ratio > self.stop_loss_ratio:
                    self.logger.log_warning(f"触发止损线 {self.stop_loss_ratio:.2%}，执行平仓")
                    self.pm.close_put_position(current_date, current_option_price, etf_price)

    def _execute_put_trade(self, current_date: datetime, expiry: datetime, 
                          option_data: pd.DataFrame, etf_price: float) -> bool:
        """执行PUT期权交易"""
        strike_price = option_data['行权价'].iloc[0]
        delta = option_data['Delta'].iloc[0]
        premium = option_data['收盘价'].iloc[0]
        
        # 计算每张合约需要的保证金
        margin_per_contract = calculate_margin_requirement(
            strike_price=strike_price,
            etf_price=etf_price,
            contract_multiplier=self.pm.contract_multiplier
        )
        
        # 计算可以卖出的最大合约数量
        max_contracts = 0
        while True:
            total_cost = (max_contracts + 1) * self.pm.transaction_cost_per_contract
            total_margin = (max_contracts + 1) * margin_per_contract
            
            if self.pm.cash - total_cost >= total_margin:
                max_contracts += 1
            else:
                break

        if max_contracts <= 0:
            self.logger.log_warning(
                f"{current_date} 资金不足，无法开仓\n"
                f"当前现金: {self.pm.cash:.2f}\n"
                f"所需保证金: {margin_per_contract:.2f}/张"
            )
            return False

        # 创建期权持仓对象
        self.pm.put_position = OptionPosition(
            expiry=expiry,
            strike=strike_price,
            delta=delta,
            premium=premium,
            num_contracts=max_contracts,
            trade_code=option_data['交易代码'].iloc[0],
            initial_cash=self.pm.cash,
            margin=margin_per_contract * max_contracts,
            open_date=current_date
        )
        
        # 扣除交易成本
        total_cost = self.pm.transaction_cost_per_contract * max_contracts
        self.pm.cash -= total_cost
        
        # 收取权利金
        premium_income = premium * max_contracts * self.pm.contract_multiplier
        self.pm.cash += premium_income
        
        # 记录开仓交易
        self.pm.trades[current_date] = {
            '交易类型': '卖出PUT',
            '期权价格': premium,
            'ETF价格': etf_price,
            '行权价': strike_price,
            '合约数量': max_contracts,
            '权利金收入': premium_income,
            '交易成本': total_cost,
            'Delta': delta,
            '实现盈亏': 0,  # 开仓时盈亏为0
            '剩余现金': self.pm.cash,
            '保证金': margin_per_contract * max_contracts
        }
        
        # 更新统计数据
        self.pm.statistics['put_sold'] += 1
        self.pm.statistics['total_put_premium'] += premium_income
        self.pm.statistics['total_transaction_cost'] += total_cost
        self.pm.statistics['min_cash_position'] = min(
            self.pm.statistics['min_cash_position'], 
            self.pm.cash
        )
        
        # 记录交易点
        current_return = (self.pm.cash - self.pm.initial_cash) / self.pm.initial_cash * 100
        self.pm.put_trades.append((current_date, current_return))
        
        self.logger.log_trade(current_date, "卖出PUT", {
            "行权价": strike_price,
            "期权价格": premium,
            "合约数量": max_contracts,
            "权利金收入": premium_income,
            "交易成本": total_cost,
            "保证金": margin_per_contract * max_contracts,
            "剩余现金": self.pm.cash
        })
        
        return True

    def _get_eligible_options(self, current_date: datetime, expiry: datetime, 
                            option_type: str, option_data: pd.DataFrame) -> pd.DataFrame:
        """获取符合条件的期权"""
        # 先判断日期
        date_filtered = option_data[option_data['日期'] == current_date]
        
        # 从交易代码中判断期权类型和月份
        year_str = str(expiry.year)[-2:]  # 获取年份的后两位
        month_str = str(expiry.month).zfill(2)  # 补零成两位数
        
        # 构建交易代码的匹配模式
        code_pattern = f'{option_type}{year_str}{month_str}'
        
        return date_filtered[date_filtered['交易代码'].str.contains(code_pattern)]

    def _get_closest_option(self, options: pd.DataFrame, target_delta: float) -> pd.DataFrame:
        """获取Delta值最接近目标值的期权"""
        # 对于PUT期权，寻找最接近-target_delta的期权
        closest_idx = (options['Delta'] + target_delta).abs().idxmin()
        return options.loc[[closest_idx]] 