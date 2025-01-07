from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime
from portfolio_manager import PortfolioManager
from option_trader import OptionTrader
from strategy_analyzer import StrategyAnalyzer
from logger import TradeLogger
from utils import get_trading_dates, get_next_monthly_expiry, get_monthly_expiry
from visualization import StrategyVisualizer
from backtest_params import BacktestParams, StrategyType
from config import BacktestConfig
import sqlite3
import os

class BacktestEngine:
    def __init__(self, params: BacktestConfig):
        """
        回测引擎
        
        Args:
            params: 回测参数对象，包含ETF代码、日期范围、策略参数等
        """
        self.params = params
        self.option_data = None
        self.etf_data = None
        self.logger = TradeLogger()
        self.visualizer = StrategyVisualizer()
        
        # 从配置中获取参数
        self.initial_capital = params.initial_capital
        self.contract_multiplier = params.contract_multiplier
        self.transaction_cost = params.transaction_cost
        self.margin_ratio = 0.12  # 保证金比例
        self.stop_loss_ratio = 0.5  # 止损比例
        
        # 验证参数
        self._validate_params()
        
        # 记录初始化信息
        self.logger.log_trade(datetime.now(), "初始化回测引擎", {
            "ETF代码": self.params.etf_code,
            "持仓方式": self.params.holding_type,
            "Delta": self.params.delta,
            "初始资金": self.initial_capital,
            "合约乘数": self.contract_multiplier,
            "交易成本": self.transaction_cost,
            "保证金比例": f"{self.margin_ratio*100}%",
            "止损比例": f"{self.stop_loss_ratio*100}%"
        })
        
    def _validate_params(self):
        """验证基础参数的合法性"""
        # 验证资金相关参数
        if self.initial_capital <= 0:
            raise ValueError("初始资金必须大于0")
        
        # 验证合约乘数
        if self.contract_multiplier <= 0:
            raise ValueError("合约乘数必须大于0")
        
        # 验证交易成本
        if self.transaction_cost < 0:
            raise ValueError("交易成本不能为负数")
        
        # 验证保证金比例
        if not (0 < self.margin_ratio <= 1):
            raise ValueError("保证金比例必须在0到1之间")
        
        # 验证止损比例
        if not (0 < self.stop_loss_ratio <= 1):
            raise ValueError("止损比例必须在0到1之间")
        
        # 验证数据库文件
        if not os.path.exists(self.params.db_path):
            raise ValueError(f"找不到数据库文件: {self.params.db_path}")
        
        # 验证ETF代码
        if not self.params.etf_code:
            raise ValueError("ETF代码不能为空")
        
    def run_backtest(self) -> Optional[Dict[str, Any]]:
        """运行回测"""
        if not self.load_data():
            return None
            
        # 初始化组件
        portfolio_manager = PortfolioManager(
            initial_cash=self.initial_capital,
            contract_multiplier=self.contract_multiplier,
            transaction_cost_per_contract=self.transaction_cost,
            margin_ratio=self.margin_ratio
        )
        
        option_trader = OptionTrader(
            portfolio_manager=portfolio_manager,
            delta=self.params.delta,
            stop_loss_ratio=self.stop_loss_ratio
        )
        
        # 获取交易日期列表
        trading_dates = get_trading_dates(
            self.params.start_date,
            self.params.end_date,
            self.option_data
        )
        
        # 检查是否有有效的交易日期
        if not trading_dates:
            self.logger.log_error("没有找到有效的交易日期，请检查日期范围和数据文件")
            return None
        
        self.logger.log_trade(trading_dates[0], "回测开始", {
            "初始资金": self.initial_capital,
            "标的": self.params.etf_code,
            "持仓方式": self.params.holding_type,
            "Delta": self.params.delta,
            "开始日期": trading_dates[0].strftime('%Y-%m-%d'),
            "结束日期": trading_dates[-1].strftime('%Y-%m-%d')
        })
        
        # 遍历每个交易日
        for current_date in trading_dates:
            # 获取当日ETF价格
            etf_price = self.etf_data.at[current_date, '收盘价'] \
                       if current_date in self.etf_data.index else None
            if etf_price is None:
                self.logger.log_warning(f"无法获取 {current_date} 的ETF价格")
                continue
            
            # 处理期权到期或平仓
            option_trader.handle_positions(current_date, self.etf_data, self.option_data)
            
            # 如果没有持仓，尝试开仓
            if not option_trader.has_positions():
                # 第一次开仓使用当月到期日，后续使用下月到期日
                if not portfolio_manager.trades:  # 如果没有交易记录，说明是第一次开仓
                    expiry = get_monthly_expiry(current_date, self.option_data)
                else:
                    expiry = get_next_monthly_expiry(current_date, self.option_data)
                    
                if expiry:
                    option_trader.open_positions(current_date, expiry, self.option_data, etf_price)
            
            # 计算当日投资组合价值
            portfolio_value, unrealized_pnl = portfolio_manager.calculate_portfolio_value(
                current_date, etf_price, self.option_data
            )
            
            # 记录每日投资组合状态
            self.logger.log_daily_portfolio(current_date, {
                'cash': portfolio_manager.cash,
                'option_value': unrealized_pnl,
                'total_value': portfolio_value,
                'daily_return': portfolio_manager.portfolio_values[current_date].daily_return,
                'cumulative_return': portfolio_manager.portfolio_values[current_date].total_value / \
                                   self.initial_capital - 1
            })
        
        # 分析策略结果
        analysis_results = StrategyAnalyzer.calculate_metrics(
            portfolio_manager.portfolio_values,
            portfolio_manager.trades,
            self.initial_capital,
            self.etf_data
        )
        
        # 生成策略报告
        report = StrategyAnalyzer.generate_report(analysis_results)
        
        self.logger.log_trade(trading_dates[-1], "回测结束", {
            "报告": report
        })
        
        # 生成可视化图表
        plots = self.visualizer.create_plots(
            portfolio_manager.portfolio_values,
            portfolio_manager.trades,
            self.params.etf_code,
            self.etf_data,
            analysis_results
        )
        
        # 返回回测结果
        return {
            "etf_code": self.params.etf_code,
            "holding_type": self.params.holding_type,
            "delta": self.params.delta,
            "portfolio_values": portfolio_manager.portfolio_values,
            "trades": portfolio_manager.trades,
            "analysis": analysis_results,
            "report": report,
            "plots": plots
        }

    def load_data(self) -> bool:
        """从SQLite数据库加载数据"""
        try:
            # 连接数据库
            conn = sqlite3.connect('market_data.db')
            
            self.logger.log_trade(datetime.now(), "开始从数据库加载数据", {
                "ETF代码": self.params.etf_code,
                "开始日期": self.params.start_date.strftime('%Y-%m-%d') if self.params.start_date else "earliest",
                "结束日期": self.params.end_date.strftime('%Y-%m-%d') if self.params.end_date else "latest"
            })
            
            # 构建ETF数据查询
            etf_query = f"""
                SELECT date, open_price, close_price
                FROM etf_daily
                WHERE etf_code = '{self.params.etf_code}'
            """
            if self.params.start_date:
                etf_query += f" AND date >= '{self.params.start_date.strftime('%Y-%m-%d')}'"
            if self.params.end_date:
                etf_query += f" AND date <= '{self.params.end_date.strftime('%Y-%m-%d')}'"
            etf_query += " ORDER BY date"
            
            # 加载ETF数据
            self.etf_data = pd.read_sql_query(etf_query, conn, parse_dates=['date'])
            self.etf_data = self.etf_data.set_index('date')
            
            # 构建期权数据查询
            option_query = f"""
                SELECT date, contract_code, change_rate, open_price, close_price,
                       strike_price, delta, settlement_price
                FROM option_daily
                WHERE etf_code = '{self.params.etf_code}'
            """
            if self.params.start_date:
                option_query += f" AND date >= '{self.params.start_date.strftime('%Y-%m-%d')}'"
            if self.params.end_date:
                option_query += f" AND date <= '{self.params.end_date.strftime('%Y-%m-%d')}'"
            option_query += " ORDER BY date"
            
            # 加载期权数据
            self.option_data = pd.read_sql_query(option_query, conn, parse_dates=['date'])
            
            # 如果没有指定日期范围，使用数据中的最小和最大日期
            if self.params.start_date is None:
                self.params.start_date = self.option_data['date'].min()
            if self.params.end_date is None:
                self.params.end_date = self.option_data['date'].max()
            
            # 记录数据加载结果
            self.logger.log_trade(datetime.now(), "数据加载完成", {
                "期权数据行数": len(self.option_data),
                "ETF数据行数": len(self.etf_data),
                "数据日期范围": f"{self.option_data['date'].min().strftime('%Y-%m-%d')} 至 {self.option_data['date'].max().strftime('%Y-%m-%d')}"
            })
            
            # 关闭数据库连接
            conn.close()
            
            # 重命名列名以匹配原有代码
            self.option_data = self.option_data.rename(columns={
                'date': '日期',
                'contract_code': '交易代码',
                'change_rate': '涨跌幅(%)',
                'open_price': '开盘价',
                'close_price': '收盘价',
                'strike_price': '行权价',
                'delta': 'Delta',
                'settlement_price': '结算价'
            })
            
            self.etf_data = self.etf_data.rename(columns={
                'open_price': '开盘价',
                'close_price': '收盘价'
            })
            
            return True
            
        except Exception as e:
            self.logger.log_error(f"数据库加载失败: {str(e)}")
            return False 

def main():
    """主函数"""
    # 创建回测配置
    configs = [
        BacktestConfig(
            etf_code='510300',  # 沪深300ETF
            delta=0.4,
            holding_type='synthetic'
        ),
        BacktestConfig(
            etf_code='510500',  # 中证500ETF
            delta=0.2,
            holding_type='synthetic'
        ),
        BacktestConfig(
            etf_code='510050',  # 上证50ETF
            delta=0.3,
            holding_type='synthetic'
        )
    ]
    
    # 运行每个配置的回测
    for config in configs:
        print(f"\n=== 开始回测 {config.etf_code} ===")
        engine = BacktestEngine(config)
        results = engine.run_backtest()
        
        if results:
            print(f"\n=== {config.etf_code}ETF策略回测结果 ===")
            if 'portfolio_total_return' in results:
                print(f"最终累计收益率 (期权策略): {results['portfolio_total_return']:.2f}%")
                print(f"最大回撤 (期权策略): {results['portfolio_max_drawdown']:.2f}%")
                print(f"最大回撤开始日期: {results['portfolio_max_drawdown_start_date']}")
                print(f"最大回撤结束日期: {results['portfolio_max_drawdown_end_date']}")
                
                etf_last_return = results['etf_buy_hold_df']['etf_buy_hold_return'].iloc[-1]
                print(f"最终累计收益率 (持有ETF): {etf_last_return:.2f}%")
                
                plot_equity_curve(results, config.etf_code)

if __name__ == "__main__":
    main() 