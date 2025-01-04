from datetime import datetime, timedelta
from calendar import monthcalendar
import pandas as pd
from typing import Optional, Tuple, List

def get_monthly_expiry(date: datetime, option_data: pd.DataFrame) -> datetime:
    """获取当月期权到期日（第四个星期三，如果不是交易日则顺延）
    
    Args:
        date: 当前日期
        option_data: 期权数据DataFrame
    
    Returns:
        datetime: 当月到期日
    """
    year = date.year
    month = date.month
    
    # 获取当月所有的星期三
    cal = monthcalendar(year, month)
    wednesdays = [
        datetime(year, month, week[2])  # week[2]是周三
        for week in cal 
        if week[2] != 0  # 确保这一天存在（不是0）
    ]
    
    if len(wednesdays) < 4:
        raise ValueError(f"月份 {month}/{year} 不足四个星期三")
    
    # 获取第四个星期三
    target_date = wednesdays[3]
    
    # 获取所有交易日期
    trading_dates = pd.to_datetime(option_data['日期'].unique())
    trading_dates = sorted(trading_dates)
    
    # 如果目标日期不是交易日，向后查找最近的交易日（最多查找10天）
    if target_date not in trading_dates:
        for i in range(1, 11):  # 最多往后找10天
            next_date = target_date + timedelta(days=i)
            if next_date in trading_dates:
                target_date = next_date
                break
        else:  # 如果10天内都没找到交易日
            raise ValueError(f"无法找到{target_date}之后的有效交易日")
    
    return target_date

def get_next_monthly_expiry(date: datetime, option_data: pd.DataFrame) -> Optional[datetime]:
    """获取下月期权到期日（第四个星期三，如果不是交易日则顺延）
    
    Args:
        date: 当前日期
        option_data: 期权数据DataFrame
    
    Returns:
        Optional[datetime]: 下月到期日，如果无法获取则返回None
    """
    try:
        # 获取下月第一天
        if date.month == 12:
            next_month = datetime(date.year + 1, 1, 1)
        else:
            next_month = datetime(date.year, date.month + 1, 1)
        
        # 获取下月所有的星期三
        cal = monthcalendar(next_month.year, next_month.month)
        wednesdays = [
            datetime(next_month.year, next_month.month, week[2])  # week[2]是周三
            for week in cal 
            if week[2] != 0  # 确保这一天存在（不是0）
        ]
        
        if len(wednesdays) < 4:
            raise ValueError(f"月份 {next_month.month}/{next_month.year} 不足四个星期三")
        
        # 获取第四个星期三
        target_date = wednesdays[3]
        
        # 获取所有交易日期
        trading_dates = pd.to_datetime(option_data['日期'].unique())
        trading_dates = sorted(trading_dates)
        
        # 如果目标日期不是交易日，向后查找最近的交易日（最多查找10天）
        if target_date not in trading_dates:
            for i in range(1, 11):  # 最多往后找10天
                next_date = target_date + timedelta(days=i)
                if next_date in trading_dates:
                    target_date = next_date
                    break
            else:  # 如果10天内都没找到交易日
                raise ValueError(f"无法找到{target_date}之后的有效交易日")
        
        return target_date
        
    except ValueError as e:
        print(f"警告: 无法获取下月到期日: {str(e)}")
        return None

def calculate_margin_requirement(strike_price: float, etf_price: float, 
                               contract_multiplier: int = 10000) -> float:
    """计算期权保证金要求（按照实际行权需求计算）
    
    Args:
        strike_price: 行权价
        etf_price: 当前ETF价格
        contract_multiplier: 合约乘数，默认10000
    
    Returns:
        float: 每张合约需要的保证金（等于行权时需要的现金）
    """
    # 对于卖出PUT，需要准备行权价 × 合约乘数的现金
    # 因为最坏情况下需要以行权价买入ETF
    return strike_price * contract_multiplier

def get_trading_dates(start_date: datetime, end_date: datetime, 
                     option_data: pd.DataFrame) -> List[datetime]:
    """获取有效的交易日期列表
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        option_data: 期权数据DataFrame
    
    Returns:
        List[datetime]: 交易日期列表
    """
    trading_dates = option_data[
        (option_data['日期'] >= start_date) & 
        (option_data['日期'] <= end_date)
    ]['日期'].unique()
    
    return sorted(trading_dates)

def calculate_returns(values: pd.Series, 
                     annualization: int = 252) -> Tuple[float, float, float]:
    """计算收益率指标
    
    Args:
        values: 净值序列
        annualization: 年化系数，默认252个交易日
    
    Returns:
        Tuple[float, float, float]: (年化收益率, 年化波动率, 夏普比率)
    """
    # 计算日收益率
    daily_returns = values.pct_change().dropna()
    
    # 计算年化收益率
    total_return = (values.iloc[-1] / values.iloc[0]) - 1
    days = (values.index[-1] - values.index[0]).days
    annual_return = (1 + total_return) ** (annualization / days) - 1
    
    # 计算年化波动率
    annual_volatility = daily_returns.std() * (annualization ** 0.5)
    
    # 计算夏普比率（假设无风险利率为2%）
    risk_free_rate = 0.02
    sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility != 0 else 0
    
    return annual_return, annual_volatility, sharpe_ratio

def format_number(value: float, precision: int = 2) -> str:
    """格式化数字输出
    
    Args:
        value: 数值
        precision: 小数位数
    
    Returns:
        str: 格式化后的字符串
    """
    if abs(value) >= 1e6:
        return f"{value/1e6:.{precision}f}M"
    elif abs(value) >= 1e3:
        return f"{value/1e3:.{precision}f}K"
    else:
        return f"{value:.{precision}f}" 