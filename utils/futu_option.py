import pytz
import requests
from bs4 import BeautifulSoup
from typing import Optional
import logging
import traceback
import sqlite3
from datetime import datetime, timedelta
import random

def get_cached_delta(option_symbol: str, db_path: str) -> Optional[float]:
    """从缓存中获取delta值"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT delta, next_update_time 
            FROM option_delta_cache 
            WHERE option_symbol = ?
        """, (option_symbol,))
        result = cursor.fetchone()
        
        if result:
            delta, next_update = result
            if datetime.now() < datetime.fromisoformat(next_update):
                return delta
        return None
    finally:
        conn.close()

def cache_delta(option_symbol: str, delta: float, db_path: str):
    """缓存delta值"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 随机延迟15-20分钟，避免所有期权同时更新
        next_update = datetime.now() + timedelta(minutes=15) + timedelta(seconds=random.randint(0, 300))
        
        cursor.execute("""
            INSERT OR REPLACE INTO option_delta_cache 
            (option_symbol, delta, update_time, next_update_time)
            VALUES (?, ?, ?, ?)
        """, (option_symbol, delta, datetime.now().isoformat(), next_update.isoformat()))
        
        conn.commit()
    finally:
        conn.close()

from db.us_stock_db import USStockDatabase

def is_us_market_trading_hours() -> bool:
    """判断当前是否为美股交易时段
    
    美股交易时间：
    - 夏令时：北京时间 21:30-04:00
    - 冬令时：北京时间 22:30-05:00
    """
    now = datetime.now(pytz.timezone('Asia/Shanghai'))  # 使用北京时间
    
    # 判断是否为工作日
    if now.weekday() >= 5:  # 周六日休市
        return False
        
    # 获取当前日期的夏令时信息
    us_eastern = pytz.timezone('US/Eastern')
    us_time = now.astimezone(us_eastern)
    is_dst = us_time.dst() != timedelta(0)
    
    # 转换为当天的小时和分钟
    hour = now.hour
    minute = now.minute
    current_time = hour * 100 + minute  # 转为时间数值，例如 21:30 -> 2130
    
    if is_dst:
        # 夏令时：21:30 - 04:00
        return (2130 <= current_time <= 2359) or (0 <= current_time <= 400)
    else:
        # 冬令时：22:30 - 05:00
        return (2230 <= current_time <= 2359) or (0 <= current_time <= 500)

def get_option_delta(option_symbol: str) -> Optional[float]:
    # 暂时采用手动刷新
    # return 0
    
    """获取期权的delta值，优先使用缓存"""
    db = USStockDatabase()
    
    # 检查是否为交易时段
    is_trading_hours = is_us_market_trading_hours()
    
    # 获取缓存的delta值
    cached_delta = db.get_cached_delta(option_symbol)
    
    # 非交易时段，直接返回缓存值（即使已过期）
    if not is_trading_hours and cached_delta is not None:
        return cached_delta
    elif cached_delta is not None:
        return cached_delta
    else:
        return 0
        


def get_option_delta_with_cached(option_symbol: str) -> Optional[float]:
    # 暂时采用手动刷新
    # return 0
    
    """获取期权的delta值，优先使用缓存"""
    db = USStockDatabase()
    
    # 检查是否为交易时段
    is_trading_hours = is_us_market_trading_hours()
    
    # 获取缓存的delta值
    cached_delta = db.get_cached_delta(option_symbol)
    
    # 非交易时段，直接返回缓存值（即使已过期）
    if not is_trading_hours and cached_delta is not None:
        return cached_delta
        
    # 交易时段且缓存已过期，从富途网站获取新值
    if cached_delta is None or is_trading_hours:
        try:
            delta = get_delta_from_futu(option_symbol)
            if delta is not None:
                db.cache_delta(option_symbol, delta)
                return delta
        except Exception as e:
            logging.error(f"获取期权 {option_symbol} 的delta值失败: {str(e)}\n{traceback.format_exc()}")
            # 如果获取失败但有缓存值，返回缓存值
            if cached_delta is not None:
                return cached_delta
            return None
    
    return cached_delta

def get_eastern_time() -> datetime:
    """获取美东时间"""
    from datetime import datetime
    import pytz
    
    # 获取当前UTC时间
    utc_now = datetime.now(pytz.UTC)
    # 转换为美东时间
    et = pytz.timezone('US/Eastern')
    return utc_now.astimezone(et)

import time
from functools import lru_cache

# 添加请求限流器
class RateLimiter:
    def __init__(self, max_requests=3, time_window=1):
        """初始化限流器
        
        Args:
            max_requests: 时间窗口内允许的最大请求数
            time_window: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    def can_request(self) -> bool:
        """检查是否可以发送请求"""
        now = time.time()
        # 清理过期的请求记录
        self.requests = [req_time for req_time in self.requests 
                        if now - req_time < self.time_window]
        
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False
    
    def wait_if_needed(self):
        """如果需要等待，则等待到可以请求为止"""
        while not self.can_request():
            time.sleep(0.1)  # 等待100ms后重试

# 创建全局限流器实例，改为每2秒最多1个请求
_rate_limiter = RateLimiter(max_requests=1, time_window=2)  # 修改限流参数

@lru_cache(maxsize=100)  # 使用LRU缓存避免重复请求
def get_delta_from_futu(option_symbol: str) -> Optional[float]:    
    """从富途网页获取期权的delta值"""
    # 在发送请求前检查限流
    _rate_limiter.wait_if_needed()
    
    # 添加随机延时 1-3 秒
    time.sleep(random.uniform(1, 3))
    
    # 构建URL
    url = f"https://www.futunn.com/stock/{option_symbol}-US"
    params = {
        'global_content': '{"promote_id":13766,"sub_promote_id":1}'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Referer': 'https://www.futunn.com/'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        # 检查页面是否包含期权代码，如果不包含可能是重定向到了错误页面
        if option_symbol not in response.text:
            logging.error(
                f"页面未包含期权代码，可能是重定向到了错误页面\n"
                f"URL: {url}\n"
                f"最终URL: {response.url}\n"
                f"页面标题: {BeautifulSoup(response.text, 'html.parser').title.text if BeautifulSoup(response.text, 'html.parser').title else 'No title'}"
            )
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尝试查找错误信息或登录提示
        error_msg = soup.find('div', class_='error-message')
        if error_msg:
            logging.error(f"页面返回错误信息: {error_msg.text}")
            return None
            
        # 添加页面内容日志，帮助诊断问题
        logging.debug(f"期权 {option_symbol} 的响应内容:\n{response.text[:500]}...")  # 只记录前500个字符
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 记录所有找到的span元素，帮助分析页面结构
        all_spans = soup.find_all('span')
        logging.debug(f"页面中找到的所有span元素: {[span.text for span in all_spans[:10]]}...")  # 只记录前10个
        
        delta_spans = soup.find_all('span', string='Delta')
        if delta_spans:
            # 获取Delta值的span（通常是前一个兄弟元素）
            delta_value = delta_spans[0].find_previous_sibling('span')
            if delta_value:
                try:
                    logging.warning(f"找到期权 {option_symbol} 的Delta值: {delta_value.text}")
                    return float(delta_value.text)
                except ValueError:
                    logging.error(
                        f"无法转换期权 {option_symbol} 的delta值: {delta_value.text}\n"
                        f"URL: {url}\n"
                        f"响应状态码: {response.status_code}"
                    )
                    return None
        
        logging.warning(
            f"未找到期权 {option_symbol} 的Delta值\n"
            f"URL: {url}\n"
            f"响应状态码: {response.status_code}\n"
            f"页面是否包含'Delta'文本: {'Delta' in response.text}\n"
            f"页面是否包含期权代码: {option_symbol in response.text}"
        )
        return None
        
    except requests.RequestException as e:
        logging.error(
            f"请求期权 {option_symbol} 数据失败\n"
            f"URL: {url}\n"
            f"错误类型: {type(e).__name__}\n"
            f"错误信息: {str(e)}\n"
            f"堆栈信息:\n{traceback.format_exc()}"
        )
        return None
    except Exception as e:
        logging.error(
            f"解析期权 {option_symbol} 数据失败\n"
            f"URL: {url}\n"
            f"错误类型: {type(e).__name__}\n"
            f"错误信息: {str(e)}\n"
            f"堆栈信息:\n{traceback.format_exc()}"
        )
        return None

# # 测试代码
# option_symbol = 'NVDA250321C132000'
# option_symbol = 'MELI250228C2200000'
# delta = get_option_delta(option_symbol)
# print(f"期权 {option_symbol} 的delta值为: {delta}")