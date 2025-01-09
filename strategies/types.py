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

@dataclass
class PositionConfig:
    """持仓配置"""
    def __init__(self,
                 etf_code: str,
                 sell_delta: float,
                 buy_delta: float,
                 contract_multiplier: int,
                 margin_ratio: float,
                 stop_loss_ratio: float,
                 transaction_cost: float,
                 end_date: Optional[datetime] = None):
        self.etf_code = etf_code
        self.sell_delta = sell_delta
        self.buy_delta = buy_delta
        self.contract_multiplier = contract_multiplier
        self.margin_ratio = margin_ratio
        self.stop_loss_ratio = stop_loss_ratio
        self.transaction_cost = transaction_cost
        self.end_date = end_date

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