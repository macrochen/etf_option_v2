from flask import Blueprint, render_template, request, jsonify
from db.market_db import MarketDatabase
import logging

symbol_mapping_bp = Blueprint('symbol_mapping', __name__)
db = MarketDatabase()

@symbol_mapping_bp.route('/symbol_mapping')
def index():
    """渲染管理页面"""
    return render_template('symbol_mapping.html')

@symbol_mapping_bp.route('/api/symbol_mapping/list', methods=['GET'])
def get_mappings():
    """获取所有映射"""
    market = request.args.get('market')
    return jsonify(db.get_symbol_mappings(market))

@symbol_mapping_bp.route('/api/symbol_mapping/update', methods=['POST'])
def update_mapping():
    """新增或更新映射"""
    try:
        data = request.json
        symbol = data.get('symbol')
        market = data.get('market', 'HK')
        display_name = data.get('display_name')
        short_name = data.get('short_name')
        
        if not symbol or not display_name:
            return jsonify({'success': False, 'error': '代码和显示名称不能为空'}), 400
            
        db.update_symbol_mapping(symbol, market, display_name, short_name)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Update mapping error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@symbol_mapping_bp.route('/api/symbol_mapping/delete', methods=['POST'])
def delete_mapping():
    """删除映射"""
    try:
        data = request.json
        symbol = data.get('symbol')
        market = data.get('market')
        
        if not symbol or not market:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
            
        db.delete_symbol_mapping(symbol, market)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
