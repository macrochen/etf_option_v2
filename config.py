import os
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class BacktestConfig:
    """回测配置类"""
    
    etf_code: str                # ETF代码，如 '510050', '510500', '510300'
    delta: float = 0.5          # Delta值，默认为0.5
    initial_capital: float = 1000000  # 初始资金
    contract_multiplier: int = 10000  # 合约乘数
    transaction_cost: float = 3.6     # 每张合约交易成本
    risk_free_rate: float = 0.02      # 无风险利率
    start_date: pd.Timestamp = None   # 回测开始日期
    end_date: pd.Timestamp = None     # 回测结束日期
    holding_type: str = 'stock'       # 持仓方式，'stock'为正股持仓，'synthetic'为合成持仓
    db_path: str = 'market_data.db'   # SQLite数据库路径
    
    def __post_init__(self):
        """初始化后的验证"""
        # 验证ETF代码
        if not self.etf_code:
            raise ValueError("ETF代码不能为空")
        
        # 验证Delta值
        if not 0 <= self.delta <= 1:
            raise ValueError("Delta值必须在0到1之间")
        
        # 验证初始资金
        if self.initial_capital <= 0:
            raise ValueError("初始资金必须大于0")
        
        # 验证合约乘数
        if self.contract_multiplier <= 0:
            raise ValueError("合约乘数必须大于0")
        
        # 验证交易成本
        if self.transaction_cost < 0:
            raise ValueError("交易成本不能为负数")
        
        # 验证无风险利率
        if self.risk_free_rate < 0:
            raise ValueError("无风险利率不能为负数")
        
        # 验证持仓方式
        if self.holding_type not in ['stock', 'synthetic']:
            raise ValueError("持仓方式必须是'stock'或'synthetic'")
        
        # 验证数据库文件
        if not os.path.exists(self.db_path):
            raise ValueError(f"找不到数据库文件: {self.db_path}")
        
        # 验证日期
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期") 