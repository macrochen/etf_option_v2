from flask import Blueprint, jsonify
from futu import *
import logging
import traceback

from routes.tiger_routes import HK_STOCK_NAMES

futu_bp = Blueprint('futu', __name__)
# 在文件开头添加映射表
STOCK_NAME_MAPPING = {
    '中国平安': '平安',
    '腾讯控股': '腾讯',
    '安踏体育': '安踏',
    '携程集团': '携程',
    '比亚迪股份': '比亚迪',
    '美团-W': '美团',
    '京东集团-SW': '京东',
    '阿里巴巴-W': '阿里',
    '小米集团': '小米',
    '香港交易所': '港交所',
    '新鸿基地产': '新鸿基',
    # 可以根据需要添加更多映射
}

# 添加反向映射
OPTION_NAME_MAPPING = {v: k for k, v in STOCK_NAME_MAPPING.items()}
NAME_TO_CODE_MAPPING = {v: k for k, v in HK_STOCK_NAMES.items()}  # 使用 HK_STOCK_NAMES 创建反向映射


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

        # 处理所有持仓数据
        for _, pos in data.iterrows():
            if safe_float(pos['qty']) == 0:
                continue

            # 判断是否为期权
            is_option = ' ' in pos['stock_name']
            base_name = pos['stock_name']
            code = pos['code']
            
            
            # 计算盈亏百分比 - 使用API提供的pl_ratio
            pnl_percentage = float(pos['pl_ratio']) if pos['pl_ratio_valid'] else 0
            
            if is_option:
                # 从stock_name解析期权信息：例如 "安踏 250227 67.50 沽"
                option_parts = pos['stock_name'].split()
                if len(option_parts) >= 4:
                    base_name = option_parts[0]  # 平安
                    # base_name = OPTION_NAME_MAPPING.get(option_base_name, option_base_name)  # 转换为股票全称
                    expiry_date = option_parts[1]  # 250227
                    strike_price = option_parts[2]  # 67.50
                    option_type = option_parts[3]
                    
                    formatted_expiry = f"20{expiry_date[:2]}-{expiry_date[2:4]}-{expiry_date[4:]}"
            else:
                base_name = pos['stock_name']
            
            position_data = {
                'code': code,  # 股票代码 0700 表示腾讯
                'symbol': base_name,  # 使用基础股票名称
                'quantity': safe_float(pos['qty']),
                'average_cost': safe_float(pos['cost_price']) if pos['cost_price_valid'] else None,  # 持仓成本价
                'market_value': safe_float(pos['market_val']),  # 持仓市值
                'latest_price': safe_float(pos['nominal_price']),  # 最新价
                'unrealized_pnl': safe_float(pos['pl_val']),  # 未实现盈亏
                'unrealized_pnl_percentage': pnl_percentage,  # 盈亏百分比
                'realized_pnl': safe_float(pos['realized_pl']),  # 已实现盈亏
                'market': 'HK' if pos['code'].startswith('HK.') else 'US',
                'sec_type': 'OPT' if is_option else 'STK',
                'position_ratio': (safe_float(pos['market_val']) / total_market_value * 100) if total_market_value else 0,
                'daily_pnl': safe_float(pos['today_pl_val']),  # 今日盈亏
                'currency': pos['currency'],  # 货币类型
            }
            
            if is_option:
                position_data.update({
                    'strike': float(strike_price),
                    'expiry': formatted_expiry,
                    'put_call': option_type
                })
                
                # 添加到分组中
                full_name = OPTION_NAME_MAPPING.get(base_name, base_name)  # 转换为股票全称
                if full_name in grouped_positions:
                    grouped_positions[full_name]['options'].append(position_data)
                    group = grouped_positions[full_name]
                    group['total_market_value'] += position_data['market_value']
                    group['total_unrealized_pnl'] += position_data['unrealized_pnl']
                    group['total_realized_pnl'] += position_data['realized_pnl']
                    group['total_position_ratio'] += position_data['position_ratio']
                    group['total_daily_pnl'] += position_data['daily_pnl']
                else:
                    grouped_positions[full_name] = {
                        'symbol': full_name,
                        'code': NAME_TO_CODE_MAPPING.get(full_name),  # 使用反向映射获取代码
                        'stock': None,
                        'options': [position_data],
                        'market': position_data['market'],
                        'total_market_value': position_data['market_value'],
                        'total_unrealized_pnl': position_data['unrealized_pnl'],
                        'total_realized_pnl': position_data['realized_pnl'],
                        'is_group': True,
                        'total_position_ratio': position_data['position_ratio'],
                        'total_daily_pnl': 0
                    }
            else:
                # 检查是否有相关的期权持仓
                short_name = STOCK_NAME_MAPPING.get(base_name, base_name)
                has_options = any(
                    opt['stock_name'].split()[0] == short_name
                    for _, opt in data.iterrows() 
                    if ' ' in opt['stock_name']
                )
                
                if has_options:
                    if base_name not in grouped_positions:
                        grouped_positions[base_name] = {
                            'symbol': base_name,
                            'code': NAME_TO_CODE_MAPPING.get(base_name),  # 使用反向映射获取代码
                            'stock': position_data,
                            'options': [],
                            'market': position_data['market'],
                            'total_market_value': position_data['market_value'],
                            'total_unrealized_pnl': position_data['unrealized_pnl'],
                            'total_realized_pnl': position_data['realized_pnl'],
                            'is_group': True,
                            'total_position_ratio': position_data['position_ratio'],
                            'total_daily_pnl': 0
                        }
                    else:
                        group = grouped_positions[base_name]
                        group['total_market_value'] += position_data['market_value']
                        group['total_unrealized_pnl'] += position_data['unrealized_pnl']
                        group['total_realized_pnl'] += position_data['realized_pnl']
                        group['total_position_ratio'] += position_data['position_ratio']
                        group['total_daily_pnl'] += position_data['daily_pnl']
                        group['stock'] = position_data
                else:
                    ungrouped_positions.append(position_data)
        
        # 合并分组和非分组数据
        final_positions = list(grouped_positions.values()) + ungrouped_positions
        
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