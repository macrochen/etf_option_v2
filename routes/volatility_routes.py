from flask import Blueprint, jsonify, request, render_template
from datetime import datetime
import numpy as np
from db.database import Database
from backtest_engine import BacktestEngine
from backtest_params import BacktestParam, BacktestConfig
from strategies.factory import StrategyFactory
from utils.error_handler import api_error_handler, log_error
from db.scheme_db import SchemeDatabase
from db.config import DB_CONFIG
from utils import get_trading_dates
from routes.backtest_routes import update_scheme, create_scheme
import json

volatility_bp = Blueprint('volatility', __name__)
db = Database(DB_CONFIG['market_data']['path'])
scheme_db = SchemeDatabase(DB_CONFIG['backtest_schemes']['path'])

@volatility_bp.route('/volatility_strategy')
def volatility_strategy_page():
    """渲染波动率策略页面"""
    try:
        from app import ETF_OPTIONS
        return render_template('volatility_strategy.html', etf_options=ETF_OPTIONS)
    except Exception as e:
        error_msg = log_error(e, "加载波动率策略页面失败")
        return jsonify({'error': error_msg}), 500

@volatility_bp.route('/api/etf/volatility')
@api_error_handler
def get_etf_volatility():
    """获取ETF的波动率统计数据"""
    try:
        symbol = request.args.get('symbol')
        if not symbol:
            return jsonify({'error': '缺少ETF代码参数'}), 400

        with db.get_connection() as conn:
            # 获取最新的波动率统计数据
            cursor = conn.cursor()
            cursor.execute("""
                SELECT stats_data, display_data, start_date, end_date 
                FROM volatility_stats 
                WHERE etf_code = ? 
                ORDER BY calc_date DESC 
                LIMIT 1
            """, (symbol,))
            
            row = cursor.fetchone()
            if not row:
                return jsonify({'error': f'未找到ETF {symbol} 的波动率数据'}), 404
                
            stats_data = json.loads(row[0])
            display_data = json.loads(row[1])
            
            # 将百分位数据转换为数组格式
            if 'upward' in stats_data and 'percentiles' in stats_data['upward']:
                stats_data['upward']['percentiles'] = [
                    float(value) for value in stats_data['upward']['percentiles'].values()
                ]
            if 'downward' in stats_data and 'percentiles' in stats_data['downward']:
                stats_data['downward']['percentiles'] = [
                    float(value) for value in stats_data['downward']['percentiles'].values()
                ]
            
            return jsonify({
                'volatility_stats': stats_data,
                'display_data': display_data,
                'trading_range': {
                    'start': row[2],
                    'end': row[3]
                }
            })
            
    except Exception as e:
        error_msg = log_error(e, "获取ETF波动率数据失败")
        return jsonify({'error': error_msg}), 500

@volatility_bp.route('/api/backtest/volatility', methods=['POST'])
@api_error_handler
def run_volatility_backtest():
    """执行波动率策略回测"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400
            
        # 检查是否需要保存方案
        save_scheme = data.pop('save_scheme', False)
        scheme_id = data.pop('scheme_id', None)
        scheme_name = data.get('scheme_name', f"波动率策略_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # 创建回测参数
        try:
            param = BacktestParam(
                strategy_type='volatility',
                etf_code=data['symbol'],
                start_date=datetime.strptime(data['start_date'], '%Y-%m-%d'),
                end_date=datetime.strptime(data['end_date'], '%Y-%m-%d'),
                strategy_params={
                    'put_volatility': data['put_volatility'] if isinstance(data['put_volatility'], list) else [data['put_volatility']],
                    'call_volatility': data['call_volatility'] if isinstance(data['call_volatility'], list) else [data['call_volatility']]
                }
            )
        except (KeyError, ValueError) as e:
            error_msg = log_error(e, "回测参数无效")
            return jsonify({'error': error_msg}), 400
        
        # 创建回测引擎
        config = BacktestConfig()  # 使用默认配置
        engine = BacktestEngine(config)
        
        # 执行回测
        result = engine.run_backtest(param)
        if result is None:
            error_msg = log_error(None, "回测执行失败，未返回结果")
            return jsonify({'error': error_msg}), 500
            
        # 格式化响应数据
        response_data = result.to_dict()
        
        # 保存方案
        if save_scheme:
            try:
                if scheme_id:  # 更新已有方案
                    update_scheme(scheme_id, param.to_dict(), response_data)
                else:  # 创建新方案
                    create_scheme(scheme_name, param.to_dict(), response_data)
            except Exception as e:
                error_msg = log_error(e, "保存回测方案失败")
                # 继续返回回测结果，但添加警告信息
                response_data['warning'] = error_msg
        
        return jsonify(response_data)
        
    except Exception as e:
        error_msg = log_error(e, "执行波动率策略回测失败")
        return jsonify({'error': error_msg}), 500
