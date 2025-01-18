from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional
import traceback
import logging
from strategies.types import StrategyType

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('../backtest.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """固定的回测配置信息"""
    initial_capital: float = 1000000  # 初始资金100万
    contract_multiplier: int = 10000  # 合约乘数
    transaction_cost: float = 3.6  # 每张合约交易成本
    margin_ratio: float = 0.12  # 保证金比例
    stop_loss_ratio: float = 0.5  # 止损比例


@dataclass
class BaseStrategyContext:
    """基础回测参数类"""
    etf_code: Optional[str] = ''  # ETF代码（必需）
    strategy_type: Optional[StrategyType] = None # 这里可以使用 StrategyType
    start_date: Optional[datetime] = None  # 回测开始日期（可选）
    end_date: Optional[datetime] = None  # 回测结束日期（可选）
    
    def validate(self):
        """验证基础参数的有效性"""
        if not self.etf_code:
            raise ValueError("ETF代码不能为空")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")


@dataclass
class StrategyContext(BaseStrategyContext):
    strategy_params: Dict = field(default_factory=dict)  # 策略特定参数，如 delta 值等
    contract_multiplier: int = BacktestConfig.contract_multiplier # 合约乘数
    transaction_cost: float = BacktestConfig.transaction_cost  # 交易成本
    sell_put_value: float = 0
    buy_put_value: float = 0
    sell_call_value: float = 0
    buy_call_value: float = 0

    def __post_init__(self):
        """dataclass 初始化后的处理"""
        try:
            logger.debug("开始初始化回测参数，原始数据: %s", self.__dict__)

            # 如果传入的是字典，需要先提取参数
            if isinstance(self.etf_code, dict):
                params = self.etf_code  # 实际上传入的是整个参数字典
                self.strategy_params = params.get('strategy_params', {})
                self.etf_code = params.get('etf_code', '')

                # 基础参数验证
                self._validate_basic_params(params)

            else:
                # 如果是单独的参数，直接验证
                self._validate_basic_params(self.__dict__)

            logger.debug("参数初始化完成: %s", self.__dict__)

        except Exception as e:
            logger.error("参数验证失败: %s", str(e))
            logger.error("错误堆栈:\n%s", traceback.format_exc())
            logger.error("输入参数: %s", self.__dict__)
            raise ValueError(f"参数验证失败: {str(e)}")

    def _validate_basic_params(self, params: Dict):
        """验证基本参数
        
        Args:
            params: 包含回测参数的字典
            
        Raises:
            ValueError: 当参数验证失败时抛出
        """
        try:
            # 验证ETF代码
            if 'etf_code' not in params:
                raise ValueError("缺少ETF代码参数")
            self.etf_code = params['etf_code']

            # 验证日期逻辑
            if self.start_date and self.end_date and self.start_date >= self.end_date:
                raise ValueError("结束日期必须晚于开始日期")

            # 验证策略参数存在性
            if 'strategy_params' not in params:
                raise ValueError("缺少策略参数")

            # 记录日志
            logger.debug("基本参数验证通过: %s", {
                'etf_code': self.etf_code,
                'start_date': self.start_date,
                'end_date': self.end_date,
                'strategy_params': params.get('strategy_params')
            })

        except Exception as e:
            logger.error("基本参数验证失败: %s", str(e))
            logger.error("输入参数: %s", params)
            logger.error("错误堆栈:\n%s", traceback.format_exc())
            raise ValueError(f"基本参数验证失败: {str(e)}")

    def to_dict(self, strategy_params):
        # 返回可序列化的字典
        return {
            'etf_code': self.etf_code,
            'start_date': self.start_date.strftime('%Y-%m-%d'),  # 格式化为只包含日期
            'end_date': self.end_date.strftime('%Y-%m-%d'),  # 格式化为只包含日期
            'strategy_params': self.strategy_params if strategy_params is None else strategy_params
        }


class DeltaIronCondorStrategyContext(StrategyContext):
    def __init__(self, strategy_type,
                 buy_call_delta: float, sell_call_delta: float,
                 buy_put_delta: float, sell_put_delta: float,
                 **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.buy_call_value = buy_call_delta
        self.sell_call_value = sell_call_delta
        self.buy_put_value = buy_put_delta
        self.sell_put_value = sell_put_delta

class DeltaBearishCallStrategyContext(StrategyContext):
    def __init__(self, strategy_type, buy_call_delta: float, sell_call_delta: float, **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.buy_call_value = buy_call_delta
        self.sell_call_value = sell_call_delta

class DeltaBullishPutStrategyContext(StrategyContext):
    def __init__(self, strategy_type, sell_put_delta: float, buy_put_delta: float, **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.sell_put_value = sell_put_delta
        self.buy_put_value = buy_put_delta

class DeltaNakedPutStrategyContext(StrategyContext):
    def __init__(self, strategy_type, sell_put_delta: float, **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.sell_put_value = sell_put_delta

class VolatilityIronCondorStrategyContext(StrategyContext):
    def __init__(self, strategy_type, buy_call_volatility: float, sell_call_volatility: float, buy_put_volatility: float, sell_put_volatility: float, **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.buy_call_value = buy_call_volatility
        self.sell_call_value = sell_call_volatility
        self.buy_put_value = buy_put_volatility
        self.sell_put_value = sell_put_volatility

class VolatilityBearishCallStrategyContext(StrategyContext):
    def __init__(self, strategy_type, buy_call_volatility: float, sell_call_volatility: float, **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.buy_call_value = buy_call_volatility
        self.sell_call_value = sell_call_volatility


class VolatilityBullishPutStrategyContext(StrategyContext):
    def __init__(self, strategy_type, sell_put_volatility: float, buy_put_volatility: float, **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.sell_put_value = sell_put_volatility
        self.buy_put_value = buy_put_volatility


class VolatilityNakedPutStrategyContext(StrategyContext):
    def __init__(self, strategy_type, sell_put_volatility: float, **kwargs):
        super().__init__(**kwargs)
        self.strategy_type = strategy_type
        self.sell_put_volatility = sell_put_volatility



class StrategyContextFactory:

    @staticmethod
    def create_context(data: Dict) -> StrategyContext:
        """根据前端数据生成相应的回测参数"""
        etf_code = data.get('etf_code', '')
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d') if 'start_date' in data else None
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d') if 'end_date' in data else None

        sp = data['strategy_params']
        # 确定策略类型
        strategy_type = None
        if 'call_buy_delta' in sp and 'call_sell_delta' in sp and 'put_buy_delta' in sp and 'put_sell_delta' in sp:
            from strategies.types import StrategyType
            strategy_type = StrategyType.IRON_CONDOR
            return DeltaIronCondorStrategyContext(strategy_type=strategy_type,
                                                  buy_call_delta=sp['call_buy_delta'],
                                                  sell_call_delta=sp['call_sell_delta'],
                                                  buy_put_delta=sp['put_buy_delta'],
                                                  sell_put_delta=sp['put_sell_delta'],
                                                  etf_code=etf_code,
                                                  start_date=start_date,
                                                  end_date=end_date)

        elif 'call_buy_delta' in sp and 'call_sell_delta' in sp:

            from strategies.types import StrategyType

            strategy_type = StrategyType.BEARISH_CALL

            return DeltaBearishCallStrategyContext(strategy_type=strategy_type,
                                                   buy_call_delta=sp['call_buy_delta'],
                                                   sell_call_delta=sp['call_sell_delta'],
                                                   etf_code=etf_code,

                                                   start_date=start_date,

                                                   end_date=end_date)

        elif 'put_sell_delta' in sp and 'put_buy_delta' in sp:
            from strategies.types import StrategyType
            strategy_type = StrategyType.BULLISH_PUT
            return DeltaBullishPutStrategyContext(strategy_type=strategy_type,
                                                 sell_put_delta=sp['put_sell_delta'],
                                                 buy_put_delta=sp['put_buy_delta'],
                                                 etf_code=etf_code,
                                                 start_date=start_date,
                                                 end_date=end_date)
        elif 'put_sell_delta' in sp and 'put_buy_delta' not in sp:
            from strategies.types import StrategyType
            strategy_type = StrategyType.NAKED_PUT
            return DeltaNakedPutStrategyContext(strategy_type=strategy_type,
                                                 sell_put_delta=sp['put_sell_delta'],
                                                 etf_code=etf_code,
                                                 start_date=start_date,
                                                 end_date=end_date)
        elif 'call_buy_volatility' in sp and 'call_sell_volatility' in sp and 'put_sell_volatility' in sp and 'put_buy_volatility' in sp:
            from strategies.types import StrategyType
            strategy_type = StrategyType.VOLATILITY_IRON_CONDOR
            return VolatilityIronCondorStrategyContext(strategy_type=strategy_type,
                                                        buy_call_volatility=sp['call_buy_volatility'],
                                                        sell_call_volatility=sp['call_sell_volatility'],
                                                       sell_put_volatility=sp['put_sell_volatility'],
                                                       buy_put_volatility=sp['put_buy_volatility'],
                                                        etf_code=etf_code,
                                                        start_date=start_date,
                                                        end_date=end_date)
        elif 'call_buy_volatility' in sp and 'call_sell_volatility' in sp:
            from strategies.types import StrategyType
            strategy_type = StrategyType.VOLATILITY_BEARISH_CALL
            return VolatilityBearishCallStrategyContext(strategy_type=strategy_type,
                                                        buy_call_volatility=sp['call_buy_volatility'],
                                                        sell_call_volatility=sp['call_sell_volatility'],
                                                        etf_code=etf_code,
                                                        start_date=start_date,
                                                        end_date=end_date)
        elif 'put_sell_volatility' in sp and 'put_buy_volatility' in sp:
            from strategies.types import StrategyType
            strategy_type = StrategyType.VOLATILITY_BULLISH_PUT
            return VolatilityBullishPutStrategyContext(strategy_type=strategy_type,
                                                       sell_put_volatility=sp['put_sell_volatility'],
                                                       buy_put_volatility=sp['put_buy_volatility'],
                                                       etf_code=etf_code,
                                                       start_date=start_date,
                                                       end_date=end_date)

        elif 'put_sell_volatility' in sp and 'put_buy_volatility' not in sp:
            from strategies.types import StrategyType
            strategy_type = StrategyType.VOLATILITY_BULLISH_PUT
            return VolatilityNakedPutStrategyContext(strategy_type=strategy_type,
                                                     sell_put_volatility=sp['put_sell_volatility'],
                                                     etf_code=etf_code,
                                                     start_date=start_date,
                                                     end_date=end_date)

        # 添加其他策略类型的判断逻辑...

        if strategy_type is None:
            raise ValueError("无法确定策略类型")

        return None
