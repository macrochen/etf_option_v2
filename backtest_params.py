from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional
from strategies.types import StrategyType
import traceback
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('backtest.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@dataclass
class BacktestConfig:
    """固定的回测配置信息"""
    initial_capital: float = 1000000  # 初始资金100万
    contract_multiplier: int = 10000  # 合约乘数
    transaction_cost: float = 3.6     # 每张合约交易成本
    margin_ratio: float = 0.12        # 保证金比例
    stop_loss_ratio: float = 0.5      # 止损比例

@dataclass
class BacktestParam:
    """回测参数，对应前端输入"""
    etf_code: str = ''                # ETF代码（必需）
    strategy_type: Optional[StrategyType] = None  # 策略类型（根据参数自动判断）
    strategy_params: Dict = field(default_factory=dict)  # 策略特定参数，如 delta 值等
    start_date: Optional[datetime] = None  # 回测开始日期（可选）
    end_date: Optional[datetime] = None    # 回测结束日期（可选）

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
                
                # 策略类型验证
                self.strategy_type = self._validate_strategy_type(params.get('strategy_type'))
                
                # 根据策略类型验证参数
                self.strategy_params = self._validate_strategy_params(
                    self.strategy_type,
                    self.strategy_params
                )
            else:
                # 如果是单独的参数，直接验证
                self._validate_basic_params(self.__dict__)
                self.strategy_type = self._validate_strategy_type(self.strategy_type)
                self.strategy_params = self._validate_strategy_params(
                    self.strategy_type,
                    self.strategy_params
                )
            
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
            
            # 验证日期格式（如果提供）
            if 'start_date' in params and params['start_date']:
                try:
                    self.start_date = datetime.strptime(params['start_date'], '%Y-%m-%d')
                except ValueError:
                    raise ValueError("开始日期格式无效，应为YYYY-MM-DD")
                    
            if 'end_date' in params and params['end_date']:
                try:
                    self.end_date = datetime.strptime(params['end_date'], '%Y-%m-%d')
                except ValueError:
                    raise ValueError("结束日期格式无效，应为YYYY-MM-DD")
            
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

    def _validate_delta_values(self):
        """验证Delta值的有效性"""
        # 验证PUT策略的Delta值
        if self.put_sell_delta is not None:
            try:
                self.put_sell_delta = float(self.put_sell_delta)
                if not (-1 < self.put_sell_delta < 0):
                    raise ValueError("PUT Delta值必须在-1到0之间")
                    
                # 如果存在买入Delta，则验证买入Delta（双腿策略）
                if self.put_buy_delta is not None:
                    self.put_buy_delta = float(self.put_buy_delta)
                    if not (-1 < self.put_buy_delta < 0):
                        raise ValueError("PUT Delta值必须在-1到0之间")
                    if self.put_sell_delta >= self.put_buy_delta:
                        raise ValueError("PUT策略中，卖出Delta必须小于买入Delta")
            except (TypeError, ValueError) as e:
                raise ValueError(f"PUT Delta值无效: {str(e)}")

        # 验证CALL策略的Delta值
        if self.call_sell_delta is not None or self.call_buy_delta is not None:
            if self.call_sell_delta is None or self.call_buy_delta is None:
                raise ValueError("CALL策略需要同时设置买入和卖出Delta")
            try:
                self.call_sell_delta = float(self.call_sell_delta)
                self.call_buy_delta = float(self.call_buy_delta)
                if not (0 < self.call_sell_delta < 1 and 0 < self.call_buy_delta < 1):
                    raise ValueError("CALL Delta值必须在0到1之间")
                if self.call_sell_delta <= self.call_buy_delta:
                    raise ValueError("CALL策略中，卖出Delta必须大于买入Delta")
            except (TypeError, ValueError) as e:
                raise ValueError(f"CALL Delta值无效: {str(e)}")

    def _validate_strategy_type(self, strategy_type: Optional[str]) -> StrategyType:
        """验证并确定策略类型
        
        Args:
            strategy_type: 策略类型字符串
            
        Returns:
            StrategyType: 验证后的策略类型枚举值
            
        Raises:
            ValueError: 当策略类型无效时抛出
        """
        try:
            # 如果没有提供策略类型，根据参数自动判断
            if not strategy_type:
                strategy_params = self.strategy_params
                
                # 检查是否为轮转策略
                if (strategy_params.get('put_sell_delta') == -0.5 and 
                    strategy_params.get('call_sell_delta') == 0.5 and
                    'put_buy_delta' not in strategy_params and
                    'call_buy_delta' not in strategy_params):
                    return StrategyType.WHEEL
                    
                # 检查是否为铁鹰策略
                elif all(key in strategy_params for key in [
                    'put_sell_delta', 'put_buy_delta',
                    'call_sell_delta', 'call_buy_delta'
                ]):
                    return StrategyType.IRON_CONDOR
                    
                # 检查是否为单腿看跌策略
                elif ('put_sell_delta' in strategy_params and
                      'put_buy_delta' not in strategy_params):
                    return StrategyType.NAKED_PUT
                    
                # 检查是否为牛市看跌策略
                elif all(key in strategy_params for key in [
                    'put_sell_delta', 'put_buy_delta'
                ]):
                    return StrategyType.BULLISH_PUT
                    
                # 检查是否为熊市看涨策略
                elif all(key in strategy_params for key in [
                    'call_sell_delta', 'call_buy_delta'
                ]):
                    return StrategyType.BEARISH_CALL
                    
                else:
                    raise ValueError("无法根据参数确定策略类型")
            
            # 如果提供了策略类型，验证其有效性
            try:
                return StrategyType[strategy_type.upper()]
            except (KeyError, AttributeError):
                raise ValueError(f"无效的策略类型: {strategy_type}")
                
            logger.debug("策略类型验证通过: %s", strategy_type)
            return strategy_type
            
        except Exception as e:
            logger.error("策略类型验证失败: %s", str(e))
            logger.error("策略参数: %s", self.strategy_params)
            logger.error("错误堆栈:\n%s", traceback.format_exc())
            raise ValueError(f"策略类型验证失败: {str(e)}")
    
    def _validate_strategy_params(self, strategy_type: str, params: Dict) -> Dict:
        """验证策略参数
        
        Args:
            strategy_type: 策略类型
            params: 策略参数
            
        Returns:
            验证后的策略参数
        """
        if strategy_type == 'wheel':
            # 轮转策略只需要验证卖出Delta
            if 'put_sell_delta' not in params:
                raise ValueError("轮转策略需要设置PUT卖出Delta")
            if params['put_sell_delta'] != -0.5:
                raise ValueError("轮转策略的PUT卖出Delta必须为-0.5")
            if 'call_sell_delta' not in params:
                raise ValueError("轮转策略需要设置CALL卖出Delta")
            if params['call_sell_delta'] != 0.5:
                raise ValueError("轮转策略的CALL卖出Delta必须为0.5")
                
            return {
                'put_sell_delta': params['put_sell_delta'],
                'call_sell_delta': params['call_sell_delta']
            }
            
        elif strategy_type == 'iron_condor':
            # 铁鹰策略验证逻辑
            self._validate_put_strategy(params)
            self._validate_call_strategy(params)
            return params
            
        elif strategy_type == 'naked_put':
            # 单腿看跌策略验证逻辑
            if 'put_sell_delta' not in params:
                raise ValueError("单腿看跌策略需要设置卖出Delta")
            return {'put_sell_delta': params['put_sell_delta']}
            
        elif strategy_type == 'bullish_put':
            # 牛市看跌策略验证逻辑
            self._validate_put_strategy(params)
            return params
            
        elif strategy_type == 'bearish_call':
            # 熊市看涨策略验证逻辑
            self._validate_call_strategy(params)
            return params
            
        else:
            raise ValueError(f"不支持的策略类型: {strategy_type}")
    
    def _validate_put_strategy(self, params: Dict):
        """验证PUT策略参数"""
        if 'put_sell_delta' not in params:
            raise ValueError("PUT策略需要设置卖出Delta")
        if 'put_buy_delta' not in params:
            raise ValueError("PUT策略需要设置买入Delta")
        if params['put_sell_delta'] >= params['put_buy_delta']:
            raise ValueError("PUT策略中卖出Delta必须小于买入Delta")
    
    def _validate_call_strategy(self, params: Dict):
        """验证CALL策略参数"""
        if 'call_sell_delta' not in params:
            raise ValueError("CALL策略需要设置卖出Delta")
        if 'call_buy_delta' not in params:
            raise ValueError("CALL策略需要设置买入Delta")
        if params['call_sell_delta'] <= params['call_buy_delta']:
            raise ValueError("CALL策略中卖出Delta必须大于买入Delta")