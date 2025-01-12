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
import traceback
from typing import Dict, Any, List

# 创建蓝图
backtest_bp = Blueprint('backtest', __name__)

# 创建数据库实例
scheme_db = SchemeDatabase(DB_CONFIG['backtest_schemes']['path'])

@backtest_bp.route('/api/backtest', methods=['POST'])
def run_backtest():
    logger = TradeLogger()
    try:
        data = request.get_json()
        
        # 检查是否需要保存方案
        save_scheme = data.pop('save_scheme', False)
        scheme_name = data.pop('scheme_name', None)
        
        # 解析和验证参数
        params = BacktestParam(data)
        
        # 创建回测引擎
        engine = BacktestEngine(BacktestConfig())
        
        # 执行回测
        result = engine.run_backtest(params)

        if not result:
            error_msg = "回测执行失败，未返回结果"
            logger.log_error(error_msg)
            return jsonify({'error': error_msg}), 400

        # 转换图表为JSON格式
        try:
            response_data = format_backtest_result(result)
            
            # 如果需要保存方案
            if save_scheme and scheme_name:
                try:
                    scheme_db.create_scheme(
                        name=scheme_name,
                        params=json.dumps(data, ensure_ascii=False),
                        results=json.dumps(response_data, ensure_ascii=False)
                    )
                except Exception as e:
                    logger.log_error(f"保存方案失败: {str(e)}")
                    # 保存方案失败不影响回测结果返回
            
            logger.log_info("回测执行成功，返回结果")
            return jsonify(response_data)

        except Exception as e:
            stack_trace = traceback.format_exc()
            error_msg = f'处理回测结果失败: {str(e)}\n堆栈信息:\n{stack_trace}'
            logger.log_error(error_msg)
            return jsonify({'error': str(e)}), 400

    except Exception as e:
        stack_trace = traceback.format_exc()
        error_msg = f"回测执行过程中发生未知错误: {str(e)}\n堆栈信息:\n{stack_trace}"
        logger.log_error(error_msg)
        return jsonify({'error': str(e)}), 500

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