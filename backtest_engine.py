from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime
from strategy_analyzer import StrategyAnalyzer
from logger import TradeLogger
from utils import get_trading_dates, get_next_monthly_expiry, get_monthly_expiry
from visualization import StrategyVisualizer
from backtest_params import BacktestConfig, StrategyType, BacktestParam
from strategies.factory import StrategyFactory
from strategies.types import PositionConfig, BacktestResult
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
        # 初始化 delta 参数
        sell_delta = buy_delta = None
        put_sell_delta = put_buy_delta = None
        call_sell_delta = call_buy_delta = None
        
        # 根据策略类型选择对应的 delta 参数
        if param.strategy_type == StrategyType.BEARISH_CALL:
            sell_delta = param.strategy_params.get('call_sell_delta')
            buy_delta = param.strategy_params.get('call_buy_delta')
        elif param.strategy_type == StrategyType.BULLISH_PUT:
            sell_delta = param.strategy_params.get('put_sell_delta')
            buy_delta = param.strategy_params.get('put_buy_delta')
        elif param.strategy_type == StrategyType.NAKED_PUT:
            sell_delta = param.strategy_params.get('put_sell_delta')
            buy_delta = None  # 单腿策略不需要买入 Delta
        elif param.strategy_type == StrategyType.IRON_CONDOR:
            # 铁鹰策略需要四个 delta 参数
            put_sell_delta = param.strategy_params.get('put_sell_delta')
            put_buy_delta = param.strategy_params.get('put_buy_delta')
            call_sell_delta = param.strategy_params.get('call_sell_delta')
            call_buy_delta = param.strategy_params.get('call_buy_delta')
        elif param.strategy_type == StrategyType.WHEEL:
            # 检查Wheel策略的Delta值
            put_sell_delta = param.strategy_params.get('put_sell_delta')
            call_sell_delta = param.strategy_params.get('call_sell_delta')
            
            # 检查PUT和CALL的Delta值
            if put_sell_delta != -0.5 or call_sell_delta != 0.5:
                self.logger.log_error(
                    f"Wheel策略的Delta值不正确: "
                    f"PUT卖出Delta必须为-0.5 (当前值: {put_sell_delta}), "
                    f"CALL卖出Delta必须为0.5 (当前值: {call_sell_delta})"
                )
                return None
                    
            # 确保没有设置买入Delta
            if 'put_buy_delta' in param.strategy_params or 'call_buy_delta' in param.strategy_params:
                self.logger.log_error("Wheel策略不应设置买入Delta值")
                return None
        else:
            self.logger.log_error(f"不支持的策略类型: {param.strategy_type}")
            return None
        
        
        
        # 创建持仓配置
        try:
            position_config = PositionConfig(
                etf_code=param.etf_code,
                # 传入统一的 delta 参数（用于非铁鹰策略）
                sell_delta=sell_delta,
                buy_delta=buy_delta,
                # 传入分开的 delta 参数（用于铁鹰策略）
                put_sell_delta=put_sell_delta,
                put_buy_delta=put_buy_delta,
                call_sell_delta=call_sell_delta,
                call_buy_delta=call_buy_delta,
                # 其他配置参数
                contract_multiplier=self.config.contract_multiplier,
                margin_ratio=self.config.margin_ratio,
                stop_loss_ratio=self.config.stop_loss_ratio,
                transaction_cost=self.config.transaction_cost,
                end_date=param.end_date
            )
            
            # 创建策略实例
            strategy = StrategyFactory.create_strategy(
                strategy_type=param.strategy_type,
                config=position_config,
                option_data=self.option_data,
                etf_data=self.etf_data
            )

            # 根据策略类型记录不同的日志信息
            if param.strategy_type == StrategyType.IRON_CONDOR:
                self.logger.log_debug(
                    f"创建策略成功:\n"
                    f"策略类型: {param.strategy_type.name}\n"
                    f"PUT价差: sell_delta={put_sell_delta}, buy_delta={put_buy_delta}\n"
                    f"CALL价差: sell_delta={call_sell_delta}, buy_delta={call_buy_delta}"
                )
            else:
                self.logger.log_debug(
                    f"创建策略成功:\n"
                    f"策略类型: {param.strategy_type.name}\n"
                    f"卖出Delta: {sell_delta}\n"
                    f"买入Delta: {buy_delta}"
                )

            return strategy

        except Exception as e:
            import traceback
            self.logger.log_error(
                f"策略创建失败:\n{str(e)}\n{traceback.format_exc()}"
            )
            return None

    def run_backtest(self, param: BacktestParam) -> Optional[BacktestResult]:
        """运行回测
        
        Args:
            param: 回测参数对象
            
        Returns:
            Optional[BacktestResult]: 回测结果对象，如果回测失败则返回None
        """
        try:
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
                param.etf_code,
                self.etf_data,
                analysis_results
            )
            
            # 返回回测结果
            return BacktestResult(
                    etf_code=param.etf_code,
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

    def load_data(self, param: BacktestParam) -> bool:
        """加载数据
        
        Args:
            param: 回测参数对象，包含每次运行需要的参数
        """
        try:
            # 连接数据库
            db_path = os.path.join('db', 'market_data.db')
            conn = sqlite3.connect(db_path)
            
            # 如果没有指定日期范围，先获取数据的日期范围
            if param.start_date is None or param.end_date is None:
                date_query = """
                    SELECT MIN(date) as min_date, MAX(date) as max_date
                    FROM option_daily 
                    WHERE etf_code = ?
                """
                date_df = pd.read_sql_query(date_query, conn, params=(param.etf_code,))
                
                if date_df.empty:
                    raise ValueError(f"未找到{param.etf_code}的期权数据")
                    
                min_date = pd.to_datetime(date_df['min_date'].iloc[0])
                max_date = pd.to_datetime(date_df['max_date'].iloc[0])
                
                # 设置默认日期范围
                if param.start_date is None:
                    param.start_date = min_date
                if param.end_date is None:
                    param.end_date = max_date
                    
                # 验证日期范围
                if param.start_date < min_date:
                    raise ValueError(f"开始日期不能早于数据最早日期: {min_date.strftime('%Y-%m-%d')}")
                if param.end_date > max_date:
                    raise ValueError(f"结束日期不能晚于数据最晚日期: {max_date.strftime('%Y-%m-%d')}")
                if param.end_date < param.start_date:
                    raise ValueError("结束日期不能早于开始日期")
            
            # 确保 param.end_date 是 datetime 类型
            if isinstance(param.end_date, str):
                param.end_date = datetime.strptime(param.end_date, '%Y-%m-%d')

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
            # self.option_data = self.option_data.set_index('日期')
            
            if self.option_data.empty:
                raise ValueError(
                    f"在指定日期范围内没有找到期权数据\n"
                    f"查询日期范围: {param.start_date.strftime('%Y-%m-%d')} 至 "
                    f"{param.end_date.strftime('%Y-%m-%d')}"
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
                    param.etf_code,
                    param.start_date.strftime('%Y-%m-%d'),
                    param.end_date.strftime('%Y-%m-%d')
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
                    f"查询日期范围: {param.start_date.strftime('%Y-%m-%d')} 至 "
                    f"{param.end_date.strftime('%Y-%m-%d')}"
                )
            
            conn.close()
            return True
            
        except Exception as e:
            import traceback
            print(f"加载数据时出错: {str(e)}")
            print("堆栈信息:")
            print(traceback.format_exc())
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