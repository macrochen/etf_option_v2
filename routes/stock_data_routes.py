from flask import Blueprint, request, jsonify, render_template
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import yfinance as yf
from db.us_stock_db import USStockDatabase
from tools.volatility_data_generator import VolatilityDataGenerator
from datetime import datetime
import logging
import traceback

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
        db.save_stock_data(stock_code, date.date(), open_price, close_price, 'US')
    
    return jsonify({"message": f"{stock_code} data downloaded and saved to database successfully."})

@stock_data_bp.route('/download_hk', methods=['POST'])
def download_hk_data():
    stock_code = request.json['stock_code']
    
    logging.info(f"开始下载港股数据: {stock_code}")
    
    # 计算时间范围（5年）
    end_date = datetime.now() - timedelta(days=1)  # 昨天
    start_date = end_date - timedelta(days=365*5)  # 5年前
    
    # 转换为Unix时间戳
    period1 = int(start_date.timestamp())
    period2 = int(end_date.timestamp())
    
    # 构建API URL
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_code}.HK"
    params = {
        "period1": period1,
        "period2": period2,
        "interval": "1d",
        "events": "capitalGain|div|split",
        "includeAdjustedClose": "true"
    }
    
    try:
        # 发送请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://finance.yahoo.com',
            'Cookie':'GUC=AQABCAFnh0lnskIdigS3&s=AQAAAELmwDqB&g=Z4X8Jg; A3=d=AQABBBz8hWcCEO3wLIqVcFi8lVjEbZNID38FEgABCAFJh2eyZ-A9b2UB9qMAAAcIufuFZ-l6lkI&S=AQAAAqC6rv1ADBDQ9v3Vu-V-igo; A1=d=AQABBBz8hWcCEO3wLIqVcFi8lVjEbZNID38FEgABCAFJh2eyZ-A9b2UB9qMAAAcIufuFZ-l6lkI&S=AQAAAqC6rv1ADBDQ9v3Vu-V-igo; A1S=d=AQABBBz8hWcCEO3wLIqVcFi8lVjEbZNID38FEgABCAFJh2eyZ-A9b2UB9qMAAAcIufuFZ-l6lkI&S=AQAAAqC6rv1ADBDQ9v3Vu-V-igo; _cb=mwgT6CB6jQKDSTEBO; cmp=t=1737599781&j=1&u=1---&v=63; EuConsent=CQLOJoAQLOJoAAOACBDEBZFoAP_gAEPgACiQKptB9G7WTXFneXp2YPskOYUX0VBJ4MAwBgCBAcABzBIUIBwGVmAzJEyIICACGAIAIGBBIABtGAhAQEAAYIAFAABIAEgAIBAAIGAAACAAAABACAAAAAAAAAAQgEAXMBQgmAZEBFoIQUhAggAgAQAAAAAEAIgBCgQAEAAAQAAICAAIACgAAgAAAAAAAAAEAFAIEQAAIAECAotkdQAAAAAAAAAAAAAAAAABAAAAAIKpgAkGpUQBFgSEhAIGEECAEQUBABQIAgAACBAAAATBAUIAwAVGAiAEAIAAAAAAAAACABAAABAAhAAEAAQIAAAAAIAAgAIBAAACAAAAAAAAAAAAAAAAAAAAAAAAAGIBQggABABBAAQUAAAAAgAAAAAAAAAIgACAAAAAAAAAAAAAAIgAAAAAAAAAAAAAAAAAAIAAAAIAAAAgBEFgAAAAAAAAAAAAAAAAABAAAAAIAAA; PRF=t%3D0700.HK%252BTSLA; _chartbeat2=.1736834676457.1737600056687.1000000001.BY-IwoBuvrVRD70yvmBah2dBBXFDAd.3'
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        # 解析JSON响应
        data = response.json()
        
        if not data or 'chart' not in data or not data['chart']['result']:
            return jsonify({"error": "无法获取数据"}), 404
            
        # 获取数据
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quotes = result['indicators']['quote'][0]
        adjclose = result['indicators']['adjclose'][0]['adjclose']
        
        # 保存数据到数据库
        success_count = 0
        for i, timestamp in enumerate(timestamps):
            try:
                # 转换时间戳为日期
                date = datetime.fromtimestamp(timestamp).date()
                
                # 获取价格数据
                open_price = float(quotes['open'][i]) if quotes['open'][i] is not None else None
                close_price = float(quotes['close'][i]) if quotes['close'][i] is not None else None
                
                if open_price is not None and close_price is not None:
                    db.save_stock_data(stock_code, date, open_price, close_price, 'HK')
                    success_count += 1
                    
            except (TypeError, ValueError, IndexError) as e:
                logging.error(f"处理数据时出错: {e}, 股票代码: {stock_code}, 时间戳: {timestamp}")
                continue
        
        if success_count == 0:
            logging.warning(f"股票 {stock_code} 没有获取到任何有效数据")
            return jsonify({"error": "未能获取到任何有效数据"}), 404
            
        logging.info(f"股票 {stock_code} 数据下载完成，成功保存 {success_count} 条记录")
        return jsonify({
            "message": f"{stock_code} (HK) 数据下载并保存成功",
            "count": success_count
        })
        
    except requests.RequestException as e:
        stack_trace = traceback.format_exc()
        print(f"API请求异常: \n{stack_trace}")  # 打印堆栈信息到控制台
        return jsonify({
            "error": "获取数据失败",
            "details": str(e),
            "stack_trace": stack_trace
        }), 500
    except Exception as e:
        stack_trace = traceback.format_exc()
        print(f"数据处理异常: \n{stack_trace}")  # 打印堆栈信息到控制台
        return jsonify({
            "error": "处理数据时出错",
            "details": str(e),
            "stack_trace": stack_trace
        }), 500

@stock_data_bp.route('/api/generate_volatility/<stock_code>', methods=['POST'])
def generate_volatility(stock_code):
    """生成指定股票的历史波动率数据"""
    market_type = request.json.get('market_type', 'US')  # 获取市场类型，默认为US
    
    # 根据市场类型选择不同的生成器
    if market_type == 'US':
        from tools.volatility_data_generator import USVolatilityDataGenerator
        volatility_generator = USVolatilityDataGenerator(db)
    elif market_type == 'HK':
        from tools.volatility_data_generator import HKVolatilityDataGenerator
        volatility_generator = HKVolatilityDataGenerator(db)
    else:
        return jsonify({"error": f"不支持的市场类型: {market_type}"}), 400

    # 生成波动率数据
    volatility_generator.generate_data([stock_code])

    return jsonify({
        "message": f"{market_type}市场的{stock_code}波动率数据生成并保存成功"
    }), 201

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