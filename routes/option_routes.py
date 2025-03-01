from flask import Blueprint, jsonify, request
from utils.futu_data_service import get_delta_from_futu,refresh_option_delta
from db.us_stock_db import USStockDatabase
from futu import OpenQuoteContext, TrdMarket, PriceReminderType, SetPriceReminderOp, PriceReminderFreq
import time
from collections import defaultdict
import pandas as pd
import logging
import traceback

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/macrochen/PycharmProjects/etf_option_v2/logs/option_routes.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

option_bp = Blueprint('option', __name__)

def add_price_reminder(quote_ctx, code, strike, reminder_type, stock_reminder_count, request_count, last_request_time):
    """添加到价提醒的通用函数
    
    Args:
        quote_ctx: 富途API上下文
        code: 股票代码
        strike: 行权价
        reminder_type: 提醒类型（向上/向下）
        stock_reminder_count: 每只股票的提醒计数
        request_count: 当前请求计数
        last_request_time: 上次请求时间
    
    Returns:
        tuple: (是否成功, 新的请求计数, 新的上次请求时间)
    """
    reminder_type_str = "向上" if reminder_type == PriceReminderType.PRICE_UP else "向下"
    option_type = "CALL" if reminder_type == PriceReminderType.PRICE_UP else "PUT"
    
    # 检查提醒数量限制
    if stock_reminder_count[code][reminder_type] >= 10:
        logger.warning(f"股票 {code} {reminder_type_str}突破提醒已达上限(10个)，跳过添加 {strike}")
        return False, request_count, last_request_time
        
    # 检查频率限制
    current_time = time.time()
    if request_count >= 60 and current_time - last_request_time < 30:
        sleep_time = 30 - (current_time - last_request_time)
        logger.info(f"达到接口频率限制，等待 {sleep_time:.1f} 秒")
        time.sleep(sleep_time)
        request_count = 0
        last_request_time = time.time()
        
    try:
        ret, data = quote_ctx.set_price_reminder(
            code=code,
            reminder_type=reminder_type,
            reminder_freq=PriceReminderFreq.ONCE_A_DAY,
            value=strike,
            op=SetPriceReminderOp.ADD,
            note=f"{option_type}期权行权价 {strike} {reminder_type_str}突破提醒"
        )
        request_count += 1
        
        if ret == 0:
            stock_reminder_count[code][reminder_type] += 1
            logger.info(f"成功添加{reminder_type_str}突破提醒 - 股票: {code}, 价格: {strike}")
            time.sleep(0.5)  # 每次请求后等待 0.5 秒
            return True, request_count, last_request_time
        else:
            logger.error(f"添加{reminder_type_str}突破提醒失败 - 股票: {code}, 价格: {strike}, 错误: {data}")
            return False, request_count, last_request_time
            
    except Exception as e:
        logger.error(f"添加{reminder_type_str}突破提醒异常 - 股票: {code}, 价格: {strike}\n"
                    f"错误信息: {str(e)}\n堆栈信息: {traceback.format_exc()}")
        return False, request_count, last_request_time

@option_bp.route('/api/update_price_alerts', methods=['POST'])
def update_price_alerts():
    try:
        market = request.json.get('market', 'US')
        quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        
        # 获取当前所有到价提醒
        ret, data = quote_ctx.get_price_reminder(market=TrdMarket.US if market == 'US' else TrdMarket.HK)
        if ret != 0:
            raise Exception(f"获取到价提醒失败: {data}")
        
        # 检查每只股票现有的提醒数量
        logger.info(f"获取到的到价提醒数据: {data}")  # 添加日志以查看数据结构
        
        # 检查每只股票现有的提醒数量
        stock_reminder_count = defaultdict(lambda: defaultdict(int))
        if isinstance(data, pd.DataFrame):  # 如果返回的是DataFrame
            for _, row in data.iterrows():
                stock_reminder_count[row.code][row.reminder_type] += 1
        else:  # 如果返回的是列表或其他结构
            for item in data:
                if isinstance(item, dict):
                    stock_reminder_count[item['code']][item['reminder_type']] += 1
                else:
                    logger.error(f"意外的数据项类型: {type(item)}, 值: {item}")
        
       # 整理现有提醒数据
        existing_alerts = {}
        price_alerts = {}
        
        if isinstance(data, pd.DataFrame):
            for _, row in data.iterrows():
                key = (row.code, row.reminder_type, row.reminder_freq)
                existing_alerts[key] = row.value
                
                code = row.code
                if code not in price_alerts:
                    price_alerts[code] = []
                price_alerts[code].append({
                    'price': float(row.value),
                    'key': float(row.key),
                    'type': row.reminder_type,
                    'freq': row.reminder_freq
                })
        else:
            for item in data:
                if isinstance(item, dict):
                    key = (item['code'], item['reminder_type'], item['reminder_freq'])
                    existing_alerts[key] = item['price']
                    
                    code = item['code']
                    if code not in price_alerts:
                        price_alerts[code] = []
                    price_alerts[code].append({
                        'price': float(item['price']),
                        'key': item['key'],
                        'type': item['reminder_type'],
                        'freq': item['reminder_freq']
                    })
            
        # 获取当前持仓的期权信息
        from .tiger_routes import get_positions
        response = get_positions()
        positions_data = response.get_json()
        
        if positions_data['status'] != 'success':
            raise Exception('获取持仓信息失败')
            
            
        # 整理持仓期权数据，按股票代码分组
        position_strikes = {}
        market_key = f"{market.lower()}_positions"  # 将 'US' 转换为 'us_positions'
        for position in positions_data['data'][market_key]:
            if 'options' in position:
                symbol = market + "." + position['symbol']
                if symbol not in position_strikes:
                    position_strikes[symbol] = {'call': set(), 'put': set()}
                
                for option in position['options']:
                    strike = float(option['strike'])
                    if option['put_call'].upper() == 'CALL':
                        position_strikes[symbol]['call'].add(strike)
                    else:
                        position_strikes[symbol]['put'].add(strike)
        
        # 删除不需要的到价提醒
        removed_count = 0
        for code, alerts in price_alerts.items():
            if code in position_strikes:
                for alert in alerts:
                    price = alert['price']
                    if price not in position_strikes[code]['call'] and price not in position_strikes[code]['put']:
                        try:
                            # https://openapi.futunn.com/futu-api-doc/quote/set-price-reminder.html
                            ret, data = quote_ctx.set_price_reminder(
                                code=code,
                                key=int(alert['key']),
                                op=SetPriceReminderOp.DISABLE,
                                reminder_type=alert['type'],
                                reminder_freq=alert['freq'],
                                value=price
                            )
                            if ret != 0:
                                logger.error(f"DISABLE到价提醒失败 - 股票: {code}, 价格: {price}, 类型: {alert['type']}, 错误: {data}")
                            else:
                                removed_count += 1
                                stock_reminder_count[code][alert['type']] -= 1
                                logger.info(f"成功DISABLE到价提醒 - 股票: {code}, 价格: {price}, 类型: {alert['type']}")
                            # 删除操作后等待 0.5 秒
                            time.sleep(0.5)
                        except Exception as e:
                            logger.error(f"DISABLE到价提醒异常 - 股票: {code}, 价格: {price}, 类型: {alert['type']}\n"
                                      f"错误信息: {str(e)}\n堆栈信息: {traceback.format_exc()}")

        # 添加新的到价提醒
        added_count = 0
        request_count = 0
        last_request_time = time.time()
        
        for code, strikes in position_strikes.items():
            existing_prices = {a['price'] for a in price_alerts.get(code, [])}
            
            # 添加CALL期权的向上突破提醒
            for strike in strikes['call']:
                if strike not in existing_prices:
                    success, request_count, last_request_time = add_price_reminder(
                        quote_ctx, code, strike, PriceReminderType.PRICE_UP,
                        stock_reminder_count, request_count, last_request_time
                    )
                    if success:
                        added_count += 1
            
            # 添加PUT期权的向下突破提醒
            for strike in strikes['put']:
                if strike not in existing_prices:
                    success, request_count, last_request_time = add_price_reminder(
                        quote_ctx, code, strike, PriceReminderType.PRICE_DOWN,
                        stock_reminder_count, request_count, last_request_time
                    )
                    if success:
                        added_count += 1

        logger.info(f"到价提醒更新完成 - 添加: {added_count}个, 删除: {removed_count}个")
        
        return jsonify({
            'status': 'success',
            'data': {
                'added_count': added_count,
                'removed_count': removed_count
            },
            'message': f'更新成功，添加{added_count}个提醒，删除{removed_count}个提醒'
        })
        
    except Exception as e:
        error_msg = f"错误信息: {str(e)}\n堆栈信息: {traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'stack_trace': error_msg
        }), 500

@option_bp.route('/api/refresh_option_delta/<option_symbol>', methods=['POST'])
def refresh_option_delta(option_symbol):
    """手动刷新期权的delta值
    
    Args:
        option_symbol: 期权代码，例如 'NVDA250321C132000'
    """
    try:
        # 从富途网站获取最新delta值
        delta = get_delta_from_futu(option_symbol)
        
        if delta is not None:
            # 更新缓存
            db = USStockDatabase()
            db.cache_delta(option_symbol, delta)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'option_symbol': option_symbol,
                    'delta': delta
                }
            })
        else:
            # 改为返回 500 状态码，因为这是服务器端的处理问题
            return jsonify({
                'status': 'error',
                'message': f'获取期权 {option_symbol} 的delta值失败'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    
@option_bp.route('/api/refresh_all_deltas', methods=['POST'])
def refresh_all_deltas():
    """批量刷新所有持仓期权的delta值"""
    try:
        # 从tiger_routes获取当前持仓的期权列表
        from .tiger_routes import get_positions
        response = get_positions()
        positions_data = response.get_json()
        
        if positions_data['status'] != 'success':
            return jsonify({
                'status': 'error',
                'message': '获取持仓信息失败'
            }), 500
            
        # 收集所有期权的futu_symbol
        updated_options = []
        failed_options = []
        db = USStockDatabase()  # 将数据库连接移到循环外
        
        for market in ['us_positions']:
            for position in positions_data['data'][market]:
                if 'options' in position:
                    for option in position['options']:
                        if 'futu_symbol' in option:
                            try:
                                delta = refresh_option_delta(option['futu_symbol'])
                                if delta is not None:
                                    db.cache_delta(option['futu_symbol'], delta)
                                    updated_options.append({
                                        'symbol': option['futu_symbol'],
                                        'delta': delta
                                    })
                                else:
                                    failed_options.append({
                                        'symbol': option['futu_symbol'],
                                        'reason': '获取delta值失败'
                                    })
                            except Exception as e:
                                failed_options.append({
                                    'symbol': option['futu_symbol'],
                                    'reason': str(e)
                                })
        
        return jsonify({
            'status': 'success',
            'data': {
                'updated_options': updated_options,
                'failed_options': failed_options
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500