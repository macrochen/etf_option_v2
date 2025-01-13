import logging
from datetime import datetime
from typing import Dict, Any
import os

class TradeLogger:
    """交易日志记录器"""
    
    def __init__(self):
        """初始化日志记录器"""
        # 创建logs目录（如果不存在）
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # 设置日志文件名（使用当前时间）
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f'logs/backtest_{current_time}.log'
        
        # 配置日志记录器
        self.logger = logging.getLogger(f'backtest_{current_time}')
        self.logger.setLevel(logging.INFO)
        
        # 创建文件处理器
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
    def log_info(self, message: str):
        """记录信息日志"""
        self.logger.info(message)
        
    def log_error(self, message: str):
        """记录错误日志"""
        # 添加分隔线，使错误日志更醒目
        self.logger.error('-' * 80)
        self.logger.error(message)
        self.logger.error('-' * 80)
        
    def log_warning(self, message: str):
        """记录警告日志"""
        self.logger.warning(message)
        
    def log_debug(self, message: str):
        """记录调试日志"""
        self.logger.debug(message)
        
    def log_trade(self, date: datetime, action: str, details: Dict[str, Any]):
        """记录交易日志
        
        Args:
            date: 交易日期
            action: 交易动作
            details: 交易详情
        """
        message = f"[{date.strftime('%Y-%m-%d %H:%M:%S')}] {action}"
        if details:
            message += "\n" + "\n".join(f"    {k}: {v}" for k, v in details.items())
        self.logger.info(message)
        
    def log_daily_portfolio(self, date: datetime, portfolio_state: Dict[str, Any]):
        """记录每日投资组合状态
        
        Args:
            date: 日期
            portfolio_state: 投资组合状态
        """
        message = f"[{date.strftime('%Y-%m-%d')}] 投资组合状态:"
        for key, value in portfolio_state.items():
            if isinstance(value, float):
                message += f"\n    {key}: {value:.2f}"
            else:
                message += f"\n    {key}: {value}"
        self.logger.debug(message) 