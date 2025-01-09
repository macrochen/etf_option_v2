from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional
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
    etf_code: str                     # ETF代码（必需）
    strategy_type: StrategyType       # 策略类型（根据参数自动判断）
    strategy_params: Dict             # 策略特定参数，如 delta 值等
    start_date: Optional[datetime] = None  # 回测开始日期（可选）
    end_date: Optional[datetime] = None    # 回测结束日期（可选）

    def _validate_delta_values(self):
        """验证Delta值的有效性"""
        # 验证PUT策略的Delta值
        if self.put_sell_delta is not None or self.put_buy_delta is not None:
            if self.put_sell_delta is None or self.put_buy_delta is None:
                raise ValueError("PUT策略需要同时设置买入和卖出Delta")
            try:
                self.put_sell_delta = float(self.put_sell_delta)
                self.put_buy_delta = float(self.put_buy_delta)
                if not (-1 < self.put_sell_delta < 0 and -1 < self.put_buy_delta < 0):
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

    def _determine_strategy_type(self) -> StrategyType:
        """根据参数确定策略类型"""
        has_put = self.put_sell_delta is not None and self.put_buy_delta is not None
        has_call = self.call_sell_delta is not None and self.call_buy_delta is not None

        if has_put and has_call:
            return StrategyType.IRON_CONDOR
        elif has_put:
            return StrategyType.BULLISH_PUT
        elif has_call:
            return StrategyType.BEARISH_CALL
        else:
            raise ValueError("至少需要设置一组完整的期权策略参数")

    def __init__(self, params: Dict):
        """初始化回测参数
        
        Args:
            params: 包含回测参数的字典
        """
        # 必需字段
        required_fields = ['etf_code']
        missing_fields = [field for field in required_fields if field not in params]
        if missing_fields:
            raise ValueError(f"缺少必要参数: {', '.join(missing_fields)}")
        
        try:
            # ETF代码
            self.etf_code = params['etf_code']
            
            # 解析日期字符串（如果提供）
            if 'start_date' in params and params['start_date']:
                self.start_date = datetime.strptime(params['start_date'], '%Y-%m-%d')
            else:
                self.start_date = None

            if 'end_date' in params and params['end_date']:
                self.end_date = datetime.strptime(params['end_date'], '%Y-%m-%d')
            else:
                self.end_date = None
            
            # 如果提供了日期范围，验证其有效性
            if self.start_date and self.end_date and self.end_date < self.start_date:
                raise ValueError("结束日期不能早于开始日期")
            
            # 策略参数
            strategy_params = params.get('strategy_params', {})
            
            # PUT期权参数
            self.put_sell_delta = strategy_params.get('put_sell_delta')
            self.put_buy_delta = strategy_params.get('put_buy_delta')
            
            # CALL期权参数
            self.call_sell_delta = strategy_params.get('call_sell_delta')
            self.call_buy_delta = strategy_params.get('call_buy_delta')
            
            # 验证Delta值
            self._validate_delta_values()
            
            # 确定策略类型
            self.strategy_type = self._determine_strategy_type()
            
            # 保存策略参数
            self.strategy_params = {
                'put_sell_delta': self.put_sell_delta,
                'put_buy_delta': self.put_buy_delta,
                'call_sell_delta': self.call_sell_delta,
                'call_buy_delta': self.call_buy_delta
            }
            
        except ValueError as e:
            raise ValueError(f"参数验证失败: {str(e)}")
        except Exception as e:
            raise ValueError(f"参数解析失败: {str(e)}") 