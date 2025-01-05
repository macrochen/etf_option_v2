import plotly.graph_objs as go
from typing import Dict, List, Tuple
from datetime import datetime
import pandas as pd

from models import DailyPortfolio


class StrategyVisualizer:
    @staticmethod
    def create_performance_plot(portfolio_values: Dict[datetime, DailyPortfolio],
                              put_trades: List[Tuple[datetime, float]],
                              symbol: str,
                              etf_data: pd.DataFrame = None) -> Dict:
        """创建收益率曲线图"""
        # 创建投资组合收益率序列
        dates = list(portfolio_values.keys())
        portfolio_returns = [
            (portfolio_values[date].total_value / portfolio_values[dates[0]].total_value - 1) * 100
            for date in dates
        ]
        
        # 创建策略收益曲线
        trace1 = go.Scatter(
            x=dates,
            y=portfolio_returns,
            name='期权策略收益率',
            line=dict(color='blue', width=2)
        )
        
        # 创建ETF持有收益曲线（如果提供了ETF数据）
        traces = [trace1]
        if etf_data is not None:
            # 获取相同时间段的ETF数据
            etf_prices = etf_data.loc[dates[0]:dates[-1]]['收盘价']
            etf_returns = [(price / etf_prices.iloc[0] - 1) * 100 for price in etf_prices]
            
            trace2 = go.Scatter(
                x=etf_prices.index,
                y=etf_returns,
                name=f'持有{symbol}ETF收益率',
                line=dict(color='gray', width=2)
            )
            traces.append(trace2)
        
        # 添加交易点标记
        if put_trades:
            trade_dates, trade_returns = zip(*put_trades)
            trace3 = go.Scatter(
                x=trade_dates,
                y=trade_returns,
                mode='markers',
                name='期权交易',
                marker=dict(color='red', size=8, symbol='circle')
            )
            traces.append(trace3)
        
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
                tickfont=dict(size=10),
                tickmode='auto',
                nticks=15
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
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            margin=dict(b=80)
        )
        
        return {'data': traces, 'layout': layout}

    @staticmethod
    def create_drawdown_plot(portfolio_values: Dict[datetime, float],
                           max_drawdown_start: datetime,
                           max_drawdown_end: datetime) -> Dict:
        """创建回撤分析图表"""
        portfolio_df = pd.DataFrame.from_dict(portfolio_values, orient='index')
        
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
        
        # 标记最大回撤区间
        max_drawdown_period = go.Scatter(
            x=[max_drawdown_start, max_drawdown_end],
            y=[drawdown[max_drawdown_start], drawdown[max_drawdown_end]],
            mode='markers+lines',
            name='最大回撤区间',
            line=dict(color='red', width=2, dash='dash'),
            marker=dict(size=8)
        )
        
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
        
        return {'data': [trace, max_drawdown_period], 'layout': layout}

    @staticmethod
    def create_pnl_distribution_plot(daily_returns: pd.Series) -> Dict:
        """创建收益分布图表"""
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