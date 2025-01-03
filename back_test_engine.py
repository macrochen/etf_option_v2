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
        total_return = (portfolio_values_series.iloc[-1] - portfolio_values_series.iloc[0]) / portfolio_values_series.iloc[0]
        portfolio_df['cumulative_return'] = (portfolio_values_series - initial_cash) / initial_cash * 100
        
        # 计算最大回撤
        peak = portfolio_values_series.expanding(min_periods=1).max()
        drawdown = (portfolio_values_series - peak) / peak
        max_drawdown = drawdown.min()
        max_drawdown_end_date = drawdown.idxmin()
        max_drawdown_start_date = peak[:max_drawdown_end_date].idxmax()
        
        # 计算日收益率，用于计算波动率
        daily_returns = portfolio_values_series.pct_change().dropna()
        annual_volatility = daily_returns.std() * np.sqrt(252)
        
        # 计算夏普比率
        risk_free_rate = 0.02  # 假设无风险利率为2%
        sharpe_ratio = (portfolio_annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0
        
        return {
            "portfolio_df": portfolio_df,
            "max_drawdown": max_drawdown * 100,
            "max_drawdown_start_date": max_drawdown_start_date,
            "max_drawdown_end_date": max_drawdown_end_date,
            "sharpe_ratio": sharpe_ratio,
            "annual_return": portfolio_annual_return,
            "annual_volatility": annual_volatility,
            "total_return": total_return,
            "put_trades": put_trades,
            "call_trades": call_trades,
            "portfolio_metrics": {
                'sharpe_ratio': sharpe_ratio,
                'annual_return': portfolio_annual_return,
                'annual_volatility': annual_volatility,
                'total_return': portfolio_total_return
            }
        }

    @staticmethod
    def print_strategy_statistics(statistics, portfolio_values, initial_cash, etf_buy_hold_portfolio, analysis_results):
        """打印策略统计信息"""
        # 计算期权策略的指标
        portfolio_values_series = pd.Series({date: data['portfolio_value'] 
                                          for date, data in portfolio_values.items()})
        portfolio_metrics = calculate_sharpe_ratio(portfolio_values_series)
        
        # 计算ETF持有策略的指标
        etf_values_series = pd.Series({date: data['etf_buy_hold_value'] 
                                     for date, data in etf_buy_hold_portfolio.items()})
        etf_metrics = calculate_sharpe_ratio(etf_values_series)
        
        # 计算ETF持有策略的最大回撤
        etf_peak = etf_values_series.expanding(min_periods=1).max()
        etf_drawdown = (etf_values_series - etf_peak) / etf_peak
        etf_max_drawdown = etf_drawdown.min() * 100
        
        print("\n=== 策略绩效对比 ===")
        print("指标              期权组合策略    ETF持有策略")
        print("-" * 45)
        print(f"年化收益率:      {portfolio_metrics['annual_return']*100:8.2f}%    {etf_metrics['annual_return']*100:8.2f}%")
        print(f"年化波动率:      {portfolio_metrics['annual_volatility']*100:8.2f}%    {etf_metrics['annual_volatility']*100:8.2f}%")
        print(f"夏普比率:        {portfolio_metrics['sharpe_ratio']:8.2f}    {etf_metrics['sharpe_ratio']:8.2f}")
        print(f"最大回撤:        {analysis_results['max_drawdown']:8.2f}%    {etf_max_drawdown:8.2f}%")
        
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
    trading_days = sorted(pd.Index(option_data['日期'].unique()).union(etf_data.index))
    
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
    
    # 计算回测的实际日历天数
    start_date = trading_days[0]
    end_date = trading_days[-1]
    calendar_days = (end_date - start_date).days + 1
    
    # 计算期权策略的累计收益率和年化收益率
    portfolio_values_series = pd.Series({date: data['portfolio_value'] 
                                     for date, data in portfolio_manager.portfolio_values.items()})
    portfolio_total_return = (portfolio_values_series.iloc[-1] - portfolio_values_series.iloc[0]) / portfolio_values_series.iloc[0]
    portfolio_annual_return = (1 + portfolio_total_return) ** (365/calendar_days) - 1
    
    # 计算ETF策略的累计收益率和年化收益率
    etf_values_series = pd.Series({date: data['etf_buy_hold_value'] 
                                for date, data in etf_buy_hold_portfolio.items()})
    etf_total_return = (etf_values_series.iloc[-1] - etf_values_series.iloc[0]) / etf_values_series.iloc[0]
    etf_annual_return = (1 + etf_total_return) ** (365/calendar_days) - 1
    
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
        'annual_return': etf_annual_return,
        'total_return': etf_total_return
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
    
    return analysis_results

def get_monthly_expiry(date, option_data):
    year = date.year
    month = date.month
    cal = monthcalendar(year, month)
    wednesdays = [day for week in cal for day in week if day != 0 and datetime(year, month, day).weekday() == 2]
    if len(wednesdays) < 4:
        raise ValueError(f"Month {month} in {year} does not have four Wednesdays.")
    potential_expiry_day = wednesdays[3]  # 获取第四个星期三
    potential_expiry_date = pd.Timestamp(datetime(year, month, potential_expiry_day))

    # 检查期权数据中是否存在该日期，并添加最大搜索天数限制
    search_days = 0
    max_search_days = 10  # 设置最大搜索天数，可以根据实际情况调整
    while search_days < max_search_days:
        if any(option_data['日期'].dt.date == potential_expiry_date.date()):
            return potential_expiry_date
        else:
            potential_expiry_date += pd.Timedelta(days=1)
            search_days += 1

    raise ValueError(f"Could not find valid expiry date for {date.strftime('%Y-%m')} within {max_search_days} days in option data.")

def get_next_monthly_expiry(date, option_data):
    # print(f"get_next_monthly_expiry called with date: {date}")  # 调试信息

    # 获取下个月的第一天
    next_month_date = date.replace(day=1)
    if next_month_date.month == 12:
        next_month_date = next_month_date.replace(year=next_month_date.year + 1, month=1)
    else:
        next_month_date = next_month_date.replace(month=next_month_date.month + 1)

    year = next_month_date.year
    month = next_month_date.month
    cal = monthcalendar(year, month)
    wednesdays = [day for week in cal for day in week if day != 0 and datetime(year, month, day).weekday() == 2]
    if len(wednesdays) < 4:
        raise ValueError(f"Month {month} in {year} does not have four Wednesdays.")
    potential_expiry_day = wednesdays[3]  # 获取第四个星期三
    potential_expiry_date = pd.Timestamp(datetime(year, month, potential_expiry_day))
    # print(f"Initial potential_expiry_date: {potential_expiry_date}") # 调试信息

    max_data_date = option_data['日期'].max() # 获取期权数据的最大日期

    # 检查计算出的到期日是否超出数据范围
    if potential_expiry_date > max_data_date:
        print(f"Warning: Potential expiry date {potential_expiry_date} exceeds maximum data date {max_data_date}.")
        return None  # 或者返回上个月的到期日，根据你的策略调整

    # 检查期权数据中是否存在该日期，并添加最大搜索天数限制
    search_days = 0
    max_search_days = 10  # 设置最大搜索天数，可以根据实际情况调整
    while search_days < max_search_days:
        # print(f"Checking potential_expiry_date: {potential_expiry_date.date()}") # 调试信息
        if any(option_data['日期'].dt.date == potential_expiry_date.date()):
            return potential_expiry_date
        else:
            potential_expiry_date += pd.Timedelta(days=1)
            if potential_expiry_date > max_data_date: # 再次检查是否超出数据范围
                print(f"Warning: Potential expiry date exceeded maximum data date during search.")
                return None
            search_days += 1
            # print(f"Incremented potential_expiry_date to: {potential_expiry_date.date()}") # 调试信息

    print(f"Could not find valid next monthly expiry date, last checked date: {potential_expiry_date.date()}") # 调试信息
    raise ValueError(f"Could not find valid next monthly expiry date for {date.strftime('%Y-%m')} within {max_search_days} days in option data.")

def calculate_sharpe_ratio(portfolio_values, risk_free_rate=0.02):
    """
    计算策略的Sharpe ratio
    :param portfolio_values: 包含每日投资组合价值的Series
    :param risk_free_rate: 无风险利率，默认2%
    :return: Sharpe ratio
    """
    # 确保输入是Series类型
    if not isinstance(portfolio_values, pd.Series):
        portfolio_values = pd.Series(portfolio_values)
    
    try:
        # 计算累计收益率
        total_return = (portfolio_values.iloc[-1] - portfolio_values.iloc[0]) / portfolio_values.iloc[0]
        
        # 计算实际日历天数
        start_date = portfolio_values.index[0]
        end_date = portfolio_values.index[-1]
        calendar_days = (end_date - start_date).days + 1  # 加1是因为包含起始日
        
        # 计算年化收益率
        # 使用复利公式: (1 + r)^n = (1 + total_return)，其中n = 365/calendar_days
        annual_return = (1 + total_return) ** (365/calendar_days) - 1
        
        # 计算日收益率，用于计算波动率
        daily_returns = portfolio_values.pct_change().dropna()
        
        # 计算年化波动率
        annual_volatility = daily_returns.std() * np.sqrt(252)  # 波动率仍使用交易日数252
        
        # 计算Sharpe ratio
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0
        
        return {
            'sharpe_ratio': sharpe_ratio,
            'annual_return': annual_return,
            'annual_volatility': annual_volatility
        }
    except Exception as e:
        print(f"Warning: Error calculating Sharpe ratio: {str(e)}")
        return {
            'sharpe_ratio': 0,
            'annual_return': 0,
            'annual_volatility': 0
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
        # 加载期权数据
        all_option_data = []
        for file_path in self.config.option_file_paths:
            try:
                df = pd.read_excel(file_path)
                # 清理 '日期' 列：移除包含特定字符串的行
                df = df[~df['日期'].astype(str).str.contains('数据来源')]
                # 将 '日期' 列转换为 datetime 类型
                df['日期'] = pd.to_datetime(df['日期'])
                all_option_data.append(df)
            except FileNotFoundError:
                print(f"Error: Option data file not found: {file_path}")
                return False
            except ImportError as e:
                if 'openpyxl' in str(e):
                    print("Error: Missing the 'openpyxl' library. Please install it using:")
                    print("pip install openpyxl")
                    return False
                else:
                    raise e
        
        self.option_data = pd.concat(all_option_data, ignore_index=True)
        
        # 加载ETF数据
        try:
            self.etf_data = pd.read_csv(self.config.etf_file_path)
            self.etf_data['日期'] = pd.to_datetime(self.etf_data['日期'])
        except FileNotFoundError:
            print(f"Error: ETF data file not found: {self.config.etf_file_path}")
            return False
        
        # 根据日期范围过滤数据
        if self.config.start_date:
            self.option_data = self.option_data[self.option_data['日期'] >= self.config.start_date]
            self.etf_data = self.etf_data[self.etf_data['日期'] >= self.config.start_date]
        
        if self.config.end_date:
            self.option_data = self.option_data[self.option_data['日期'] <= self.config.end_date]
            self.etf_data = self.etf_data[self.etf_data['日期'] <= self.config.end_date]
        
        # 确保数据不为空
        if len(self.option_data) == 0 or len(self.etf_data) == 0:
            print("Error: No data available for the specified date range")
            return False
            
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
            print(f"最大回撤 (期权策略): {my_results['max_drawdown']:.2f}%")
            print(f"最大回撤开始日期: {my_results['max_drawdown_start_date']}")
            print(f"最大回撤结束日期: {my_results['max_drawdown_end_date']}")
            
            etf_last_return = my_results['etf_buy_hold_df']['etf_buy_hold_return'].iloc[-1]
            print(f"最终累计收益率 (持有ETF): {etf_last_return:.2f}%")
            
            plot_equity_curve(my_results, my_results['symbol'])

if __name__ == "__main__":
    main()