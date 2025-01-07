from datetime import datetime
from typing import Dict, Optional, Union
from enum import Enum

class StrategyType(Enum):
    BULL_PUT_SPREAD = "BULL_PUT_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"

class BacktestParams:
    """回测参数处理类"""
    
    def __init__(self, params: dict):
        """
        初始化回测参数
        
        Args:
            params: 包含回测参数的字典，格式如下：
            {
                'etf_code': str,
                'start_date': str,
                'end_date': str,
                'strategy': {
                    'put_sell_delta': float,
                    'put_buy_delta': float,
                    'call_sell_delta': float,
                    'call_buy_delta': float
                }
            }
        """
        self.etf_code = self._validate_etf_code(params.get('etf_code'))
        self.start_date = self._parse_date(params.get('start_date'), 'start_date')
        self.end_date = self._parse_date(params.get('end_date'), 'end_date')
        self.strategy = self._validate_strategy(params.get('strategy', {}))
        self._validate_dates()
        
    def _validate_etf_code(self, etf_code: Optional[str]) -> str:
        """验证ETF代码"""
        if not etf_code:
            raise ValueError('ETF代码不能为空')
        return etf_code
        
    def _parse_date(self, date_str: Optional[str], field_name: str) -> datetime:
        """解析日期字符串"""
        if not date_str:
            raise ValueError(f'{field_name}不能为空')
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f'{field_name}格式无效，应为YYYY-MM-DD')
            
    def _validate_dates(self):
        """验证日期范围"""
        if self.start_date >= self.end_date:
            raise ValueError('结束日期必须晚于开始日期')
            
    def _validate_strategy(self, strategy: Dict[str, float]) -> Dict[str, float]:
        """
        验证策略参数
        
        验证规则：
        1. PUT策略：卖出Delta必须小于买入Delta，且都为负值
        2. CALL策略：卖出Delta必须大于买入Delta，且都为正值
        3. 至少需要一组完整的策略
        """
        if not strategy:
            raise ValueError('策略参数不能为空')
            
        # 提取策略参数
        put_sell = strategy.get('put_sell_delta')
        put_buy = strategy.get('put_buy_delta')
        call_sell = strategy.get('call_sell_delta')
        call_buy = strategy.get('call_buy_delta')
        
        # 验证PUT策略
        has_put = False
        if put_sell is not None or put_buy is not None:
            if put_sell is None or put_buy is None:
                raise ValueError('PUT策略需要同时设置买入和卖出Delta')
            if not (put_sell < 0 and put_buy < 0):
                raise ValueError('PUT策略的Delta值必须为负数')
            if not (put_sell < put_buy):
                raise ValueError('PUT策略中，卖出Delta必须小于买入Delta')
            has_put = True
            
        # 验证CALL策略
        has_call = False
        if call_sell is not None or call_buy is not None:
            if call_sell is None or call_buy is None:
                raise ValueError('CALL策略需要同时设置买入和卖出Delta')
            if not (call_sell > 0 and call_buy > 0):
                raise ValueError('CALL策略的Delta值必须为正数')
            if not (call_sell > call_buy):
                raise ValueError('CALL策略中，卖出Delta必须大于买入Delta')
            has_call = True
            
        # 验证是否至少有一组策略
        if not (has_put or has_call):
            raise ValueError('至少需要设置一组完整的期权策略')
            
        return strategy
        
    @property
    def strategy_type(self) -> StrategyType:
        """识别策略类型"""
        has_put = all(k in self.strategy for k in ['put_sell_delta', 'put_buy_delta'])
        has_call = all(k in self.strategy for k in ['call_sell_delta', 'call_buy_delta'])
        
        if has_put and has_call:
            return StrategyType.IRON_CONDOR
        elif has_put:
            return StrategyType.BULL_PUT_SPREAD
        elif has_call:
            return StrategyType.BEAR_CALL_SPREAD
        else:
            raise ValueError('无效的策略组合')
            
    def to_dict(self) -> Dict[str, Union[str, Dict[str, float]]]:
        """转换为字典格式"""
        return {
            'etf_code': self.etf_code,
            'start_date': self.start_date.strftime('%Y-%m-%d'),
            'end_date': self.end_date.strftime('%Y-%m-%d'),
            'strategy': self.strategy,
            'strategy_type': self.strategy_type.value
        } 