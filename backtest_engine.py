from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime
from portfolio_manager import PortfolioManager
from option_trader import OptionTrader
from strategy_analyzer import StrategyAnalyzer
from logger import TradeLogger
from utils import get_trading_dates, get_next_monthly_expiry, get_monthly_expiry
from visualization import StrategyVisualizer
from backtest_params import BacktestConfig, StrategyType, BacktestParam
from strategies.factory import StrategyFactory
from strategies.types import PositionConfig
from strategies.base import OptionStrategy
import sqlite3
import os

class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        """
        回测引擎
        
        Args:
            config: 回测配置对象，包含固定的系统配置信息
        """
        self.config = config
        self.option_data = None
        self.etf_data = None
        self.logger = TradeLogger()
        self.visualizer = StrategyVisualizer()
        
        # 记录初始化信息
        self.logger.log_trade(datetime.now(), "初始化回测引擎", {
            "初始资金": self.config.initial_capital,
            "合约乘数": self.config.contract_multiplier,
            "交易成本": self.config.transaction_cost,
            "保证金比例": f"{self.config.margin_ratio*100}%",
            "止损比例": f"{self.config.stop_loss_ratio*100}%"
        })
        
    def _create_strategy(self, param: BacktestParam) -> Optional[OptionStrategy]:
        """根据参数创建策略实例"""
        # 创建持仓配置
        position_config = PositionConfig(
            etf_code=param.etf_code,
            sell_delta=param.strategy_params.get('call_sell_delta'),
            buy_delta=param.strategy_params.get('call_buy_delta'),
            contract_multiplier=self.config.contract_multiplier,
            margin_ratio=self.config.margin_ratio,
            stop_loss_ratio=self.config.stop_loss_ratio,
            transaction_cost=self.config.transaction_cost
        )
        
        try:
            # 添加调试信息
            print(f"Debug - Creating strategy of type: {param.strategy_type}")
            print(f"Debug - Strategy type value: {param.strategy_type.value}")
            print(f"Debug - Available strategies: {StrategyFactory._strategies}")
            print(f"Debug - Strategy type in dict: {param.strategy_type in StrategyFactory._strategies}")
            
            return StrategyFactory.create_strategy(param.strategy_type, position_config)
        except Exception as e:
            self.logger.log_error(f"创建策略失败: {str(e)}")
            return None

    def run_backtest(self, param: BacktestParam) -> Optional[Dict[str, Any]]:
        """
        运行回测
        
        Args:
            param: 回测参数对象，包含每次运行需要的参数
        """
        if not self.load_data(param):
            return None
            
        # 创建策略实例
        strategy = self._create_strategy(param)
        if not strategy:
            return None
            
        # 设置策略的期权数据和初始资金
        strategy.set_option_data(self.option_data)
        strategy.cash = self.config.initial_capital  # 设置初始资金
        
        # 获取交易日期列表
        trading_dates = get_trading_dates(
            param.start_date,
            param.end_date,
            self.option_data
        )
        
        # 检查是否有有效的交易日期
        if not trading_dates:
            self.logger.log_error("没有找到有效的交易日期，请检查日期范围和数据文件")
            return None
        
        self.logger.log_trade(trading_dates[0], "回测开始", {
            "初始资金": self.config.initial_capital,
            "标的": param.etf_code,
            "策略类型": strategy.__class__.__name__,
            "开始日期": trading_dates[0].strftime('%Y-%m-%d'),
            "结束日期": trading_dates[-1].strftime('%Y-%m-%d')
        })
        
        # 遍历每个交易日
        daily_portfolio_values = {}
        for current_date in trading_dates:
            # 获取当日市场数据
            market_data = {
                'etf': self.etf_data[self.etf_data.index == current_date],
                'option': self.option_data[self.option_data['日期'] == current_date]
            }
            
            # 执行策略
            trade_result = strategy.execute(current_date, market_data)
            
            # 计算当日投资组合价值
            portfolio_value = strategy.cash - strategy.margin
            for code, position in strategy.positions.items():
                current_price = strategy._get_current_price(
                    code, current_date, self.option_data
                )
                if current_price is not None:
                    portfolio_value += current_price * position.quantity * self.config.contract_multiplier
            
            # 记录每日投资组合状态
            self.logger.log_daily_portfolio(current_date, {
                'cash': strategy.cash,
                'margin': strategy.margin,
                'portfolio_value': portfolio_value,
                'positions': len(strategy.positions)
            })
            
            # 记录每日投资组合价值
            daily_portfolio_values[current_date] = {
                'total_value': portfolio_value,
                'margin_occupied': strategy.margin,
                'daily_return': (portfolio_value / self.config.initial_capital - 1) * 100
            }
        
        # 分析策略结果
        analysis_results = StrategyAnalyzer.calculate_metrics(
            daily_portfolio_values,
            strategy.trades,
            self.config.initial_capital,
            self.etf_data
        )
        
        # 生成策略报告
        report = StrategyAnalyzer.generate_report(analysis_results)
        
        self.logger.log_trade(trading_dates[-1], "回测结束", {
            "报告": report
        })
        
        # 生成可视化图表
        plots = self.visualizer.create_plots(
            strategy.trades,
            param.etf_code,
            self.etf_data,
            analysis_results
        )
        
        # 返回回测结果
        return {
            "etf_code": param.etf_code,
            "strategy_type": strategy.__class__.__name__,
            "trades": strategy.trades,
            "analysis": analysis_results,
            "report": report,
            "plots": plots
        }

    def load_data(self, param: BacktestParam) -> bool:
        """加载数据
        
        Args:
            param: 回测参数对象，包含每次运行需要的参数
        """
        try:
            # 连接数据库
            conn = sqlite3.connect('market_data.db')
            
            # 加载期权数据
            option_query = """
                SELECT *, 
                CASE 
                    WHEN contract_code LIKE '%C%' THEN '认购'
                    WHEN contract_code LIKE '%P%' THEN '认沽'
                END as option_type
                FROM option_daily 
                WHERE etf_code = ? 
                AND date BETWEEN ? AND ?
            """
            self.option_data = pd.read_sql_query(
                option_query, 
                conn, 
                params=(
                    param.etf_code,
                    param.start_date.strftime('%Y-%m-%d'),
                    param.end_date.strftime('%Y-%m-%d')
                )
            )
            
            # 转换日期列
            self.option_data['date'] = pd.to_datetime(self.option_data['date'])
            self.option_data = self.option_data.rename(columns={
                'date': '日期',
                'contract_code': '交易代码',
                'close_price': '收盘价',
                'strike_price': '行权价',
                'delta': 'Delta',
                'option_type': '认购认沽'
            })
            
            if self.option_data.empty:
                print(f"警告: 在指定日期范围内没有找到期权数据")
                return False

            # 加载ETF数据
            etf_query = """
                SELECT * FROM etf_daily 
                WHERE etf_code = ? 
                AND date BETWEEN ? AND ?
            """
            etf_data = pd.read_sql_query(
                etf_query, 
                conn, 
                params=(
                    param.etf_code,
                    param.start_date.strftime('%Y-%m-%d'),
                    param.end_date.strftime('%Y-%m-%d')
                )
            )
            
            # 转换日期列并设置为索引
            etf_data['date'] = pd.to_datetime(etf_data['date'])
            self.etf_data = etf_data.set_index('date')
            self.etf_data = self.etf_data.rename(columns={
                'close_price': '收盘价',
                'open_price': '开盘价'
            })

            if self.etf_data.empty:
                print(f"警告: 在指定日期范围内没有找到ETF数据")
                return False
            
            conn.close()
            return True
            
        except Exception as e:
            print(f"加载数据时出错: {str(e)}")
            return False

def main():
    """主函数"""
    # 创建固定的回测配置
    config = BacktestConfig()
    
    # 创建回测引擎
    engine = BacktestEngine(config)
    
    # 创建回测参数（这里仅作示例，实际应该从前端获取）
    param = BacktestParam(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 12, 31),
        etf_code='510300',  # 沪深300ETF
        strategy_type=StrategyType.BEARISH_CALL,
        strategy_params={
            'call_sell_delta': 0.3,  # 卖出0.3 Delta的看涨期权
            'call_buy_delta': 0.2    # 买入0.2 Delta的看涨期权
        }
    )
    
    # 打印回测参数
    print("\n=== 开始回测 ===")
    print(f"标的: {param.etf_code}")
    print(f"策略: {param.strategy_type.value}")
    print(f"参数: {param.strategy_params}")
    print(f"日期: {param.start_date.strftime('%Y-%m-%d')} 至 {param.end_date.strftime('%Y-%m-%d')}")
    
    # 运行回测
    results = engine.run_backtest(param)
    
    if results:
        print(f"\n=== 策略回测结果 ===")
        print(f"策略类型: {results['strategy_type']}")
        print(f"交易次数: {len(results['trades'])}")
        
        if 'analysis' in results:
            analysis = results['analysis']
            print(f"累计收益率: {analysis.get('total_return', 0):.2f}%")
            print(f"年化收益率: {analysis.get('annual_return', 0):.2f}%")
            print(f"最大回撤: {analysis.get('max_drawdown', 0):.2f}%")
            print(f"夏普比率: {analysis.get('sharpe_ratio', 0):.2f}")
            
        if 'report' in results:
            print("\n详细报告:")
            print(results['report'])

if __name__ == "__main__":
    main() 