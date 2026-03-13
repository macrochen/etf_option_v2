from flask import Blueprint, jsonify, request, render_template
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from grid.min_data_loader import MinDataLoader
from grid.shannon_engine import ShannonEngine
from services.shannon_scorer import ShannonGridScorer
from services.similarity_searcher import SimilaritySearcher
from grid.boundary_calc import DynamicGridBoundary
import logging

shannon_bp = Blueprint('shannon', __name__)
min_loader = MinDataLoader()
boundary_calc = DynamicGridBoundary()
similarity_searcher = SimilaritySearcher()

def safe_float(value, default):
    try:
        if value is None or value == '':
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)

def clean_nan(obj):
    """递归将 NaN/Inf 替换为 0.0，确保 JSON 兼容"""
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    elif isinstance(obj, float) or np.isscalar(obj):
        try:
            val = float(obj)
            if np.isnan(val) or np.isinf(val):
                return 0.0
            return val
        except (ValueError, TypeError):
            return obj
    return obj

@shannon_bp.route('/api/grid_trade/etf_list', methods=['GET'])
def get_etf_list():
    """获取已有的ETF列表 (基于分钟线数据库)"""
    loader = MinDataLoader()
    etf_list = loader.get_etf_list()
    return jsonify(etf_list)

@shannon_bp.route('/api/shannon/score', methods=['GET'])
def get_shannon_score():
    """获取香农网格适格性评分"""
    try:
        symbol = request.args.get('symbol')
        if not symbol:
            return jsonify({'error': 'Missing symbol'}), 400
            
        # 加载全量日线数据 (从分钟数据聚合)
        df_daily = min_loader.load_daily_data(symbol)
        
        if df_daily.empty:
            return jsonify({'error': 'No data found for scoring'}), 404
        
        scorer = ShannonGridScorer(df_daily)
        result = scorer.calculate_score()
        
        return jsonify(clean_nan(result))
        
    except Exception as e:
        logging.error(f"Shannon Score Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def _get_engine(symbol, start_date, end_date):
    """
    Helper to load data and init engine.
    Strictly local REAL minute data only.
    """
    # 尝试从本地加载
    df = min_loader.load_data(symbol, start_date, end_date)
    
    if df.empty:
        raise ValueError(f"本地未找到 {symbol} 的分钟数据。请确保已下载数据或导入数据到数据库。")
        
    return ShannonEngine(df)

def _build_atr_snapshot(symbol, current_date, window_start_date=None):
    """计算指定日期的 ATR20 及其历史分位。"""
    df_daily = min_loader.load_daily_data(symbol)
    if df_daily.empty:
        return None

    target_dt = pd.to_datetime(current_date)
    df_daily = df_daily[df_daily['date'] <= target_dt].copy()
    if df_daily.empty:
        return None

    df_daily['prev_close'] = df_daily['close'].shift(1)
    tr_components = pd.concat([
        (df_daily['high'] - df_daily['low']).abs(),
        (df_daily['high'] - df_daily['prev_close']).abs(),
        (df_daily['low'] - df_daily['prev_close']).abs(),
    ], axis=1)
    df_daily['tr'] = tr_components.max(axis=1)
    df_daily['atr20'] = df_daily['tr'].rolling(20).mean()
    df_daily['atr20_pct'] = np.where(df_daily['close'] > 0, df_daily['atr20'] / df_daily['close'], np.nan)

    hist = df_daily.dropna(subset=['atr20_pct']).copy()
    if window_start_date:
        start_dt = pd.to_datetime(window_start_date)
        hist = hist[hist['date'] >= start_dt]

    if hist.empty:
        return None

    current_row = hist.iloc[-1]
    current_atr_pct = float(current_row['atr20_pct'])
    rank_pct = float((hist['atr20_pct'] < current_atr_pct).mean() * 100)

    if rank_pct < 20:
        status = '低波动'
    elif rank_pct > 80:
        status = '高波动'
    else:
        status = '适中'

    return {
        'atr20_pct': round(current_atr_pct * 100, 2),
        'percentile': round(rank_pct, 1),
        'status': status,
        'window_start': hist['date'].iloc[0].strftime('%Y-%m-%d'),
        'window_end': hist['date'].iloc[-1].strftime('%Y-%m-%d'),
        'actual_date': current_row['date'].strftime('%Y-%m-%d')
    }


@shannon_bp.route('/api/shannon/download_data', methods=['POST'])
def download_data():
    """专门的数据下载接口"""
    try:
        data = request.json
        symbol = data['symbol']
        logging.info(f"Starting manual download for {symbol}...")
        
        sync_result = min_loader.update_data(symbol)

        if sync_result.get('success'):
            return jsonify({
                'success': True,
                'info': sync_result.get('info'),
                'sync': sync_result
            })

        return jsonify({
            'success': False,
            'error': sync_result.get('message') or '下载失败或数据源无数据',
            'sync': sync_result
        }), 400
            
    except Exception as e:
        logging.error(f"Download Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@shannon_bp.route('/api/shannon/similar_scenarios', methods=['GET'])
def get_similar_scenarios():
    """获取历史相似情景"""
    try:
        symbol = request.args.get('symbol')
        metric = request.args.get('metric', 'auto')
        if not symbol:
            return jsonify({'error': 'Missing symbol'}), 400
            
        result = similarity_searcher.find_similar_moments(symbol, metric_preference=metric)
        return jsonify(clean_nan(result))
    except Exception as e:
        logging.error(f"Similar Scenarios Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@shannon_bp.route('/api/shannon/price_info', methods=['GET'])
def get_price_info():
    """根据标的和日期获取开盘价及推荐网格区间"""
    try:
        symbol = request.args.get('symbol')
        date_str = request.args.get('date')
        start_date = request.args.get('start_date') or None
        metric = request.args.get('metric', 'auto')
        
        if not symbol or not date_str:
            return jsonify({'error': 'Missing symbol or date'}), 400
            
        # 使用 MinDataLoader 获取指定日期的数据
        # 为了性能，限制 end_date = start_date + 7 days (寻找最近交易日)
        next_week = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=7)).strftime('%Y-%m-%d')
        df = min_loader.load_data(symbol, start_date=date_str, end_date=next_week)
        
        if df.empty:
            return jsonify({'error': 'No data found near this date'}), 404
        
        # 取第一条数据作为基准
        first_row = df.iloc[0]
        base_price = float(first_row['open'])
        
        # 使用 DynamicGridBoundary 计算动态上下限
        # 传入 start_date 作为回测视角下的"当前时间"
        limits = boundary_calc.calculate_limits(symbol, base_price, date_str, metric, window_start_date=start_date)
        
        return jsonify({
            'success': True,
            'price': base_price,
            'rec_lower': limits['lower'],
            'rec_upper': limits['upper'],
            'valuation': limits['valuation'],
            'volatility': _build_atr_snapshot(symbol, date_str, start_date),
            'actual_date': str(first_row['timestamp'])[:10]
        })
        
    except Exception as e:
        logging.error(f"Price Info Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@shannon_bp.route('/api/shannon/planner_snapshot', methods=['GET'])
def get_planner_snapshot():
    """获取网格参数规划卡所需的快照。"""
    try:
        symbol = request.args.get('symbol')
        metric = request.args.get('metric', 'auto')
        plan_date = request.args.get('date')
        if not symbol:
            return jsonify({'error': 'Missing symbol'}), 400

        available_range = min_loader.get_available_range(symbol)
        if not available_range:
            return jsonify({'error': 'No local data available'}), 404

        latest_date = available_range['end'][:10]
        df_daily = min_loader.load_daily_data(symbol)
        if df_daily.empty:
            return jsonify({'error': 'No daily data available'}), 404

        requested_date = plan_date or latest_date
        actual_date = latest_date
        price_source = 'latest_close'
        current_price = None

        if requested_date and requested_date < latest_date:
            next_week = (datetime.strptime(requested_date, '%Y-%m-%d') + timedelta(days=7)).strftime('%Y-%m-%d')
            df_min = min_loader.load_data(symbol, start_date=requested_date, end_date=next_week)
            if not df_min.empty:
                first_row = df_min.iloc[0]
                current_price = float(first_row['open'])
                actual_date = str(first_row['timestamp'])[:10]
                price_source = 'session_open'
            else:
                future_daily = df_daily[df_daily['date'] >= pd.to_datetime(requested_date)]
                if future_daily.empty:
                    return jsonify({'error': 'No data found near requested planning date'}), 404
                first_daily = future_daily.iloc[0]
                current_price = float(first_daily['open'])
                actual_date = first_daily['date'].strftime('%Y-%m-%d')
                price_source = 'daily_open'
        else:
            latest_row = df_daily.iloc[-1]
            current_price = float(latest_row['close'])
            actual_date = latest_row['date'].strftime('%Y-%m-%d')

        limits = boundary_calc.calculate_limits(symbol, current_price, actual_date, metric)

        kline = []
        for _, row in df_daily.iterrows():
            kline.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'open': round(float(row['open']), 3),
                'high': round(float(row['high']), 3),
                'low': round(float(row['low']), 3),
                'close': round(float(row['close']), 3),
            })

        return jsonify({
            'success': True,
            'latest_date': latest_date,
            'requested_date': requested_date,
            'actual_date': actual_date,
            'price_source': price_source,
            'current_price': round(current_price, 3),
            'rec_lower': limits['lower'],
            'rec_upper': limits['upper'],
            'valuation': limits['valuation'],
            'volatility': _build_atr_snapshot(symbol, actual_date),
            'kline': kline,
        })
    except Exception as e:
        logging.error(f"Planner Snapshot Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@shannon_bp.route('/api/shannon/planner_edge', methods=['GET'])
def get_planner_edge():
    """基于历史相似样本估算当前规划的经验胜率。"""
    try:
        symbol = request.args.get('symbol')
        metric = request.args.get('metric', 'auto')
        current_price = safe_float(request.args.get('current_price'), 0)
        lower = safe_float(request.args.get('lower'), 0)
        upper = safe_float(request.args.get('upper'), 0)
        as_of_date = request.args.get('as_of_date') or None
        if not symbol:
            return jsonify({'error': 'Missing symbol'}), 400

        result = similarity_searcher.estimate_planner_edge(
            symbol,
            current_price=current_price,
            lower=lower,
            upper=upper,
            metric_preference=metric,
            as_of_date=as_of_date,
        )
        status = 400 if result.get('error') else 200
        return jsonify(clean_nan(result)), status
    except Exception as e:
        logging.error(f"Planner Edge Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@shannon_bp.route('/shannon')
def index():
    return render_template('shannon_grid.html')

@shannon_bp.route('/api/shannon/backtest', methods=['POST'])
def run_backtest():
    try:
        data = request.json
        symbol = data['symbol']
        start_date = data.get('start_date', '2023-01-01')
        end_date = data.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        
        # 策略参数
        initial_capital = safe_float(data.get('initial_capital'), 100000)
        grid_density = safe_float(data.get('grid_density'), 0.015)
        sell_gap = safe_float(data.get('sell_gap'), 0.02)
        pos_per_grid = safe_float(data.get('pos_per_grid'), 5000)  # 每格固定份额
        
        # 顶层资产配置 (百分比转小数)
        faith_ratio = safe_float(data.get('faith_ratio'), 0.0) / 100.0
        grid_ratio = safe_float(data.get('grid_ratio'), 30.0) / 100.0
        
        lower_limit = safe_float(data.get('lower_limit'), 0.0)
        upper_limit = safe_float(data.get('upper_limit'), 999.0)
        boundary_source = 'user_input'
        
        # 初始化引擎
        engine = _get_engine(symbol, start_date, end_date)
        
        # 如果前端还没拿到推荐值，则按与 UI 一致的口径补默认边界
        if lower_limit <= 0.0 or upper_limit >= 999.0:
            try:
                boundary_date = start_date or end_date
                next_week = (datetime.strptime(boundary_date, '%Y-%m-%d') + timedelta(days=7)).strftime('%Y-%m-%d')
                boundary_df = min_loader.load_data(symbol, start_date=boundary_date, end_date=next_week)
                if not boundary_df.empty:
                    base_price = float(boundary_df.iloc[0]['open'])
                    limits = boundary_calc.calculate_limits(symbol, base_price, boundary_date)
                    if lower_limit <= 0.0:
                        lower_limit = limits['lower']
                    if upper_limit >= 999.0:
                        upper_limit = limits['upper']
                    boundary_source = 'auto_start_based'
                    logging.info(f"Backtest initialized with start-based limits: {lower_limit} - {upper_limit}")
            except Exception as e:
                logging.error(f"Error calculating fallback backtest limits: {e}")
        
        # 运行回测
        result = engine.run(
            initial_capital=initial_capital,
            grid_density=grid_density,
            sell_gap=sell_gap,
            pos_per_grid=pos_per_grid,
            faith_ratio=faith_ratio,
            grid_ratio=grid_ratio,
            lower_limit=lower_limit,
            upper_limit=upper_limit
        )
        
        # 计算核心指标
        equity_curve = result['equity_curve']
        cash_history = result['cash_history']
        initial = initial_capital
        final = result['final_equity']
        
        total_return = (final - initial) / initial * 100
        
        # 最大回撤
        max_eq = np.maximum.accumulate(equity_curve)
        dd = (max_eq - equity_curve) / max_eq
        max_drawdown = np.max(dd) * 100
        
        # 套牢时长 (Max Underwater Days)
        # 统计连续处于 watermark 以下的天数 (近似分钟数 / 240)
        is_underwater = equity_curve < max_eq
        max_underwater_days = 0
        current_run = 0
        for u in is_underwater:
            if u:
                current_run += 1
            else:
                if current_run > max_underwater_days:
                    max_underwater_days = current_run
                current_run = 0
        # 补丁：处理一直处于水位下的情况
        if current_run > max_underwater_days:
            max_underwater_days = current_run
            
        max_underwater_days = round(max_underwater_days / 240, 1) # 换算为天
        
        # 资金效率 (Avg Cash Utilization)
        if len(equity_curve) > 0:
            utilization_curve = np.where(equity_curve > 0, (equity_curve - cash_history) / equity_curve, 0)
            avg_utilization = np.mean(utilization_curve) * 100
            max_utilization = np.max(utilization_curve) * 100
            min_cash = np.min(cash_history)
        else:
            avg_utilization = max_utilization = min_cash = 0.0
        
        # 构建 Daily Curve (用于前端图表)
        try:
            df = engine.df.copy()
            df['equity'] = equity_curve
            df['dt'] = pd.to_datetime(df['ts_int'].astype(str), format='%Y%m%d%H%M')
            df['date_str'] = df['dt'].dt.strftime('%Y-%m-%d')
            
            daily_df = df.groupby('date_str').agg({
                'equity': 'last',
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last' 
            }).reset_index()
            
            # --- 优化 MA250 计算 ---
            # 为了让回测第一天就有 MA250，我们需要加载更早的数据进行预热
            # 1. 计算预热开始时间 (提前 400 天，确保覆盖 250 个交易日)
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            warmup_start = (start_dt - timedelta(days=600)).strftime('%Y-%m-%d')
            
            # 2. 加载预热数据 (只用于算 MA)
            # 注意：这里会重新查询数据库，耗时稍增但值得
            df_warmup = min_loader.load_data(symbol, warmup_start, end_date)
            
            # 3. 聚合为日线
            # df_warmup['timestamp'] 通常是 "YYYY-MM-DD HH:MM:SS" 字符串
            df_warmup['dt'] = pd.to_datetime(df_warmup['timestamp'])
            df_warmup['date_str'] = df_warmup['dt'].dt.strftime('%Y-%m-%d')
            daily_warmup = df_warmup.groupby('date_str')['close'].last().reset_index()
            
            # 4. 计算全量均线
            daily_warmup['ma20'] = daily_warmup['close'].rolling(20).mean()
            daily_warmup['ma250'] = daily_warmup['close'].rolling(250).mean()
            
            # 5. 建立映射表
            ma20_map = daily_warmup.set_index('date_str')['ma20'].to_dict()
            ma250_map = daily_warmup.set_index('date_str')['ma250'].to_dict()
            
            # 3. 构建返回列表
            daily_curve = []
            if daily_df.empty:
                 raise ValueError("Backtest generated no daily data (time range too short?)")

            base_close = daily_df.iloc[0]['close']
            for _, row in daily_df.iterrows():
                d_str = row['date_str']
                daily_curve.append({
                    'date': d_str,
                    'equity': row['equity'],
                    'benchmark': initial * (row['close'] / base_close),
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'ma20': ma20_map.get(d_str),
                    'ma250': ma250_map.get(d_str) # 从全量映射表中取值
                })

            # Benchmark 指标计算 (Buy & Hold)
            bench_return = (daily_df.iloc[-1]['close'] - base_close) / base_close * 100
            bench_prices = daily_df['close'].values
            bench_max_p = np.maximum.accumulate(bench_prices)
            bench_dd = (bench_max_p - bench_prices) / bench_max_p
            bench_max_dd = np.max(bench_dd) * 100
            
            # 夏普比率计算 (基于日线)
            equity_series = pd.Series([d['equity'] for d in daily_curve])
            returns = equity_series.pct_change().dropna()
            if returns.std() > 0:
                sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)
            else:
                sharpe_ratio = 0.0
                
            # 年化收益率 (CAGR)
            days_trading = len(equity_curve) / 240
            if days_trading > 10: # 至少10个交易日才算年化，否则太失真
                annualized_return = ((final / initial) ** (252 / days_trading) - 1) * 100
            else:
                annualized_return = total_return # 短期直接用总收益
                
            # 基准夏普
            bench_series = pd.Series([d['benchmark'] for d in daily_curve])
            bench_returns = bench_series.pct_change().dropna()
            if bench_returns.std() > 0:
                bench_sharpe = (bench_returns.mean() / bench_returns.std()) * np.sqrt(252)
            else:
                bench_sharpe = 0.0
                
            # 心理按摩指标
            # 1. 回撤优化率
            if bench_max_dd > 0.001: 
                dd_reduction = (bench_max_dd - max_drawdown) / bench_max_dd * 100
            else:
                dd_reduction = 0.0
            
            # 2. 卡玛比率 (年化收益 / 最大回撤)
            calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0.1 else annualized_return / 0.1
            bench_annual = ((initial * (daily_df.iloc[-1]['close'] / base_close) / initial) ** (252 / days_trading) - 1) * 100 if days_trading > 10 else bench_return
            bench_calmar = bench_annual / bench_max_dd if bench_max_dd > 0.1 else bench_annual / 0.1
            
            # 3. 夏普提升率
            if abs(bench_sharpe) > 0.01:
                sharpe_imp = (sharpe_ratio - bench_sharpe) / abs(bench_sharpe) * 100
            else:
                sharpe_imp = 0.0
                
            # 4. 卡玛提升率
            if abs(bench_calmar) > 0.01:
                calmar_imp = (calmar_ratio - bench_calmar) / abs(bench_calmar) * 100
            else:
                calmar_imp = 0.0

            # 清洗 NaN
            for v in [dd_reduction, sharpe_imp, calmar_imp, calmar_ratio, bench_calmar]:
                if np.isnan(v) or np.isinf(v):
                    v = 0.0

        except Exception as e:
            logging.error(f"Error constructing daily curve: {e}", exc_info=True)
            raise e

        response_raw = {
            'metrics': {
                'total_return': round(total_return, 2),
                'annualized_return': round(annualized_return, 2),
                'max_drawdown': round(max_drawdown, 2),
                'final_equity': round(final, 2),
                'trade_count': len(result['trades']),
                'max_underwater_days': max_underwater_days,
                'avg_utilization': round(avg_utilization, 2),
                'max_utilization': round(max_utilization, 2),
                'min_cash': round(min_cash, 2),
                'data_mode': 'REAL',
                'bench_return': round(bench_return, 2),
                'bench_max_drawdown': round(bench_max_dd, 2),
                'sharpe_ratio': round(sharpe_ratio, 2),
                'bench_sharpe': round(bench_sharpe, 2),
                'sharpe_imp': round(sharpe_imp, 1),
                'calmar_ratio': round(calmar_ratio, 2),
                'bench_calmar': round(bench_calmar, 2),
                'calmar_imp': round(calmar_imp, 1),
                'dd_reduction': round(dd_reduction, 1)
            },
            'daily_curve': daily_curve,
            'trades': result['trades'],
            'boundaries': {
                'lower_limit': round(lower_limit, 3),
                'upper_limit': round(upper_limit, 3),
                'source': boundary_source
            }
        }
        
        return jsonify(clean_nan(response_raw))
        
    except Exception as e:
        logging.error(f"Shannon Backtest Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@shannon_bp.route('/api/shannon/heatmap', methods=['POST'])
def run_heatmap():
    try:
        data = request.json
        symbol = data['symbol']
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # 固定参数
        initial_capital = float(data.get('initial_capital', 100000))
        pos_per_grid = float(data.get('pos_per_grid', 5000))  # 每格固定份额
        faith_ratio = float(data.get('faith_ratio', 0.0)) / 100.0
        grid_ratio = float(data.get('grid_ratio', 30.0)) / 100.0
        
        lower_limit = float(data.get('lower_limit', 0.0))
        upper_limit = float(data.get('upper_limit', 999.0))
        
        # 扫描范围
        density_range = np.arange(0.005, 0.051, 0.005) # 10 steps
        gap_range = np.arange(0.005, 0.051, 0.005)     # 10 steps
        
        engine = _get_engine(symbol, start_date, end_date)
        heatmap_data = []
        
        # 预热
        engine.run(initial_capital, 0.01, 0.01, pos_per_grid, faith_ratio, grid_ratio, lower_limit, upper_limit)
        
        for d in density_range:
            row_data = []
            for g in gap_range:
                res = engine.run(
                    initial_capital=initial_capital,
                    grid_density=d,
                    sell_gap=g,
                    pos_per_grid=pos_per_grid,
                    faith_ratio=faith_ratio,
                    grid_ratio=grid_ratio,
                    lower_limit=lower_limit,
                    upper_limit=upper_limit
                )
                
                # 计算夏普比率 (性能优化版)
                # 1. 降采样分钟线到日线 (每 240 点取一个)
                # 假设每天固定 240 分钟，取收盘净值
                equity_min = res['equity_curve']
                if len(equity_min) > 240:
                    # 使用切片 [239::240] 取每天第 240 分钟的值
                    equity_daily = equity_min[239::240]
                    # 计算日收益率: (Today - Yesterday) / Yesterday
                    # numpy diff / shift
                    if len(equity_daily) > 1:
                        daily_returns = np.diff(equity_daily) / equity_daily[:-1]
                        std = np.std(daily_returns)
                        mean = np.mean(daily_returns)
                        sharpe = (mean / std) * np.sqrt(252) if std > 0 else 0.0
                    else:
                        sharpe = 0.0
                else:
                    sharpe = 0.0
                
                # 计算总收益和回撤用于 Calmar
                final_eq = res['final_equity']
                total_ret_pct = (final_eq - initial_capital) / initial_capital * 100
                
                # 最大回撤
                eq_curve = res['equity_curve']
                max_eq = np.maximum.accumulate(eq_curve)
                dd = (max_eq - eq_curve) / max_eq
                max_dd = np.max(dd) * 100
                
                # Calmar = 年化收益 / 最大回撤
                # 简单估算年化：总收益 / (天数/252)
                # 分钟数 -> 天数
                days_approx = len(eq_curve) / 240
                if days_approx > 0:
                    annual_ret = total_ret_pct / (days_approx / 252)
                else:
                    annual_ret = 0.0
                    
                if max_dd > 0.1: # 避免除以0或极小回撤
                    calmar = annual_ret / max_dd
                else:
                    calmar = 10.0 # 极佳 (无回撤)
                
                row_data.append({
                    'density': round(d * 100, 1), 
                    'gap': round(g * 100, 1), 
                    'value': round(sharpe, 2),
                    'calmar': round(calmar, 2),
                    'ret': round(total_ret_pct, 2)
                })
            heatmap_data.append(row_data)
            
        return jsonify(clean_nan({
            'x_axis': [f"{x*100:.1f}%" for x in gap_range],
            'y_axis': [f"{y*100:.1f}%" for y in density_range],
            'data': heatmap_data
        }))
        
    except Exception as e:
        logging.error(f"Shannon Heatmap Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500