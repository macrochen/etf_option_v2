import os
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class BacktestConfig:
    """回测配置"""
    etf_code: str                    # ETF代码
    start_date: Optional[datetime]   # 开始日期
    end_date: Optional[datetime]     # 结束日期
    holding_type: str               # 持仓方式
    initial_capital: float = 1000000  # 初始资金
    contract_multiplier: int = 10000  # 合约乘数
    transaction_cost: float = 5.0    # 每张合约交易成本
    db_path: str = 'market_data.db'  # 数据库路径
    
    # 策略参数
    call_sell_delta: Optional[float] = None  # 卖出看涨期权的Delta
    call_buy_delta: Optional[float] = None   # 买入看涨期权的Delta
    put_sell_delta: Optional[float] = None   # 卖出看跌期权的Delta
    put_buy_delta: Optional[float] = None    # 买入看跌期权的Delta
    
    def __post_init__(self):
        """验证参数"""
        self._validate_strategy_params()
        
    def _validate_strategy_params(self):
        """验证策略参数的合法性"""
        # 检查是否至少有一组完整的策略参数
        has_call = (self.call_sell_delta is not None and self.call_buy_delta is not None)
        has_put = (self.put_sell_delta is not None and self.put_buy_delta is not None)
        
        if not (has_call or has_put):
            raise ValueError("至少需要一组完整的策略参数（看涨或看跌）")
            
        # 验证看涨策略参数
        if has_call:
            if not (0 < self.call_buy_delta < self.call_sell_delta < 1):
                raise ValueError("看涨策略的Delta值必须满足: 0 < 买入Delta < 卖出Delta < 1")
                
        # 验证看跌策略参数
        if has_put:
            if not (-1 < self.put_sell_delta < self.put_buy_delta < 0):
                raise ValueError("看跌策略的Delta值必须满足: -1 < 卖出Delta < 买入Delta < 0") 