from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime

class StrategyMode(Enum):
    ACCUMULATE = "Accumulate"  # 潜伏积累 (估值 < 20%)
    NEUTRAL = "Neutral"        # 标准震荡 (20% <= 估值 <= 70%)
    TREND = "Trend"            # 趋势/防卖飞 (估值 > 70%)

@dataclass
class GridContext:
    """网格交易上下文配置"""
    symbol: str
    current_price: float
    total_capital: float
    base_position_ratio: float  # 底仓比例 (0.0 - 1.0)
    # 基本面参数 (人工录入)
    pe_percentile: float        # 0-100
    pb_percentile: float        # 0-100
    
    cash_reserve_ratio: float = 0.0 # 预留现金比例 (0.0 - 1.0)
    
    # 高级配置
    atr_period: int = 14
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    min_grid_count: int = 10
    
    # 强制覆盖模式 (Optional)
    force_mode: Optional[StrategyMode] = None

@dataclass
class GridLine:
    """单条网格线定义"""
    price: float
    buy_vol: int
    sell_vol: int
    is_base_position: bool = False # 是否为底仓

@dataclass
class StrategyResult:
    """策略生成结果"""
    symbol: str
    mode: StrategyMode
    
    # 核心参数
    price_min: float
    price_max: float
    step_price: float    # 绝对值步长
    step_percent: float  # 百分比步长 (相对于当前价)
    grid_count: int
    
    # 资金分配
    cash_per_grid: float
    vol_per_grid: int
    
    # 网格表
    grid_lines: List[GridLine]
    
    # 波动率评分
    beta: float = 0.0
    amplitude: float = 0.0
    volatility_score: float = 0.0
    
    # 描述信息
    description: str = ""

@dataclass
class TradeRecord:
    """回测交易记录"""
    date: str  # YYYY-MM-DD
    type: str  # 'BUY' or 'SELL'
    price: float
    volume: int
    amount: float
    fee: float = 0.0
    # 资产状态快照
    current_position: int = 0
    position_value: float = 0.0
    cash: float = 0.0
    total_value: float = 0.0

@dataclass
class BacktestResult:
    """回测结果"""
    total_return: float         # 总收益率
    annualized_return: float    # 年化收益率
    grid_profit: float          # 网格利润 (已实现)
    float_pnl: float           # 浮动盈亏 (持仓市值变动)
    
    trade_count: int            # 总成交单数
    daily_trade_count: float    # 日均成交
    
    win_rate: float             # 胜率 (网格通常不适用，可作为参考)
    max_drawdown: float         # 最大回撤
    break_rate: float           # 破网率
    
    trades: List[TradeRecord]
    daily_equity: List[Dict]    # 每日权益曲线 [{'date':.., 'equity':.., 'benchmark':..}]
    
    capital_utilization: float = 0.0 # 资金利用率
    buy_count: int = 0          # 买入次数
    sell_count: int = 0         # 卖出次数
    missed_trades: int = 0      # 无效触网次数
    sharpe_ratio: float = 0.0   # 夏普比率
    
    # 基准 (Buy & Hold) 指标
    benchmark_total_return: float = 0.0
    benchmark_annualized_return: float = 0.0
    benchmark_max_drawdown: float = 0.0
    benchmark_sharpe_ratio: float = 0.0
