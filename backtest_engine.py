from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime
from portfolio_manager import PortfolioManager
from option_trader import OptionTrader
from strategy_analyzer import StrategyAnalyzer
from logger import TradeLogger
from utils import get_trading_dates, get_next_monthly_expiry, get_monthly_expiry
from visualization import StrategyVisualizer

class BacktestEngine:
    def __init__(self, config):
        """
        回测引擎
        
        Args:
            config: 回测配置对象
        """
        self.config = config
        self.option_data = None
        self.etf_data = None
        self.logger = TradeLogger()
        self.visualizer = StrategyVisualizer()
        
    def run_backtest(self) -> Optional[Dict[str, Any]]:
        """运行回测"""
        if not self.load_data():
            return None
            
        # 初始化组件
        portfolio_manager = PortfolioManager(
            initial_cash=self.config.initial_capital,
            contract_multiplier=self.config.contract_multiplier,
            transaction_cost_per_contract=self.config.transaction_cost
        )
        
        option_trader = OptionTrader(
            portfolio_manager=portfolio_manager,
            target_delta=self.config.delta,
            stop_loss_ratio=self.config.stop_loss_ratio
        )
        
        # 获取交易日期列表
        trading_dates = get_trading_dates(
            self.config.start_date or self.option_data['日期'].min(),
            self.config.end_date or self.option_data['日期'].max(),
            self.option_data
        )
        
        # 检查是否有有效的交易日期
        if not trading_dates:
            self.logger.log_error("没有找到有效的交易日期，请检查日期范围和数据文件")
            return None
        
        self.logger.log_trade(trading_dates[0], "回测开始", {
            "初始资金": self.config.initial_capital,
            "标的": self.config.symbol,
            "目标Delta": self.config.delta,
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
            option_trader.handle_option_expiry(current_date, self.etf_data, self.option_data)
            
            # 如果没有持仓，尝试开仓
            if not portfolio_manager.put_position:
                # 第一次开仓使用当月到期日，后续使用下月到期日
                if not portfolio_manager.trades:  # 如果没有交易记录，说明是第一次开仓
                    expiry = get_monthly_expiry(current_date, self.option_data)
                else:
                    expiry = get_next_monthly_expiry(current_date, self.option_data)
                    
                if expiry:
                    option_trader.sell_put(current_date, expiry, self.option_data, etf_price)
            
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
                                   self.config.initial_capital - 1
            })
        
        # 分析策略结果
        analysis_results = StrategyAnalyzer.calculate_metrics(
            portfolio_manager.portfolio_values,
            portfolio_manager.trades,
            self.config.initial_capital,
            self.etf_data
        )
        
        # 生成策略报告
        report = StrategyAnalyzer.generate_report(analysis_results)
        
        # 生成策略对比数据
        comparison_data = StrategyAnalyzer.generate_comparison_table(analysis_results)
        
        self.logger.log_trade(trading_dates[-1], "回测结束", {
            "报告": report
        })
        
        # 生成可视化图表
        performance_plot = self.visualizer.create_performance_plot(
            portfolio_manager.portfolio_values,
            portfolio_manager.put_trades,
            self.config.symbol
        )
        
        drawdown_plot = self.visualizer.create_drawdown_plot(
            portfolio_manager.portfolio_values,
            analysis_results['portfolio_metrics']['max_drawdown_start'],
            analysis_results['portfolio_metrics']['max_drawdown_end']
        )
        
        pnl_distribution = self.visualizer.create_pnl_distribution_plot(
            analysis_results['portfolio_metrics']['daily_returns']
        )
        
        # 返回回测结果
        return {
            "symbol": self.config.symbol,
            "portfolio_values": portfolio_manager.portfolio_values,
            "trades": portfolio_manager.trades,
            "statistics": portfolio_manager.statistics,
            "analysis": analysis_results,
            "report": report,
            "plots": {
                "performance": performance_plot,
                "drawdown": drawdown_plot,
                "pnl_distribution": pnl_distribution
            }
        }

    def load_data(self) -> bool:
        """加载数据"""
        self.logger.log_trade(datetime.now(), "开始加载数据", {
            "期权文件数量": len(self.config.option_file_paths),
            "ETF文件": self.config.etf_file_path
        })
        
        try:
            # 加载期权数据
            option_data_list = []
            for file_path in self.config.option_file_paths:
                df = pd.read_excel(file_path)
                df = df[~df['日期'].astype(str).str.contains('数据来源')]
                df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
                df = df.dropna(subset=['日期'])
                option_data_list.append(df)
            
            self.option_data = pd.concat(option_data_list, ignore_index=True)
            self.option_data = self.option_data.sort_values('日期')
            
            # 加载ETF数据
            self.etf_data = pd.read_csv(self.config.etf_file_path)
            self.etf_data['日期'] = pd.to_datetime(self.etf_data['日期'])
            self.etf_data = self.etf_data.set_index('日期').sort_index()
            
            # 根据日期范围过滤数据
            if self.config.start_date:
                self.option_data = self.option_data[self.option_data['日期'] >= self.config.start_date]
                self.etf_data = self.etf_data[self.etf_data.index >= self.config.start_date]
            
            if self.config.end_date:
                self.option_data = self.option_data[self.option_data['日期'] <= self.config.end_date]
                self.etf_data = self.etf_data[self.etf_data.index <= self.config.end_date]
            
            self.logger.log_trade(datetime.now(), "数据加载完成", {
                "期权数据行数": len(self.option_data),
                "ETF数据行数": len(self.etf_data),
                "数据日期范围": f"{self.option_data['日期'].min()} 至 {self.option_data['日期'].max()}"
            })
            
            return True
            
        except Exception as e:
            self.logger.log_error(f"数据加载失败: {str(e)}")
            return False 