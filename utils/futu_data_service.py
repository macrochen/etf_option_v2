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

def get_cached_option_delta(option_symbol: str, force_cache: bool = False) -> Optional[float]:
    """获取期权的delta值，优先使用缓存
    
    Args:
        option_symbol: 期权代码
        force_cache: 是否强制只使用缓存数据，True表示只从缓存获取，不进行网络请求
    
    Returns:
        float: delta值，如果获取失败则返回None或0
    """
    db = USStockDatabase()
    
    # 获取缓存的delta值
    cached_delta = db.get_cached_delta(option_symbol, force_cache)
    
    # 如果有缓存值，直接返回
    if cached_delta is not None:
        return cached_delta
    
    # 如果没有缓存值，返回默认值0
    return 0


def refresh_option_delta(option_symbol: str) -> Optional[float]:
    """获取期权的delta值，如果缓存中没有则从富途网站获取并更新缓存
    
    Args:
        option_symbol: 期权代码
    
    Returns:
        float: delta值，如果获取失败则返回None
    """
    db = USStockDatabase()
    
    # 获取缓存的delta值
    cached_delta = db.get_cached_delta(option_symbol)
    
    if cached_delta is not None:
        return cached_delta  # 修正：返回缓存的delta值，而不是cache_delta函数
    else:
        # 缓存中没有的，到futu取
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
from functools import lru_cache, wraps

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

def lru_cache_except_none(maxsize=128):
    """自定义缓存装饰器，不缓存None结果"""
    def decorator(func):
        cache_func = lru_cache(maxsize=maxsize)(func)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = cache_func(*args, **kwargs)
            if result is None:
                # 如果结果是None，清除这个键的缓存
                cache_func.cache_clear()  # 这会清除所有缓存，不够精确
                # 重新调用原始函数
                return func(*args, **kwargs)
            return result
        
        # 保留原始缓存函数的方法
        wrapper.cache_info = cache_func.cache_info
        wrapper.cache_clear = cache_func.cache_clear
        
        return wrapper
    return decorator

@lru_cache_except_none(maxsize=100)  # 使用LRU缓存避免重复请求
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

# 使用自定义装饰器替换原来的lru_cache
@lru_cache_except_none(maxsize=100)
def get_real_time_price(symbol: str, market: str = 'US') -> Optional[float]:
    """从富途获取实时价格
    
    Args:
        symbol: 股票代码或期权代码
        market: 市场类型（US/HK）
    
    Returns:
        float: 当前价格，如果获取失败则返回None
    """
    _rate_limiter.wait_if_needed()
    time.sleep(random.uniform(1, 2))
    
    url = f"https://www.futunn.com/stock/{symbol}-{market}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找价格元素，优先查找股票价格格式
        price_element = soup.find('li', class_='price')
        if not price_element:
            # 如果没找到股票价格格式，尝试期权价格格式
            price_element = soup.find('span', class_='price')
        
        if price_element:
            # 提取纯数字价格
            price_text = ''.join(filter(lambda x: x.isdigit() or x == '.', price_element.text.strip()))
            try:
                return float(price_text)
            except ValueError:
                logging.error(f"无法转换{symbol}的价格文本: {price_text}")
                return None
        
        logging.warning(f"未找到{symbol}的价格信息\nURL: {url}")
        return None
        
    except Exception as e:
        logging.error(f"获取{symbol}实时价格失败: {str(e)}\n{traceback.format_exc()}")
        return None

def create_sim_trade(trade_data: dict) -> dict:
    """创建模拟交易持仓
    
    Args:
        trade_data: 交易数据字典
    
    Returns:
        dict: 处理结果
    """
    try:
        db = USStockDatabase()
        
        # 如果没有提供价格，尝试获取实时价格
        if not trade_data.get('price'):
            if trade_data['type'] == 'stock':
                price = get_real_time_price(trade_data['symbol'], trade_data['market'])
            else:  # option
                # 构建期权代码
                expiry = datetime.strptime(trade_data['expiry'], '%Y-%m-%d')
                strike = float(trade_data['strike'])
                option_symbol = f"{trade_data['underlying']}{expiry.strftime('%y%m%d')}{trade_data['optionType'][0].upper()}{int(strike*1000)}"
                price = get_real_time_price(option_symbol, trade_data['market'])
            
            if price is None:
                return {
                    'status': 'error',
                    'message': '无法获取实时价格，请手动输入价格'
                }
            trade_data['price'] = price
        
        position_id = db.create_sim_position(trade_data)
        return {
            'status': 'success',
            'data': {'position_id': position_id}
        }
    except Exception as e:
        logging.error(f"创建模拟交易持仓失败: {str(e)}\n{traceback.format_exc()}")
        return {
            'status': 'error',
            'message': str(e)
        }

def get_sim_positions() -> dict:
    """获取模拟持仓数据，返回格式与富途持仓一致"""
    try:
        db = USStockDatabase()
        positions = db.get_sim_positions()
        
        # 创建按标的分组的字典和非分组列表
        grouped_positions = {}
        ungrouped_positions = []
        
        # 计算总市值
        total_market_value = 0
        temp_positions = []
        
        # 第一次遍历，获取实时价格和计算总市值
        for pos in positions:
            current_price = get_real_time_price(pos['symbol'], pos['market'])
            if current_price:
                market_value = current_price * pos['quantity']
                total_market_value += market_value
                temp_positions.append((pos, current_price, market_value))
        
        # 处理所有持仓数据
        for pos, current_price, market_value in temp_positions:
            position_data = {
                'symbol': pos['symbol'],
                'quantity': pos['quantity'],
                'average_cost': pos['price'],
                'market_value': market_value,
                'latest_price': current_price,
                'unrealized_pnl': (current_price - pos['price']) * pos['quantity'] * (1 if pos['direction'] == 'buy' else -1),
                'unrealized_pnl_percentage': ((current_price - pos['price']) / pos['price'] * 100) * (1 if pos['direction'] == 'buy' else -1),
                'realized_pnl': 0,  # 模拟交易暂不记录已实现盈亏
                'market': pos['market'],
                'sec_type': 'OPT' if pos['position_type'] == 'option' else 'STK',
                'position_ratio': (market_value / total_market_value * 100) if total_market_value else 0,
                'daily_pnl': 0,  # 模拟交易暂不记录日内盈亏
                'currency': 'USD' if pos['market'] == 'US' else 'HKD',
                'position_id': pos['id']  # 添加持仓ID
            }
            
            if pos['position_type'] == 'option':
                position_data.update({
                    'strike': pos['strike'],
                    'expiry': pos['expiry'],
                    'put_call': '沽' if pos['option_type'] == 'put' else '购'
                })
                
                # 添加到分组中
                if pos['underlying'] in grouped_positions:
                    grouped_positions[pos['underlying']]['options'].append(position_data)
                    group = grouped_positions[pos['underlying']]
                    group['total_market_value'] += market_value
                    group['total_unrealized_pnl'] += position_data['unrealized_pnl']
                    group['total_position_ratio'] += position_data['position_ratio']
                else:
                    grouped_positions[pos['underlying']] = {
                        'symbol': pos['underlying'],
                        'stock': None,
                        'options': [position_data],
                        'market': pos['market'],
                        'total_market_value': market_value,
                        'total_unrealized_pnl': position_data['unrealized_pnl'],
                        'total_realized_pnl': 0,
                        'is_group': True,
                        'total_position_ratio': position_data['position_ratio'],
                        'total_daily_pnl': 0
                    }
            else:
                # 检查是否有相关的期权持仓
                has_options = any(
                    p['position_type'] == 'option' and p['underlying'] == pos['symbol']
                    for p in positions
                )
                
                if has_options:
                    if pos['symbol'] not in grouped_positions:
                        grouped_positions[pos['symbol']] = {
                            'symbol': pos['symbol'],
                            'stock': position_data,
                            'options': [],
                            'market': pos['market'],
                            'total_market_value': market_value,
                            'total_unrealized_pnl': position_data['unrealized_pnl'],
                            'total_realized_pnl': 0,
                            'is_group': True,
                            'total_position_ratio': position_data['position_ratio'],
                            'total_daily_pnl': 0
                        }
                    else:
                        group = grouped_positions[pos['symbol']]
                        group['stock'] = position_data
                        group['total_market_value'] += market_value
                        group['total_unrealized_pnl'] += position_data['unrealized_pnl']
                        group['total_position_ratio'] += position_data['position_ratio']
                else:
                    ungrouped_positions.append(position_data)
        
        # 合并分组和非分组数据
        final_positions = list(grouped_positions.values()) + ungrouped_positions
        
        # 按市场分类并按symbol排序
        us_positions = sorted([p for p in final_positions if p.get('market') == 'US'], 
                            key=lambda x: x['symbol'])
        hk_positions = sorted([p for p in final_positions if p.get('market') == 'HK'], 
                            key=lambda x: x['symbol'])
        # 将所有持仓合并到一个列表中，以适配前端期望的格式
        all_positions = us_positions + hk_positions
        
        return {
            'status': 'success',
            'data': {
                'positions': all_positions,
                # 保留原有的分类，以便将来可能需要
                # 'us_positions': us_positions,
                # 'hk_positions': hk_positions
            }
        }
    except Exception as e:
        logging.error(f"获取模拟持仓失败: {str(e)}\n{traceback.format_exc()}")
        return {
            'status': 'error',
            'message': str(e)
        }

def close_sim_position(position_id: int) -> dict:
    """关闭模拟交易持仓
    
    Args:
        position_id: 持仓ID
    
    Returns:
        dict: 处理结果
    """
    try:
        db = USStockDatabase()
        if db.close_sim_position(position_id):
            return {
                'status': 'success',
                'message': '持仓已关闭'
            }
        else:
            return {
                'status': 'error',
                'message': '持仓不存在或已关闭'
            }
    except Exception as e:
        logging.error(f"关闭模拟持仓失败: {str(e)}\n{traceback.format_exc()}")
        return {
            'status': 'error',
            'message': str(e)
        }

# # 测试代码
# option_symbol = 'NVDA250321C132000'
# option_symbol = 'MELI250228C2200000'
# delta = get_option_delta(option_symbol)
# print(f"期权 {option_symbol} 的delta值为: {delta}")