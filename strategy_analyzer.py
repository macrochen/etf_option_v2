import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime
from models import TradeRecord, DailyPortfolio
from utils import calculate_returns, format_number

class StrategyAnalyzer:
    @staticmethod
    def calculate_metrics(portfolio_values: Dict[datetime, Dict],
                         trades: Dict[datetime, Dict],
                         initial_cash: float,
                         etf_data: pd.DataFrame = None) -> Dict[str, Any]:
        """计算策略的各项指标，包括与ETF买入持有的对比
        
        Args:
            portfolio_values: 每日投资组合状态记录
            trades: 交易记录字典，键为日期，值为当日交易列表
            initial_cash: 初始资金
            etf_data: ETF价格数据，用于计算买入持有收益
        """
        # 检查是否有数据
        if not portfolio_values:
            return {
                "portfolio_metrics": {
                    "annual_return": 0,
                    "annual_volatility": 0,
                    "sharpe_ratio": 0,
                    "max_drawdown": 0,
                    "max_drawdown_start": None,
                    "max_drawdown_end": None,
                    "total_return": 0,
                    "daily_returns": pd.Series()
                },
                "etf_metrics": {},
                "trade_metrics": StrategyAnalyzer._calculate_trade_metrics(trades),
                "risk_metrics": {
                    "max_margin_ratio": 0,
                    "avg_margin_ratio": 0,
                    "var_95": 0,
                    "var_99": 0,
                    "max_daily_loss": 0,
                    "max_daily_profit": 0
                }
            }
        
        # 创建净值序列
        portfolio_series = pd.Series(
            {date: data['total_value'] for date, data in portfolio_values.items()}
        ).sort_index()
        
        # 计算期权策略的收益率指标
        annual_return, annual_volatility, sharpe_ratio = calculate_returns(portfolio_series)
        
        # 计算最大回撤
        portfolio_peak = portfolio_series.expanding(min_periods=1).max()
        portfolio_drawdown = (portfolio_series - portfolio_peak) / portfolio_peak
        
        # 检查是否有有效的回撤数据
        if portfolio_drawdown.empty:
            max_drawdown = 0
            max_drawdown_end_date = None
            max_drawdown_start_date = None
        else:
            max_drawdown = abs(portfolio_drawdown.min())
            max_drawdown_end_date = portfolio_drawdown.idxmin() if not pd.isna(portfolio_drawdown.min()) else None
            if max_drawdown_end_date:
                peak_series = portfolio_peak[:max_drawdown_end_date]
                max_drawdown_start_date = peak_series.idxmax() if not peak_series.empty else None
            else:
                max_drawdown_start_date = None
        
        # 计算ETF买入持有的收益率（如果提供了ETF数据）
        etf_metrics = {}
        if etf_data is not None and not portfolio_series.empty:
            etf_series = etf_data['收盘价'].loc[portfolio_series.index]
            if not etf_series.empty:
                etf_returns = etf_series / etf_series.iloc[0]
                etf_values = initial_cash * etf_returns
                
                # 计算ETF买入持有的收益率指标
                etf_annual_return, etf_annual_vol, etf_sharpe = calculate_returns(etf_values)
                
                # 计算ETF的最大回撤
                etf_peak = etf_values.expanding(min_periods=1).max()
                etf_drawdown = (etf_values - etf_peak) / etf_peak
                etf_max_drawdown = abs(etf_drawdown.min())
                
                etf_metrics = {
                    "annual_return": etf_annual_return,
                    "annual_volatility": etf_annual_vol,
                    "sharpe_ratio": etf_sharpe,
                    "max_drawdown": etf_max_drawdown * 100,
                    "total_return": (etf_values.iloc[-1] / initial_cash - 1) * 100
                }
        
        # 计算交易相关指标
        trade_metrics = StrategyAnalyzer._calculate_trade_metrics(trades)
        
        # 计算风险指标
        risk_metrics = StrategyAnalyzer._calculate_risk_metrics(portfolio_values)
        
        return {
            "portfolio_metrics": {
                "annual_return": annual_return,
                "annual_volatility": annual_volatility,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown * 100,
                "max_drawdown_start": max_drawdown_start_date,
                "max_drawdown_end": max_drawdown_end_date,
                "total_return": (portfolio_series.iloc[-1] / initial_cash - 1) * 100 if not portfolio_series.empty else 0,
                "daily_returns": portfolio_series.pct_change().dropna()
            },
            "etf_metrics": etf_metrics,
            "trade_metrics": trade_metrics,
            "risk_metrics": risk_metrics
        }

    @staticmethod
    def generate_comparison_table(metrics: Dict[str, Any]) -> List[List[str]]:
        """生成策略对比表格数据"""
        portfolio = metrics['portfolio_metrics']
        etf = metrics.get('etf_metrics', {})
        
        comparison_data = [
            ['总收益率', f"{portfolio['total_return']:.2f}%",
             f"{etf.get('total_return', 0):.2f}%" if etf else 'N/A'],
            ['年化收益率', f"{portfolio['annual_return']*100:.2f}%",
             f"{etf.get('annual_return', 0)*100:.2f}%" if etf else 'N/A'],
            ['年化波动率', f"{portfolio['annual_volatility']*100:.2f}%",
             f"{etf.get('annual_volatility', 0)*100:.2f}%" if etf else 'N/A'],
            ['夏普比率', f"{portfolio['sharpe_ratio']:.2f}",
             f"{etf.get('sharpe_ratio', 0):.2f}" if etf else 'N/A'],
            ['最大回撤', f"{portfolio['max_drawdown']:.2f}%",
             f"{etf.get('max_drawdown', 0):.2f}%" if etf else 'N/A'],
        ]
        
        return comparison_data

    @staticmethod
    def _calculate_trade_metrics(trades: Dict[datetime, Dict]) -> Dict[str, Any]:
        """计算交易相关指标
        
        Args:
            trades: 交易记录字典，键为日期，值为当日交易列表
            
        Returns:
            Dict[str, Any]: 交易指标字典
        """
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'max_win': 0,
                'max_loss': 0,
                'total_pnl': 0,
                'total_cost': 0
            }
        
        # 将所有交易记录展平为一个列表
        trade_records = []
        for date, trade in trades.items():
            trade_records.append({
                'date': date,
                'type': trade['action'],
                'details': trade['details'],
                'cash': trade['cash'],
                'margin': trade['margin']
            })
        
        # 转换为DataFrame
        trades_df = pd.DataFrame(trade_records)
        
        # 计算指标
        total_trades = len(trades_df)
        total_pnl = trades_df['cash'].iloc[-1] - trades_df['cash'].iloc[0]
        
        # 计算每笔交易的盈亏
        trades_df['pnl'] = trades_df['cash'].diff()
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        metrics = {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / total_trades if total_trades > 0 else 0,
            'avg_win': winning_trades['pnl'].mean() if not winning_trades.empty else 0,
            'avg_loss': losing_trades['pnl'].mean() if not losing_trades.empty else 0,
            'max_win': winning_trades['pnl'].max() if not winning_trades.empty else 0,
            'max_loss': losing_trades['pnl'].min() if not losing_trades.empty else 0,
            'total_pnl': total_pnl,
            'total_cost': 0  # 暂时不计算总成本
        }
        
        return metrics

    @staticmethod
    def _calculate_risk_metrics(portfolio_values: Dict[datetime, Dict]) -> Dict[str, Any]:
        """计算风险相关指标"""
        # 转换为DataFrame便于分析
        portfolio_df = pd.DataFrame([
            {
                'date': date,
                'total_value': data['total_value'],
                'margin_occupied': data['margin_occupied'],
                'daily_return': data['daily_return']
            } for date, data in portfolio_values.items()
        ])
        
        # 计算风险指标
        return {
            "max_margin_ratio": (portfolio_df['margin_occupied'] / portfolio_df['total_value']).max(),
            "avg_margin_ratio": (portfolio_df['margin_occupied'] / portfolio_df['total_value']).mean(),
            "var_95": np.percentile(portfolio_df['daily_return'], 5),  # 95% VaR
            "var_99": np.percentile(portfolio_df['daily_return'], 1),  # 99% VaR
            "max_daily_loss": portfolio_df['daily_return'].min(),
            "max_daily_profit": portfolio_df['daily_return'].max()
        }

    @staticmethod
    def generate_report(metrics: Dict[str, Any]) -> str:
        """生成策略分析报告"""
        report = []
        report.append("=== 策略绩效报告 ===\n")
        
        # 收益率指标
        report.append("收益率指标:")
        report.append(f"  年化收益率: {metrics['portfolio_metrics']['annual_return']*100:.2f}%")
        report.append(f"  年化波动率: {metrics['portfolio_metrics']['annual_volatility']*100:.2f}%")
        report.append(f"  夏普比率: {metrics['portfolio_metrics']['sharpe_ratio']:.2f}")
        report.append(f"  最大回撤: {metrics['portfolio_metrics']['max_drawdown']:.2f}%")
        report.append(f"  总收益率: {metrics['portfolio_metrics']['total_return']:.2f}%\n")
        
        # 交易统计
        report.append("交易统计:")
        report.append(f"  总交易次数: {metrics['trade_metrics']['total_trades']}")
        report.append(f"  胜率: {metrics['trade_metrics']['win_rate']*100:.2f}%")
        report.append(f"  平均盈利: {format_number(metrics['trade_metrics']['avg_win'])}")
        report.append(f"  平均亏损: {format_number(metrics['trade_metrics']['avg_loss'])}")
        report.append(f"  最大单笔盈利: {format_number(metrics['trade_metrics']['max_win'])}")
        report.append(f"  最大单笔亏损: {format_number(metrics['trade_metrics']['max_loss'])}\n")
        
        # 风险指标
        report.append("风险指标:")
        report.append(f"  最大保证金占用比例: {metrics['risk_metrics']['max_margin_ratio']*100:.2f}%")
        report.append(f"  平均保证金占用比例: {metrics['risk_metrics']['avg_margin_ratio']*100:.2f}%")
        report.append(f"  95% VaR: {metrics['risk_metrics']['var_95']:.2f}%")
        report.append(f"  99% VaR: {metrics['risk_metrics']['var_99']:.2f}%")
        report.append(f"  最大日亏损: {metrics['risk_metrics']['max_daily_loss']:.2f}%")
        report.append(f"  最大日盈利: {metrics['risk_metrics']['max_daily_profit']:.2f}%")
        
        return "\n".join(report) 