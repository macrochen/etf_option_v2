import plotly.graph_objs as go
from typing import Dict, List, Tuple, Any
from datetime import datetime
import pandas as pd

import json
import plotly

from strategies.types import TradeRecord, PortfolioValue, BacktestResult
from strategy_analyzer import StrategyAnalyzer




class StrategyVisualizer:
    def create_plots(self, pvs: Dict[datetime, PortfolioValue],
                    trades: Dict[datetime, List[TradeRecord]],
                    symbol: str, etf_data: pd.DataFrame,
                    analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """创建所有可视化图表
        
        Args:
            pvs: 每日收益记录
            symbol: ETF代码
            etf_data: ETF数据
            analysis_results: 分析结果
        
        Returns:
            Dict[str, Any]: 包含所有图表的字典
        """
        # 从交易记录中提取每日投资组合价值
        portfolio_values = {
            date: {'total_value': pv.total_value}
            for date, pv in pvs.items()
        }
        
        # 获取交易DataFrame
        trades_df = pd.DataFrame(analysis_results['trade_metrics']['strategy_trades'])
        
        # 创建收益率曲线图
        performance_plot = self.create_performance_plot(
            portfolio_values,
            trades_df,
            symbol,
            etf_data
        )
        
        # 创建回撤分析图
        drawdown_plot = self.create_drawdown_plot(
            portfolio_values,
            analysis_results['portfolio_metrics']['max_drawdown_start'],
            analysis_results['portfolio_metrics']['max_drawdown_end']
        )
        
        # 创建收益分布图
        pnl_distribution_plot = self.create_pnl_distribution_plot(
            analysis_results['portfolio_metrics']['daily_returns']
        )
        
        return {
            'performance': performance_plot,
            'drawdown': drawdown_plot,
            'pnl_distribution': pnl_distribution_plot
        }

    def create_performance_plot(self, portfolio_values: Dict[datetime, Dict],
                              trades_df: pd.DataFrame,
                              symbol: str,
                              etf_data: pd.DataFrame = None) -> Dict:
        """创建收益率曲线图"""
        # 创建投资组合收益率序列
        dates = sorted(portfolio_values.keys())
        if not dates:
            return {'data': [], 'layout': {}}
            
        initial_value = portfolio_values[dates[0]]['total_value']
        if initial_value == 0:
            print("警告: 初始投资组合价值为0，无法计算收益率")
            return {'data': [], 'layout': {}}
            
        portfolio_returns = [
            (portfolio_values[date]['total_value'] / initial_value - 1) * 100
            for date in dates
        ]
        
        # 创建策略收益曲线
        traces = [
            go.Scatter(
                x=dates,
                y=portfolio_returns,
                name='期权策略收益率',
                line=dict(color='blue', width=2)
            )
        ]
        
        # 添加ETF基准线
        if etf_data is not None:
            etf_prices = etf_data.loc[dates[0]:dates[-1]]['收盘价']
            if not etf_prices.empty:
                etf_returns = [(price / etf_prices.iloc[0] - 1) * 100 for price in etf_prices]
                traces.append(
                    go.Scatter(
                        x=etf_prices.index,
                        y=etf_returns,
                        name=f'持有{symbol}ETF收益率',
                        line=dict(color='gray', width=2)
                    )
                )
        
        # 添加交易盈亏标记
        if not trades_df.empty:
            # 获取已完成的交易
            completed_trades = trades_df[trades_df['total_pnl'].notna()]
            
            # 盈利交易标记
            winning_trades = completed_trades[completed_trades['total_pnl'] > 0]
            if not winning_trades.empty:
                winning_returns = [
                    (portfolio_values[date]['total_value'] / initial_value - 1) * 100
                    for date in winning_trades['close_date']
                ]
                traces.append(
                    go.Scatter(
                        x=winning_trades['close_date'],
                        y=winning_returns,
                        mode='markers',
                        name='盈利平仓',
                        marker=dict(
                            color='red',
                            size=10,
                            symbol='circle',
                            line=dict(color='white', width=1)
                        ),
                        text=[f"盈利: {pnl:.2f}" for pnl in winning_trades['total_pnl']],
                        hovertemplate='%{text}<extra></extra>'
                    )
                )
            
            # 亏损交易标记
            losing_trades = completed_trades[completed_trades['total_pnl'] < 0]
            if not losing_trades.empty:
                losing_returns = [
                    (portfolio_values[date]['total_value'] / initial_value - 1) * 100
                    for date in losing_trades['close_date']
                ]
                traces.append(
                    go.Scatter(
                        x=losing_trades['close_date'],
                        y=losing_returns,
                        mode='markers',
                        name='亏损平仓',
                        marker=dict(
                            color='green',
                            size=10,
                            symbol='circle',
                            line=dict(color='white', width=1)
                        ),
                        text=[f"亏损: {pnl:.2f}" for pnl in losing_trades['total_pnl']],
                        hovertemplate='%{text}<extra></extra>'
                    )
                )
        
        # 创建图表布局
        layout = go.Layout(
            title=dict(
                text=f'期权策略 vs 持有{symbol}ETF收益率对比',
                x=0.5,
                y=0.95
            ),
            width=1200,
            height=600,
            xaxis=dict(
                title='日期',
                showgrid=True,
                gridcolor='rgba(0,0,0,0.1)',
                type='date',
                dtick='M1',
                tickformat='%y-%m',
                tickangle=45,
                tickfont=dict(size=10)
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
            margin=dict(l=50, r=50, t=150, b=80)
        )
        
        return {'data': traces, 'layout': layout}

    @staticmethod
    def create_drawdown_plot(portfolio_values: Dict[datetime, Dict],
                           max_drawdown_start: datetime,
                           max_drawdown_end: datetime) -> Dict:
        """创建回撤分析图表"""
        if not portfolio_values:
            return {'data': [], 'layout': {}}
            
        # 创建DataFrame
        dates = sorted(portfolio_values.keys())
        values = [portfolio_values[date]['total_value'] for date in dates]
        portfolio_df = pd.DataFrame({'total_value': values}, index=dates)
        
        # 计算回撤序列
        portfolio_peak = portfolio_df['total_value'].expanding(min_periods=1).max()
        drawdown = (portfolio_df['total_value'] - portfolio_peak) / portfolio_peak * 100
        
        # 创建回撤曲线
        trace = go.Scatter(
            x=drawdown.index,
            y=drawdown,
            name='回撤',
            fill='tozeroy',
            fillcolor='rgba(255,0,0,0.2)',
            line=dict(color='red', width=1)
        )
        
        traces = [trace]
        
        # 标记最大回撤区间
        if max_drawdown_start is not None and max_drawdown_end is not None:
            # 确保日期在数据范围内
            if max_drawdown_start in drawdown.index and max_drawdown_end in drawdown.index:
                max_drawdown_period = go.Scatter(
                    x=[max_drawdown_start, max_drawdown_end],
                    y=[drawdown[max_drawdown_start], drawdown[max_drawdown_end]],
                    mode='markers+lines',
                    name='最大回撤区间',
                    line=dict(color='red', width=2, dash='dash'),
                    marker=dict(size=8)
                )
                traces.append(max_drawdown_period)
        
        layout = go.Layout(
            title=dict(
                text='策略回撤分析',
                x=0.5,
                y=0.95
            ),
            width=1200,
            height=400,
            xaxis=dict(
                title='日期',
                showgrid=True,
                gridcolor='rgba(0,0,0,0.1)'
            ),
            yaxis=dict(
                title='回撤 (%)',
                showgrid=True,
                gridcolor='rgba(0,0,0,0.1)'
            ),
            plot_bgcolor='white',
            showlegend=True
        )
        
        return {'data': traces, 'layout': layout}

    @staticmethod
    def create_pnl_distribution_plot(daily_returns: pd.Series) -> Dict:
        """创建收益分布图表"""
        if daily_returns.empty:
            return {'data': [], 'layout': {}}
            
        trace = go.Histogram(
            x=daily_returns,
            nbinsx=50,
            name='日收益分布',
            opacity=0.75,
            marker_color='blue'
        )
        
        layout = go.Layout(
            title=dict(
                text='日收益率分布',
                x=0.5,
                y=0.95
            ),
            width=800,
            height=400,
            xaxis=dict(
                title='日收益率 (%)',
                showgrid=True,
                gridcolor='rgba(0,0,0,0.1)'
            ),
            yaxis=dict(
                title='频次',
                showgrid=True,
                gridcolor='rgba(0,0,0,0.1)'
            ),
            plot_bgcolor='white'
        )
        
        return {'data': [trace], 'layout': layout}

    @staticmethod
    def create_strategy_plot(results: Dict[str, Any]) -> Dict:
        """创建策略对比图表
        
        Args:
            results: 回测结果字典，包含portfolio_df、etf_buy_hold_df等数据
            
        Returns:
            包含图表数据和布局的字典
        """
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


def format_backtest_result(result: BacktestResult) -> Dict[str, Any]:
    """格式化回测结果，确保返回格式与方案加载时一致"""
    # 转换图表数据
    plots = {}
    if result.plots:
        for plot_name, plot_data in result.plots.items():
            plots[plot_name] = json.dumps(plot_data, cls=plotly.utils.PlotlyJSONEncoder)

    # 构建统一的返回格式
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
        ['胜率', f"{metrics['win_rate'] * 100:.2f}%"],
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