from flask import Flask, render_template, request, jsonify
from backtest_params import BacktestParam, StrategyType, BacktestConfig
from backtest_engine import BacktestEngine
import plotly
import plotly.graph_objs as go
import json
import pandas as pd
import traceback
from typing import Dict, Any, List
from logger import TradeLogger
from strategies.types import BacktestResult
from strategy_analyzer import StrategyAnalyzer
from datetime import datetime


app = Flask(__name__)

# ETF选项列表
ETF_OPTIONS = [
    {'value': '510050', 'label': '上证50ETF (510050)'},
    {'value': '510300', 'label': '沪深300ETF (510300)'},
    {'value': '510500', 'label': '中证500ETF (510500)'},
    {'value': '159901', 'label': '深证100ETF (159901)'},
    {'value': '159915', 'label': '创业板ETF (159915)'},
    {'value': '159919', 'label': '深市沪深300ETF (159919)'},
    {'value': '159922', 'label': '深市中证500ETF (159922)'},
    {'value': '588000', 'label': '科创板50ETF (588000)'},
    {'value': '588080', 'label': '科创板100ETF (588080)'}
]

@app.route('/')
def index():
    return render_template('index.html', etf_options=ETF_OPTIONS)

@app.route('/api/backtest', methods=['POST'])
def run_backtest_api():
    logger = TradeLogger()  # 创建日志记录器
    try:
        # 解析和验证参数
        params = BacktestParam(request.json)
        
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
            plots = {}
            if result.plots:
                for plot_name, plot_data in result.plots.items():
                    plots[plot_name] = json.dumps(plot_data, cls=plotly.utils.PlotlyJSONEncoder)

            response_data = {
                'plots': plots,
                'trade_records': format_trade_records(result),
                'trade_summary': format_trade_summary(result),
                'daily_pnl': format_daily_pnl(result),
                'strategy_comparison': format_strategy_comparison(result)
            }
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
    # todo
    # stats = result.analysis['statistics']
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
        ['总实现盈亏', f"{metrics['total_pnl']:.2f}"],
        # ['最大保证金占用', f"{risk_metrics['max_margin_ratio']*100:.2f}%"],
        # ['平均保证金占用', f"{risk_metrics['avg_margin_ratio']*100:.2f}%"]
    ]
    
    return {
        'headers': ['统计项', '数值'],
        'data': data
    }

if __name__ == '__main__':
    app.run(debug=True) 