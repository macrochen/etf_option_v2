from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from typing import Dict, Any, Optional, List

class OptionType(Enum):
    """期权类型"""
    CALL = 'call'
    PUT = 'put'

class StrategyType(str, Enum):
    """策略类型枚举"""
    BULLISH_PUT = 'bullish_put'      # 牛市看跌
    BEARISH_CALL = 'bearish_call'    # 熊市看涨
    IRON_CONDOR = 'iron_condor'      # 铁鹰
    NAKED_PUT = 'naked_put'          # 单腿卖出看跌
    WHEEL = "wheel"                  # 轮式策略
    VOLATILITY_BULLISH_PUT = "volatility_bullish_put"        # 波动率策略
    VOLATILITY_BEARISH_CALL = "volatility_bearish_call"        # 波动率策略

@dataclass
class OptionPosition:
    """期权持仓"""
    contract_code: str          # 合约代码
    option_type: OptionType     # 期权类型
    expiry: datetime           # 到期日
    strike: float              # 行权价
    delta: float               # Delta值
    quantity: int              # 持仓数量（正数为买入，负数为卖出）
    open_price: float          # 开仓价格
    open_date: datetime        # 开仓日期
    contract_multiplier: int    # 合约乘数
    premium: float             # 权利金（正数表示收取，负数表示支付，已考虑合约乘数）
    open_cost: float             # 开仓成本（佣金+交易费）
    close_cost: float             # 平仓成本（佣金+交易费）

    def __init__(self, contract_code: str, option_type: OptionType, 
                 expiry: datetime, strike: float, delta: float,
                 quantity: int, open_price: float, open_date: datetime,
                 contract_multiplier: int, transaction_cost:float):
        self.contract_code = contract_code
        self.option_type = option_type
        self.expiry = expiry
        self.strike = strike
        self.delta = delta
        self.quantity = quantity # 买入期权(quantity > 0), 卖出期权(quantity < 0) 没有真正的收到，是负债，所以为负
        self.open_price = open_price
        self.open_date = open_date
        self.contract_multiplier = contract_multiplier
        # 计算权利金：
        # - 买入期权(quantity > 0)：收取权利金，所以是正数
        # - 卖出期权(quantity < 0)：支付权利金，所以是负数 和 quantity 逻辑是反的
        self.premium = open_price * -quantity * contract_multiplier
        # 卖出开仓不收费
        self.open_cost = 0 if quantity < 0 else transaction_cost * quantity
        # 平仓不管是 buy 还是 sell 都要收费
        self.close_cost = transaction_cost * abs(quantity)

    def __str__(self) -> str:
        """返回持仓的字符串表示"""
        action = "买入" if self.quantity > 0 else "卖出"
        option_type = "看涨" if self.option_type == OptionType.CALL else "看跌"
        return (
            f"{action}{option_type}期权持仓(\n"
            f"  合约代码: {self.contract_code}\n"
            f"  到期日: {self.expiry.strftime('%Y-%m-%d')}\n"
            f"  行权价: {self.strike:.4f}\n"
            f"  Delta: {self.delta:.4f}\n"
            f"  数量: {abs(self.quantity)}\n"
            f"  开仓价格: {self.open_price:.4f}\n"
            f"  开仓日期: {self.open_date.strftime('%Y-%m-%d')}\n"
            f"  合约乘数: {self.contract_multiplier}\n"
            f"  总权利金: {self.premium:.4f}\n"
            f")"
        )

@dataclass
class TradeRecord:
    """交易记录"""
    date: datetime  # 交易日期
    action: str  # 交易类型
    etf_price: float  # ETF价格
    strike: float  # 行权价
    price: float  # 期权价格
    quantity: int  # 合约数量
    premium: float  # 权利金
    cost: float  # 交易成本
    delta: float  # Delta值
    pnl: Optional[float]  # 实现盈亏
    total_pnl: Optional[float] = None  # 总盈亏（仅在最后一条记录中）
    total_cost: Optional[float] = None  # 总成本（仅在最后一条记录中）

    def to_list(self) -> List[str]:
        """转换为列表格式，用于前端展示"""
        return [
            self.date.strftime('%Y-%m-%d'),
            self.action,
            f"{self.etf_price:.4f}",
            f"{self.strike:.4f}",
            f"{self.price:.4f}",
            f"{self.quantity}张",
            f"{abs(self.premium):.4f}",
            f"{self.cost:.2f}",
            f"{self.delta:.3f}",
            f"{self.pnl:.2f}" if self.pnl is not None else "0.00"
        ] 

@dataclass
class TradeResult:
    """交易结果"""
    records: List[TradeRecord]  # 交易记录列表
    etf_price: float           # ETF价格
    total_pnl: float          # 总盈亏
    total_cost: float         # 总成本

@dataclass
class PortfolioValue:
    """投资组合每日价值"""
    cash: float  # 现金
    option_value: float  # 期权市值
    total_value: float  # 总市值
    daily_return: float  # 日收益率（百分比）

    @property
    def formatted_daily_return(self) -> str:
        """格式化的日收益率，带颜色标记"""
        if self.daily_return > 0:
            return f'<span style="color: #4CAF50">{self.daily_return:.2f}%</span>'
        elif self.daily_return < 0:
            return f'<span style="color: #F44336">{self.daily_return:.2f}%</span>'
        else:
            return f'{self.daily_return:.2f}%' 

@dataclass
class BacktestResult:
    """回测结果"""
    etf_code: str  # ETF代码
    strategy_type: str  # 策略类型
    trades: Dict[datetime, list]  # 交易记录
    portfolio_values: Dict[datetime, PortfolioValue]  # 每日投资组合价值
    analysis: Dict[str, Any]  # 分析结果
    report: str  # 报告
    plots: Dict[str, Any]  # 图表数据

    @property
    def has_trades(self) -> bool:
        """是否有交易记录"""
        return bool(self.trades)

    @property
    def trade_count(self) -> int:
        """交易次数"""
        return sum(len(trades) for trades in self.trades.values()) 

@dataclass
class PriceConditions:
    """期权价差平仓的价格条件"""
    expire_below: Optional[float] = None  # 低于此价格时作废
    expire_above: Optional[float] = None  # 高于此价格时作废
    partial_below: Optional[float] = None  # 低于此价格时部分平仓
    partial_above: Optional[float] = None  # 高于此价格时部分平仓
    
    def validate(self) -> bool:
        """验证价格条件是否有效"""
        # 检查必要的价格条件是否都存在
        if any(x is None for x in [
            self.expire_below, 
            self.expire_above,
            self.partial_below,
            self.partial_above
        ]):
            return False
            
        # 检查价格区间的合理性
        if not (self.expire_below <= self.partial_below <= 
                self.partial_above <= self.expire_above):
            return False
            
        return True 