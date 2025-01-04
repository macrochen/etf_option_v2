from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import pandas as pd
from models import OptionPosition, TradeRecord, DailyPortfolio
from logger import TradeLogger
from utils import calculate_margin_requirement

class PortfolioManager:
    def __init__(self, initial_cash: float, contract_multiplier: int = 10000,
                 transaction_cost_per_contract: float = 3.6, margin_ratio: float = 1.0):
        """
        投资组合管理器
        
        Args:
            initial_cash: 初始资金
            contract_multiplier: 合约乘数
            transaction_cost_per_contract: 每张合约交易成本
            margin_ratio: 保证金比例
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.contract_multiplier = contract_multiplier
        self.transaction_cost_per_contract = transaction_cost_per_contract
        self.margin_ratio = margin_ratio
        
        # 持仓和交易记录
        self.put_position: Optional[OptionPosition] = None
        self.portfolio_values: Dict[datetime, DailyPortfolio] = {}
        # 修改交易记录的存储结构，改为以日期为key，值为交易列表
        self.trades: Dict[datetime, List[Dict]] = {}
        self.put_trades: List[tuple] = []  # 用于绘图
        
        # 统计信息
        self.statistics = {
            'put_sold': 0,            # put卖出次数
            'put_expired': 0,         # put到期作废次数
            'put_closed': 0,          # put平仓次数
            'total_put_premium': 0,   # put权利金收入
            'total_close_cost': 0,    # put平仓成本
            'total_transaction_cost': 0,  # 总交易成本
            'min_cash_position': float('inf'),
            'max_loss_trade': 0,      # 单次最大亏损
            'total_realized_pnl': 0   # 总实现盈亏
        }
        
        self.logger = TradeLogger()

    def calculate_portfolio_value(self, current_date: datetime, etf_price: float, 
                                option_data: pd.DataFrame) -> Tuple[float, float]:
        """计算当日投资组合价值"""
        # 计算期权持仓的市值和未实现盈亏
        unrealized_pnl = self._calculate_option_value(current_date, option_data)
        
        # 计算总市值（现金 + 未实现盈亏）
        total_value = self.cash + unrealized_pnl
        
        # 计算日收益率（不包括未锁定的权利金收入）
        if self.portfolio_values:
            prev_value = list(self.portfolio_values.values())[-1].total_value
            daily_return = (total_value - prev_value) / prev_value * 100
        else:
            daily_return = 0.0
        
        # 记录当日投资组合状态
        self.portfolio_values[current_date] = DailyPortfolio(
            date=current_date,
            cash=self.cash,
            option_value=unrealized_pnl,
            total_value=total_value,
            daily_return=daily_return,
            unrealized_pnl=unrealized_pnl,
            margin_occupied=self.put_position.margin if self.put_position else 0,
            initial_value=self.initial_cash
        )
        
        return total_value, unrealized_pnl

    def _calculate_option_value(self, current_date: datetime, 
                              option_data: pd.DataFrame) -> float:
        """计算期权持仓的浮动盈亏"""
        if not self.put_position:
            return 0.0
            
        current_options = option_data[
            (option_data['日期'] == current_date) & 
            (option_data['交易代码'] == self.put_position.trade_code)
        ]
        
        if current_options.empty:
            self.logger.log_warning(f"无法获取期权 {self.put_position.trade_code} 在 {current_date} 的价格")
            return 0.0
            
        current_option_price = current_options['收盘价'].iloc[0]
        
        # 浮动盈亏 = (收到的权利金 - 当前期权价格) * 合约数量 * 合约乘数
        # 注意：这里的权利金收入实际上是一项负债，直到期权到期或平仓时才真正确认为收益
        floating_pnl = (self.put_position.premium - current_option_price) * \
                      self.put_position.num_contracts * self.contract_multiplier
                      
        return floating_pnl

    def close_put_position(self, current_date: datetime, close_price: float, 
                          etf_price: float) -> bool:
        """平仓PUT期权"""
        if not self.put_position:
            self.logger.log_warning(f"{current_date} 尝试平仓时发现没有持仓")
            return False
            
        # 计算平仓成本
        close_cost = close_price * self.contract_multiplier * self.put_position.num_contracts
        transaction_cost = self.transaction_cost_per_contract * self.put_position.num_contracts
        total_cost = close_cost + transaction_cost
        
        # 检查是否有足够的现金平仓
        if self.cash < total_cost:
            self.logger.log_error(
                f"{current_date} 现金不足，无法平仓\n"
                f"当前现金: {self.cash:.2f}\n"
                f"所需现金: {total_cost:.2f}\n"
                f"资金缺口: {total_cost - self.cash:.2f}"
            )
            return False
            
        # 执行平仓
        self.cash -= total_cost
        
        # 计算平仓损益
        original_premium = self.put_position.premium * self.contract_multiplier * \
                         self.put_position.num_contracts
        realized_pnl = original_premium - close_cost - transaction_cost
        
        # 更新统计信息
        self.statistics['put_closed'] += 1
        self.statistics['total_close_cost'] += close_cost
        self.statistics['total_transaction_cost'] += transaction_cost
        self.statistics['total_realized_pnl'] += realized_pnl
        self.statistics['max_loss_trade'] = min(
            self.statistics['max_loss_trade'], 
            realized_pnl
        )
        self.statistics['min_cash_position'] = min(
            self.statistics['min_cash_position'], 
            self.cash
        )
        
        # 记录交易信息
        trade_record = {
            '交易类型': 'PUT平仓',
            '期权价格': close_price,
            'ETF价格': etf_price,
            '行权价': self.put_position.strike,
            '合约数量': self.put_position.num_contracts,
            '权利金收入': -close_cost,  # 平仓时为支出
            '交易成本': transaction_cost,
            '实现盈亏': realized_pnl,
            '剩余现金': self.cash,
            'Delta': self.put_position.delta,
            '保证金': 0  # 平仓后保证金释放
        }
        
        # 将交易记录添加到当日交易列表中
        if current_date not in self.trades:
            self.trades[current_date] = []
        self.trades[current_date].append(trade_record)
        
        # 记录交易点（用于绘图）
        current_return = (self.cash - self.initial_cash) / self.initial_cash * 100
        self.put_trades.append((current_date, current_return))
        
        # 清除持仓
        self.put_position = None
        
        return True

    def handle_put_expiry(self, current_date: datetime, current_option_price, current_option_delta, etf_price: float) -> None:
        """处理PUT期权到期"""
        if not self.put_position or self.put_position.expiry != current_date:
            return
            
        # 计算权利金收入
        premium_income = self.put_position.premium * self.contract_multiplier * \
                        self.put_position.num_contracts
        
        # 计算实现盈亏
        realized_pnl = 0
        put_action = ""
        transaction_cost = 0
        if etf_price < self.put_position.strike:
            # PUT被行权，需要按行权价买入ETF
            exercise_cost = (self.put_position.strike - etf_price) * \
                           self.contract_multiplier * self.put_position.num_contracts

            transaction_cost = self.transaction_cost_per_contract * self.put_position.num_contracts

            realized_pnl = premium_income - exercise_cost - transaction_cost

            
            self.logger.log_warning(
                f"{current_date} PUT期权被行权\n"
                f"当前ETF价格: {etf_price:.4f}\n"
                f"行权价: {self.put_position.strike:.4f}\n"
                f"行权成本: {exercise_cost:.2f}\n"
                f"权利金收入: {premium_income:.2f}\n"
                f"实现盈亏: {realized_pnl:.2f}"
            )
            
            # 更新现金
            self.cash -= exercise_cost
            put_action = "行权"
        else:
            # 期权作废，盈利为权利金收入
            realized_pnl = premium_income
            
            self.logger.log_trade(current_date, "PUT期权到期作废", {
                "ETF价格": f"{etf_price:.4f}",
                "行权价": f"{self.put_position.strike:.4f}",
                "权利金收入": f"{premium_income:.2f}"
            })
            put_action = "作废"
        
        # 更新统计信息
        if etf_price < self.put_position.strike:
            self.statistics['put_exercised'] = self.statistics.get('put_exercised', 0) + 1
        else:
            self.statistics['put_expired'] += 1
        
        self.statistics['total_realized_pnl'] += realized_pnl
        self.statistics['min_cash_position'] = min(
            self.statistics['min_cash_position'], 
            self.cash
        )
        
        # 记录交易信息
        trade_record = {
            '交易类型': 'PUT' + put_action,
            '期权价格': current_option_price,
            'ETF价格': etf_price,
            '行权价': self.put_position.strike,
            '合约数量': self.put_position.num_contracts,
            '权利金收入': 0,  # 到期时不再有权利金收入
            '交易成本': transaction_cost,
            'Delta': current_option_delta,
            '实现盈亏': realized_pnl,
            '剩余现金': self.cash,
            '保证金': 0  # 到期后保证金释放
        }
        
        # 将交易记录添加到当日交易列表中
        if current_date not in self.trades:
            self.trades[current_date] = []
        self.trades[current_date].append(trade_record)
        
        # 记录交易点（用于绘图）
        current_return = (self.cash - self.initial_cash) / self.initial_cash * 100
        self.put_trades.append((current_date, current_return))
        
        # 清除持仓
        self.put_position = None 