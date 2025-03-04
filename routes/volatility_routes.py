import json
from datetime import datetime

from flask import Blueprint, jsonify, request, render_template

from backtest_engine import BacktestEngine
from db.config import DB_CONFIG
from db.database import Database
from db.scheme_db import SchemeDatabase
from routes.backtest_routes import update_scheme, create_scheme
from strategies import StrategyContextFactory, BacktestConfig
from utils.error_handler import api_error_handler, log_error
from visualization import format_backtest_result

volatility_bp = Blueprint('volatility', __name__)
db = Database(DB_CONFIG['market_data']['path'])
scheme_db = SchemeDatabase(DB_CONFIG['backtest_schemes']['path'])


@volatility_bp.route('/volatility_backtest')
def volatility_strategy_page():
    """渲染波动率策略页面"""
    try:
        from app import ETF_OPTIONS
        return render_template('volatility_backtest.html', etf_options=ETF_OPTIONS)
    except Exception as e:
        error_msg = log_error(e, "加载波动率策略页面失败")
        return jsonify({'error': error_msg}), 500


@volatility_bp.route('/api/etf/volatility')
@api_error_handler
def get_etf_volatility():
    """获取ETF的波动率统计数据"""
    try:
        etf_code = request.args.get('etf_code')
        if not etf_code:
            return jsonify({'error': '缺少ETF代码参数'}), 400

        # 获取数据范围参数
        data_range = request.args.get('data_range', None)  # 默认获取所有数据

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT stats_data, start_date, end_date 
                FROM volatility_stats 
                WHERE etf_code = ? 
                ORDER BY calc_date DESC 
                LIMIT 1
            """, (etf_code,))

            row = cursor.fetchone()
            if not row:
                return jsonify({'error': f'未找到ETF {etf_code} 的波动率数据'}), 404

            stats_data = json.loads(row[0])

            # 根据参数选择数据
            if data_range == '3个月':
                result = {
                    'up_volatility': stats_data['3个月']['up_volatility'],
                    'down_volatility': stats_data['3个月']['down_volatility']
                }
                return jsonify({
                    'volatility_stats': result,
                    'trading_range': {
                        'start': row[1],
                        'end': row[2]
                    }
                })
            else:
                return jsonify(stats_data)


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
        scheme_name = data.get('scheme_name', f"波动率策略_{datetime.now().strftime('%Y%m%d')}")

        strategy_params = data.get("strategy_params")

        # 创建回测参数
        try:
            context = StrategyContextFactory.create_context(data)
        except (KeyError, ValueError) as e:
            error_msg = log_error(e, "回测参数无效")
            return jsonify({'error': error_msg}), 400

        # 创建回测引擎
        config = BacktestConfig()  # 使用默认配置
        engine = BacktestEngine(config)

        # 执行回测
        result = engine.run_backtest(context)
        if result is None:
            error_msg = log_error(None, "回测执行失败，未返回结果")
            return jsonify({'error': error_msg}), 500

        # 格式化响应数据
        formatted_result = format_backtest_result(result)

        # 保存方案
        if save_scheme:
            try:
                if scheme_id:  # 更新已有方案
                    update_scheme(scheme_id, context.to_dict(strategy_params), formatted_result)
                else:  # 创建新方案
                    create_scheme(scheme_name, context.to_dict(strategy_params), formatted_result)
            except Exception as e:
                error_msg = log_error(e, "保存回测方案失败")
                # 继续返回回测结果，但添加警告信息
                formatted_result['warning'] = error_msg

        return jsonify(formatted_result)

    except Exception as e:
        error_msg = log_error(e, "执行波动率策略回测失败")
        return jsonify({'error': error_msg}), 500
