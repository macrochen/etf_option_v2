from flask import Flask, render_template, request, jsonify
from datetime import datetime
from routes.scheme_routes import scheme_bp
from routes.backtest_routes import backtest_bp
from routes.volatility_routes import volatility_bp
from routes.stock_data_routes import stock_data_bp
from routes.etf_data_routes import etf_data_bp
from routes.tiger_routes import tiger_bp
from routes.futu_routes import futu_bp
from routes.earnings_routes import earnings_bp
from routes.option_routes import option_bp
from routes.sim_trade_routes import sim_trade_bp
from routes.hpc_routes import hpc_bp
from routes.shannon_routes import shannon_bp
from routes.data_download_routes import data_download_bp
from routes.wyckoff_routes import wyckoff_bp
from routes.portfolio_routes import portfolio_bp
from routes.symbol_mapping_routes import symbol_mapping_bp

app = Flask(__name__)

APP_DISPLAY_NAME = "交易策略与资产组合分析平台"
PROJECT_SLUG = "strategy_portfolio_platform"

# 注册蓝图
app.register_blueprint(scheme_bp)
app.register_blueprint(backtest_bp)
app.register_blueprint(volatility_bp)
app.register_blueprint(stock_data_bp)
app.register_blueprint(etf_data_bp)
app.register_blueprint(shannon_bp)
app.register_blueprint(earnings_bp)  # 注册财报分析蓝图
app.register_blueprint(data_download_bp)  # 注册数据下载蓝图
app.register_blueprint(wyckoff_bp) # 注册威科夫分析蓝图
app.register_blueprint(portfolio_bp) # 注册资产全景蓝图
app.register_blueprint(symbol_mapping_bp) # 注册标的映射管理蓝图

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

import requests
import time
import subprocess

# 缓存汇率数据
EXCHANGE_RATES_CACHE = {
    'data': None,
    'timestamp': 0
}

@app.route('/api/exchange_rates')
def get_exchange_rates():
    current_time = time.time()
    # 缓存 1 小时
    if EXCHANGE_RATES_CACHE['data'] and (current_time - EXCHANGE_RATES_CACHE['timestamp'] < 3600):
        return jsonify(EXCHANGE_RATES_CACHE['data'])
    
    try:
        # 获取 USD 汇率
        usd_res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        usd_data = usd_res.json()
        
        if usd_data['result'] == 'success':
            rates = {
                'USD_CNY': usd_data['rates']['CNY'],
                'HKD_CNY': usd_data['rates']['CNY'] / usd_data['rates']['HKD'],
                'timestamp': current_time
            }
            EXCHANGE_RATES_CACHE['data'] = rates
            EXCHANGE_RATES_CACHE['timestamp'] = current_time
            return jsonify(rates)
    except Exception as e:
        app.logger.error(f"获取汇率失败: {str(e)}")
    
    # 失败时返回兜底汇率
    return jsonify({
        'USD_CNY': 7.25,
        'HKD_CNY': 0.93,
        'is_fallback': True
    })

@app.route('/')
def index():
    return render_template('index.html', etf_options=ETF_OPTIONS)

@app.context_processor
def inject_app_metadata():
    return {
        'app_display_name': APP_DISPLAY_NAME,
        'project_slug': PROJECT_SLUG
    }

app.register_blueprint(tiger_bp)  # 注册Tiger API蓝图
app.register_blueprint(futu_bp)  # 注册富途 API蓝图
app.register_blueprint(option_bp)
app.register_blueprint(sim_trade_bp)
app.register_blueprint(hpc_bp)

@app.before_request
def log_request_info():
    if request.method == 'DELETE':
        app.logger.info(f"Handling DELETE request: {request.url}")

@app.errorhandler(404)
def page_not_found(e):
    app.logger.error(f"404 Error: {request.url}")
    return jsonify(error=str(e)), 404

def init_app():
    # 应用初始化代码，不再包含同步操作
    pass
    
if __name__ == "__main__":
    init_app()
    port = 5001
    
    # 检查端口是否被占用
    try:
        # 查找占用端口的进程
        result = subprocess.run(['lsof', '-i', f':{port}'], capture_output=True, text=True)
        if result.stdout:
            # 提取PID并终止进程
            pid = result.stdout.split('\n')[1].split()[1]
            # os.system(f'kill -9 {pid}')
            print(f'已终止占用端口 {port} 的进程 (PID: {pid})')
    except Exception as e:
        print(f'检查端口占用时出错: {e}')

    # app.run(host='192.168.31.133', port=5000, debug=True)
    # app.run(host='0.0.0.0', port=5000, debug=True)
    # app.run(host='192.168.31.113', port=5000, debug=True)
    # app.run(host='192.168.31.198', port=5000, debug=True)
    app.run(host='127.0.0.1', port=port, debug=True)
