from flask import Blueprint, jsonify, request
from utils.futu_data_service import get_delta_from_futu,update_prev_close_price,FutuBlockedException
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
        logging.FileHandler('logs/option_routes.log'),  # 修改为相对路径
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

option_bp = Blueprint('option', __name__)


def add_price_reminder(quote_ctx, code, strike, reminder_type, stock_reminder_count, 
                      request_count, last_request_time, expiry_date=None, quantity=0):
    """添加到价提醒的通用函数
    
    Args:
        quote_ctx: 富途API上下文
        code: 股票代码
        strike: 行权价
        reminder_type: 提醒类型（向上/向下）
        stock_reminder_count: 每只股票的提醒计数
        request_count: 当前请求计数
        last_request_time: 上次请求时间
        expiry_date: 期权到期日（可选）
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
        expiry_info = f" ({expiry_date})" if expiry_date else ""
        quantity_info = f" {quantity}" if quantity else ""
        
        ret, data = quote_ctx.set_price_reminder(
            code=code,
            reminder_type=reminder_type,
            reminder_freq=PriceReminderFreq.ONCE_A_DAY,
            value=strike,
            op=SetPriceReminderOp.ADD,
            note=f"{quantity_info} {option_type} {expiry_info}"
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

@option_bp.route('/api/delete_stock_alerts/<symbol>', methods=['DELETE'])
def delete_stock_alerts(symbol):
    """删除指定股票的所有到价提醒"""
    try:
        quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        try:
            stock_code = f"US.{symbol}"
            # 直接获取指定股票的到价提醒
            ret, data = quote_ctx.get_price_reminder(code=stock_code)
            if ret != 0:
                raise Exception(f"获取到价提醒失败: {data}")
            
            deleted_count = 0
            if isinstance(data, pd.DataFrame) and not data.empty:
                for _, alert in data.iterrows():
                    ret, resp = quote_ctx.set_price_reminder(
                        code=stock_code,
                        key=int(alert['key']),
                        op=SetPriceReminderOp.DEL,
                        reminder_type=alert['reminder_type'],
                        reminder_freq=alert['reminder_freq'],
                        value=float(alert['value'])
                    )
                    if ret == 0:
                        deleted_count += 1
                        logger.info(f"成功删除到价提醒 - 股票: {symbol}, key: {alert['key']}, 价格: {alert['value']}")
                    else:
                        logger.error(f"删除到价提醒失败 - 股票: {symbol}, key: {alert['key']}, 错误: {resp}")
                    time.sleep(0.5)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'symbol': symbol,
                    'deleted_count': deleted_count
                },
                'message': f'成功删除 {deleted_count} 个到价提醒'
            })
            
        finally:
            quote_ctx.close()
            
    except Exception as e:
        error_msg = f"删除到价提醒失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'stack_trace': error_msg
        }), 500


def get_existing_alerts(quote_ctx, market):
    """获取现有的到价提醒"""
    ret, data = quote_ctx.get_price_reminder(market=TrdMarket.US if market == 'US' else TrdMarket.HK)
    if ret != 0:
        raise Exception(f"获取到价提醒失败: {data}")
    
    stock_reminder_count = defaultdict(lambda: defaultdict(int))
    price_alerts = {}
    
    if isinstance(data, pd.DataFrame):
        for _, row in data.iterrows():
            stock_reminder_count[row.code][row.reminder_type] += 1
            
            
            code = row.code
            if code not in price_alerts:
                price_alerts[code] = []
            price_alerts[code].append({
                'price': float(row.value),
                'key': row.key,
                'type': row.reminder_type,
                'freq': row.reminder_freq
            })
    
    return stock_reminder_count, price_alerts

def get_position_strikes(positions_data, market, is_futu):
    """整理持仓期权数据"""
    position_strikes = {}
    market_key = f"{market.lower()}_positions"
    
    for position in positions_data['data'][market_key]:
        if 'options' in position:
            if is_futu:
                symbol = market + "." + position['code']
            else:
                symbol = market + "." + position['symbol']

            if symbol not in position_strikes:
                position_strikes[symbol] = {'call': {}, 'put': {}}
            
            for option in position['options']:
                strike = float(option['strike'])
                expiry_date = option.get('expiry')
                quantity = option.get('quantity', 0)  # 获取期权数量

                if quantity == 0:
                    continue
                
                # 根据是否是富途持仓和市场类型来判断期权类型
                if is_futu and market == 'HK':
                    is_call = option['put_call'] == '购'
                else:
                    is_call = option['put_call'].upper() == 'CALL'
                    
                if is_call:
                    position_strikes[symbol]['call'][strike] = {'expiry': expiry_date, 'quantity': quantity}
                else:
                    position_strikes[symbol]['put'][strike] = {'expiry': expiry_date, 'quantity': quantity}
    
    return position_strikes

def delete_alerts(quote_ctx, code, alerts, position_strikes, stock_reminder_count):
    """删除不需要的到价提醒"""
    removed_count = 0
    
    if code not in position_strikes:
        # 删除非持仓股票的所有提醒
        for alert in alerts:
            try:
                ret, data = quote_ctx.set_price_reminder(
                    code=code,
                    key=alert['key'],
                    op=SetPriceReminderOp.DEL,
                    reminder_type=alert['type'],
                    reminder_freq=alert['freq'],
                    value=float(alert['price'])
                )
                if ret == 0:
                    removed_count += 1
                    stock_reminder_count[code][alert['type']] -= 1
                    logger.info(f"成功删除非持仓股票的到价提醒 - 股票: {code}, key: {alert['key']}, 价格: {alert['price']}")
                else:
                    logger.error(f"删除非持仓股票的到价提醒失败 - 股票: {code}, key: {alert['key']}, 错误: {data}")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"删除非持仓股票的到价提醒异常 - 股票: {code}, key: {alert['key']}\n"
                          f"错误信息: {str(e)}\n堆栈信息: {traceback.format_exc()}")
    else:
        # 删除持仓股票的不匹配提醒
        for alert in alerts:
            price = alert['price']
            if price not in position_strikes[code]['call'] and price not in position_strikes[code]['put']:
                try:
                    ret, data = quote_ctx.set_price_reminder(
                        code=code,
                        key=alert['key'],
                        op=SetPriceReminderOp.DEL,
                        reminder_type=alert['type'],
                        reminder_freq=alert['freq'],
                        value=float(price)
                    )
                    if ret == 0:
                        removed_count += 1
                        stock_reminder_count[code][alert['type']] -= 1
                        logger.info(f"成功删除到价提醒 - 股票: {code}, key: {alert['key']}, 价格: {price}")
                    else:
                        logger.error(f"删除到价提醒失败 - 股票: {code}, key: {alert['key']}, 价格: {price}, 错误: {data}")
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"删除到价提醒异常 - 股票: {code}, key: {alert['key']}, 价格: {price}\n"
                              f"错误信息: {str(e)}\n堆栈信息: {traceback.format_exc()}")
    
    return removed_count

@option_bp.route('/api/update_price_alerts', methods=['POST'])
def update_price_alerts():
    """更新到价提醒"""
    try:
        market = request.json.get('market', 'US')
        is_futu = request.json.get('is_futu', False)
        quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        
        # 获取现有提醒
        stock_reminder_count, price_alerts = get_existing_alerts(quote_ctx, market)
        
        # 获取当前持仓信息
        # 根据 is_futu 参数决定从哪里获取持仓信息
        if is_futu:
            from .futu_routes import get_futu_positions
            response = get_futu_positions()
        else:
            from .tiger_routes import get_positions
            response = get_positions()

        positions_data = response.get_json()
        
        if positions_data['status'] != 'success':
            raise Exception('获取持仓信息失败')
        
        # 整理持仓数据
        position_strikes = get_position_strikes(positions_data, market, is_futu)
        
        # 删除不需要的提醒
        removed_count = 0
        for code, alerts in price_alerts.items():
            removed_count += delete_alerts(quote_ctx, code, alerts, position_strikes, stock_reminder_count)
        
        # 添加新的提醒
        added_count = 0
        request_count = 0
        last_request_time = time.time()
        
        # 在 update_price_alerts 函数中
        for code, strikes in position_strikes.items():
            existing_prices = {a['price'] for a in price_alerts.get(code, [])}
            
            # 添加CALL期权的向上突破提醒
            for strike, info in strikes['call'].items():
                if strike not in existing_prices:
                    success, request_count, last_request_time = add_price_reminder(
                        quote_ctx, code, strike, PriceReminderType.PRICE_UP,
                        stock_reminder_count, request_count, last_request_time,
                        expiry_date=info['expiry'],
                        quantity=info['quantity']
                    )
                    if success:
                        added_count += 1
            
            # 添加PUT期权的向下突破提醒
            for strike, info in strikes['put'].items():
                if strike not in existing_prices:
                    success, request_count, last_request_time = add_price_reminder(
                        quote_ctx, code, strike, PriceReminderType.PRICE_DOWN,
                        stock_reminder_count, request_count, last_request_time,
                        expiry_date=info['expiry'],
                        quantity=info['quantity']
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
    

@option_bp.route('/api/refresh_all_prev_close', methods=['POST'])
def refresh_all_prev_close():
    """批量更新所有持仓股票和期权的前一日收盘价"""
    try:
        logger.info("开始批量更新前收价...")
        # 从tiger_routes获取当前持仓的股票列表
        from .tiger_routes import get_positions
        response = get_positions()
        positions_data = response.get_json()
        
        if positions_data['status'] != 'success':
            return jsonify({
                'status': 'error',
                'message': '获取持仓信息失败'
            }), 500
            
        # 收集所有股票代码和市场
        market_symbol_dict = {'US': []}
        # 收集所有期权代码（使用相同的数据结构）
        option_symbol_dict = {'US': []}
        
        # 处理美股持仓
        for position in positions_data['data']['us_positions']:
            # 处理股票
            symbol = position.get('symbol')
            if symbol:
                market_symbol_dict['US'].append(symbol)
            
            # 处理期权
            if 'options' in position:
                for option in position['options']:
                    if 'futu_symbol' in option:
                        option_symbol_dict['US'].append(option['futu_symbol'])
        
        # 查询数据库中缺失前收价的股票和期权（使用同一个接口）
        db = USStockDatabase()
        missing_symbols = db.get_symbols_without_prev_close(market_symbol_dict)
        missing_options = db.get_symbols_without_prev_close(option_symbol_dict)
        
        # 更新缺失的前收价
        updated_stocks = []
        failed_stocks = []
        updated_options = []
        failed_options = []
        
        # 更新股票前收价
        total_stocks = len(missing_symbols)
        logger.info(f"开始更新股票前收价，共 {total_stocks} 个股票需要更新")
        
        for index, (symbol, market) in enumerate(missing_symbols, 1):
            logger.info(f"正在更新股票 [{index}/{total_stocks}] {market}.{symbol} 的前收价")
            try:
                success = update_prev_close_price(symbol, market)
                if success:
                    updated_stocks.append({
                        'symbol': symbol,
                        'market': market
                    })
                    logger.info(f"[{index}/{total_stocks}] {market}.{symbol} 更新成功")
                else:
                    failed_stocks.append({
                        'symbol': symbol,
                        'market': market,
                        'reason': '获取前收价失败'
                    })
                    logger.warning(f"[{index}/{total_stocks}] {market}.{symbol} 更新失败")
            except FutuBlockedException as e:
                logger.error(f"富途请求被屏蔽，终止批量处理: {str(e)}")
                return jsonify({
                    'status': 'partial_success',
                    'data': {
                        'stocks': {
                            'total': len(market_symbol_dict['US']),
                            'updated': updated_stocks,
                            'failed': failed_stocks,
                            'remaining': [
                                {'symbol': sym, 'market': mkt}
                                for sym, mkt in missing_symbols[index:]
                            ]
                        },
                        'options': {
                            'total': len(option_symbol_dict['US']),
                            'updated': updated_options,
                            'failed': failed_options,
                            'remaining': missing_options
                        }
                    },
                    'message': f'富途请求被屏蔽，已处理 {len(updated_stocks)}/{total_stocks} 个股票，'
                             f'期权尚未开始处理'
                })
            except Exception as e:
                failed_stocks.append({
                    'symbol': symbol,
                    'market': market,
                    'reason': str(e)
                })
        
        # 更新期权前收价
        total_options = len(missing_options)
        logger.info(f"开始更新期权前收价，共 {total_options} 个期权需要更新")
        
        for index, (option_symbol, market) in enumerate(missing_options, 1):
            logger.info(f"正在更新期权 [{index}/{total_options}] {option_symbol} 的前收价")
            try:
                success = update_prev_close_price(option_symbol, market, is_option=True)
                if success:
                    updated_options.append({
                        'symbol': option_symbol,
                        'market': market
                    })
                    logger.info(f"[{index}/{total_options}] {option_symbol} 更新成功")
                else:
                    failed_options.append({
                        'symbol': option_symbol,
                        'market': market,
                        'reason': '获取前收价失败'
                    })
                    logger.warning(f"[{index}/{total_options}] {option_symbol} 更新失败")
            except FutuBlockedException as e:
                logger.error(f"富途请求被屏蔽，终止批量处理: {str(e)}")
                return jsonify({
                    'status': 'partial_success',
                    'data': {
                        'stocks': {
                            'total': len(market_symbol_dict['US']),
                            'updated': updated_stocks,
                            'failed': failed_stocks
                        },
                        'options': {
                            'total': len(option_symbol_dict['US']),
                            'updated': updated_options,
                            'failed': failed_options,
                            'remaining': [
                                {'symbol': sym, 'market': mkt}
                                for sym, mkt in missing_options[index:]
                            ]
                        }
                    },
                    'message': f'富途请求被屏蔽，股票已完成更新，期权已处理 {len(updated_options)}/{total_options} 个'
                })
            except Exception as e:
                failed_options.append({
                    'symbol': option_symbol,
                    'reason': str(e)
                })
        
        logger.info(f"批量更新完成，股票：成功 {len(updated_stocks)} 个，失败 {len(failed_stocks)} 个；"
                   f"期权：成功 {len(updated_options)} 个，失败 {len(failed_options)} 个")
        
        return jsonify({
            'status': 'success',
            'data': {
                'stocks': {
                    'total': len(market_symbol_dict['US']),
                    'updated': updated_stocks,
                    'failed': failed_stocks
                },
                'options': {
                    'total': len(option_symbol_dict['US']),
                    'updated': updated_options,
                    'failed': failed_options
                }
            },
            'message': f'更新完成：股票总数 {len(market_symbol_dict["US"])} 个，'
                      f'成功 {len(updated_stocks)} 个，失败 {len(failed_stocks)} 个；'
                      f'期权总数 {len(option_symbol_dict["US"])} 个，'
                      f'成功 {len(updated_options)} 个，失败 {len(failed_options)} 个'
        })
        
    except Exception as e:
        error_msg = f"更新前收价失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'stack_trace': error_msg
        }), 500

@option_bp.route('/api/refresh_all_deltas', methods=['POST'])
def refresh_all_deltas():
    """批量刷新所有持仓期权的delta值"""
    try:
        logger.info("开始批量更新期权delta值...")
        
        # 从tiger_routes获取当前持仓的期权列表
        from .tiger_routes import get_positions
        from utils.futu_data_service import FutuBlockedException
        
        logger.info("正在获取持仓信息...")
        response = get_positions()
        positions_data = response.get_json()
        
        if positions_data['status'] != 'success':
            return jsonify({
                'status': 'error',
                'message': '获取持仓信息失败'
            }), 500
        
        # 收集所有期权的futu_symbol
        all_options = []
        for market in ['us_positions']:
            for position in positions_data['data'][market]:
                if 'options' in position:
                    all_options.extend([
                        opt['futu_symbol'] for opt in position['options']
                        if 'futu_symbol' in opt
                    ])
        
        total_count = len(all_options)
        logger.info(f"共找到 {total_count} 个期权需要更新delta值")
        
        updated_options = []
        failed_options = []
        db = USStockDatabase()
        
        for index, option_symbol in enumerate(all_options, 1):
            logger.info(f"正在更新 [{index}/{total_count}] {option_symbol} 的delta值")
            try:
                delta = get_delta_from_futu(option_symbol)
                if delta is not None:
                    db.cache_delta(option_symbol, delta)
                    updated_options.append({
                        'symbol': option_symbol,
                        'delta': delta
                    })
                    logger.info(f"[{index}/{total_count}] {option_symbol} 更新成功，delta = {delta}")
                else:
                    failed_options.append({
                        'symbol': option_symbol,
                        'reason': '获取delta值失败'
                    })
                    logger.warning(f"[{index}/{total_count}] {option_symbol} 更新失败")
            except FutuBlockedException as e:
                # 如果检测到被屏蔽，立即返回已处理的结果
                logger.error(f"富途请求被屏蔽，终止批量处理: {str(e)}")
                return jsonify({
                    'status': 'partial_success',
                    'data': {
                        'updated_options': updated_options,
                        'failed_options': failed_options,
                        'remaining_options': all_options[index:]
                    },
                    'message': f'富途请求被屏蔽，已处理 {len(updated_options)} 个期权，'
                             f'失败 {len(failed_options)} 个'
                             f'剩余未处理 {len(all_options) - index} 个'
                })
            except Exception as e:
                failed_options.append({
                    'symbol': option_symbol,
                    'reason': str(e)
                })
                logger.error(f"[{index}/{total_count}] {option_symbol} 更新出错: {str(e)}")
        
        logger.info(f"批量更新完成，成功 {len(updated_options)} 个，失败 {len(failed_options)} 个")
        return jsonify({
            'status': 'success',
            'data': {
                'updated_options': updated_options,
                'failed_options': failed_options
            },
            'message': f'成功更新 {len(updated_options)} 个期权的delta值，'
                      f'失败 {len(failed_options)} 个'
        })
        
    except Exception as e:
        error_msg = f"批量更新delta值失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'stack_trace': error_msg
        }), 500