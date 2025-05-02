# 从原来的utils.py复制所有功能到这里
# 例如：
from calendar import monthcalendar
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

import pandas as pd


def format_date(date_str: str) -> str:
    """格式化日期字符串"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        return date_str

def validate_params(params: dict) -> bool:
    """验证参数"""
    required_fields = ['etf_code', 'start_date', 'end_date']
    return all(field in params for field in required_fields)

# ... 其他原有功能
def get_monthly_expiry(current_date: datetime, option_data: pd.DataFrame) -> datetime:
    """获取当月期权到期日（第四个星期三，如果不是交易日则顺延）

    Args:
        current_date: 当前日期
        option_data: 期权数据DataFrame

    Returns:
        datetime: 当月到期日
    """
    year = current_date.year
    month = current_date.month

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
        # 检查数据边界
        max_date = pd.to_datetime(option_data['日期'].max())
        if date >= max_date:
            print(f"警告: 当前日期 {date.strftime('%Y-%m-%d')} 已超出数据范围")
            return None

        # 获取下月第一天
        if date.month == 12:
            next_month = datetime(date.year + 1, 1, 1)
        else:
            next_month = datetime(date.year, date.month + 1, 1)

        # 如果下月第一天已超出数据范围，返回None
        if next_month > max_date:
            print(f"警告: 下月 {next_month.strftime('%Y-%m')} 已超出数据范围")
            # 从交易日列表中找出最接近或者等于max_date的交易日返回
            # trading_dates = sorted(option_data['日期'].unique())
            # return max(d for d in trading_dates if d <= max_date)

        # 获取下月所有的星期三
        cal = monthcalendar(next_month.year, next_month.month)
        wednesdays = [
            datetime(next_month.year, next_month.month, week[2])  # week[2]是周三
            for week in cal
            if week[2] != 0  # 确保这一天存在（不是0）
        ]

        if len(wednesdays) < 4:
            print(f"警告: 月份 {next_month.month}/{next_month.year} 不足四个星期三")
            return None

        # 获取第四个星期三
        target_date = wednesdays[3]

        # 获取所有交易日期
        trading_dates = pd.to_datetime(option_data['日期'].unique())
        trading_dates = sorted(trading_dates)

        # 如果目标日期超出数据范围，返回None
        if target_date > max_date:
            print(f"警告: 目标到期日 {target_date.strftime('%Y-%m-%d')} 已超出数据范围： {max_date.strftime('%Y-%m-%d')}")
            return None

        # 如果目标日期不是交易日，向后查找最近的交易日（最多查找10天）
        if target_date not in trading_dates:
            for i in range(1, 11):  # 最多往后找10天
                next_date = target_date + timedelta(days=i)
                if next_date > max_date:
                    print(f"警告: 无法找到合适的到期日，已超出数据范围")
                    return None
                if next_date in trading_dates:
                    target_date = next_date
                    break
            else:  # 如果10天内都没找到交易日
                print(f"警告: 无法找到 {target_date.strftime('%Y-%m-%d')} 之后的有效交易日")
                return None

        return target_date

    except Exception as e:
        print(f"警告: 无法获取下月到期日: {str(e)}")
        return None


def get_trading_dates(start_date: datetime, end_date: datetime, option_data: pd.DataFrame) -> List[datetime]:
    """获取交易日期列表

    Args:
        start_date: 开始日期
        end_date: 结束日期
        option_data: 期权数据

    Returns:
        List[datetime]: 交易日期列表
    """
    # 确保日期列是datetime类型
    if not pd.api.types.is_datetime64_any_dtype(option_data['日期']):
        option_data['日期'] = pd.to_datetime(option_data['日期'])

    # 获取日期范围内的所有交易日
    mask = (option_data['日期'] >= start_date) & (option_data['日期'] <= end_date)
    trading_dates = sorted(option_data[mask]['日期'].unique())

    return trading_dates


def calculate_returns(values: pd.Series,
                     annualization: int = 252) -> Tuple[float, float, float]:
    """计算收益率指标

    Args:
        values: 净值序列
        annualization: 年化系数，默认252个交易日

    Returns:
        Tuple[float, float, float]: (年化收益率, 年化波动率, 夏普比率)
    """
    if values.empty:
        return 0.0, 0.0, 0.0

    # 计算日收益率
    daily_returns = values.pct_change().dropna()
    if daily_returns.empty:
        return 0.0, 0.0, 0.0

    # 计算年化收益率
    total_return = (values.iloc[-1] / values.iloc[0]) - 1 if len(values) > 1 else 0
    days = (values.index[-1] - values.index[0]).days
    if days <= 0:
        return 0.0, 0.0, 0.0
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
