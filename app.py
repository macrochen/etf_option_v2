from flask import Flask, render_template, request, jsonify
import plotly
import plotly.graph_objs as go
import json
import pandas as pd
from typing import Dict, Any, List, Tuple
from config import BacktestConfig  # 改用新的配置类
from backtest_engine import BacktestEngine  # 改用新的回测引擎
from logger import TradeLogger
from strategy_analyzer import StrategyAnalyzer
from traceback import format_exc  # 添加这行导入

app = Flask(__name__)

# 常量定义
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

DELTA_OPTIONS = [
    {'value': 0.2, 'label': '0.2 (保守)'},
    {'value': 0.3, 'label': '0.3 (稳健)'},
    {'value': 0.4, 'label': '0.4 (平衡)'},
    {'value': 0.5, 'label': '0.5 (积极)'},
    {'value': 0.6, 'label': '0.6 (激进)'}
]

HOLDING_TYPES = [
    {'value': 'stock', 'label': '正股持仓'},
    {'value': 'synthetic', 'label': '合成持仓'}
]

@app.route('/')
def index():
    return render_template('index.html', 
                         etf_options=ETF_OPTIONS,
                         delta_options=DELTA_OPTIONS,
                         holding_types=HOLDING_TYPES)

@app.route('/run_backtest', methods=['POST'])
def run_backtest():
    logger = TradeLogger()  # 创建日志记录器
    try:
        # 获取表单数据
        etf_code = request.form.get('etf_code')
        delta = float(request.form.get('delta'))
        holding_type = request.form.get('holding_type', 'stock')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        # 转换日期字符串为datetime对象
        if start_date:
            start_date = pd.to_datetime(start_date)
        if end_date:
            end_date = pd.to_datetime(end_date)
        
        # 运行回测
        config = BacktestConfig(
            symbol=etf_code,
            delta=delta,
            start_date=start_date,
            end_date=end_date,
            holding_type=holding_type
        )
        
        engine = BacktestEngine(config)
        results = engine.run_backtest()
        
        if not results:
            logger.log_error("回测执行失败，未返回结果")
            return jsonify({'error': '回测执行失败'})
        
        # 转换图表为JSON格式
        plots = {
            'performance': json.dumps(results['plots']['performance'], cls=plotly.utils.PlotlyJSONEncoder),
            'drawdown': json.dumps(results['plots']['drawdown'], cls=plotly.utils.PlotlyJSONEncoder),
            'pnl_distribution': json.dumps(results['plots']['pnl_distribution'], cls=plotly.utils.PlotlyJSONEncoder)
        }
        
        return jsonify({
            'plots': plots,
            'trade_records': format_trade_records(results),
            'trade_summary': format_trade_summary(results),
            'daily_pnl': format_daily_pnl(results),
            'strategy_comparison': format_strategy_comparison(results)
        })
        
    except Exception as e:
        # 记录详细的错误信息和堆栈跟踪
        error_msg = f"回测执行出错: {str(e)}\n{format_exc()}"
        logger.log_error(error_msg)
        # 只返回简单的错误信息给前端
        return jsonify({'error': '回测执行出错，请查看日志了解详情'})

def create_plot(results):
    """创建Plotly图表"""
    portfolio_df = results['portfolio_df']
    etf_buy_hold_df = results['etf_buy_hold_df']
    put_trades = results['put_trades']
    call_trades = results['call_trades']
    
    # 创建策略收益曲线
    trace1 = go.Scatter(
        x=portfolio_df.index,
        y=portfolio_df['cumulative_return'],
        name='期权策略收益率',
        line=dict(color='blue', width=2)
    )
    
    # 创建ETF持有收益曲线
    trace2 = go.Scatter(
        x=etf_buy_hold_df.index,
        y=etf_buy_hold_df['etf_buy_hold_return'],
        name=f'持有{results["symbol"]}ETF收益率',
        line=dict(color='gray', width=2)
    )
    
    # 添加PUT交易点
    put_dates = [date for date, _ in put_trades]
    put_returns = [etf_buy_hold_df.loc[date, 'etf_buy_hold_return'] for date, _ in put_trades]
    trace3 = go.Scatter(
        x=put_dates,
        y=put_returns,
        mode='markers',
        name='卖出PUT',
        marker=dict(color='red', size=10, symbol='circle')
    )
    
    # 添加CALL交易点
    call_dates = [date for date, _ in call_trades]
    call_returns = [etf_buy_hold_df.loc[date, 'etf_buy_hold_return'] for date, _ in call_trades]
    trace4 = go.Scatter(
        x=call_dates,
        y=call_returns,
        mode='markers',
        name='卖出CALL',
        marker=dict(color='green', size=10, symbol='circle')
    )
    
    # 添加最大回撤区间
    max_drawdown_start = results.get('max_drawdown_start_date')
    max_drawdown_end = results.get('max_drawdown_end_date')
    if max_drawdown_start and max_drawdown_end:
        # 获取从开始到结束的所有数据
        drawdown_data = portfolio_df.loc[max_drawdown_start:max_drawdown_end]
        
        # 获取最大回撤期间的峰值
        peak = portfolio_df.loc[:max_drawdown_end]['cumulative_return'].expanding().max()
        drawdown_peak = peak.loc[max_drawdown_start:max_drawdown_end]
        
        # 创建回撤区域
        trace5 = go.Scatter(
            x=drawdown_data.index,
            y=drawdown_peak,
            mode='lines',
            line=dict(color='rgba(255,0,0,0)', width=0),
            showlegend=False,
            hoverinfo='skip'
        )
        
        trace6 = go.Scatter(
            x=drawdown_data.index,
            y=drawdown_data['cumulative_return'],
            fill='tonextx',
            mode='lines',
            fillcolor='rgba(255,0,0,0.2)',
            line=dict(color='rgba(255,0,0,0)', width=0),
            showlegend=True,
            name=f'最大回撤 ({abs(results.get("max_drawdown", 0)):.2f}%)'
        )
        
        # 注意：trace5必须在trace6之前，这样填充才会在两条线之间
        data = [trace1, trace2, trace3, trace4, trace5, trace6]
    else:
        data = [trace1, trace2, trace3, trace4]
    
    # 创建图表布局
    layout = go.Layout(
        title=dict(
            text=f'期权策略 vs 持有{results["symbol"]}ETF收益率对比',
            x=0.5,
            y=0.95
        ),
        width=1200,
        height=800,
        xaxis=dict(
            title='日期',
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            type='date',
            dtick='M3',  # 每3个月显示一个刻度
            tickformat='%y/%m',  # 只显示年份的后两位
            tickangle=45,  # 45度角显示日期
            tickfont=dict(size=10)  # 调整字体大小
        ),
        yaxis=dict(
            title='累计收益率 (%)',
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            zeroline=True,
            zerolinecolor='rgba(0,0,0,0.2)'
        ),
        hovermode='x unified',
        plot_bgcolor='white',
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.15,
            xanchor="center",
            x=0.5,
            bgcolor='rgba(255,255,255,0.8)'
        ),
        margin=dict(l=50, r=50, t=150, b=80)  # 增加底部边距，为倾斜的日期留出空间
    )
    
    return {'data': data, 'layout': layout}

def format_trade_records(results: Dict[str, Any]) -> Dict[str, Any]:
    """格式化交易记录"""
    trade_data = []
    
    # 获取所有交易记录
    for date, trades_list in results['trades'].items():
        # 处理当日的每笔交易
        for trade in trades_list:
            trade_data.append([
                date.strftime('%Y-%m-%d'),
                trade['交易类型'],
                f"{trade['ETF价格']:.4f}",
                f"{trade['行权价']:.4f}",
                f"{trade['期权价格']:.4f}",
                f"{trade['合约数量']}张",
                f"{abs(trade['权利金收入']):.4f}",
                f"{trade['交易成本']:.2f}",
                f"{trade['Delta']:.2f}",
                f"{trade['实现盈亏']:.2f}" if trade['实现盈亏'] else "0.00"
            ])
    
    return {
        'headers': ['日期', '交易类型', 'ETF价格', '行权价', '期权价格', 
                   '合约数量', '权利金', '交易成本', 'Delta', '实现盈亏'],
        'data': sorted(trade_data, key=lambda x: x[0])  # 按日期排序
    }

def format_daily_pnl(results: Dict[str, Any]) -> Dict[str, Any]:
    """格式化每日盈亏数据"""
    daily_data = []
    
    # 获取每日盈亏数据
    for date, portfolio in results['portfolio_values'].items():
        daily_return = portfolio.daily_return
        # 为收益率添加颜色标识
        if daily_return > 0:
            return_str = f'<span style="color: #4CAF50">{daily_return:.2f}%</span>'
        elif daily_return < 0:
            return_str = f'<span style="color: #F44336">{daily_return:.2f}%</span>'
        else:
            return_str = f'{daily_return:.2f}%'
            
        daily_data.append([
            date.strftime('%Y-%m-%d'),
            f"{portfolio.cash:.2f}",
            f"{portfolio.option_value:.2f}",
            f"{portfolio.total_value:.2f}",
            return_str
        ])
    
    return {
        'headers': ['日期', '现金', '期权市值', '总市值', '当日收益率'],
        'data': sorted(daily_data, key=lambda x: x[0])  # 按日期排序
    }

def format_strategy_comparison(results: Dict[str, Any]) -> Dict[str, List[List[str]]]:
    """格式化策略对比数据"""
    comparison_data = StrategyAnalyzer.generate_comparison_table(results['analysis'])
    return {
        'data': comparison_data
    }

def format_trade_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    """格式化交易汇总数据"""
    stats = results['statistics']
    metrics = results['analysis']['trade_metrics']
    risk_metrics = results['analysis']['risk_metrics']
    
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
        ['最大保证金占用', f"{risk_metrics['max_margin_ratio']*100:.2f}%"],
        ['平均保证金占用', f"{risk_metrics['avg_margin_ratio']*100:.2f}%"]
    ]
    
    return {
        'headers': ['统计项', '数值'],
        'data': data
    }

if __name__ == '__main__':
    app.run(debug=True) 