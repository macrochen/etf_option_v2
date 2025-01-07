from datetime import datetime
from dataclasses import dataclass
from typing import Dict
from strategies.types import StrategyType

@dataclass
class BacktestConfig:
    """固定的回测配置信息"""
    initial_capital: float = 1000000  # 初始资金100万
    contract_multiplier: int = 10000  # 合约乘数
    transaction_cost: float = 5.0     # 每张合约交易成本
    margin_ratio: float = 0.12        # 保证金比例
    stop_loss_ratio: float = 0.5      # 止损比例

@dataclass
class BacktestParam:
    """回测参数，对应前端输入"""
    start_date: datetime              # 回测开始日期
    end_date: datetime                # 回测结束日期
    etf_code: str                     # ETF代码
    strategy_type: StrategyType       # 策略类型
    strategy_params: Dict             # 策略特定参数，如 delta 值等 