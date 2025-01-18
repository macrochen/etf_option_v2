from flask import Blueprint, request, jsonify
from backtest_engine import BacktestEngine
from strategies import StrategyContextFactory, BacktestConfig
from strategies.types import TradeRecord, PortfolioValue, BacktestResult
from visualization import format_backtest_result
from strategy_analyzer import StrategyAnalyzer
from logger import TradeLogger
from db.scheme_db import SchemeDatabase
from db.config import DB_CONFIG
import json
import plotly
from typing import Dict, Any, List
from datetime import datetime
from models.scheme_model import SchemeModel
from utils.error_handler import api_error_handler, log_error

# 创建蓝图
backtest_bp = Blueprint('backtest', __name__)

# 创建数据库实例
scheme_db = SchemeDatabase(DB_CONFIG['backtest_schemes']['path'])

@backtest_bp.route('/api/backtest', methods=['POST'])
@api_error_handler
def run_backtest():
    data = request.get_json()
    
    # 检查是否需要保存方案
    save_scheme = data.pop('save_scheme', False)
    scheme_id = data.pop('scheme_id', None)  # 获取方案 ID
    scheme_name = data.get('scheme_name')  # 获取方案名称
    
    # 解析和验证参数
    # 可以传递backtest_config参数，以便自定义回测配置
    context = StrategyContextFactory.create_context(data)  # 这里会自动验证参数

    # 创建回测引擎
    engine = BacktestEngine(BacktestConfig())
    
    # 执行回测
    result = engine.run_backtest(context)

    if not result:
        error_msg = "回测执行失败，未返回结果"
        # 注解: 回测执行失败，返回错误信息
        return jsonify({'error': error_msg}), 400

    # 格式化结果
    formatted_result = format_backtest_result(result)
    
    # 如果需要保存方案
    if save_scheme:
        if scheme_id:  # 更新已有方案
            update_scheme(scheme_id, context.to_dict(), formatted_result)
        else:  # 创建新方案
            create_scheme(scheme_name, context.to_dict(), formatted_result)
        
    return jsonify(formatted_result)

def update_scheme(scheme_id, params, results):
    """更新方案时的数据处理"""
    # 确保参数格式统一
    formatted_params = {
        'etf_code': params.get('etf_code'),
        'start_date': params.get('start_date'),
        'end_date': params.get('end_date'),
        'delta_list': params.get('delta_list', []),  # 确保包含 delta_list
        'strategy_params': params.get('strategy_params', {})  # 保存策略参数
    }
    
    # 移除空值，但保留空列表
    formatted_params = {k: v for k, v in formatted_params.items() 
                       if v is not None and (not isinstance(v, (list, dict)) or v)}
    
    # 处理日期时间对象
    for key, value in formatted_params.items():
        if isinstance(value, datetime):
            formatted_params[key] = value.strftime('%Y-%m-%d')
    
    # 更新方案
    scheme_db.update_scheme(
        scheme_id,
        params=json.dumps(formatted_params, ensure_ascii=False),
        results=json.dumps(results, ensure_ascii=False)
    )

def create_scheme(name, params, results):
    """创建新方案时的数据处理"""
    # 确保参数格式统一
    formatted_params = {
        'etf_code': params.get('etf_code'),
        'start_date': params.get('start_date'),
        'end_date': params.get('end_date'),
        'strategy_params': params.get('strategy_params', {}),
        'delta_list': params.get('delta_list', [])
    }
    
    # 如果没有 delta_list 但有 strategy_params，从 strategy_params 构建 delta_list
    if not formatted_params['delta_list'] and formatted_params['strategy_params']:
        delta_list = []
        for key in ['put_sell_delta', 'put_buy_delta', 'call_sell_delta', 'call_buy_delta']:
            value = formatted_params['strategy_params'].get(key)
            if value is not None:
                delta_list.append(value)
        formatted_params['delta_list'] = delta_list
    
    # 移除空值，但保留空列表和字典
    formatted_params = {k: v for k, v in formatted_params.items() 
                       if v is not None and (not isinstance(v, (list, dict)) or v)}
    
    # 处理日期时间对象
    for key, value in formatted_params.items():
        if isinstance(value, datetime):
            formatted_params[key] = value.strftime('%Y-%m-%d')
    
    # 保存方案
    scheme_db.create_scheme(
        name=name,
        params=json.dumps(formatted_params, ensure_ascii=False),
        results=json.dumps(results, ensure_ascii=False)
    )

@backtest_bp.route('/save_scheme', methods=['POST'])
@api_error_handler
def save_scheme():
    """保存方案"""
    data = request.json
    
    # 验证输入数据
    if not data or 'scheme_name' not in data or 'params' not in data:
        return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400
        
    scheme_name = data['scheme_name']
    params = data['params']
    
    # 检查方案名称是否已存在
    if SchemeModel.check_scheme_exists(scheme_name):
        return jsonify({
            'status': 'error',
            'message': f'方案"{scheme_name}"已存在，请选择其他名称'
        }), 400
        
    # 保存方案
    SchemeModel.save_scheme({
        'name': scheme_name,
        'params': params,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    
    return jsonify({
        'status': 'success',
        'message': '方案保存成功'
    })