from flask import Blueprint, request, jsonify, render_template
from db.scheme_db import SchemeDatabase
from db.config import DB_CONFIG
import json
from utils.error_handler import api_error_handler, log_error

# 创建蓝图
scheme_bp = Blueprint('schemes', __name__)

# 创建数据库实例
scheme_db = SchemeDatabase(DB_CONFIG['backtest_schemes']['path'])

@scheme_bp.route('/api/schemes', methods=['GET'])
@api_error_handler
def get_schemes():
    """获取所有方案列表"""
    schemes = scheme_db.get_all_schemes()
    return jsonify({
        'status': 'success',
        'schemes': schemes
    })

@scheme_bp.route('/api/schemes/<int:scheme_id>', methods=['GET'])
@api_error_handler
def get_scheme(scheme_id):
    """获取单个方案详情"""
    scheme = scheme_db.get_scheme(scheme_id)
    if not scheme:
        return jsonify({
            'status': 'error',
            'message': '方案不存在'
        }), 404
    
    try:
        # 解析存储的JSON字符串
        params = json.loads(scheme['params']) if scheme['params'] else {}
        backtest_results = json.loads(scheme['results']) if scheme['results'] else {}
        
        # 构建参数对象，使用get方法安全地获取可选参数
        formatted_params = {
            'etf_code': params.get('etf_code', ''),  # 提供默认值
            'start_date': params.get('start_date', ''),
            'end_date': params.get('end_date', ''),
            'delta_list': params.get('delta_list', [])  # 默认空列表
        }
        
        return jsonify({
            'status': 'success',
            'params': formatted_params,
            'backtest_results': backtest_results
        })
    except json.JSONDecodeError as e:
        log_error(e, "解析方案数据时发生错误")
        return jsonify({
            'status': 'error',
            'message': '方案数据格式错误'
        }), 500

@scheme_bp.route('/api/schemes', methods=['POST'])
@api_error_handler
def create_scheme():
    """创建新方案"""
    data = request.get_json()
    
    # 验证必要字段
    if not all(k in data for k in ['name', 'params']):
        return jsonify({'status': 'error', 'message': '缺少必要字段'}), 400
    
    # 创建方案
    scheme_id = scheme_db.create_scheme(
        name=data['name'],
        params=json.dumps(data['params'], ensure_ascii=False),
        results=json.dumps(data.get('results', {}), ensure_ascii=False)
    )
    
    return jsonify({'status': 'success', 'scheme_id': scheme_id})

@scheme_bp.route('/api/schemes/<int:scheme_id>', methods=['PATCH'])
def update_scheme(scheme_id):
    """更新方案"""
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
    
    # 更新参数
    if 'params' in data:
        update_data['params'] = json.dumps(data['params'], ensure_ascii=False)
    
    # 更新名称
    if 'name' in data:
        update_data['name'] = data['name']  # 添加名称更新

    # 更新回测结果
    if 'results' in data:
        update_data['results'] = json.dumps(data['results'], ensure_ascii=False)  # 添加回测结果更新

    # 更新方案
    success = scheme_db.update_scheme(scheme_id, **update_data)
    
    if success:
        return jsonify({'status': 'success', 'message': '方案更新成功'}), 200
    else:
        return jsonify({'status': 'error', 'message': '方案更新失败'}), 500

@scheme_bp.route('/api/schemes/<int:scheme_id>', methods=['DELETE'])
@api_error_handler
def delete_scheme(scheme_id):
    """删除方案"""
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

@scheme_bp.route('/api/check_conditions_saved', methods=['POST'])
@api_error_handler
def check_conditions_saved():
    data = request.get_json()

    if not data:
        return jsonify({'status': 'error', 'message': '缺少参数'}), 400

    try:
        # 检查数据库中是否存在相同的参数
        existing_scheme = scheme_db.get_scheme_by_params(data)
        if existing_scheme:
            return jsonify({
                'status': 'exists',
                'message': f'方案参数已存在，是否要更新方案"{existing_scheme["name"]}"？',
                'existing_scheme_id': existing_scheme['id']
            }), 409  # 409 Conflict
        
        return jsonify({'status': 'success'}), 200 
    except Exception as e:
        error_msg = log_error(e, "检查方案参数时发生错误")
        return jsonify({'status': 'error', 'message': '服务器错误'}), 500 

@scheme_bp.route('/api/schemes/check_exists', methods=['POST'])
@api_error_handler
def check_scheme_exists():
    """检查方案名称是否已存在"""
    data = request.get_json()
    scheme_name = data.get('name')

    if not scheme_name:
        return jsonify({'status': 'error', 'message': '缺少方案名称'}), 400

    existing_scheme = scheme_db.get_scheme_by_name(scheme_name)
    if existing_scheme:
        return jsonify({
            'status': 'exists',
            'message': f'方案"{scheme_name}"已存在，是否要更新该方案？',
            'existing_scheme_id': existing_scheme['id']
        }), 409  # 409 Conflict

    return jsonify({'status': 'success'}), 200 

@scheme_bp.route('/scheme_management', methods=['GET'])
def scheme_management():
    """方案管理页面"""
    return render_template('scheme_management.html') 