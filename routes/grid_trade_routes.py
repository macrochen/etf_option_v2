from typing import Dict, List
from flask import Blueprint, render_template, jsonify, request
from datetime import datetime, timedelta
from db.market_db import MarketDatabase
from grid.backtest_engine import BacktestEngine
from grid.evaluator import BacktestEvaluator, EvaluationResult
from grid.grid_backtester import GridBacktester
from grid.grid_calculator import GridCalculator
import requests
import logging
import traceback
from jqdatasdk import auth, get_price, normalize_code
import pandas as pd
from config.jq_config import JQ_USERNAME, JQ_PASSWORD
import akshare as ak

from grid.parameter_analyzer import ParameterAnalyzer

# 创建蓝图
grid_trade_bp = Blueprint('grid_trade', __name__)
market_db = MarketDatabase()
grid_calculator = GridCalculator()

@grid_trade_bp.route('/grid_trade')
def index():
    """渲染网格交易分析页面"""
    return render_template('grid_trade.html')

# 新增API endpoints
@grid_trade_bp.route('/api/grid_trade/etf_list', methods=['GET'])
def get_etf_list():
    """获取已有的ETF列表"""
    etf_list = market_db.get_grid_trade_etf_list()
    return jsonify(etf_list)


def download_ak_data(etf_code: str) -> dict[str, list[any]]:
    """从AKShare下载ETF历史数据
    
    Returns:
        dict[str, list[any]]: 历史数据字典，包含日期、开盘价、收盘价等数据
    """
    logging.info(f"开始从AKShare下载ETF数据: {etf_code}")
    
    try:
        
        # 计算时间范围（5年）
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        logging.info(f"下载时间范围: {start_date} 至 {end_date}")
        
        # 获取数据
        df = ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="qfq"  # 前复权
        )
        
        if df.empty:
            raise ValueError(f"未找到ETF {etf_code} 的数据")
            
        logging.info(f"成功获取 {len(df)} 条历史数据记录")
        
        # 转换数据格式
        return {
            'date': df['日期'].tolist(),
            'open': df['开盘'].tolist(),
            'close': df['收盘'].tolist(),
            'high': df['最高'].tolist(),
            'low': df['最低'].tolist(),
            'volume': df['成交量'].tolist()
        }
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"下载ETF数据失败: \nETF代码: {etf_code}\n错误信息: {str(e)}\n堆栈信息:\n{stack_trace}")
        raise ValueError(f"下载ETF数据失败: {str(e)}")


@grid_trade_bp.route('/api/grid_trade/load_etf', methods=['POST'])
def load_etf_data():
    """下载并保存ETF数据"""
    try:
        data = request.get_json()
        if not data or 'etf_code' not in data:
            return jsonify({'error': '缺少必要参数'}), 400
            
        etf_code = data['etf_code']
        
        logging.info(f"开始处理ETF数据下载请求: code={etf_code}")
        
        # 从AKShare下载数据
        history_data = download_ak_data(etf_code)
        
        logging.info(f"开始保存ETF数据到数据库...")
        market_db.save_grid_trade_data(etf_code, history_data)
        
        logging.info(f"ETF数据处理完成: {etf_code}")
        return jsonify({'success': True})
        
    except ValueError as e:
        logging.error(f"数据验证错误: \n参数: {data}\n错误信息: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"处理ETF数据请求失败: \n参数: {data}\n错误信息: {str(e)}\n堆栈信息:\n{stack_trace}")
        return jsonify({'error': f"处理请求失败: {str(e)}"}), 500

@grid_trade_bp.route('/api/grid_trade/analyze', methods=['POST'])
def analyze():
    """执行网格交易分析"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400
            
        # 1. 参数验证
        required_fields = ['etf_code', 'months']
        if not all(field in data for field in required_fields):
            return jsonify({'error': '缺少必要参数'}), 400
            
        # 2. 获取ETF历史数据
        history_data = market_db.get_grid_trade_data(
            data['etf_code'],
            data['months']
        )
        if not history_data:
            return jsonify({'error': 'ETF数据不存在'}), 404
            
        # 3. 评估ETF是否适合网格交易
        suitability_result = grid_calculator.evaluate_grid_suitability(history_data)
        if not suitability_result['suitable']:
            return jsonify({
                'suitable': False,
                'reason': suitability_result['reason'],
                'scores': suitability_result['scores'],
                'atr': suitability_result['atr']
            }), 200

        analysis_result = {
            'suitable': True,
            'reason': suitability_result['reason'],
            'scores': suitability_result['scores'],
            'atr': suitability_result['atr']
        }
        
        return jsonify(analysis_result)
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"分析ETF数据时发生错误: \n参数: {data if 'data' in locals() else 'N/A'}\n错误信息: {str(e)}\n堆栈信息:\n{stack_trace}")
        return jsonify({'error': str(e)}), 500


@grid_trade_bp.route('/api/grid_trade/calculate_range', methods=['GET'])
def calculate_range():
    """计算网格交易的价格范围"""
    try:
        etf_code = request.args.get('etf_code')
        period_type = request.args.get('period_type')
        grid_count = int(request.args.get('grid_count', 10))
        initial_capital = float(request.args.get('initial_capital', 100000))

        if not all([etf_code, period_type]):
            return jsonify({'error': '缺少必要参数'}), 400

        # 获取历史数据
        history_data = market_db.get_grid_trade_data(etf_code, period_type)
        if not history_data:
            return jsonify({'error': 'ETF数据不存在'}), 404

        # 计算网格参数
        grid_params = grid_calculator.calculate_grid_params(
            history_data,
            initial_capital,
            grid_count
        )

        return jsonify({
            'upper': grid_params['upper_price'],
            'lower': grid_params['lower_price'],
            'grid_amount': initial_capital / grid_count
        })

    except ValueError as e:
        logging.error(f"参数验证错误: \n参数: etf_code={etf_code if 'etf_code' in locals() else 'N/A'}, "
                     f"period_type={period_type if 'period_type' in locals() else 'N/A'}\n错误信息: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"计算网格范围时发生错误: \n"
                     f"参数: etf_code={etf_code if 'etf_code' in locals() else 'N/A'}, "
                     f"period_type={period_type if 'period_type' in locals() else 'N/A'}, "
                     f"grid_count={grid_count if 'grid_count' in locals() else 'N/A'}, "
                     f"initial_capital={initial_capital if 'initial_capital' in locals() else 'N/A'}\n"
                     f"错误信息: {str(e)}\n堆栈信息:\n{stack_trace}")
        return jsonify({'error': str(e)}), 500
    
@grid_trade_bp.route('/api/grid_trade/analyze_params', methods=['POST'])
def analyze_grid_params():
    """执行网格交易参数回测分析，通过回测找出最优参数组合"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400
            
        # 参数验证和类型转换
        try:
            etf_code = str(data['etf_code'])
            months = data['months']
            atr = float(data['atr'])
            initial_capital = float(data.get('initial_capital', 100000.0))
            fee_rate = float(data.get('fee_rate', 0.0001))
            
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'参数类型错误: {str(e)}'}), 400
            
        # 获取ETF历史数据
        history_data = market_db.get_grid_trade_data(etf_code, months)
        if not history_data:
            return jsonify({'error': 'ETF数据不存在'}), 404

        # --- 提前计算基准（标的持有）的收益率 --- #
        prices = pd.Series(history_data['close'])
        daily_returns_for_stats = prices.pct_change().fillna(0)
        
        evaluator = BacktestEvaluator()

        if history_data and len(history_data['open']) > 0 and history_data['open'][0] is not None and history_data['open'][0] > 0:
            benchmark_total_return = (history_data['close'][-1] / history_data['open'][0]) - 1
        else:
            benchmark_total_return = 0.0

        days = len(daily_returns_for_stats)
        if days > 0:
            years = days / 252
            benchmark_annual_return = (1 + benchmark_total_return) ** (1 / years) - 1 if benchmark_total_return > -1 else -1
        else:
            benchmark_annual_return = 0.0
        # --- 基准收益率计算结束 --- #

        # 创建参数优化器并执行分析
        analyzer = ParameterAnalyzer(initial_capital=initial_capital, fee_rate=fee_rate)
        results = analyzer.analyze(
            hist_data={
                'dates': history_data['dates'],
                'close': history_data['close'],
                'open': history_data['open'],
                'high': history_data['high'],
                'low': history_data['low']
            },
            atr=atr,
            benchmark_annual_return=benchmark_annual_return # 传递基准收益率
        )
        
        # 获取得分最高的结果
        best_result = max(results, key=lambda x: x.evaluation['total_score'])

        # 计算其他基准指标用于返回给前端
        benchmark_max_drawdown = evaluator._calculate_max_drawdown(daily_returns_for_stats)
        benchmark_sharpe_ratio = evaluator._calculate_sharpe_ratio(daily_returns_for_stats)
        benchmark_total_score = evaluator._calculate_score({
            'annual_return': benchmark_annual_return,
            'max_drawdown': benchmark_max_drawdown,
            'sharpe_ratio': benchmark_sharpe_ratio,
            'trade_frequency': 1,
            'capital_utilization': 1,
            'relative_return': 1  # 基准与自身的相对表现为1
        })
        
        # 转换结果为前端所需格式
        response = {
            'parameter_results': [{
                'id': i + 1,  # 组合ID
                'params': {
                    'grid_count': result.params['grid_count'],  # 网格数量
                    'atr_factor': result.params['atr_factor'],  # ATR系数
                    'grid_percent': result.params['grid_percent'],  # ATR系数
                },
                'metrics': {
                    'total_return': result.evaluation['total_return'],  # 总收益率
                    'annual_return': result.evaluation['annual_return'],  # 年化收益率
                    'sharpe_ratio': result.evaluation['sharpe_ratio'],  # 夏普比率
                    'max_drawdown': result.evaluation['max_drawdown'],  # 最大回撤
                    'trade_count': result.evaluation['trade_count'],  # 
                    'capital_utilization': result.evaluation['capital_utilization'],  # 
                    'relative_return': result.evaluation['relative_return'],      # 相对表现
                    'score': result.evaluation['total_score'],  # 综合得分
                }
            } for i, result in enumerate(results)],

            'benchmark': {
                'total_return': benchmark_total_return, # 总收益率
                'daily_returns': (daily_returns_for_stats.cumsum() * 100).tolist(),  # 转换为累积收益率并转为百分比
                'annual_return': benchmark_annual_return,
                'max_drawdown': benchmark_max_drawdown,
                'sharpe_ratio': benchmark_sharpe_ratio,
                'total_score': benchmark_total_score
            },
            
            'best_backtest': {
                'trades': [{
                    'timestamp': trade.timestamp.strftime('%Y-%m-%d'),
                    'direction': trade.direction,
                    'price': trade.price,
                    'amount': trade.amount,
                    'value': trade.price * trade.amount,
                    'current_position': trade.current_position,
                    'position_value': trade.position_value,
                    'total_value': trade.total_value,
                    'cash': trade.cash
                } for trade in best_result.trades],
                
                'grids': [{
                    'index': i,
                    'price': grid.price,
                    'grid_percent': grid.grid_percent,
                    'position': grid.position,
                    'profit': grid.profit
                } for i, grid in enumerate(best_result.grids)],
                
                # 添加收益率数据
                'all_dates': best_result.daily_returns.index.strftime('%Y-%m-%d').tolist(),
                'all_prices': prices.tolist(),
                'all_returns': (best_result.daily_returns.cumsum() * 100).tolist()  # 转换为累积收益率并转为百分比
            }
        }
        
        return jsonify(response)
        
    except ValueError as e:
        logging.error(f"参数验证错误: \n参数: {data}\n错误信息: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"执行回测分析时发生错误: \n参数: {data if 'data' in locals() else 'N/A'}\n错误信息: {str(e)}\n堆栈信息:\n{stack_trace}")
        return jsonify({'error': str(e)}), 500

@grid_trade_bp.route('/api/grid_trade/manual_backtest', methods=['POST'])
def manual_backtest():
    """执行手动参数回测"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400
            
        etf_code = data['etf_code']
        start_date = data['start_date']
        grid_percent = float(data['grid_percent'])
        grid_count = int(data.get('grid_count', 20))
        initial_capital = float(data.get('initial_capital', 100000.0))
        
        # 获取可选参数
        initial_base_price = float(data['initial_base_price']) if data.get('initial_base_price') else None
        trade_size = int(data['trade_size']) if data.get('trade_size') else None
        
        # 获取历史数据
        history_data = market_db.get_grid_trade_data_by_date(etf_code, start_date)
        if not history_data or len(history_data['close']) < 2:
            return jsonify({'error': '指定日期范围内无数据'}), 404
            
        # 计算基准收益
        prices = pd.Series(history_data['close'])
        daily_returns = prices.pct_change().fillna(0)
        
        total_return = (prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0]
        days = len(prices)
        years = days / 252 if days > 0 else 0
        benchmark_annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else 0.0
        
        # 计算基准的其他指标
        evaluator = BacktestEvaluator()
        benchmark_max_drawdown = evaluator._calculate_max_drawdown(daily_returns)
        benchmark_sharpe_ratio = evaluator._calculate_sharpe_ratio(daily_returns)

        backtest_engine = BacktestEngine(initial_capital=initial_capital)
        result = backtest_engine.run_manual_backtest(
            hist_data=history_data,
            grid_percent=grid_percent,
            grid_count=grid_count,
            benchmark_annual_return=benchmark_annual_return,
            initial_base_price=initial_base_price,
            trade_size=trade_size
        )
        
        # 构建响应
        response = {
            'benchmark': {
                'daily_returns': (daily_returns.cumsum() * 100).tolist(),
                'total_return': total_return,
                'annual_return': benchmark_annual_return,
                'max_drawdown': benchmark_max_drawdown,
                'sharpe_ratio': benchmark_sharpe_ratio,
                'trade_count': 1,
                'capital_utilization': 1.0
            },
            'best_backtest': {
                'evaluation': result.evaluation,  # 确保包含评估结果
                'trades': [{
                    'timestamp': trade.timestamp.strftime('%Y-%m-%d'),
                    'direction': trade.direction,
                    'price': trade.price,
                    'amount': trade.amount,
                    'value': trade.price * trade.amount,
                    'current_position': trade.current_position,
                    'position_value': trade.position_value,
                    'total_value': trade.total_value,
                    'cash': trade.cash
                } for trade in result.trades],
                'grids': [{
                    'index': i,
                    'price': grid.price,
                    'grid_percent': grid.grid_percent,
                    'position': grid.position,
                    'profit': grid.profit
                } for i, grid in enumerate(result.grids)],
                'all_dates': result.daily_returns.index.strftime('%Y-%m-%d').tolist(),
                'all_prices': prices.tolist(),
                'all_returns': (result.daily_returns.cumsum() * 100).tolist()
            }
        }
        return jsonify(response)
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"手动回测失败: {str(e)}\n{stack_trace}")
        return jsonify({'error': f"回测失败: {str(e)}"}), 500

@grid_trade_bp.route('/api/grid_trade/run_backtest', methods=['POST'])
def run_backtest():
    """执行指定参数的回测"""
    try:
        data = request.get_json()
        etf_code = data['etf_code']
        months = data['months']
        grid_count = data['grid_count']
        atr_factor = data['atr_factor']
        atr = data['atr']
        
         # 获取ETF历史数据
        history_data = market_db.get_grid_trade_data(etf_code, months)
        if not history_data:
            return jsonify({'error': 'ETF数据不存在'}), 404
            
        backtest_engine = BacktestEngine()
        result = backtest_engine.run_backtest(
            hist_data=history_data,
            grid_count=grid_count,
            atr=atr,
            atr_factor=atr_factor
        )
        
        # 计算标的持有收益
        prices = pd.Series(history_data['close'])
        # 计算每日收益率
        daily_returns = prices.pct_change().fillna(0)
        
        # 转换结果为前端所需格式
        response = {

            'benchmark': {
                'daily_returns': (daily_returns.cumsum() * 100).tolist(),  # 转换为累积收益率并转为百分比
            },
            
            'best_backtest': {
                'trades': [{
                    'timestamp': trade.timestamp.strftime('%Y-%m-%d'),
                    'direction': trade.direction,
                    'price': trade.price,
                    'amount': trade.amount,
                    'value': trade.price * trade.amount,
                    'current_position': trade.current_position,
                    'position_value': trade.position_value,
                    'total_value': trade.total_value,
                    'cash': trade.cash                } for trade in result.trades],
                
                'grids': [{
                    'index': i,
                    'price': grid.price,
                    'grid_percent': grid.grid_percent,
                    'position': grid.position,
                    'profit': grid.profit
                } for i, grid in enumerate(result.grids)],
                
                # 添加收益率数据
                'all_dates': result.daily_returns.index.strftime('%Y-%m-%d').tolist(),
                'all_prices': prices.tolist(),
                'all_returns': (result.daily_returns.cumsum() * 100).tolist()  # 转换为累积收益率并转为百分比
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logging.error(f"回测执行失败: {str(e)}")
        return jsonify({'error': f'回测执行失败: {str(e)}'}), 500  