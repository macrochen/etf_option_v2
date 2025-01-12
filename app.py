from flask import Flask, render_template, request, jsonify
from datetime import datetime
from routes.scheme_routes import scheme_bp
from routes.backtest_routes import backtest_bp


app = Flask(__name__)

# 注册蓝图
app.register_blueprint(scheme_bp)
app.register_blueprint(backtest_bp)

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

@app.route('/')
def index():
    return render_template('index.html', etf_options=ETF_OPTIONS)

if __name__ == '__main__':
    app.run(debug=True) 