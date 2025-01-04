import plotly.graph_objs as go
from typing import Dict, List, Tuple
from datetime import datetime
import pandas as pd

class StrategyVisualizer:
    @staticmethod
    def create_performance_plot(portfolio_values: Dict[datetime, float],
                              put_trades: List[Tuple[datetime, float]],
                              symbol: str) -> Dict:
        """创建策略表现图表
        
        Args:
            portfolio_values: 投资组合每日净值
            put_trades: PUT期权交易点列表
            symbol: ETF代码
            
        Returns:
            Dict: Plotly图表配置
        """
        # 创建策略收益曲线
        portfolio_df = pd.DataFrame([
            {
                'total_value': data.total_value,
                'cumulative_return': (data.total_value / data.initial_value - 1) * 100
            }
            for date, data in portfolio_values.items()
        ], index=portfolio_values.keys())
        
        trace1 = go.Scatter(
            x=portfolio_df.index,
            y=portfolio_df['cumulative_return'],
            name='期权策略收益率',
            line=dict(color='blue', width=2)
        )
        
        # 添加PUT交易点
        put_dates = [date for date, _ in put_trades]
        put_returns = [portfolio_values[date].cumulative_return for date, _ in put_trades]
        trace2 = go.Scatter(
            x=put_dates,
            y=put_returns,
            mode='markers',
            name='卖出PUT',
            marker=dict(color='red', size=10, symbol='circle')
        )
        
        # 创建图表布局
        layout = go.Layout(
            title=dict(
                text=f'{symbol}ETF期权策略收益率',
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
                tickformat='%y/%m',
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
        
        return {'data': [trace1, trace2], 'layout': layout}

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