from flask import Blueprint, render_template, jsonify, request
from db.market_db import MarketDatabase
from grid.models import GridContext, StrategyMode
from grid.data_loader import GridDataLoader
from grid.strategy import SmartGridStrategy
from grid.backtester import PathSimulator
from grid.indicators import Indicators
import logging
import traceback
import akshare as ak
from datetime import datetime, timedelta
import pandas as pd

# 创建蓝图
grid_trade_bp = Blueprint('grid_trade', __name__)
market_db = MarketDatabase()
data_loader = GridDataLoader()

@grid_trade_bp.route('/grid_trade')
def index():
    """渲染网格交易分析页面"""
    return render_template('grid_trade.html')

@grid_trade_bp.route('/api/grid_trade/etf_list', methods=['GET'])
def get_etf_list():
    """获取已有的ETF列表"""
    etf_list = market_db.get_grid_trade_etf_list()
    return jsonify(etf_list)

@grid_trade_bp.route('/api/grid_trade/load_etf', methods=['POST'])
def load_etf_data():
    """下载并保存ETF数据"""
    try:
        data = request.get_json()
        if not data or 'etf_code' not in data:
            return jsonify({'error': '缺少必要参数'}), 400
            
        etf_code = data['etf_code']
        logging.info(f"开始处理ETF数据下载请求: code={etf_code}")
        
        # 计算时间范围（5年）
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        # 获取数据 (注意：此处仅负责下载并存库，不做清洗)
        df = ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="qfq"  # 前复权
        )
        
        if df.empty:
            raise ValueError(f"未找到ETF {etf_code} 的数据")
            
        history_data = {
            'date': df['日期'].tolist(),
            'open': df['开盘'].tolist(),
            'close': df['收盘'].tolist(),
            'high': df['最高'].tolist(),
            'low': df['最低'].tolist(),
            'volume': df['成交量'].tolist()
        }
        
        market_db.save_grid_trade_data(etf_code, history_data)
        return jsonify({'success': True})
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"""处理ETF数据请求失败: {str(e)}
{stack_trace}""")
        return jsonify({'error': f"处理请求失败: {str(e)}"}), 500

@grid_trade_bp.route('/api/grid_trade/smart_generate', methods=['POST'])
def smart_generate():
    """生成SmartGrid策略并回测"""
    try:
        data = request.get_json()
        
        # 1. 解析参数
        symbol = data.get('symbol')
        total_capital = float(data.get('total_capital', 100000))
        base_pos_ratio = float(data.get('base_position_ratio', 0.0))
        cash_res_ratio = float(data.get('cash_reserve_ratio', 0.0))
        pe_percentile = float(data.get('pe_percentile', 50.0))
        pb_percentile = float(data.get('pb_percentile', 50.0))
        
        # 高级参数
        force_mode_str = data.get('force_mode')
        force_mode = StrategyMode(force_mode_str) if force_mode_str else None
        
        # 2. 加载数据
        df = data_loader.load_daily_data(symbol)
        if df.empty:
            return jsonify({'error': '未找到该ETF的历史数据，请先下载'}), 404
            
        current_price = data_loader.get_latest_price(symbol)
        if current_price <= 0:
            return jsonify({'error': '当前价格无效'}), 400

        # 加载基准数据 (510300 - 沪深300ETF) 用于计算 Beta
        benchmark_df = data_loader.load_daily_data('510300')

        # 3. 策略生成 (Current - For Trading)
        context_current = GridContext(
            symbol=symbol,
            current_price=current_price,
            total_capital=total_capital,
            base_position_ratio=base_pos_ratio,
            cash_reserve_ratio=cash_res_ratio,
            pe_percentile=pe_percentile,
            pb_percentile=pb_percentile,
            force_mode=force_mode
        )
        
        strategy_current = SmartGridStrategy(context_current)
        strategy_result_current = strategy_current.generate(df, benchmark_df) 
        
        # 4. 回测 (Historical Simulation - For Validation)
        # 逻辑分离：为了让回测有意义，我们需要模拟"如果在一年前开始跑这个策略，效果如何"
        # 因此，回测用的网格参数（区间、步长）应该基于"一年前的价格和波动率"生成，而不是今天的。
        
        custom_start_date = data.get('custom_start_date')
        custom_end_date = data.get('custom_end_date')
        
        if custom_start_date:
            start_date_str = custom_start_date
        else:
            backtest_days = 365
            start_date_dt = datetime.now() - timedelta(days=backtest_days)
            start_date_str = start_date_dt.strftime('%Y-%m-%d')
            
        # 切分数据
        # 历史用于生成参数 (Pre-Start)
        df_history_for_params = df[df['date'] < start_date_str]
        
        # 未来用于回测 (Post-Start)
        if custom_end_date:
            df_backtest = df[(df['date'] >= start_date_str) & (df['date'] <= custom_end_date)].copy()
            # 同时切分用于计算指标的 DF (注意：indicators 需要历史数据，所以这里切分的是用于 PathSimulator 的数据)
            # 但下面的 df_backtest_with_indicators 是全量 df 的切片
            df_backtest_with_indicators = df[(df['date'] >= start_date_str) & (df['date'] <= custom_end_date)].copy()
        else:
            df_backtest = df[df['date'] >= start_date_str].copy()
            df_backtest_with_indicators = df[df['date'] >= start_date_str].copy()
        
        if df_history_for_params.empty or df_backtest.empty:
             return jsonify({'error': '数据不足或日期范围无效，无法进行回测分离计算'}), 400
             
        # 获取回测起点的价格 (使用回测第一天的 Open 或前一天的 Close)
        backtest_start_price = df_backtest.iloc[0]['open']
        
        # 构建回测用的 Context (假设当时的估值分位与现在相似，或者使用由当前推导的模式)
        # 注意：这里我们沿用当前计算出的 Mode，但重新计算 Price Range 和 Step
        context_backtest = GridContext(
            symbol=symbol,
            current_price=backtest_start_price,
            total_capital=total_capital,
            base_position_ratio=base_pos_ratio,
            cash_reserve_ratio=cash_res_ratio,
            pe_percentile=pe_percentile, # 假设估值逻辑一致
            pb_percentile=pb_percentile,
            force_mode=strategy_result_current.mode # 强制使用与当前一致的策略模式
        )
        
        strategy_backtest = SmartGridStrategy(context_backtest)
        strategy_result_backtest = strategy_backtest.generate(df_history_for_params, benchmark_df) # 基于过去数据生成网格
        
        # 计算回测区间的布林带 (为了画图)
        mid, upper, lower = Indicators.calculate_bollinger(df, context_current.bollinger_period, context_current.bollinger_std)
        df['boll_mid'] = mid
        df['boll_upper'] = upper
        df['boll_lower'] = lower
        
        # 重新切片布林带数据以匹配回测区间
        if custom_end_date:
            df_backtest_with_indicators = df[(df['date'] >= start_date_str) & (df['date'] <= custom_end_date)].copy()
        else:
            df_backtest_with_indicators = df[df['date'] >= start_date_str].copy()
        
        simulator = PathSimulator(
            grid_lines=strategy_result_backtest.grid_lines, # 使用基于历史生成的网格
            initial_capital=total_capital,
            base_position_ratio=base_pos_ratio # 使用用户输入的底仓比例
        )
        
        bt_result = simulator.run(df_backtest_with_indicators)
        
        # 5. 构造返回结果
        # 注意：前端展示的"策略建议"应该是 Current 的，但"回测结果"是 Backtest 的。
        # 可以在图表中展示 Backtest 用的网格线，而在卡片中展示 Current 网格线。
        # 或者为了避免混淆，明确标注。
        
        boll_mid = df_backtest_with_indicators['boll_mid'].tolist()
        boll_upper = df_backtest_with_indicators['boll_upper'].tolist()
        boll_lower = df_backtest_with_indicators['boll_lower'].tolist()
        
        response = {
            'strategy': { # 展示给用户的"明日策略"
                'mode': strategy_result_current.mode.value,
                'price_range': [strategy_result_current.price_min, strategy_result_current.price_max],
                'step': {
                    'price': strategy_result_current.step_price,
                    'percent': strategy_result_current.step_percent
                },
                'grid_count': strategy_result_current.grid_count,
                'per_grid': {
                    'cash': round(strategy_result_current.cash_per_grid, 2),
                    'volume': strategy_result_current.vol_per_grid,
                    'buy_vol': strategy_result_current.grid_lines[0].buy_vol,
                    'sell_vol': strategy_result_current.grid_lines[0].sell_vol
                },
                'description': strategy_result_current.description,
                'scores': {
                    'total': strategy_result_current.volatility_score,
                    'beta': strategy_result_current.beta,
                    'amplitude': strategy_result_current.amplitude
                },
                'grid_lines': [ # 当前建议的挂单表
                    {
                        'price': g.price,
                        'buy_vol': g.buy_vol,
                        'sell_vol': g.sell_vol
                    } for g in strategy_result_current.grid_lines
                ]
            },
            'backtest': { # 基于一年前参数跑出来的结果
                'parameters': { # 新增：回测时使用的参数快照
                    'price_range': [strategy_result_backtest.price_min, strategy_result_backtest.price_max],
                    'step': {
                        'price': strategy_result_backtest.step_price,
                        'percent': strategy_result_backtest.step_percent
                    },
                    'grid_count': strategy_result_backtest.grid_count,
                    'per_grid': {
                        'cash': round(strategy_result_backtest.cash_per_grid, 2),
                        'volume': strategy_result_backtest.vol_per_grid,
                        'buy_vol': strategy_result_backtest.grid_lines[0].buy_vol,
                        'sell_vol': strategy_result_backtest.grid_lines[0].sell_vol
                    }
                },
                'summary': {
                    'total_return': bt_result.total_return,
                    'annualized_return': bt_result.annualized_return,
                    'grid_profit': bt_result.grid_profit,
                    'float_pnl': bt_result.float_pnl,
                    'max_drawdown': bt_result.max_drawdown,
                    'sharpe_ratio': bt_result.sharpe_ratio,
                    'trade_count': bt_result.trade_count,
                    'buy_count': bt_result.buy_count,
                    'sell_count': bt_result.sell_count,
                    'break_rate': bt_result.break_rate,
                    'missed_trades': bt_result.missed_trades,
                    'capital_utilization': bt_result.capital_utilization,
                    'benchmark_total_return': bt_result.benchmark_total_return,
                    'benchmark_annualized_return': bt_result.benchmark_annualized_return,
                    'benchmark_max_drawdown': bt_result.benchmark_max_drawdown,
                    'benchmark_sharpe_ratio': bt_result.benchmark_sharpe_ratio
                },
                'curve': [
                    {
                        'date': item['date'],
                        'equity': round(item['equity'], 2),
                        'benchmark_equity': round(item.get('benchmark_equity', 0), 2),
                        'price': item['price'],
                        'open': item.get('open'),
                        'high': item.get('high'),
                        'low': item.get('low'),
                        'boll_mid': round(boll_mid[i], 3) if not pd.isna(boll_mid[i]) else None,
                        'boll_upper': round(boll_upper[i], 3) if not pd.isna(boll_upper[i]) else None,
                        'boll_lower': round(boll_lower[i], 3) if not pd.isna(boll_lower[i]) else None
                    } for i, item in enumerate(bt_result.daily_equity)
                ],
                'trades': [
                    {
                        'date': t.date,
                        'type': t.type,
                        'price': t.price,
                        'volume': t.volume,
                        'amount': t.amount,
                        'current_position': t.current_position,
                        'position_value': t.position_value,
                        'cash': t.cash,
                        'total_value': t.total_value
                    } for t in bt_result.trades
                ],
                'backtest_grid_lines': [ # 回测时实际使用的网格线 (用于图表绘制，不同于当前建议)
                    {
                        'price': g.price
                    } for g in strategy_result_backtest.grid_lines
                ]
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"""SmartGrid error: {str(e)}
{stack_trace}""")
        return jsonify({'error': str(e)}), 500