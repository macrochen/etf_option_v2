from flask import Blueprint, request, jsonify
from db.scheme_db import SchemeDatabase
from db.config import DB_CONFIG
import json
import traceback
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('backtest.log')
    ]
)
logger = logging.getLogger(__name__)

# 创建蓝图
scheme_bp = Blueprint('schemes', __name__)

# 创建数据库实例
scheme_db = SchemeDatabase(DB_CONFIG['backtest_schemes']['path'])

@scheme_bp.route('/api/schemes', methods=['GET'])
def get_schemes():
    """获取所有方案列表"""
    try:
        schemes = scheme_db.get_all_schemes()
        return jsonify({
            'status': 'success',
            'schemes': schemes
        })
    except Exception as e:
        error_msg = f"获取方案列表失败: {str(e)}\n堆栈信息:\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@scheme_bp.route('/api/schemes/<int:scheme_id>', methods=['GET'])
def get_scheme(scheme_id):
    """获取单个方案详情"""
    try:
        scheme = scheme_db.get_scheme(scheme_id)
        if not scheme:
            return jsonify({
                'status': 'error',
                'message': '方案不存在'
            }), 404
            
        return jsonify({
            'status': 'success',
            'scheme': scheme
        })
    except Exception as e:
        error_msg = f"获取方案详情失败: {str(e)}\n堆栈信息:\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@scheme_bp.route('/api/schemes', methods=['POST'])
def create_scheme():
    """创建新方案"""
    try:
        data = request.get_json()
        
        # 验证必要字段
        if not all(k in data for k in ['name', 'params']):
            return jsonify({
                'status': 'error',
                'message': '缺少必要字段'
            }), 400
            
        # 将参数转换为JSON字符串
        params_json = json.dumps(data['params'], ensure_ascii=False)
        results_json = json.dumps(data.get('results', {}), ensure_ascii=False)
        
        # 创建方案
        scheme_id = scheme_db.create_scheme(
            name=data['name'],
            params=params_json,
            results=results_json
        )
        
        return jsonify({
            'status': 'success',
            'scheme_id': scheme_id
        })
    except Exception as e:
        error_msg = f"创建方案失败: {str(e)}\n堆栈信息:\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@scheme_bp.route('/api/schemes/<int:scheme_id>', methods=['PATCH'])
def update_scheme(scheme_id):
    """更新方案"""
    try:
        data = request.get_json()
        
        # 检查方案是否存在
        scheme = scheme_db.get_scheme(scheme_id)
        if not scheme:
            return jsonify({
                'status': 'error',
                'message': '方案不存在'
            }), 404
            
        # 准备更新数据
        update_data = {}
        if 'name' in data:
            update_data['name'] = data['name']
        if 'params' in data:
            update_data['params'] = json.dumps(data['params'], ensure_ascii=False)
        if 'results' in data:
            update_data['results'] = json.dumps(data['results'], ensure_ascii=False)
            
        # 更新方案
        success = scheme_db.update_scheme(scheme_id, **update_data)
        
        if not success:
            return jsonify({
                'status': 'error',
                'message': '更新失败'
            }), 500
            
        return jsonify({
            'status': 'success'
        })
    except Exception as e:
        error_msg = f"更新方案失败: {str(e)}\n堆栈信息:\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@scheme_bp.route('/api/schemes/<int:scheme_id>', methods=['DELETE'])
def delete_scheme(scheme_id):
    """删除方案"""
    try:
        # 检查方案是否存在
        scheme = scheme_db.get_scheme(scheme_id)
        if not scheme:
            return jsonify({
                'status': 'error',
                'message': '方案不存在'
            }), 404
            
        # 删除方案
        success = scheme_db.delete_scheme(scheme_id)
        
        if not success:
            return jsonify({
                'status': 'error',
                'message': '删除失败'
            }), 500
            
        return jsonify({
            'status': 'success'
        })
    except Exception as e:
        error_msg = f"删除方案失败: {str(e)}\n堆栈信息:\n{traceback.format_exc()}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500 