from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class OptionPosition:
    """期权持仓数据模型"""
    expiry: datetime          # 到期日
    strike: float            # 行权价
    premium: float          # 期权费
    num_contracts: int      # 合约数量
    trade_code: str         # 交易代码
    initial_cash: float     # 建仓时的现金
    margin: float = 0.0     # 占用保证金
    open_date: Optional[datetime] = None  # 开仓日期
    
    def __post_init__(self):
        """数据验证"""
        if self.num_contracts <= 0:
            raise ValueError("合约数量必须大于0")
        if self.strike <= 0:
            raise ValueError("行权价必须大于0")
        if self.premium <= 0:
            raise ValueError("期权费必须大于0")
        if self.margin < 0:
            raise ValueError("保证金不能为负")

@dataclass
class TradeRecord:
    """交易记录数据模型"""
    date: datetime          # 交易日期
    trade_type: str        # 交易类型（卖出PUT/平仓）
    price: float           # 交易价格
    num_contracts: int     # 交易数量
    premium: float         # 期权费
    cost: float           # 交易成本
    pnl: float = 0.0      # 交易盈亏
    
    def __post_init__(self):
        """数据验证"""
        if self.num_contracts <= 0:
            raise ValueError("交易数量必须大于0")
        if self.price <= 0:
            raise ValueError("交易价格必须大于0")
        if self.cost < 0:
            raise ValueError("交易成本不能为负")

@dataclass
class DailyPortfolio:
    """每日投资组合状态"""
    date: datetime         # 日期
    cash: float           # 现金
    option_value: float   # 期权市值
    total_value: float    # 总市值
    daily_return: float   # 日收益率
    unrealized_pnl: float # 未实现盈亏
    margin_occupied: float # 占用保证金
    initial_value: float  # 添加初始值属性
    
    def __post_init__(self):
        """数据验证"""
        if self.total_value <= 0:
            raise ValueError("总市值必须大于0")
        if self.cash < 0:
            raise ValueError("现金不能为负")
        if self.margin_occupied < 0:
            raise ValueError("占用保证金不能为负") 
    
    @property
    def cumulative_return(self) -> float:
        """计算累计收益率（百分比）"""
        return (self.total_value / self.initial_value - 1) * 100 