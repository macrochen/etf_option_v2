import os
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd

from logger import TradeLogger
from strategies import BacktestConfig, StrategyContext
from strategies.base import OptionStrategy
from strategies.factory import StrategyFactory
from strategies.types import BacktestResult
from strategy_analyzer import StrategyAnalyzer
from utils import get_trading_dates
from visualization import StrategyVisualizer


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
        
    def _create_strategy(self, context: StrategyContext) -> Optional[OptionStrategy]:
        """根据参数创建策略实例"""
        
        # 创建持仓配置
        try:
            # 创建策略实例
            strategy = StrategyFactory.create_strategy(
                strategy_type=context.strategy_type,
                context=context,
                option_data=self.option_data,
                etf_data=self.etf_data
            )

            return strategy

        except Exception as e:
            import traceback
            self.logger.log_error(
                f"策略创建失败:\n{str(e)}\n{traceback.format_exc()}"
            )
            return None

    def run_backtest(self, context: StrategyContext) -> Optional[BacktestResult]:
        """运行回测
        
        Args:
            context: 回测参数对象
            
        Returns:
            Optional[BacktestResult]: 回测结果对象，如果回测失败则返回None
        """
        try:
            if not self.load_data(context):
                return None
                
            # 创建策略实例
            strategy = self._create_strategy(context)
            if not strategy:
                return None
                
            # 设置策略的期权数据和初始资金
            strategy.set_option_data(self.option_data)
            strategy.cash = self.config.initial_capital  # 设置初始资金
            
            # 获取交易日期列表
            trading_dates = get_trading_dates(
                context.start_date,
                context.end_date,
                self.option_data
            )
            
            # 检查是否有有效的交易日期
            if not trading_dates:
                self.logger.log_error("没有找到有效的交易日期，请检查日期范围和数据文件")
                return None
            
            self.logger.log_trade(trading_dates[0], "回测开始", {
                "初始资金": self.config.initial_capital,
                "标的": context.etf_code,
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
                strategy.execute(current_date, market_data)
                
                # 计算当日投资组合价值
                portfolio_value = strategy.calculate_portfolio_value(current_date)
                
                # 记录每日投资组合状态
                self.logger.log_daily_portfolio(current_date, {
                    'cash': strategy.cash,
                    'portfolio_value': portfolio_value,
                    'positions': len(strategy.positions)
                })
                
                # 记录每日投资组合价值
                daily_portfolio_values[current_date] = portfolio_value

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
                daily_portfolio_values,
                strategy.trades,
                context.etf_code,
                self.etf_data,
                analysis_results
            )
            
            # 返回回测结果
            return BacktestResult(
                    etf_code=context.etf_code,
                    strategy_type=strategy.__class__.__name__,
                    trades=strategy.trades,
                    portfolio_values=daily_portfolio_values,
                    analysis=analysis_results,
                    report=report,
                    plots=plots
                )
            
        except Exception as e:
            import traceback
            print(f"回测执行过程中发生错误: {str(e)}")
            print("堆栈信息:")
            print(traceback.format_exc())
            return None

    def load_data(self, context: StrategyContext) -> bool:
        """加载数据
        
        Args:
            context: 回测参数对象，包含每次运行需要的参数
        """
        try:
            # 连接数据库
            db_path = os.path.join('db', 'market_data.db')
            conn = sqlite3.connect(db_path)
            
            # 如果没有指定日期范围，先获取数据的日期范围
            if context.start_date is None or context.end_date is None:
                date_query = """
                    SELECT MIN(date) as min_date, MAX(date) as max_date
                    FROM option_daily 
                    WHERE etf_code = ?
                """
                date_df = pd.read_sql_query(date_query, conn, params=(context.etf_code,))
                
                if date_df.empty:
                    raise ValueError(f"未找到{context.etf_code}的期权数据")
                    
                min_date = pd.to_datetime(date_df['min_date'].iloc[0])
                max_date = pd.to_datetime(date_df['max_date'].iloc[0])
                
                # 设置默认日期范围
                if context.start_date is None:
                    context.start_date = min_date
                if context.end_date is None:
                    context.end_date = max_date
                    
                # 验证日期范围
                if context.start_date < min_date:
                    raise ValueError(f"开始日期不能早于数据最早日期: {min_date.strftime('%Y-%m-%d')}")
                if context.end_date > max_date:
                    raise ValueError(f"结束日期不能晚于数据最晚日期: {max_date.strftime('%Y-%m-%d')}")
                if context.end_date < context.start_date:
                    raise ValueError("结束日期不能早于开始日期")
            
            # 确保 param.end_date 是 datetime 类型
            if isinstance(context.end_date, str):
                context.end_date = datetime.strptime(context.end_date, '%Y-%m-%d')

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
                    context.etf_code,
                    context.start_date.strftime('%Y-%m-%d'),
                    context.end_date.strftime('%Y-%m-%d')
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
            # self.option_data = self.option_data.set_index('日期')
            
            if self.option_data.empty:
                raise ValueError(
                    f"在指定日期范围内没有找到期权数据\n"
                    f"查询日期范围: {context.start_date.strftime('%Y-%m-%d')} 至 "
                    f"{context.end_date.strftime('%Y-%m-%d')}"
                )

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
                    context.etf_code,
                    context.start_date.strftime('%Y-%m-%d'),
                    context.end_date.strftime('%Y-%m-%d')
                )
            )
            
            # 转换日期列并设置为索引
            etf_data['date'] = pd.to_datetime(etf_data['date'])
            self.etf_data = etf_data.rename(columns={
                'date': '日期',
                'close_price': '收盘价',
                'open_price': '开盘价'
            })
            self.etf_data = self.etf_data.set_index('日期')
            
            if self.etf_data.empty:
                raise ValueError(
                    f"在指定日期范围内没有找到ETF数据\n"
                    f"查询日期范围: {context.start_date.strftime('%Y-%m-%d')} 至 "
                    f"{context.end_date.strftime('%Y-%m-%d')}"
                )
            
            conn.close()
            return True
            
        except Exception as e:
            import traceback
            print(f"加载数据时出错: {str(e)}")
            print("堆栈信息:")
            print(traceback.format_exc())
            return False

# def main():
#     """主函数"""
#     # 创建固定的回测配置
#     config = BacktestConfig()
    
#     # 创建回测引擎
#     engine = BacktestEngine(config)
    
#     # 创建回测参数（这里仅作示例，实际应该从前端获取）
#     param = BacktestParam(
#         start_date=datetime(2023, 1, 1),
#         end_date=datetime(2023, 12, 31),
#         etf_code='510300',  # 沪深300ETF
#         strategy_type=StrategyType.BEARISH_CALL,
#         strategy_params={
#             'call_sell_delta': 0.3,  # 卖出0.3 Delta的看涨期权
#             'call_buy_delta': 0.2    # 买入0.2 Delta的看涨期权
#         }
#     )
    
#     # 打印回测参数
#     print("\n=== 开始回测 ===")
#     print(f"标的: {param.etf_code}")
#     print(f"策略: {param.strategy_type.value}")
#     print(f"参数: {param.strategy_params}")
#     print(f"日期: {param.start_date.strftime('%Y-%m-%d')} 至 {param.end_date.strftime('%Y-%m-%d')}")
    
#     # 运行回测
#     results = engine.run_backtest(param)
    
#     if results:
#         print(f"\n=== 策略回测结果 ===")
#         print(f"策略类型: {results['strategy_type']}")
#         print(f"交易次数: {len(results['trades'])}")
        
#         if 'analysis' in results:
#             analysis = results['analysis']
#             print(f"累计收益率: {analysis.get('total_return', 0):.2f}%")
#             print(f"年化收益率: {analysis.get('annual_return', 0):.2f}%")
#             print(f"最大回撤: {analysis.get('max_drawdown', 0):.2f}%")
#             print(f"夏普比率: {analysis.get('sharpe_ratio', 0):.2f}")
            
#         if 'report' in results:
#             print("\n详细报告:")
#             print(results['report'])

# if __name__ == "__main__":
#     main() 