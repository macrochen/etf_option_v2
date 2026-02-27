from flask import Blueprint, jsonify
from futu import *
import logging
import traceback

from db.market_db import MarketDatabase

futu_bp = Blueprint('futu', __name__)

def get_name_mappings():
    db = MarketDatabase()
    return {
        'hk_names': db.get_symbol_mapping_dict('HK'),
        'short_names': db.get_full_to_short_name_mapping('HK')
    }

@futu_bp.route('/api/futu_positions')
def get_futu_positions():
    """获取富途持仓信息"""
    try:
        trd_ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.HK, host='127.0.0.1', port=11111,
                                      security_firm=SecurityFirm.FUTUSECURITIES)
        ret, data = trd_ctx.position_list_query()
        
        if ret != RET_OK:
            raise Exception(f"获取持仓列表失败: {data}")
        
        # 创建按标的分组的字典和非分组列表
        grouped_positions = {}
        ungrouped_positions = []
        
        # 计算总市值（用于计算持仓占比）
        total_market_value = sum(float(pos['market_val']) for _, pos in data.iterrows())
        
        # 添加一个安全的转换函数
        def safe_float(value, default=0.0):
            try:
                return float(value) if value != 'N/A' else default
            except (ValueError, TypeError):
                return default

        # 获取最新的名称映射
        mappings = get_name_mappings()
        hk_names = mappings['hk_names']        # code -> full_name (e.g. '00700': '腾讯控股')
        short_names = mappings['short_names']  # full_name -> short_name (e.g. '腾讯控股': '腾讯')
        
        # 反向映射用于处理期权和分组
        full_names_from_short = {v: k for k, v in short_names.items()}
        code_from_full = {v: k for k, v in hk_names.items()}

        # 处理所有持仓数据
        for _, pos in data.iterrows():
            if safe_float(pos['qty']) == 0:
                continue
            
            raw_stock_name = pos['stock_name']
            is_option = ' ' in raw_stock_name
            
            # 港股名称处理逻辑改进
            if pos['code'].startswith('HK.'):
                if is_option:
                    # 期权处理逻辑： "腾讯 250227 400.00 购"
                    option_parts = raw_stock_name.split()
                    short_name_in_option = option_parts[0]
                    
                    # 关键修复：通过映射链反查数字代码
                    # 简称 -> 全称 -> 数字代码
                    full_name = full_names_from_short.get(short_name_in_option, short_name_in_option)
                    numeric_code = code_from_full.get(full_name)
                    
                    base_name = full_name
                    # 如果找不到数字代码，numeric_code 为 None，此时 underlying_code 会包含 [待配置]
                    underlying_code = numeric_code if numeric_code else f"[待配置] {short_name_in_option}"
                    
                    expiry_date = option_parts[1]
                    strike_price = option_parts[2]
                    option_type = option_parts[3]
                    formatted_expiry = f"20{expiry_date[:2]}-{expiry_date[2:4]}-{expiry_date[4:]}"
                else:
                    # 股票处理逻辑：直接从代码提取数字部分
                    underlying_code = pos['code'][3:]
                    base_name = hk_names.get(underlying_code, f"[待配置] {underlying_code}")
            else:
                base_name = raw_stock_name
                underlying_code = pos['code']

            # 计算盈亏百分比
            pnl_percentage = float(pos['pl_ratio']) if pos['pl_ratio_valid'] else 0
            
            position_data = {
                'code': pos['code'],
                'symbol': base_name,
                'hk_symbol': underlying_code, 
                'quantity': safe_float(pos['qty']),
                'average_cost': safe_float(pos['cost_price']) if pos['cost_price_valid'] else None,
                'market_value': safe_float(pos['market_val']),
                'latest_price': safe_float(pos['nominal_price']),
                'unrealized_pnl': safe_float(pos['pl_val']),
                'unrealized_pnl_percentage': pnl_percentage,
                'realized_pnl': safe_float(pos['realized_pl']),
                'market': 'HK' if pos['code'].startswith('HK.') else 'US',
                'sec_type': 'OPT' if is_option else 'STK',
                'position_ratio': (safe_float(pos['market_val']) / total_market_value * 100) if total_market_value else 0,
                'daily_pnl': safe_float(pos['today_pl_val']),
                'currency': pos['currency'],
            }
            
            if is_option:
                position_data.update({
                    'strike': float(strike_price),
                    'expiry': formatted_expiry,
                    'put_call': option_type
                })
                
                # 添加到分组
                if base_name in grouped_positions:
                    group = grouped_positions[base_name]
                    group['options'].append(position_data)
                    group['total_market_value'] += position_data['market_value']
                    group['total_unrealized_pnl'] += position_data['unrealized_pnl']
                    group['total_realized_pnl'] += position_data['realized_pnl']
                    group['total_position_ratio'] += position_data['position_ratio']
                    group['total_daily_pnl'] += position_data['daily_pnl']
                else:
                    grouped_positions[base_name] = {
                        'symbol': base_name,
                        'code': underlying_code, 
                        'stock': None,
                        'options': [position_data],
                        'market': position_data['market'],
                        'total_market_value': position_data['market_value'],
                        'total_unrealized_pnl': position_data['unrealized_pnl'],
                        'total_realized_pnl': position_data['realized_pnl'],
                        'is_group': True,
                        'total_position_ratio': position_data['position_ratio'],
                        'total_daily_pnl': position_data['daily_pnl']
                    }
            else:
                # 股票处理逻辑
                if base_name not in grouped_positions:
                    grouped_positions[base_name] = {
                        'symbol': base_name,
                        'code': underlying_code,
                        'stock': position_data,
                        'options': [],
                        'market': position_data['market'],
                        'total_market_value': position_data['market_value'],
                        'total_unrealized_pnl': position_data['unrealized_pnl'],
                        'total_realized_pnl': position_data['realized_pnl'],
                        'is_group': True,
                        'total_position_ratio': position_data['position_ratio'],
                        'total_daily_pnl': position_data['daily_pnl']
                    }
                else:
                    group = grouped_positions[base_name]
                    group['total_market_value'] += position_data['market_value']
                    group['total_unrealized_pnl'] += position_data['unrealized_pnl']
                    group['total_realized_pnl'] += position_data['realized_pnl']
                    group['total_position_ratio'] += position_data['position_ratio']
                    group['total_daily_pnl'] += position_data['daily_pnl']
                    group['stock'] = position_data
        
        # 移出未分组的股票（如果有的话，目前都在分组里处理了）
        final_positions = list(grouped_positions.values())
        
        # 对期权进行排序的辅助函数
        def option_sort_key(option):
            expiry = option['expiry'].replace('-', '')  # 转换为 YYYYMMDD 格式
            strike_price = float(option['strike'])
            option_type = option['put_call']
            # 购（认购）排在沽（认沽）前面
            type_order = 0 if option_type == '购' else 1
            return (expiry, type_order, -strike_price)
        
        # 对每个分组内的期权进行排序
        for position in final_positions:
            if position.get('is_group') and position.get('options'):
                position['options'].sort(key=option_sort_key)
        
        # 分别对美股和港股持仓进行排序（按symbol）
        us_positions = sorted([p for p in final_positions if p.get('market') == 'US'], 
                            key=lambda x: x['symbol'])
        hk_positions = sorted([p for p in final_positions if p.get('market') == 'HK'], 
                            key=lambda x: x['symbol'])
        
        return jsonify({
            'status': 'success',
            'data': {
                'us_positions': us_positions,
                'hk_positions': hk_positions,
            }
        })
            
    except Exception as e:
        logging.error(f"获取富途持仓失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500    
    finally:
        trd_ctx.close()
