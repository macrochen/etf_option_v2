from flask import Blueprint, request, jsonify
from backtest_params import BacktestParam, BacktestConfig
from backtest_engine import BacktestEngine
from strategies.types import BacktestResult
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
    params = BacktestParam(data)  # 这里会自动验证参数

    # 创建回测引擎
    engine = BacktestEngine(BacktestConfig())
    
    # 执行回测
    result = engine.run_backtest(params)

    if not result:
        error_msg = "回测执行失败，未返回结果"
        # 注解: 回测执行失败，返回错误信息
        return jsonify({'error': error_msg}), 400

    # 转换图表为JSON格式
    try:
        response_data = format_backtest_result(result)
        
        # 如果需要保存方案
        if save_scheme:
            if scheme_id:  # 更新已有方案
                update_scheme(scheme_id, params.to_dict(), response_data)
            else:  # 创建新方案
                create_scheme(scheme_name, params.to_dict(), response_data)
        
        return jsonify(response_data)

    except Exception as e:
        # 注解: 处理回测结果时发生错误
        error_msg = log_error(e, "处理回测结果时发生错误")  # 记录错误堆栈信息
        return jsonify({'error': str(e)}), 400

def update_scheme(scheme_id, params, results):
    # 更新已有方案的逻辑
    scheme_db.update_scheme(scheme_id, params=json.dumps(params), results=json.dumps(results))

def create_scheme(name, params, results):
    # 创建新方案的逻辑
    # 遍历 params 和 results，转换所有 Timestamp 对象
    for key, value in params.items():
        if isinstance(value, datetime):
            params[key] = value.strftime('%Y-%m-%d %H:%M:%S')
    
    for key, value in results.items():
        if isinstance(value, datetime):
            results[key] = value.strftime('%Y-%m-%d %H:%M:%S')

    scheme_db.create_scheme(name=name, params=json.dumps(params), results=json.dumps(results))

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

def format_backtest_result(result: BacktestResult) -> Dict[str, Any]:
    """格式化回测结果"""
    # 转换图表数据
    plots = {}
    if result.plots:
        for plot_name, plot_data in result.plots.items():
            plots[plot_name] = json.dumps(plot_data, cls=plotly.utils.PlotlyJSONEncoder)

    return {
        'plots': plots,
        'trade_records': format_trade_records(result),
        'trade_summary': format_trade_summary(result),
        'daily_pnl': format_daily_pnl(result),
        'strategy_comparison': format_strategy_comparison(result)
    }

def format_trade_records(result: BacktestResult) -> Dict[str, Any]:
    """格式化交易记录"""
    trade_data = []
    
    # 获取所有交易记录
    for date, trades_list in result.trades.items():
        # 处理当日的每笔交易
        for trade in trades_list:
            trade_data.append(trade.to_list())
    
    return {
        'headers': ['日期', '交易类型', 'ETF价格', '行权价', '期权价格', 
                   '合约数量', '权利金', '交易成本', 'Delta', '实现盈亏'],
        'data': sorted(trade_data, key=lambda x: x[0])  # 按日期排序
    }

def format_daily_pnl(result: BacktestResult) -> Dict[str, Any]:
    """格式化每日盈亏数据"""
    daily_data = []
    
    # 获取每日盈亏数据
    for date, portfolio in result.portfolio_values.items():
        daily_data.append([
            date.strftime('%Y-%m-%d'),
            f"{portfolio.cash:.2f}",
            f"{portfolio.option_value:.2f}",
            f"{portfolio.total_value:.2f}",
            portfolio.formatted_daily_return
        ])
    
    return {
        'headers': ['日期', '现金', '期权市值', '总市值', '当日收益率'],
        'data': sorted(daily_data, key=lambda x: x[0])  # 按日期排序
    }

def format_strategy_comparison(result: BacktestResult) -> List[List[str]]:
    """格式化策略对比数据"""
    return StrategyAnalyzer.generate_comparison_table(result.analysis)

def format_trade_summary(result: BacktestResult) -> Dict[str, Any]:
    """格式化交易汇总数据"""
    metrics = result.analysis['trade_metrics']
    risk_metrics = result.analysis['risk_metrics']
    
    data = [
        ['交易总次数', f"{metrics['total_trades']}次"],
        ['盈利交易', f"{metrics['winning_trades']}次"],
        ['亏损交易', f"{metrics['losing_trades']}次"],
        ['胜率', f"{metrics['win_rate']*100:.2f}%"],
        ['平均盈利', f"{metrics['avg_win']:.2f}"],
        ['平均亏损', f"{metrics['avg_loss']:.2f}"],
        ['最大单笔盈利', f"{metrics['max_win']:.2f}"],
        ['最大单笔亏损', f"{metrics['max_loss']:.2f}"],
        ['总交易成本', f"{metrics['total_cost']:.2f}"],
        ['总实现盈亏', f"{metrics['total_pnl']:.2f}"]
    ]
    
    return {
        'headers': ['统计项', '数值'],
        'data': data
    } 