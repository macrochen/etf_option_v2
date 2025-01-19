from flask import Blueprint, request, jsonify, render_template
import yfinance as yf
from db.us_stock_db import USStockDatabase
from tools.volatility_data_generator import VolatilityDataGenerator
from datetime import datetime

# 创建蓝图
stock_data_bp = Blueprint('stock_data', __name__)
db = USStockDatabase()

@stock_data_bp.route('/us_stock_volatility_management', methods=['GET'])
def download_page():
    return render_template('stock_volatility_management.html')

@stock_data_bp.route('/download', methods=['POST'])
def download_data():
    stock_code = request.json['stock_code']  # 从请求中获取股票代码
    
    # 下载最近十年的股价数据
    data = yf.download(stock_code, start="2013-01-01", end="2025-01-01")
    
    # 存储到数据库
    for date, row in data.iterrows():
        # 使用 item() 方法获取单个值并转换为浮点数
        open_price = float(row['Open'].item())
        close_price = float(row['Close'].item())
        db.save_stock_data(stock_code, date.date(), open_price, close_price)
    
    return jsonify({"message": f"{stock_code} data downloaded and saved to database successfully."})

@stock_data_bp.route('/api/generate_volatility/<stock_code>', methods=['POST'])
def generate_volatility(stock_code):
    """生成指定股票的历史波动率数据"""
    # 生成波动率数据
    volatility_generator = VolatilityDataGenerator(db)  # 使用USStockDatabase类
    volatility_generator.generate_data([stock_code])

    return jsonify({"message": "波动率数据生成并保存成功"}), 201

@stock_data_bp.route('/api/stock_list', methods=['GET'])
def get_stock_list():
    """获取已下载的股票列表"""
    stock_list = db.get_stock_list()
    return jsonify(stock_list)

@stock_data_bp.route('/api/volatility/<stock_code>', methods=['GET'])
def get_volatility(stock_code):
    """获取指定股票的波动率数据"""
    volatility = db.get_volatility(stock_code)
    if volatility:
        return jsonify(volatility)
    else:
        return jsonify({"message": "No volatility data found."}), 404 