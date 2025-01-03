import matplotlib
import pandas as pd
import numpy as np
from datetime import datetime
from calendar import monthcalendar
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm  # 导入字体管理器
import os

class OptionPosition:
    def __init__(self, expiry, strike, premium, num_contracts, trade_code, initial_cash):
        self.expiry = expiry
        self.strike = strike
        self.premium = premium
        self.num_contracts = num_contracts
        self.trade_code = trade_code
        self.initial_cash = initial_cash

class PortfolioManager:
    def __init__(self, initial_cash, contract_multiplier=10000, transaction_cost_per_contract=3.6):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.etf_held = 0
        self.contract_multiplier = contract_multiplier
        self.transaction_cost_per_contract = transaction_cost_per_contract
        self.put_position = None
        self.call_position = None
        # 添加合成持仓相关的属性
        self.synthetic_position = None  # 用于跟踪合成持仓
        self.synthetic_put = None      # 合成持仓的put期权
        self.synthetic_call = None     # 合成持仓的call期权
        self.portfolio_values = {}
        self.put_trades = []
        self.call_trades = []
        self.trades = {}
        self.statistics = {
            'put_sold': 0,
            'put_exercised': 0,
            'put_expired': 0,
            'call_sold': 0,
            'call_exercised': 0,
            'call_expired': 0,
            'total_put_premium': 0,
            'total_call_premium': 0,
            'total_transaction_cost': 0,
            'max_etf_held': 0,
            'min_cash_position': float('inf'),
            'put_exercise_cost': 0,
            'call_exercise_income': 0,
            'etf_buy_cost': 0,
            'etf_sell_income': 0,
            'total_etf_pnl': 0,
            # 添加合成持仓相关的统计
            'synthetic_positions_opened': 0,
            'synthetic_positions_closed': 0,
            'synthetic_total_cost': 0,
            'synthetic_total_pnl': 0
        }

    def calculate_portfolio_value(self, current_date, etf_price, option_data):
        """计算当日投资组合价值"""
        # 计算ETF市值
        etf_value = self.etf_held * etf_price if etf_price is not None else 0
        
        # 计算期权持仓的市值
        unrealized_option_value = self._calculate_option_value(current_date, option_data)
        
        # 计算合成持仓的市值
        synthetic_value = self._calculate_synthetic_value(current_date, option_data) if self.synthetic_position else 0
        
        # 计算总市值
        portfolio_value = self.cash + etf_value + unrealized_option_value + synthetic_value
        
        # 计算日收益率
        if len(self.portfolio_values) > 0:
            prev_value = list(self.portfolio_values.values())[-1]['portfolio_value']
            daily_return = (portfolio_value - prev_value) / prev_value * 100
        else:
            daily_return = 0.0
        
        # 记录每日数据
        self.portfolio_values[current_date] = {
            'cash': self.cash,
            'etf_value': etf_value,
            'option_value': unrealized_option_value,
            'synthetic_value': synthetic_value,
            'portfolio_value': portfolio_value,
            'daily_return': daily_return,
            'cumulative_return': (portfolio_value - self.initial_cash) / self.initial_cash * 100
        }
        
        return portfolio_value, etf_value, unrealized_option_value + synthetic_value

    def _calculate_option_value(self, current_date, option_data):
        """计算期权持仓的浮动盈亏"""
        unrealized_value = 0
        if self.put_position:
            unrealized_value += self._get_position_value(current_date, self.put_position, option_data)
        if self.call_position:
            unrealized_value += self._get_position_value(current_date, self.call_position, option_data)
        return unrealized_value

    def _get_position_value(self, current_date, position, option_data):
        """获取单个期权持仓的浮动盈亏"""
        current_options = option_data[
            (option_data['日期'] == current_date) & 
            (option_data['交易代码'] == position.trade_code)
        ]
        current_option_price = current_options['收盘价'].iloc[0] if not current_options.empty else 0
        
        # 浮动盈亏 = (收到的权利金 - 当前期权价格) * 合约数量 * 合约乘数
        # 如果当前期权价格上涨，则卖方亏损；如果下跌，则卖方盈利
        floating_pnl = (position.premium - current_option_price) * position.num_contracts * self.contract_multiplier
        return floating_pnl

    def handle_option_expiry(self, current_date, etf_data):
        """处理期权到期"""
        # 处理PUT期权到期
        if self.put_position and self.put_position.expiry <= current_date:
            self._handle_put_expiry(current_date, etf_data)
            
        # 处理CALL期权到期
        if self.call_position and self.call_position.expiry <= current_date:
            self._handle_call_expiry(current_date, etf_data)

    def _handle_put_expiry(self, current_date, etf_data):
        """处理PUT期权到期"""
        expiry_date = self.put_position.expiry
        expiry_etf_price = etf_data.at[expiry_date, '收盘价'] if expiry_date in etf_data.index else None

        if expiry_etf_price is None:
            print(f"Warning: No ETF price found for expiry date {expiry_date}")
            return

        # 在到期时将权利金计入收入
        premium_income = self.put_position.premium * self.contract_multiplier * self.put_position.num_contracts
        self.cash += premium_income

        # 记录到期信息
        expiry_details = {
            "ETF价格": f"{expiry_etf_price:.4f}",
            "行权价格": f"{self.put_position.strike:.4f}",
            "合约数量": f"{self.put_position.num_contracts}张",
            "权利金收入": f"{premium_income:.2f}"
        }

        exercise = "变废纸"
        if expiry_etf_price < self.put_position.strike:
            # PUT被行权
            contracts = self.put_position.num_contracts
            exercise_cost = self.put_position.strike * self.contract_multiplier * contracts
            self.cash -= exercise_cost
            self.etf_held += self.contract_multiplier * contracts
            expiry_details["行权成本"] = f"{exercise_cost:.2f}"
            exercise = "被行权"
            self.statistics['put_exercised'] += 1
            self.statistics['put_exercise_cost'] += exercise_cost
            self.statistics['etf_buy_cost'] += exercise_cost
        else:
            self.statistics['put_expired'] += 1
        
        self.statistics['max_etf_held'] = max(self.statistics['max_etf_held'], self.etf_held)
            
        current_position = self.cash + (self.etf_held * expiry_etf_price)
        expiry_details.update({
            "当前持仓ETF数量": str(self.etf_held),
            "当前现金": f"{self.cash:.2f}",
            "当前持仓头寸": f"{current_position:.2f}",
            "总收益率": f"{((current_position - self.initial_cash) / self.initial_cash * 100):.2f}%"
        })
        
        self.logger.log_option_expiry(f"{expiry_date.strftime('%m月')}PUT到期" + exercise, expiry_date, expiry_details)
        self.put_position = None

    def _handle_call_expiry(self, current_date, etf_data):
        """处理CALL期权到期"""
        expiry_date = self.call_position.expiry
        expiry_etf_price = etf_data.at[expiry_date, '收盘价'] if expiry_date in etf_data.index else None

        if expiry_etf_price is None:
            print(f"Warning: No ETF price found for expiry date {expiry_date}")
            return

        # 在到期时将权利金计入收入
        premium_income = self.call_position.premium * self.contract_multiplier * self.call_position.num_contracts
        self.cash += premium_income

        # 记录到期信息
        expiry_details = {
            "ETF价格": f"{expiry_etf_price:.4f}",
            "行权价格": f"{self.call_position.strike:.4f}",
            "合约数量": f"{self.call_position.num_contracts}张",
            "权利金收入": f"{premium_income:.2f}"
        }

        exercise = "作废"
        if expiry_etf_price > self.call_position.strike:
            # CALL被行权
            contracts = self.call_position.num_contracts
            exercise_income = self.call_position.strike * self.contract_multiplier * contracts
            self.cash += exercise_income
            self.etf_held -= self.contract_multiplier * contracts
            expiry_details["行权收入"] = f"{exercise_income:.2f}"
            exercise = "行权"
            self.statistics['call_exercised'] += 1
            self.statistics['call_exercise_income'] += exercise_income
            self.statistics['etf_sell_income'] += exercise_income
        else:
            self.statistics['call_expired'] += 1
            
        current_position = self.cash + (self.etf_held * expiry_etf_price)
        expiry_details.update({
            "当前持仓ETF数量": str(self.etf_held),
            "当前现金": f"{self.cash:.2f}",
            "当前持仓头寸": f"{current_position:.2f}",
            "总收益率": f"{((current_position - self.initial_cash) / self.initial_cash * 100):.2f}%"
        })
        
        self.logger.log_option_expiry(f"{expiry_date.strftime('%m月')}CALL期权到期" + exercise, expiry_date, expiry_details)
        self.call_position = None

    def _get_eligible_options(self, current_date, expiry, option_type, option_data):
        """获取符合条件的期权"""
        # 先判断日期
        date_filtered = option_data[option_data['日期'] == current_date]
        
        # 从交易代码中判断期权类型和月份
        # 例如：510500C2210M05750，需要判断C/P和年月
        year_str = str(expiry.year)[-2:]  # 获取年份的后两位
        month_str = str(expiry.month).zfill(2)  # 补零成两位数
        
        # 构建交易代码的匹配模式
        code_pattern = f'{option_type}{year_str}{month_str}'
        
        return date_filtered[date_filtered['交易代码'].str.contains(code_pattern)]

    def _get_closest_option(self, options, target_delta, is_call=True):
        """获取Delta值最接近目标值的期权"""
        # 创建options的副本以避免SettingWithCopyWarning
        options = options.copy()
        
        if is_call:
            # 对于CALL期权，寻找最接近target_delta的期权
            closest_idx = (options['Delta'] - target_delta).abs().idxmin()
            return options.loc[[closest_idx]]
        else:
            # 对于PUT期权，寻找最接近-target_delta的期权
            closest_idx = (options['Delta'] + target_delta).abs().idxmin()
            return options.loc[[closest_idx]]

    def _calculate_synthetic_value(self, current_date, option_data):
        """计算合成持仓的市值"""
        synthetic_value = 0
        if self.synthetic_position:
            # 计算put期权的价值
            if self.synthetic_put:
                synthetic_value += self._get_position_value(current_date, self.synthetic_put, option_data)
            # 计算call期权的价值
            if self.synthetic_call:
                synthetic_value += self._get_position_value(current_date, self.synthetic_call, option_data)
        return synthetic_value

class TradeLogger:
    @staticmethod
    def log_daily_portfolio(date, cash, etf_value, etf_price, option_value, total_value):
        print(f"\n[{date.strftime('%Y-%m-%d')}期权策略盈亏] ")
        print(f"现金: {cash:.2f}")
        print(f"ETF价格: {etf_price:.2f}")
        if etf_value > 0:
            print(f"ETF市值: {etf_value:.2f}")
        print(f"期权浮动盈亏: {option_value:.2f}")
        print(f"总市值: {total_value:.2f}")
        print(f"期权浮动收益率: {(option_value / total_value * 100):.2f}%\n")

    @staticmethod
    def log_option_expiry(option_type, date, details):
        print(f"\n[{option_type}] {date}")
        for key, value in details.items():
            print(f"{key}: {value}")

class StrategyAnalyzer:
    @staticmethod
    def calculate_metrics(portfolio_values, initial_cash, put_trades, call_trades, portfolio_total_return, portfolio_annual_return):
        """计算策略的各项指标"""
        # 创建DataFrame并提取portfolio_value值
        portfolio_df = pd.DataFrame.from_dict(portfolio_values, orient='index')
        portfolio_values_series = portfolio_df['portfolio_value']
        
        # 计算累计收益率
        portfolio_total_return_calc = (portfolio_values_series.iloc[-1] - portfolio_values_series.iloc[0]) / portfolio_values_series.iloc[0]
        portfolio_df['portfolio_cumulative_return'] = (portfolio_values_series - initial_cash) / initial_cash * 100
        
        # 计算最大回撤
        portfolio_peak = portfolio_values_series.expanding(min_periods=1).max()
        portfolio_drawdown = (portfolio_values_series - portfolio_peak) / portfolio_peak
        portfolio_max_drawdown = portfolio_drawdown.min()  # 这是一个负值
        portfolio_max_drawdown_end_date = portfolio_drawdown.idxmin()
        portfolio_max_drawdown_start_date = portfolio_peak[:portfolio_max_drawdown_end_date].idxmax()
        
        # 计算日收益率，用于计算波动率
        portfolio_daily_returns = portfolio_values_series.pct_change().dropna()
        portfolio_annual_volatility = portfolio_daily_returns.std() * np.sqrt(252)
        
        # 计算夏普比率
        risk_free_rate = 0.02  # 假设无风险利率为2%
        portfolio_sharpe_ratio = (portfolio_annual_return - risk_free_rate) / portfolio_annual_volatility if portfolio_annual_volatility != 0 else 0
        
        # 创建portfolio_metrics字典
        portfolio_metrics = {
            'portfolio_sharpe_ratio': portfolio_sharpe_ratio,
            'portfolio_annual_return': portfolio_annual_return,
            'portfolio_annual_volatility': portfolio_annual_volatility,
            'portfolio_total_return': portfolio_total_return
        }
        
        return {
            "portfolio_df": portfolio_df,
            "put_trades": put_trades,
            "call_trades": call_trades,
            "portfolio_metrics": portfolio_metrics,
            # 添加最大回撤相关信息，将最大回撤转换为正数
            "portfolio_max_drawdown": abs(portfolio_max_drawdown * 100),
            "portfolio_max_drawdown_start_date": portfolio_max_drawdown_start_date,
            "portfolio_max_drawdown_end_date": portfolio_max_drawdown_end_date
        }

    @staticmethod
    def print_strategy_statistics(statistics, portfolio_values, initial_cash, etf_buy_hold_portfolio, analysis_results):
        """打印策略统计信息"""
        # 计算期权策略的指标
        portfolio_values_series = pd.Series({date: data['portfolio_value'] 
                                          for date, data in portfolio_values.items()})
        portfolio_metrics = calculate_sharpe_ratio(portfolio_values_series, is_portfolio=True)
        
        # 计算ETF持有策略的指标
        etf_values_series = pd.Series({date: data['etf_buy_hold_value'] 
                                     for date, data in etf_buy_hold_portfolio.items()})
        etf_metrics = calculate_sharpe_ratio(etf_values_series, is_portfolio=False)
        
        # 计算ETF持有策略的最大回撤
        etf_peak = etf_values_series.expanding(min_periods=1).max()
        etf_drawdown = (etf_values_series - etf_peak) / etf_peak
        etf_max_drawdown = abs(etf_drawdown.min())  # 转换为正数
        
        print("\n=== 策略绩效对比 ===")
        print("指标              期权组合策略    ETF持有策略")
        print("-" * 45)
        print(f"年化收益率:      {portfolio_metrics['portfolio_annual_return']*100:8.2f}%    {etf_metrics['etf_annual_return']*100:8.2f}%")
        print(f"年化波动率:      {portfolio_metrics['portfolio_annual_volatility']*100:8.2f}%    {etf_metrics['etf_annual_volatility']*100:8.2f}%")
        print(f"夏普比率:        {portfolio_metrics['portfolio_sharpe_ratio']:8.2f}    {etf_metrics['etf_sharpe_ratio']:8.2f}")
        print(f"最大回撤:        {analysis_results['portfolio_max_drawdown']:8.2f}%    {etf_max_drawdown:8.2f}%")
        
        print("\n=== 期权交易统计 ===")
        print(f"PUT期权交易:")
        print(f"  总卖出次数: {statistics['put_sold']}")
        print(f"  被行权次数: {statistics['put_exercised']}")
        print(f"  到期作废次数: {statistics['put_expired']}")
        print(f"  总收取权利金: {statistics['total_put_premium']:.2f}")
        print(f"  总行权成本: {statistics['put_exercise_cost']:.2f}")
        
        print(f"\nCALL期权交易:")
        print(f"  总卖出次数: {statistics['call_sold']}")
        print(f"  被行权次数: {statistics['call_exercised']}")
        print(f"  到期作废次数: {statistics['call_expired']}")
        print(f"  总收取权利金: {statistics['total_call_premium']:.2f}")
        print(f"  总行权收入: {statistics['call_exercise_income']:.2f}")
        
        print(f"\n资金使用:")
        print(f"  最低现金持仓: {statistics['min_cash_position']:.2f}")
        print(f"  总交易成本: {statistics['total_transaction_cost']:.2f}")
        
        # 计算收益分解
        total_premium = statistics['total_put_premium'] + statistics['total_call_premium']
        final_value = portfolio_values_series.iloc[-1]
        total_return = final_value - initial_cash
        
        # 计算期权行权损益
        option_exercise_pnl = statistics['call_exercise_income'] - statistics['put_exercise_cost']
        
        # 计算ETF交易损益
        etf_trading_pnl = statistics['etf_sell_income'] - statistics['etf_buy_cost']
        
        # 计算当前ETF持仓的未实现盈亏
        current_etf_value = statistics['max_etf_held'] * etf_values_series.iloc[-1]
        unrealized_etf_pnl = current_etf_value - (statistics['etf_buy_cost'] - statistics['etf_sell_income'])
        
        print(f"\n收益分解:")
        print(f"  总收益: {total_return:.2f} ")
        print(f"  1. 期权权利金收入: {total_premium:.2f}")
        print(f"  2. 期权行权损益: {option_exercise_pnl:.2f}")
        print(f"  3. ETF交易已实现损益: {etf_trading_pnl:.2f}")
        print(f"  4. ETF持仓未实现损益: {unrealized_etf_pnl:.2f}")
        print(f"  5. 交易成本: {statistics['total_transaction_cost']:.2f} ")
        
        # 计算因期权行权导致的ETF交易总盈亏
        etf_exercise_pnl = etf_trading_pnl + unrealized_etf_pnl
        print(f"  6. 期权行权ETF交易总盈亏: {etf_exercise_pnl:.2f}")

def analyze_complex_strategy_with_equity_curve(etf_data, option_data, initial_cash=1000000, target_delta=0.5, holding_type='stock'):
    # 初始化各个组件
    portfolio_manager = PortfolioManager(initial_cash)
    option_trader = OptionTrader(portfolio_manager, target_delta)
    logger = TradeLogger()
    
    # 设置ETF数据的索引为日期
    etf_data = etf_data.set_index('日期')
    
    # 初始化ETF买入持有策略
    first_etf_price = etf_data['收盘价'].iloc[0]
    etf_shares_per_lot = 100
    etf_buy_hold_lots = initial_cash // (first_etf_price * etf_shares_per_lot)
    etf_buy_hold_shares = etf_buy_hold_lots * etf_shares_per_lot
    etf_buy_hold_cash = initial_cash - etf_buy_hold_shares * first_etf_price
    etf_buy_hold_portfolio = {}
    
    # 获取所有交易日并排序
    print("\n=== 交易日期验证 ===")
    # 获取有效的交易日期
    option_dates = pd.Index(option_data['日期'].unique())
    etf_dates = etf_data.index
    trading_days = sorted(option_dates.union(etf_dates))
    
    # 验证交易日期
    print(f"期权数据日期数量: {len(option_dates)}")
    print(f"ETF数据日期数量: {len(etf_dates)}")
    print(f"合并后的交易日期数量: {len(trading_days)}")
    
    # 检查是否有无效日期
    invalid_dates = [d for d in trading_days if pd.isna(d)]
    if invalid_dates:
        print("警告: 发现无效日期:")
        for d in invalid_dates:
            print(f"  - {d}")
        # 移除无效日期
        trading_days = [d for d in trading_days if not pd.isna(d)]
        print(f"清理后的交易日期数量: {len(trading_days)}")
    
    if not trading_days:
        print("错误: 没有有效的交易日期")
        return None
    
    # 获取起止日期
    start_date = trading_days[0]
    end_date = trading_days[-1]
    
    print(f"第一个交易日: {start_date}")
    print(f"最后一个交易日: {end_date}")
    
    if pd.isna(start_date) or pd.isna(end_date):
        print("错误: 起止日期无效")
        return None
    
    calendar_days = (end_date - start_date).days + 1
    print(f"\n回测区间: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    print(f"日历天数: {calendar_days}")
    
    # 遍历每个交易日
    for current_date in trading_days:
        etf_price = etf_data.at[current_date, '收盘价'] if current_date in etf_data.index else None
        if etf_price is None:
            continue
            
        # 处理期权到期
        if holding_type == 'stock':
            option_trader.handle_option_expiry(current_date, etf_data)
        else:
            option_trader.handle_synthetic_expiry(current_date, etf_data)
        
        # 执行交易策略
        if holding_type == 'stock':
            # 原有的正股持仓策略
            if not portfolio_manager.etf_held and not portfolio_manager.put_position:
                # 判断是否是第一次卖出put
                if portfolio_manager.call_position is None and len([d for d in trading_days if d < current_date]) == 0:
                    # 第一次卖出put，使用当月到期日
                    expiry = get_monthly_expiry(current_date, option_data)
                else:
                    # 之后的put都用下月到期日
                    expiry = get_next_monthly_expiry(current_date, option_data)
                    if expiry is None:  # 如果无法获取下月到期日，则跳过
                        continue
                option_trader.sell_put(current_date, expiry, option_data, etf_price)
                
            elif portfolio_manager.etf_held >= portfolio_manager.contract_multiplier and not portfolio_manager.call_position:
                expiry = get_next_monthly_expiry(current_date, option_data)
                if expiry:
                    option_trader.sell_call(current_date, expiry, option_data, etf_price)
        else:
            # 合成持仓策略
            if not portfolio_manager.synthetic_position:
                expiry = get_next_monthly_expiry(current_date, option_data)
                if expiry:
                    option_trader.execute_synthetic_position(current_date, expiry, option_data, etf_price)
            
        # 计算当日投资组合价值
        portfolio_value, etf_value, option_value = portfolio_manager.calculate_portfolio_value(
            current_date, etf_price, option_data)
        
        # 计算ETF买入持有策略的价值
        etf_buy_hold_value = etf_buy_hold_shares * etf_price + etf_buy_hold_cash
        etf_buy_hold_return = (etf_buy_hold_value - initial_cash) / initial_cash * 100
        etf_buy_hold_portfolio[current_date] = {
            'etf_buy_hold_value': etf_buy_hold_value,
            'etf_buy_hold_return': etf_buy_hold_return
        }
    
    # 创建ETF买入持有的DataFrame
    etf_buy_hold_df = pd.DataFrame.from_dict(etf_buy_hold_portfolio, orient='index')
    
    # 计算期权策略的指标
    portfolio_values_series = pd.Series({date: data['portfolio_value'] 
                                     for date, data in portfolio_manager.portfolio_values.items()})
    print("\n=== 期权策略数据验证 ===")
    print(f"期权策略数据点数量: {len(portfolio_values_series)}")
    print(f"期权策略数据范围: {portfolio_values_series.index.min()} 到 {portfolio_values_series.index.max()}")
    print(f"期权策略起始值: {portfolio_values_series.iloc[0]:.2f}")
    print(f"期权策略结束值: {portfolio_values_series.iloc[-1]:.2f}")
    
    # 计算ETF策略的指标
    etf_values_series = pd.Series({date: data['etf_buy_hold_value'] 
                                for date, data in etf_buy_hold_portfolio.items()})
    print("\n=== ETF策略数据验证 ===")
    print(f"ETF策略数据点数量: {len(etf_values_series)}")
    print(f"ETF策略数据范围: {etf_values_series.index.min()} 到 {etf_values_series.index.max()}")
    print(f"ETF策略起始值: {etf_values_series.iloc[0]:.2f}")
    print(f"ETF策略结束值: {etf_values_series.iloc[-1]:.2f}")
    
    # 确保数据是按日期排序的
    portfolio_values_series = portfolio_values_series.sort_index()
    etf_values_series = etf_values_series.sort_index()
    
    # 计算回测的实际日历天数
    start_date = trading_days[0] if len(trading_days) > 0 else None
    end_date = trading_days[-1] if len(trading_days) > 0 else None
    
    if start_date is None or end_date is None or pd.isna(start_date) or pd.isna(end_date):
        print("警告: 无法获取有效的回测起止日期")
        print(f"trading_days长度: {len(trading_days)}")
        print(f"第一个交易日: {trading_days[0] if len(trading_days) > 0 else 'N/A'}")
        print(f"最后一个交易日: {trading_days[-1] if len(trading_days) > 0 else 'N/A'}")
        return None
    
    calendar_days = (end_date - start_date).days + 1
    print(f"\n回测区间: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    print(f"日历天数: {calendar_days}")
    
    # 验证日历天数
    if calendar_days <= 0:
        print("警告: 回测区间无效，日历天数小于等于0")
        return None
    
    # 计算期权策略的累计收益率和年化收益率
    portfolio_total_return = (portfolio_values_series.iloc[-1] - portfolio_values_series.iloc[0]) / portfolio_values_series.iloc[0]
    portfolio_annual_return = (1 + portfolio_total_return) ** (365/calendar_days) - 1
    print(f"\n期权策略累计收益率: {portfolio_total_return:.4f}")
    print(f"期权策略年化收益率: {portfolio_annual_return:.4f}")
    
    # 计算ETF策略的累计收益率和年化收益率
    etf_total_return = (etf_values_series.iloc[-1] - etf_values_series.iloc[0]) / etf_values_series.iloc[0]
    etf_annual_return = (1 + etf_total_return) ** (365/calendar_days) - 1
    print(f"\nETF策略累计收益率: {etf_total_return:.4f}")
    print(f"ETF策略年化收益率: {etf_annual_return:.4f}")
    
    # 计算ETF策略的最大回撤
    etf_peak = etf_values_series.expanding().max()
    etf_drawdown = (etf_values_series - etf_peak) / etf_peak
    etf_max_drawdown = abs(etf_drawdown.min())  # 转换为正数
    
    # 计算ETF策略的日收益率和年化波动率
    etf_daily_returns = etf_values_series.pct_change().dropna()
    etf_annual_volatility = etf_daily_returns.std() * np.sqrt(252)
    
    # 计算ETF策略的夏普比率
    risk_free_rate = 0.02  # 假设无风险利率为2%
    etf_sharpe_ratio = (etf_annual_return - risk_free_rate) / etf_annual_volatility if etf_annual_volatility != 0 else 0
    
    print(f"\nETF策略指标:")
    print(f"年化波动率: {etf_annual_volatility:.4f}")
    print(f"夏普比率: {etf_sharpe_ratio:.4f}")
    print(f"最大回撤: {etf_max_drawdown:.4f}")
    
    # 分析策略结果
    analysis_results = StrategyAnalyzer.calculate_metrics(
        portfolio_manager.portfolio_values, 
        initial_cash,
        portfolio_manager.put_trades,
        portfolio_manager.call_trades,
        portfolio_total_return,
        portfolio_annual_return  # 传入计算好的年化收益率
    )
    
    # 添加ETF买入持有的DataFrame和指标到结果中
    analysis_results['etf_buy_hold_df'] = etf_buy_hold_df
    analysis_results['etf_metrics'] = {
        'etf_annual_return': etf_annual_return,
        'etf_total_return': etf_total_return,
        'etf_annual_volatility': etf_annual_volatility,
        'etf_sharpe_ratio': etf_sharpe_ratio,
        'etf_max_drawdown': etf_max_drawdown
    }
    
    # 更新portfolio指标的命名
    analysis_results['portfolio_metrics'] = {
        'portfolio_sharpe_ratio': analysis_results['portfolio_metrics']['portfolio_sharpe_ratio'],
        'portfolio_annual_return': analysis_results['portfolio_metrics']['portfolio_annual_return'],
        'portfolio_annual_volatility': analysis_results['portfolio_metrics']['portfolio_annual_volatility'],
        'portfolio_total_return': analysis_results['portfolio_metrics']['portfolio_total_return']
    }
    
    # 添加交易记录
    analysis_results['trades'] = portfolio_manager.trades
    analysis_results['portfolio_df'] = pd.DataFrame.from_dict(portfolio_manager.portfolio_values, orient='index')
    analysis_results['symbol'] = etf_data.index.name if etf_data.index.name else 'ETF'
    
    # 打印统计信息
    StrategyAnalyzer.print_strategy_statistics(
        portfolio_manager.statistics,
        portfolio_manager.portfolio_values,
        initial_cash,
        etf_buy_hold_portfolio,
        analysis_results
    )
    
    analysis_results['statistics'] = portfolio_manager.statistics
    
    # 添加原始ETF数据到结果中
    analysis_results['etf_data'] = etf_data
    
    return analysis_results

def get_monthly_expiry(date, option_data):
    """获取当月期权到期日"""
    year = date.year
    month = date.month
    
    # 获取当月所有的星期三
    cal = monthcalendar(year, month)
    wednesdays = [day for week in cal for day in week if day != 0 and datetime(year, month, day).weekday() == 2]
    
    if len(wednesdays) < 4:
        raise ValueError(f"Month {month} in {year} does not have four Wednesdays.")
    
    # 获取第四个星期三
    fourth_wednesday = wednesdays[3]
    target_date = pd.Timestamp(datetime(year, month, fourth_wednesday)).normalize()
    
    # 获取所有期权交易日期并标准化
    trading_dates = pd.DatetimeIndex(option_data['日期'].dt.normalize().unique()).sort_values()
    
    
    # 如果目标日期是交易日，直接返回
    if target_date in trading_dates:
        print(f"找到目标到期日: {target_date}")
        return target_date
        
    # 如果不是交易日，向后查找最近的交易日（最多查找10天）
    max_search_days = 10
    for i in range(1, max_search_days + 1):
        next_date = target_date + pd.Timedelta(days=i)
        if next_date in trading_dates:
            print(f"注意: {target_date} 不是交易日，到期日顺延至 {next_date}")
            return next_date
            
    raise ValueError(f"无法找到 {target_date} 之后的有效交易日（已查找{max_search_days}天）")

def get_next_monthly_expiry(date, option_data):
    """获取下月期权到期日"""
    # 获取下个月的第一天
    if date.month == 12:
        next_month = pd.Timestamp(datetime(date.year + 1, 1, 1))
    else:
        next_month = pd.Timestamp(datetime(date.year, date.month + 1, 1))
    
    # 获取下月所有的星期三
    cal = monthcalendar(next_month.year, next_month.month)
    wednesdays = [day for week in cal for day in week if day != 0 and datetime(next_month.year, next_month.month, day).weekday() == 2]
    
    if len(wednesdays) < 4:
        raise ValueError(f"Month {next_month.month} in {next_month.year} does not have four Wednesdays.")
    
    # 获取第四个星期三
    fourth_wednesday = wednesdays[3]
    target_date = pd.Timestamp(datetime(next_month.year, next_month.month, fourth_wednesday)).normalize()
    
    # 获取所有期权交易日期并标准化
    trading_dates = pd.DatetimeIndex(option_data['日期'].dt.normalize().unique()).sort_values()
    max_date = trading_dates.max()
    
    
    # 如果目标日期超出数据范围，返回None
    if target_date > max_date:
        print(f"警告: 目标到期日 {target_date} 超出数据范围 {max_date}")
        return None
    
    # 如果目标日期是交易日，直接返回
    if target_date in trading_dates:
        print(f"找到目标到期日: {target_date}")
        return target_date
        
    # 如果不是交易日，向后查找最近的交易日（最多查找10天）
    max_search_days = 10
    for i in range(1, max_search_days + 1):
        next_date = target_date + pd.Timedelta(days=i)
        if next_date > max_date:
            print(f"警告: 查找到期日时超出数据范围")
            return None
        if next_date in trading_dates:
            print(f"注意: {target_date} 不是交易日，到期日顺延至 {next_date}")
            return next_date
            
    print(f"警告: 无法找到 {target_date} 之后的有效交易日（已查找{max_search_days}天）")
    return None

def calculate_sharpe_ratio(portfolio_values, risk_free_rate=0.02, is_portfolio=True):
    """
    计算策略的Sharpe ratio
    :param portfolio_values: 包含每日投资组合价值的Series
    :param risk_free_rate: 无风险利率，默认2%
    :param is_portfolio: 是否是期权组合策略，用于区分指标前缀
    :return: Sharpe ratio
    """
    prefix = 'portfolio_' if is_portfolio else 'etf_'
    strategy_name = '期权组合' if is_portfolio else 'ETF'
    
    try:
        print(f"\n=== {strategy_name}策略指标计算调试信息 ===")
        print(f"投资组合数据点数量: {len(portfolio_values)}")
        print(f"起始值: {portfolio_values.iloc[0]:.2f}")
        print(f"结束值: {portfolio_values.iloc[-1]:.2f}")
        
        # 计算累计收益率
        total_return = (portfolio_values.iloc[-1] - portfolio_values.iloc[0]) / portfolio_values.iloc[0]
        print(f"累计收益率: {total_return:.4f}")
        
        # 计算实际日历天数
        start_date = portfolio_values.index[0]
        end_date = portfolio_values.index[-1]
        calendar_days = (end_date - start_date).days + 1
        print(f"回测区间: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
        print(f"日历天数: {calendar_days}")
        
        # 计算年化收益率
        annual_return = (1 + total_return) ** (365/calendar_days) - 1
        print(f"年化收益率: {annual_return:.4f}")
        
        # 计算日收益率，用于计算波动率
        daily_returns = portfolio_values.pct_change().dropna()
        print(f"日收益率数据点数量: {len(daily_returns)}")
        print(f"日收益率均值: {daily_returns.mean():.6f}")
        print(f"日收益率标准差: {daily_returns.std():.6f}")
        
        # 计算年化波动率
        annual_volatility = daily_returns.std() * np.sqrt(252)
        print(f"年化波动率: {annual_volatility:.4f}")
        
        # 计算Sharpe ratio
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0
        print(f"夏普比率: {sharpe_ratio:.4f}")
        print(f"计算过程: ({annual_return:.4f} - {risk_free_rate:.4f}) / {annual_volatility:.4f}")
        
        # 检查计算结果是否为nan
        if np.isnan(annual_return) or np.isnan(annual_volatility) or np.isnan(sharpe_ratio):
            print("警告: 计算结果中存在nan值!")
            print(f"annual_return is nan: {np.isnan(annual_return)}")
            print(f"annual_volatility is nan: {np.isnan(annual_volatility)}")
            print(f"sharpe_ratio is nan: {np.isnan(sharpe_ratio)}")
        
        return {
            f'{prefix}sharpe_ratio': sharpe_ratio,
            f'{prefix}annual_return': annual_return,
            f'{prefix}annual_volatility': annual_volatility
        }
    except Exception as e:
        print(f"\n警告: {strategy_name}策略指标计算出错")
        print(f"错误信息: {str(e)}")
        print("错误堆栈:")
        import traceback
        traceback.print_exc()
        
        return {
            f'{prefix}sharpe_ratio': 0,
            f'{prefix}annual_return': 0,
            f'{prefix}annual_volatility': 0
        }

def plot_equity_curve(analysis_results, symbol):
    if not analysis_results or 'portfolio_df' not in analysis_results or 'etf_buy_hold_df' not in analysis_results:
        print("No portfolio data to plot.")
        return

    portfolio_df = analysis_results['portfolio_df']
    etf_buy_hold_df = analysis_results['etf_buy_hold_df']
    max_drawdown_start_date = analysis_results['max_drawdown_start_date']
    max_drawdown_end_date = analysis_results['max_drawdown_end_date']
    
    # 获取交易点信息
    put_trades = analysis_results['put_trades']  # 格式: [(date, return)]
    call_trades = analysis_results['call_trades']  # 格式: [(date, return)]

    try:
        prop = fm.FontProperties(fname='/System/Library/Fonts/PingFang.ttc')
    except:
        try:
            prop = fm.FontProperties(fname='C:/Windows/Fonts/simhei.ttf')
        except:
            prop = {'family': 'sans-serif', 'weight': 'normal'}

    plt.figure(figsize=(15, 8))  # 增大图形尺寸以便显示标注
    
    # 绘制基本曲线
    plt.plot(portfolio_df.index, portfolio_df['cumulative_return'], label='期权策略收益率', zorder=1)
    plt.plot(etf_buy_hold_df.index, etf_buy_hold_df['etf_buy_hold_return'], 
            label=f'持有 {symbol}ETF 收益率', linestyle='-', zorder=1)

    # 标注最大回撤区间
    plt.fill_between(
        portfolio_df.loc[max_drawdown_start_date:max_drawdown_end_date].index,
        portfolio_df.loc[max_drawdown_start_date:max_drawdown_end_date]['cumulative_return'],
        color='red', alpha=0.3, label=f'期权策略最大回撤 ({analysis_results["max_drawdown"]:.2f}%)',
        zorder=0
    )

    # 在ETF曲线上标注Put交易点
    for date, _ in put_trades:
        etf_return = etf_buy_hold_df.loc[date, 'etf_buy_hold_return']
        plt.scatter(date, etf_return, color='red', marker='o', s=100, zorder=2)

    # 在ETF曲线上标注Call交易点
    for date, _ in call_trades:
        etf_return = etf_buy_hold_df.loc[date, 'etf_buy_hold_return']
        plt.scatter(date, etf_return, color='green', marker='o', s=100, zorder=2)

    plt.xlabel('日期', fontproperties=prop)
    plt.ylabel('累计收益率 (%)', fontproperties=prop)
    plt.title(f'期权策略 vs 持有 {symbol}ETF 收益率对比', fontproperties=prop)
    plt.grid(True)

    # 添加图例
    handles, labels = plt.gca().get_legend_handles_labels()
    handles.extend([
        plt.scatter([], [], color='red', marker='o', s=100, label='卖出PUT'),
        plt.scatter([], [], color='green', marker='o', s=100, label='卖出CALL')
    ])
    plt.legend(handles=handles, prop=prop)
    
    plt.tight_layout()
    plt.show()

def log_transaction(transaction_type, date, details):
    print(f"[{date}] {transaction_type}:")
    for key, value in details.items():
        print(f"  {key}: {value}")

class BacktestConfig:
    def __init__(self, 
                 symbol: str,           # 文件夹名称，如 '510050', '510500', '510300'
                 delta: float = 0.5,           # Delta值，默认为0.5
                 initial_capital: float = 1000000,  # 初始资金
                 contract_multiplier: int = 10000,  # 合约乘数
                 transaction_cost: float = 3.6,     # 每张合约交易成本
                 risk_free_rate: float = 0.02,      # 无风险利率
                 start_date: pd.Timestamp = None,   # 回测开始日期
                 end_date: pd.Timestamp = None,     # 回测结束日期
                 holding_type: str = 'stock'):      # 持仓方式，'stock'为正股持仓，'synthetic'为合成持仓
        
        self.symbol = symbol
        self.delta = delta
        self.initial_capital = initial_capital
        self.contract_multiplier = contract_multiplier
        self.transaction_cost = transaction_cost
        self.risk_free_rate = risk_free_rate
        self.start_date = start_date
        self.end_date = end_date
        self.holding_type = holding_type
        
        # 自动获取文件列表
        self.option_file_paths = []
        self.etf_file_path = None
        self._load_files(symbol)
    
    def _load_files(self, folder_name: str):
        """根据文件夹名自动加载文件列表"""
        try:
            # 获取文件夹中的所有文件
            files = os.listdir(folder_name)
            
            # 获取期权文件（xlsx文件）
            self.option_file_paths = [
                os.path.join(folder_name, f) 
                for f in files 
                if f.endswith('.xlsx') and not f.startswith('~$')
            ]
            
            # 获取ETF文件（csv文件）
            csv_files = [f for f in files if f.endswith('.csv')]
            if csv_files:
                self.etf_file_path = os.path.join(folder_name, csv_files[0])
            
            # 验证文件是否存在
            if not self.option_file_paths:
                raise ValueError(f"在 {folder_name} 文件夹中未找到期权数据文件(.xlsx)")
            if not self.etf_file_path:
                raise ValueError(f"在 {folder_name} 文件夹中未找到ETF数据文件(.csv)")
                
            # 按文件名排序期权文件，确保按时间顺序处理
            self.option_file_paths.sort()
            
            print(f"\n=== 已加载 {folder_name} 的数据文件 ===")
            print("期权文件:")
            for f in self.option_file_paths:
                print(f"  - {os.path.basename(f)}")
            print(f"ETF文件: {os.path.basename(self.etf_file_path)}")
            print()
            
        except Exception as e:
            raise ValueError(f"加载 {folder_name} 文件夹中的数据文件时出错: {str(e)}")

class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.option_data = None
        self.etf_data = None
        
    def load_data(self):
        """加载数据"""
        print("\n=== 开始加载数据 ===")
        
        # 加载期权数据
        all_option_data = []
        for file_path in self.config.option_file_paths:
            try:
                print(f"正在加载期权数据文件: {os.path.basename(file_path)}")
                df = pd.read_excel(file_path)
                
                # 清理 '日期' 列：移除包含特定字符串的行
                df = df[~df['日期'].astype(str).str.contains('数据来源')]
                
                # 将 '日期' 列转换为 datetime 类型，并处理无效日期
                df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
                invalid_dates = df[df['日期'].isna()]
                if not invalid_dates.empty:
                    print(f"  - 发现 {len(invalid_dates)} 行无效日期数据，将被移除")
                    df = df.dropna(subset=['日期'])
                
                print(f"  - 加载了 {len(df)} 行数据")
                if not df.empty:
                    print(f"  - 日期范围: {df['日期'].min()} 到 {df['日期'].max()}")
                all_option_data.append(df)
            except FileNotFoundError:
                print(f"错误: 找不到期权数据文件: {file_path}")
                return False
            except Exception as e:
                print(f"错误: 加载期权数据文件时出错: {str(e)}")
                return False
        
        if not all_option_data:
            print("错误: 没有成功加载任何期权数据")
            return False
        
        self.option_data = pd.concat(all_option_data, ignore_index=True)
        print(f"\n合并后的期权数据总行数: {len(self.option_data)}")
        print(f"期权数据日期范围: {self.option_data['日期'].min()} 到 {self.option_data['日期'].max()}")
        
        # 加载ETF数据
        try:
            print(f"\n正在加载ETF数据文件: {os.path.basename(self.config.etf_file_path)}")
            self.etf_data = pd.read_csv(self.config.etf_file_path)
            
        
            # 转换日期列并处理无效日期
            self.etf_data['日期'] = pd.to_datetime(self.etf_data['日期'], errors='coerce')
            invalid_dates = self.etf_data[self.etf_data['日期'].isna()]
            if not invalid_dates.empty:
                print(f"  - 发现 {len(invalid_dates)} 行无效日期数据，将被移除")
                self.etf_data = self.etf_data.dropna(subset=['日期'])
            
            print(f"ETF数据总行数: {len(self.etf_data)}")
            print(f"ETF数据日期范围: {self.etf_data['日期'].min()} 到 {self.etf_data['日期'].max()}")
            
        except FileNotFoundError:
            print(f"错误: 找不到ETF数据文件: {self.config.etf_file_path}")
            return False
        except Exception as e:
            print(f"错误: 加载ETF数据文件时出错: {str(e)}")
            return False
        
        # 根据日期范围过滤数据
        if self.config.start_date:
            print(f"\n使用指定的开始日期: {self.config.start_date}")
            self.option_data = self.option_data[self.option_data['日期'] >= self.config.start_date]
            self.etf_data = self.etf_data[self.etf_data['日期'] >= self.config.start_date]
        
        if self.config.end_date:
            print(f"使用指定的结束日期: {self.config.end_date}")
            self.option_data = self.option_data[self.option_data['日期'] <= self.config.end_date]
            self.etf_data = self.etf_data[self.etf_data['日期'] <= self.config.end_date]
        
        # 确保数据不为空
        if len(self.option_data) == 0:
            print("错误: 过滤后的期权数据为空")
            return False
            
        if len(self.etf_data) == 0:
            print("错误: 过滤后的ETF数据为空")
            return False
        
        # 对数据按日期排序
        self.option_data = self.option_data.sort_values('日期')
        self.etf_data = self.etf_data.sort_values('日期')
        
        print("\n=== 数据加载完成 ===")
        print(f"过滤后的期权数据行数: {len(self.option_data)}")
        print(f"过滤后的ETF数据行数: {len(self.etf_data)}")
        print(f"期权数据日期范围: {self.option_data['日期'].min()} 到 {self.option_data['日期'].max()}")
        print(f"ETF数据日期范围: {self.etf_data['日期'].min()} 到 {self.etf_data['日期'].max()}")
            
        return True
    
    def run_backtest(self):
        """运行回测"""
        if not self.load_data():
            return None
            
        # 初始化组件
        portfolio_manager = PortfolioManager(
            initial_cash=self.config.initial_capital,
            contract_multiplier=self.config.contract_multiplier,
            transaction_cost_per_contract=self.config.transaction_cost
        )
        option_trader = OptionTrader(portfolio_manager, self.config.delta)
        
        # 运行回测
        analysis_results = analyze_complex_strategy_with_equity_curve(
            self.etf_data, 
            self.option_data, 
            self.config.initial_capital,
            self.config.delta,
            self.config.holding_type
        )
        
        # 添加symbol到结果中
        analysis_results['symbol'] = self.config.symbol
        
        return analysis_results

class OptionTrader:
    def __init__(self, portfolio_manager, target_delta):
        self.pm = portfolio_manager
        self.target_delta = target_delta
        self.logger = TradeLogger()

    def sell_put(self, current_date, expiry, option_data, etf_price):
        """卖出PUT期权"""
        # 获取符合条件的PUT期权
        eligible_puts = self._get_eligible_options(current_date, expiry, 'P', option_data)
        if eligible_puts.empty:
            return
        
        # 获取Delta值最接近目标值的期权
        selected_put = self._get_closest_option(eligible_puts, self.target_delta, is_call=False)
        if selected_put.empty:
            return
            
        # 执行交易
        self._execute_put_trade(current_date, expiry, selected_put, etf_price)

    def sell_call(self, current_date, expiry, option_data, etf_price):
        """卖出CALL期权"""
        # 获取符合条件的CALL期权
        eligible_calls = self._get_eligible_options(current_date, expiry, 'C', option_data)
        if eligible_calls.empty:
            return
        
        # 获取Delta值最接近目标值的期权
        selected_call = self._get_closest_option(eligible_calls, self.target_delta, is_call=True)
        if selected_call.empty:
            return
            
        # 执行交易
        self._execute_call_trade(current_date, expiry, selected_call, etf_price)

    def handle_option_expiry(self, current_date, etf_data):
        """处理期权到期"""
        # 处理PUT期权到期
        if self.pm.put_position and self.pm.put_position.expiry <= current_date:
            self._handle_put_expiry(current_date, etf_data)
            
        # 处理CALL期权到期
        if self.pm.call_position and self.pm.call_position.expiry <= current_date:
            self._handle_call_expiry(current_date, etf_data)

    def _handle_put_expiry(self, current_date, etf_data):
        """处理PUT期权到期"""
        expiry_date = self.pm.put_position.expiry
        expiry_etf_price = etf_data.at[expiry_date, '收盘价'] if expiry_date in etf_data.index else None

        if expiry_etf_price is None:
            print(f"Warning: No ETF price found for expiry date {expiry_date}")
            return

        # 在到期时将权利金计入收入
        premium_income = self.pm.put_position.premium * self.pm.contract_multiplier * self.pm.put_position.num_contracts
        self.pm.cash += premium_income

        # 记录到期信息
        expiry_details = {
            "ETF价格": f"{expiry_etf_price:.4f}",
            "行权价格": f"{self.pm.put_position.strike:.4f}",
            "合约数量": f"{self.pm.put_position.num_contracts}张",
            "权利金收入": f"{premium_income:.2f}"
        }

        exercise = "变废纸"
        if expiry_etf_price < self.pm.put_position.strike:
            # PUT被行权
            contracts = self.pm.put_position.num_contracts
            exercise_cost = self.pm.put_position.strike * self.pm.contract_multiplier * contracts
            self.pm.cash -= exercise_cost
            self.pm.etf_held += self.pm.contract_multiplier * contracts
            expiry_details["行权成本"] = f"{exercise_cost:.2f}"
            exercise = "被行权"
            self.pm.statistics['put_exercised'] += 1
            self.pm.statistics['put_exercise_cost'] += exercise_cost
            self.pm.statistics['etf_buy_cost'] += exercise_cost
        else:
            self.pm.statistics['put_expired'] += 1
        
        self.pm.statistics['max_etf_held'] = max(self.pm.statistics['max_etf_held'], self.pm.etf_held)
            
        current_position = self.pm.cash + (self.pm.etf_held * expiry_etf_price)
        expiry_details.update({
            "当前持仓ETF数量": str(self.pm.etf_held),
            "当前现金": f"{self.pm.cash:.2f}",
            "当前持仓头寸": f"{current_position:.2f}",
            "总收益率": f"{((current_position - self.pm.initial_cash) / self.pm.initial_cash * 100):.2f}%"
        })
        
        self.logger.log_option_expiry(f"{expiry_date.strftime('%m月')}PUT到期" + exercise, expiry_date, expiry_details)
        self.pm.put_position = None

    def _handle_call_expiry(self, current_date, etf_data):
        """处理CALL期权到期"""
        expiry_date = self.pm.call_position.expiry
        expiry_etf_price = etf_data.at[expiry_date, '收盘价'] if expiry_date in etf_data.index else None

        if expiry_etf_price is None:
            print(f"Warning: No ETF price found for expiry date {expiry_date}")
            return

        # 在到期时将权利金计入收入
        premium_income = self.pm.call_position.premium * self.pm.contract_multiplier * self.pm.call_position.num_contracts
        self.pm.cash += premium_income

        # 记录到期信息
        expiry_details = {
            "ETF价格": f"{expiry_etf_price:.4f}",
            "行权价格": f"{self.pm.call_position.strike:.4f}",
            "合约数量": f"{self.pm.call_position.num_contracts}张",
            "权利金收入": f"{premium_income:.2f}"
        }

        exercise = "作废"
        if expiry_etf_price > self.pm.call_position.strike:
            # CALL被行权
            contracts = self.pm.call_position.num_contracts
            exercise_income = self.pm.call_position.strike * self.pm.contract_multiplier * contracts
            self.pm.cash += exercise_income
            self.pm.etf_held -= self.pm.contract_multiplier * contracts
            expiry_details["行权收入"] = f"{exercise_income:.2f}"
            exercise = "行权"
            self.pm.statistics['call_exercised'] += 1
            self.pm.statistics['call_exercise_income'] += exercise_income
            self.pm.statistics['etf_sell_income'] += exercise_income
        else:
            self.pm.statistics['call_expired'] += 1
            
        current_position = self.pm.cash + (self.pm.etf_held * expiry_etf_price)
        expiry_details.update({
            "当前持仓ETF数量": str(self.pm.etf_held),
            "当前现金": f"{self.pm.cash:.2f}",
            "当前持仓头寸": f"{current_position:.2f}",
            "总收益率": f"{((current_position - self.pm.initial_cash) / self.pm.initial_cash * 100):.2f}%"
        })
        
        self.logger.log_option_expiry(f"{expiry_date.strftime('%m月')}CALL期权到期" + exercise, expiry_date, expiry_details)
        self.pm.call_position = None

    def _get_eligible_options(self, current_date, expiry, option_type, option_data):
        """获取符合条件的期权"""
        # 先判断日期
        date_filtered = option_data[option_data['日期'] == current_date]
        
        # 从交易代码中判断期权类型和月份
        # 例如：510500C2210M05750，需要判断C/P和年月
        year_str = str(expiry.year)[-2:]  # 获取年份的后两位
        month_str = str(expiry.month).zfill(2)  # 补零成两位数
        
        # 构建交易代码的匹配模式
        code_pattern = f'{option_type}{year_str}{month_str}'
        
        return date_filtered[date_filtered['交易代码'].str.contains(code_pattern)]

    def _get_closest_option(self, options, target_delta, is_call=True):
        """获取Delta值最接近目标值的期权"""
        # 创建options的副本以避免SettingWithCopyWarning
        options = options.copy()
        
        if is_call:
            # 对于CALL期权，寻找最接近target_delta的期权
            closest_idx = (options['Delta'] - target_delta).abs().idxmin()
            return options.loc[[closest_idx]]
        else:
            # 对于PUT期权，寻找最接近-target_delta的期权
            closest_idx = (options['Delta'] + target_delta).abs().idxmin()
            return options.loc[[closest_idx]]

    def _execute_put_trade(self, current_date, expiry, option_data, etf_price):
        """执行PUT期权交易"""
        strike_price = option_data['行权价'].iloc[0]
        premium_per_contract = option_data['结算价'].iloc[0]
        margin_per_contract = strike_price * self.pm.contract_multiplier
        
        # 计算可以卖出的最大合约数量
        max_contracts = 0
        while True:
            total_cost = (max_contracts + 1) * self.pm.transaction_cost_per_contract
            total_margin = (max_contracts + 1) * margin_per_contract
            
            if self.pm.cash - total_cost >= total_margin:
                max_contracts += 1
            else:
                break

        if max_contracts > 0:
            # 创建期权持仓对象
            self.pm.put_position = OptionPosition(
                expiry=expiry,
                strike=strike_price,
                premium=premium_per_contract,
                num_contracts=max_contracts,
                trade_code=option_data['交易代码'].iloc[0],
                initial_cash=self.pm.cash
            )
            
            # 扣除交易成本
            total_cost = self.pm.transaction_cost_per_contract * max_contracts
            self.pm.cash -= total_cost
            
            # 计算当前总头寸
            current_position = self.pm.cash + (self.pm.etf_held * etf_price)
            
            # 记录交易信息
            self.logger.log_option_expiry(f"卖出{expiry.strftime('%m月')}PUT期权", current_date, {
                "到期日": expiry.strftime('%Y-%m-%d'),
                "行权价": f"{strike_price:.4f}",
                "当前ETF价格": f"{etf_price:.4f}",
                "期权价格": f"{premium_per_contract:.4f}",
                "收取权利金": f"{premium_per_contract * max_contracts * self.pm.contract_multiplier:.2f}",
                "合约数量": f"{max_contracts}张",
                "交易成本": f"{total_cost:.2f}",
                "当前现金": f"{self.pm.cash:.2f}",
                "当前持仓头寸": f"{current_position:.2f}"
            })
            
            # 记录交易点
            current_return = (current_position - self.pm.initial_cash) / self.pm.initial_cash * 100
            self.pm.put_trades.append((current_date, current_return))
            
            # 更新统计数据
            self.pm.statistics['put_sold'] += 1
            self.pm.statistics['total_put_premium'] += premium_per_contract * max_contracts * self.pm.contract_multiplier
            self.pm.statistics['total_transaction_cost'] += total_cost
            self.pm.statistics['min_cash_position'] = min(self.pm.statistics['min_cash_position'], self.pm.cash)

            # 记录交易信息到trades字典
            self.pm.trades[current_date] = {
                '交易类型': '卖出PUT',
                '行权价': strike_price,
                '期权价格': premium_per_contract,
                '合约数量': max_contracts,
                '权利金': premium_per_contract * max_contracts * self.pm.contract_multiplier,
                '交易成本': total_cost,
                '到期日ETF价格': etf_price,
                'Delta': option_data['Delta'].iloc[0]
            }

    def _execute_call_trade(self, current_date, expiry, option_data, etf_price):
        """执行CALL期权交易"""
        strike_price = option_data['行权价'].iloc[0]
        premium_per_contract = option_data['结算价'].iloc[0]
        num_contracts = int(self.pm.etf_held // self.pm.contract_multiplier)
        
        if num_contracts > 0:
            # 创建期权持仓对象
            self.pm.call_position = OptionPosition(
                expiry=expiry,
                strike=strike_price,
                premium=premium_per_contract,
                num_contracts=num_contracts,
                trade_code=option_data['交易代码'].iloc[0],
                initial_cash=self.pm.cash
            )
            
            # 扣除交易成本
            total_cost = self.pm.transaction_cost_per_contract * num_contracts
            self.pm.cash -= total_cost
            
            # 计算当前总头寸
            current_position = self.pm.cash + (self.pm.etf_held * etf_price)
            
            # 记录交易信息
            self.logger.log_option_expiry(f"卖出{expiry.strftime('%m月')}CALL期权", current_date, {
                "到期日": expiry.strftime('%Y-%m-%d'),
                "行权价": f"{strike_price:.4f}",
                "当前ETF价格": f"{etf_price:.4f}",
                "期权权利金": f"{premium_per_contract:.4f}",
                "合约数量": f"{num_contracts}张",
                "交易成本": f"{total_cost:.2f}",
                "当前现金": f"{self.pm.cash:.2f}",
                "当前持仓头寸": f"{current_position:.2f}"
            })
            
            # 记录交易点
            current_return = (current_position - self.pm.initial_cash) / self.pm.initial_cash * 100
            self.pm.call_trades.append((current_date, current_return))
            
            # 更新统计数据
            self.pm.statistics['call_sold'] += 1
            self.pm.statistics['total_call_premium'] += premium_per_contract * num_contracts * self.pm.contract_multiplier
            self.pm.statistics['total_transaction_cost'] += total_cost
            self.pm.statistics['min_cash_position'] = min(self.pm.statistics['min_cash_position'], self.pm.cash)

            # 记录交易信息到trades字典
            self.pm.trades[current_date] = {
                '交易类型': '卖出CALL',
                '行权价': strike_price,
                '期权价格': premium_per_contract,
                '合约数量': num_contracts,
                '权利金': premium_per_contract * num_contracts * self.pm.contract_multiplier,
                '交易成本': total_cost,
                '到期日ETF价格': etf_price,
                'Delta': option_data['Delta'].iloc[0]
            }

    def execute_synthetic_position(self, current_date, expiry, option_data, etf_price):
        """执行合成持仓交易"""
        # 获取符合条件的PUT期权
        eligible_puts = self._get_eligible_options(current_date, expiry, 'P', option_data)
        if eligible_puts.empty:
            return False

        # 获取Delta值最接近0.1的PUT期权
        selected_put = self._get_closest_option(eligible_puts, 0.1, is_call=False)
        if selected_put.empty:
            return False

        # 获取相同行权价的CALL期权
        strike_price = selected_put['行权价'].iloc[0]
        eligible_calls = self._get_eligible_options(current_date, expiry, 'C', option_data)
        if eligible_calls.empty:
            return False

        # 从CALL期权中选择相同行权价的期权
        same_strike_calls = eligible_calls[eligible_calls['行权价'] == strike_price]
        if same_strike_calls.empty:
            return False

        # 执行合成持仓交易
        return self._execute_synthetic_trade(current_date, expiry, selected_put, same_strike_calls.iloc[0], etf_price)

    def _execute_synthetic_trade(self, current_date, expiry, put_option, call_option, etf_price):
        """执行合成持仓的具体交易"""
        strike_price = put_option['行权价'].iloc[0]
        put_premium = put_option['结算价'].iloc[0]
        call_premium = call_option['结算价'].iloc[0]
        
        # 计算所需保证金
        margin_per_contract = strike_price * self.pm.contract_multiplier
        
        # 计算可以建立的最大合约数量
        max_contracts = 0
        while True:
            total_cost = (max_contracts + 1) * self.pm.transaction_cost_per_contract * 2  # PUT和CALL各一张
            total_margin = (max_contracts + 1) * margin_per_contract
            call_cost = (max_contracts + 1) * call_premium * self.pm.contract_multiplier
            
            if self.pm.cash - total_cost - call_cost >= total_margin:
                max_contracts += 1
            else:
                break

        if max_contracts > 0:
            # 创建合成持仓
            self.pm.synthetic_put = OptionPosition(
                expiry=expiry,
                strike=strike_price,
                premium=put_premium,
                num_contracts=max_contracts,
                trade_code=put_option['交易代码'].iloc[0],
                initial_cash=self.pm.cash
            )
            
            self.pm.synthetic_call = OptionPosition(
                expiry=expiry,
                strike=strike_price,
                premium=call_premium,
                num_contracts=max_contracts,
                trade_code=call_option['交易代码'].iloc[0],
                initial_cash=self.pm.cash
            )
            
            # 标记合成持仓状态
            self.pm.synthetic_position = True
            
            # 计算交易成本和权利金
            total_cost = self.pm.transaction_cost_per_contract * max_contracts * 2  # PUT和CALL各收一次费用
            put_premium_income = put_premium * max_contracts * self.pm.contract_multiplier
            call_premium_cost = call_premium * max_contracts * self.pm.contract_multiplier
            
            # 更新现金
            self.pm.cash -= total_cost
            self.pm.cash += put_premium_income  # 收取PUT权利金
            self.pm.cash -= call_premium_cost   # 支付CALL权利金
            
            # 更新统计数据
            self.pm.statistics['synthetic_positions_opened'] += 1
            self.pm.statistics['synthetic_total_cost'] += total_cost
            self.pm.statistics['min_cash_position'] = min(self.pm.statistics['min_cash_position'], self.pm.cash)
            
            # 记录交易信息到trades字典
            self.pm.trades[current_date] = {
                '交易类型': '建立合成持仓',
                '行权价': strike_price,
                'PUT期权价格': put_premium,
                'CALL期权价格': call_premium,
                '合约数量': max_contracts,
                'PUT权利金收入': put_premium_income,
                'CALL权利金支出': call_premium_cost,
                '交易成本': total_cost,
                '到期日ETF价格': etf_price,
                'Delta': put_option['Delta'].iloc[0]
            }
            
            return True
        
        return False

    def handle_synthetic_expiry(self, current_date, etf_data):
        """处理合成持仓到期"""
        if not self.pm.synthetic_position:
            return
            
        if self.pm.synthetic_put and self.pm.synthetic_put.expiry <= current_date:
            expiry_date = self.pm.synthetic_put.expiry
            expiry_etf_price = etf_data.at[expiry_date, '收盘价'] if expiry_date in etf_data.index else None
            
            if expiry_etf_price is None:
                print(f"Warning: No ETF price found for synthetic position expiry date {expiry_date}")
                return
                
            # 计算到期损益
            strike_price = self.pm.synthetic_put.strike
            contracts = self.pm.synthetic_put.num_contracts
            
            if expiry_etf_price < strike_price:
                # PUT被行权，CALL作废
                exercise_cost = strike_price * self.pm.contract_multiplier * contracts
                self.pm.cash -= exercise_cost
                self.pm.etf_held += self.pm.contract_multiplier * contracts
                self.pm.statistics['synthetic_total_pnl'] -= exercise_cost
            elif expiry_etf_price > strike_price:
                # CALL被行权，PUT作废
                exercise_income = strike_price * self.pm.contract_multiplier * contracts
                self.pm.cash += exercise_income
                self.pm.statistics['synthetic_total_pnl'] += exercise_income
            
            # 清除合成持仓
            self.pm.synthetic_put = None
            self.pm.synthetic_call = None
            self.pm.synthetic_position = False
            self.pm.statistics['synthetic_positions_closed'] += 1

def main():
    # 回测中证 500ETF，使用合成持仓策略
    my_config = BacktestConfig('510500', delta=0.2, holding_type='synthetic')
    
    # 回测沪深 300ETF，指定delta值0.4
    # my_config = BacktestConfig('510300', delta=0.4, holding_type='synthetic')
    
    # 回测上证 50ETF，指定delta值0.3
    # my_config = BacktestConfig('510050', delta=0.3, holding_type='synthetic')
    
    my_engine = BacktestEngine(my_config)
    my_results = my_engine.run_backtest()
    
    if my_results:
        print(f"\n=== {my_results['symbol']}ETF策略回测结果 ===")
        if 'portfolio_total_return' in my_results:
            print(f"最终累计收益率 (期权策略): {my_results['portfolio_total_return']:.2f}%")
            print(f"最大回撤 (期权策略): {my_results['portfolio_max_drawdown']:.2f}%")
            print(f"最大回撤开始日期: {my_results['portfolio_max_drawdown_start_date']}")
            print(f"最大回撤结束日期: {my_results['portfolio_max_drawdown_end_date']}")
            
            etf_last_return = my_results['etf_buy_hold_df']['etf_buy_hold_return'].iloc[-1]
            print(f"最终累计收益率 (持有ETF): {etf_last_return:.2f}%")
            
            plot_equity_curve(my_results, my_results['symbol'])

if __name__ == "__main__":
    main()