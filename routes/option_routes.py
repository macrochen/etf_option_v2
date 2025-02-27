from flask import Blueprint, jsonify
from utils.futu_option import get_delta_from_futu,get_option_delta_with_cached
from db.us_stock_db import USStockDatabase

option_bp = Blueprint('option', __name__)

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
                                delta = get_option_delta_with_cached(option['futu_symbol'])
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