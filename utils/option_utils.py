from typing import Optional, Tuple, List
import numpy as np
from scipy.stats import norm

def find_strike_price_by_volatility(
    current_price: float,
    target_volatility: float,
    option_type: str
) -> float:
    """
    根据目标波动率找到合适的行权价
    
    Args:
        current_price: 当前价格
        target_volatility: 目标波动率（百分比）
        option_type: 期权类型 ('call' 或 'put')
    
    Returns:
        float: 对应的行权价
    """
    volatility = target_volatility / 100  # 转换为小数
    
    if option_type == 'call':
        # 对于看涨期权，行权价应该高于当前价格
        strike = current_price * (1 + volatility)
    else:
        # 对于看跌期权，行权价应该低于当前价格
        strike = current_price * (1 - volatility)
    
    # 四舍五入到最接近的标准行权价
    return round_to_strike_price(strike)

def round_to_strike_price(price: float) -> float:
    """
    将价格四舍五入到最接近的标准行权价
    
    Args:
        price: 原始价格
    
    Returns:
        float: 标准行权价
    """
    # ETF期权的最小价格间隔通常是0.05
    strike_interval = 0.05
    return round(price / strike_interval) * strike_interval

def calculate_option_greeks(
    spot_price: float,
    strike_price: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
    option_type: str
) -> dict:
    """
    计算期权的希腊字母值
    
    Args:
        spot_price: 现货价格
        strike_price: 行权价
        time_to_expiry: 到期时间（年）
        volatility: 波动率
        risk_free_rate: 无风险利率
        option_type: 期权类型 ('call' 或 'put')
    
    Returns:
        dict: 包含delta, gamma, theta, vega等希腊字母值的字典
    """
    # 计算d1和d2
    d1 = (np.log(spot_price / strike_price) + 
          (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / \
         (volatility * np.sqrt(time_to_expiry))
    d2 = d1 - volatility * np.sqrt(time_to_expiry)
    
    # 计算N(d1)和N(d2)
    nd1 = norm.cdf(d1)
    nd2 = norm.cdf(d2)
    
    # 计算n(d1)
    npd1 = norm.pdf(d1)
    
    if option_type == 'call':
        delta = nd1
        theta = (-spot_price * npd1 * volatility / (2 * np.sqrt(time_to_expiry)) -
                risk_free_rate * strike_price * np.exp(-risk_free_rate * time_to_expiry) * nd2)
    else:
        delta = nd1 - 1
        theta = (-spot_price * npd1 * volatility / (2 * np.sqrt(time_to_expiry)) +
                risk_free_rate * strike_price * np.exp(-risk_free_rate * time_to_expiry) * (1 - nd2))
    
    gamma = npd1 / (spot_price * volatility * np.sqrt(time_to_expiry))
    vega = spot_price * np.sqrt(time_to_expiry) * npd1
    
    return {
        'delta': delta,
        'gamma': gamma,
        'theta': theta,
        'vega': vega
    }

def calculate_implied_volatility(
    option_price: float,
    spot_price: float,
    strike_price: float,
    time_to_expiry: float,
    risk_free_rate: float,
    option_type: str
) -> Optional[float]:
    """
    使用牛顿法计算隐含波动率
    
    Args:
        option_price: 期权价格
        spot_price: 现货价格
        strike_price: 行权价
        time_to_expiry: 到期时间（年）
        risk_free_rate: 无风险利率
        option_type: 期权类型 ('call' 或 'put')
    
    Returns:
        Optional[float]: 隐含波动率，如果无法收敛则返回None
    """
    MAX_ITERATIONS = 100
    PRECISION = 1.0e-5
    
    # 初始猜测值
    volatility = 0.5
    
    for i in range(MAX_ITERATIONS):
        greeks = calculate_option_greeks(
            spot_price, strike_price, time_to_expiry,
            volatility, risk_free_rate, option_type
        )
        
        # 计算期权价格
        d1 = (np.log(spot_price / strike_price) + 
              (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / \
             (volatility * np.sqrt(time_to_expiry))
        d2 = d1 - volatility * np.sqrt(time_to_expiry)
        
        if option_type == 'call':
            price = spot_price * norm.cdf(d1) - \
                    strike_price * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
        else:
            price = strike_price * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - \
                    spot_price * norm.cdf(-d1)
        
        diff = option_price - price
        
        if abs(diff) < PRECISION:
            return volatility
        
        # 使用vega更新波动率
        volatility = volatility + diff / greeks['vega']
        
        if volatility <= 0:
            return None
    
    return None
