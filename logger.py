import logging
from datetime import datetime
from typing import Dict, Any
import sys

class TradeLogger:
    def __init__(self, name: str = "option_strategy", log_file: str = None):
        """
        初始化日志记录器
        
        Args:
            name: 日志记录器名称
            log_file: 日志文件路径，如果为None则只输出到控制台
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.WARNING)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 添加控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.WARNING)
        self.logger.addHandler(console_handler)
        
        # 如果指定了日志文件，添加文件处理器
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.WARNING)
            self.logger.addHandler(file_handler)

    def log_daily_portfolio(self, date: datetime, portfolio_data: Dict[str, float]) -> None:
        """记录每日投资组合状态"""
        self.logger.info(f"\n[{date.strftime('%Y-%m-%d')}期权策略盈亏] ")
        self.logger.info(f"现金: {portfolio_data['cash']:.2f}")
        self.logger.info(f"保证金: {portfolio_data['margin']:.2f}")
        self.logger.info(f"持仓数量: {portfolio_data['positions']}")
        self.logger.info(f"总市值: {portfolio_data['portfolio_value']:.2f}")

    def log_trade(self, date: datetime, trade_type: str, trade_details: Dict[str, Any]) -> None:
        """记录交易信息"""
        self.logger.info(f"\n[{date.strftime('%Y-%m-%d')} {trade_type}]")
        for key, value in trade_details.items():
            if isinstance(value, float):
                self.logger.info(f"{key}: {value:.4f}")
            else:
                self.logger.info(f"{key}: {value}")

    def log_option_expiry(self, date: datetime, expiry_type: str, expiry_details: Dict[str, Any]) -> None:
        """记录期权到期信息"""
        self.logger.info(f"\n[{date.strftime('%Y-%m-%d')} {expiry_type}]")
        for key, value in expiry_details.items():
            self.logger.info(f"{key}: {value}")

    def log_error(self, message: str) -> None:
        """记录错误信息"""
        self.logger.error(f"\n[错误] {message}")

    def log_warning(self, message: str) -> None:
        """记录警告信息"""
        self.logger.warning(f"\n[警告] {message}")

    def log_strategy_summary(self, summary_data: Dict[str, Any]) -> None:
        """记录策略汇总信息"""
        self.logger.info("\n=== 策略执行汇总 ===")
        self.logger.info("\nPUT期权交易:")
        self.logger.info(f"  总卖出次数: {summary_data['put_sold']}")
        self.logger.info(f"  平仓次数: {summary_data['put_closed']}")
        self.logger.info(f"  到期作废次数: {summary_data['put_expired']}")
        self.logger.info(f"  总收取权利金: {summary_data['total_put_premium']:.2f}")
        self.logger.info(f"  总平仓成本: {summary_data['total_close_cost']:.2f}")
        
        self.logger.info("\n收益统计:")
        self.logger.info(f"  总交易成本: {summary_data['total_transaction_cost']:.2f}")
        self.logger.info(f"  最大单笔亏损: {summary_data['max_loss_trade']:.2f}")
        self.logger.info(f"  总实现盈亏: {summary_data['total_realized_pnl']:.2f}")
        self.logger.info(f"  最低现金持仓: {summary_data['min_cash_position']:.2f}")

    def log_margin_warning(self, date: datetime, current_margin: float, 
                          total_value: float, margin_ratio: float) -> None:
        """记录保证金警告"""
        self.logger.warning(f"\n[{date.strftime('%Y-%m-%d')} 保证金警告]")
        self.logger.warning(f"当前保证金: {current_margin:.2f}")
        self.logger.warning(f"总市值: {total_value:.2f}")
        self.logger.warning(f"保证金占用比例: {margin_ratio:.2%}") 