from flask import Blueprint, jsonify, request
from utils.futu_data_service import create_sim_trade, get_sim_positions, close_sim_position
import logging
import traceback

sim_trade_bp = Blueprint('sim_trade', __name__)

@sim_trade_bp.route('/api/sim_positions')
def get_positions():
    """获取模拟持仓信息"""
    try:
        result = get_sim_positions()
        return jsonify(result)
    except Exception as e:
        logging.error(f"获取模拟持仓失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@sim_trade_bp.route('/api/sim_trade', methods=['POST'])
def create_trade():
    """创建模拟交易"""
    try:
        trade_data = request.json
        trade_type = trade_data.get('type')
        
        # 根据交易类型检查必填字段
        if trade_type == 'stock':
            required_fields = ['type', 'symbol', 'market', 'direction', 'quantity', 'price']
        elif trade_type == 'option':
            required_fields = ['type', 'underlying', 'market', 'direction', 'quantity', 'price',
                             'expiry', 'strike', 'optionType']
        else:
            return jsonify({
                'status': 'error',
                'message': '无效的交易类型，必须是 stock 或 option'
            }), 400
        
        # 检查必填字段
        missing_fields = [field for field in required_fields if field not in trade_data]
        if missing_fields:
            return jsonify({
                'status': 'error',
                'message': f'缺少必填字段: {", ".join(missing_fields)}'
            }), 400
        
        result = create_sim_trade(trade_data)
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"创建模拟交易失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@sim_trade_bp.route('/api/sim_trade/<int:position_id>', methods=['DELETE'])
def close_trade(position_id):
    """关闭模拟交易持仓"""
    try:
        result = close_sim_position(position_id)
        return jsonify(result)
    except Exception as e:
        logging.error(f"关闭模拟持仓失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500