from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any

class OptionType(Enum):
    """期权类型"""
    CALL = 'call'
    PUT = 'put'

class StrategyType(Enum):
    """策略类型"""
    BEARISH_CALL = 'bearish_call'  # 熊市看涨
    BULLISH_PUT = 'bullish_put'    # 牛市看跌
    IRON_CONDOR = 'iron_condor'    # 铁鹰

@dataclass
class PositionConfig:
    """持仓配置"""
    etf_code: str                # ETF代码
    sell_delta: float           # 卖出期权的目标Delta值
    buy_delta: float            # 买入期权的目标Delta值
    holding_type: str           # 持仓方式
    contract_multiplier: int    # 合约乘数
    margin_ratio: float        # 保证金比例
    stop_loss_ratio: float     # 止损比例

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