from flask import Blueprint, jsonify, render_template, request
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tools.earnings_dates_fetcher import EarningsDatesFetcher
from routes.stock_data_routes import get_current_price
import math

earnings_bp = Blueprint('earnings', __name__)

@earnings_bp.route('/earnings_analysis')
def earnings_analysis():
    # 获取 URL 参数中的 symbol
    symbol = request.args.get('symbol', '')
    return render_template('earnings_analysis.html', symbol=symbol)


def calculate_weighted_movement(historical_data, weights=None):
    """计算加权平均变动幅度，使用最近12个季度的数据"""
    # 只取最近12个季度的数据
    recent_data = historical_data[-12:] if len(historical_data) > 12 else historical_data
    
    # 生成权重，最近的季度权重最大
    if weights is None:
        weights = np.linspace(1, 12, len(recent_data))
    
    return np.average(recent_data, weights=weights)

def calculate_asymmetric_movements(historical_data, weights=None):
    """计算不对称的加权平均变动幅度"""
    up_movements = []
    down_movements = []
    up_weights = []
    down_weights = []
    
    # 生成基础权重
    if weights is None:
        weights = np.linspace(1, 12, len(historical_data))
    
    # 分离上涨和下跌
    for i, movement in enumerate(historical_data):
        if movement >= 0:
            up_movements.append(movement)
            up_weights.append(weights[i])
        else:
            down_movements.append(abs(movement))
            down_weights.append(weights[i])
    
    # 计算加权平均
    up_avg = np.average(up_movements, weights=up_weights) if up_movements else 0
    down_avg = np.average(down_movements, weights=down_weights) if down_movements else 0
    
    return up_avg, down_avg

def monte_carlo_simulation(historical_movements, n_simulations=10000):
    """
    执行蒙特卡洛模拟分析
    """
    # 将百分比变化转换为对数收益率
    log_returns = [math.log(1 + x/100) for x in historical_movements]
    
    # 计算均值和标准差
    mu = np.mean(log_returns)
    sigma = np.std(log_returns, ddof=1)  # ddof=1 使用样本标准差
    
    # 生成随机模拟
    simulated_log_returns = np.random.normal(mu, sigma, n_simulations)
    
    # 转换回百分比变化
    simulated_changes = [(math.exp(x) - 1) * 100 for x in simulated_log_returns]
    
    # 计算统计数据
    expected_change = (math.exp(mu + sigma**2/2) - 1) * 100
    percentiles = np.percentile(simulated_changes, [5, 25, 50, 75, 95])
    
    return {
        'expected_change': expected_change,
        'percentiles': {
            'p5': percentiles[0],
            'p25': percentiles[1],
            'p50': percentiles[2],
            'p75': percentiles[3],
            'p95': percentiles[4]
        },
        'simulated_changes': simulated_changes
    }

def calculate_expected_move(current_price, iv, days_to_expiry):
    """
    计算基于IV的预期波动率
    
    Args:
        current_price (float): 当前股价
        iv (float): 隐含波动率(以小数形式,如50%=0.50)
        days_to_expiry (int): 到期天数
        
    Returns:
        dict: 包含预期波动的字典
    """
    # 计算时间因子
    time_factor = math.sqrt(days_to_expiry / 365)
    
    # 计算预期波动(美元)
    expected_move_dollar = current_price * iv * time_factor
    
    # 计算预期波动(百分比)
    expected_move_percent = (expected_move_dollar / current_price) * 100
    
    # 计算预期价格范围
    expected_high = current_price + expected_move_dollar
    expected_low = current_price - expected_move_dollar
    
    return {
        'expected_move_dollar': expected_move_dollar,
        'expected_move_percent': expected_move_percent,
        'expected_high': expected_high,
        'expected_low': expected_low
    }

@earnings_bp.route('/api/earnings/analysis', methods=['POST'])
def analyze_earnings():
    data = request.json
    symbol = data.get('symbol')
    input_price = data.get('current_price')  # 获取用户输入的价格
    
    # 修复 IV 数据类型转换
    atm_call_iv = float(data.get('atm_call_iv', 0)) / 100 if data.get('atm_call_iv') else 0
    atm_put_iv = float(data.get('atm_put_iv', 0)) / 100 if data.get('atm_put_iv') else 0
    days_to_expiry = int(data.get('days_to_expiry', 0)) if data.get('days_to_expiry') else 0
    
    # 如果用户没有输入价格，则通过API获取
    if input_price is None:
        try:
            current_price_response = get_current_price(symbol)
            current_price_data = current_price_response.get_json()
            current_price = current_price_data.get('current_price')
            if current_price is None:
                return jsonify({
                    'error': f'无法获取 {symbol} 的当前价格，请手动输入当前价格'
                }), 400
        except Exception as e:
            return jsonify({
                'error': f'获取 {symbol} 的当前价格时出错：{str(e)}，请手动输入当前价格'
            }), 400
    else:
        try:
            current_price = float(input_price)
        except ValueError:
            return jsonify({
                'error': f'输入的价格格式不正确：{input_price}，请输入有效的数字'
            }), 400
    
    # 如果有IV数据,计算IV预期波动
    iv_expected_move = None
    if current_price and (atm_call_iv or atm_put_iv) and days_to_expiry:
        # 使用看涨和看跌期权IV的平均值
        avg_iv = (atm_call_iv + atm_put_iv) / 2 if atm_call_iv and atm_put_iv else (atm_call_iv or atm_put_iv)
        iv_expected_move = calculate_expected_move(current_price, avg_iv, days_to_expiry)
    
    # 获取历史财报数据
    fetcher = EarningsDatesFetcher()
    earnings_data = fetcher.get_earnings_volatility(symbol)
    
    # 按日期倒序排序
    if earnings_data:
        earnings_data = sorted(earnings_data, key=lambda x: x[1], reverse=True)
        
        # 获取5年数据用于蒙特卡洛分析
        monte_carlo_data = earnings_data[:20] if len(earnings_data) > 20 else earnings_data
        # 获取3年数据用于其他分析
        earnings_data = earnings_data[:12] if len(earnings_data) > 12 else earnings_data
    
    # 处理3年数据用于常规分析
    historical_movements = {
        'dates': [],
        'pre_earnings_price': [],
        'post_earnings_price': [],
        'movement_pct': []
    }
    
    # 处理5年数据用于蒙特卡洛分析
    monte_carlo_movements = []
    
    # 处理5年数据
    for record in monte_carlo_data:
        fiscal_date_ending, reported_date, report_time, pre_close, trade_date, open_price, close_price, reported_eps, estimated_eps = record
        price_change_pct = ((close_price - pre_close) / pre_close) * 100
        monte_carlo_movements.append(price_change_pct)
    
    # 处理3年数据
    for record in earnings_data:
        fiscal_date_ending, reported_date, report_time, pre_close, trade_date, open_price, close_price, reported_eps, estimated_eps = record
        
        # 计算价格变动百分比
        price_change_pct = ((close_price - pre_close) / pre_close) * 100
        
        historical_movements['dates'].append(reported_date)
        historical_movements['pre_earnings_price'].append(pre_close)
        historical_movements['post_earnings_price'].append(close_price)
        historical_movements['movement_pct'].append(price_change_pct)
    
    # 计算加权平均变动（对称和不对称）- 使用3年数据
    movements = np.abs(historical_movements['movement_pct'])
    weighted_movement = calculate_weighted_movement(movements)
    
    # 计算不对称变动 - 使用3年数据
    up_movement, down_movement = calculate_asymmetric_movements(
        historical_movements['movement_pct']
    )
    
    # 计算具体的建议行权价（对称和不对称两种）
    if current_price:
        # 对称方法
        symmetric_put = current_price * (1 - weighted_movement/100)
        symmetric_call = current_price * (1 + weighted_movement/100)
        
        # 不对称方法
        asymmetric_put = current_price * (1 - down_movement/100)
        asymmetric_call = current_price * (1 + up_movement/100)
    else:
        symmetric_put = symmetric_call = asymmetric_put = asymmetric_call = None
    
    # 执行蒙特卡洛模拟 - 使用5年数据
    monte_carlo_results = monte_carlo_simulation(monte_carlo_movements)
    
    return jsonify({
        'symbol': symbol,
        'current_price': current_price,
        'weighted_movement': weighted_movement,
        'asymmetric_movements': {
            'up_movement': up_movement,
            'down_movement': down_movement
        },
        'historical_data': {
            'dates': historical_movements['dates'],
            'movements': historical_movements['movement_pct'],
            'pre_prices': historical_movements['pre_earnings_price'],
            'post_prices': historical_movements['post_earnings_price']
        },
        'suggested_strikes': {
            'symmetric': {
                'put_strike': f"${symmetric_put:.2f} (当前价格 - {weighted_movement:.2f}%)" if symmetric_put else None,
                'call_strike': f"${symmetric_call:.2f} (当前价格 + {weighted_movement:.2f}%)" if symmetric_call else None
            },
            'asymmetric': {
                'put_strike': f"${asymmetric_put:.2f} (当前价格 - {down_movement:.2f}%)" if asymmetric_put else None,
                'call_strike': f"${asymmetric_call:.2f} (当前价格 + {up_movement:.2f}%)" if asymmetric_call else None
            }
        },
        'monte_carlo': {
            'expected_change': monte_carlo_results['expected_change'],
            'percentiles': monte_carlo_results['percentiles'],
            'simulated_changes': monte_carlo_results['simulated_changes'][:1000]  # 只返回部分模拟数据用于绘图
        },
        'iv_analysis': iv_expected_move
    })