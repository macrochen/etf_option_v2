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
from tools.earnings_dates_fetcher import EarningsDatesFetcher
from tools.volatility_data_generator import USVolatilityDataGenerator
from tools.volatility_data_generator import HKVolatilityDataGenerator
from pathlib import Path

# 创建蓝图
stock_data_bp = Blueprint('stock_data', __name__)
db = USStockDatabase()

@stock_data_bp.route('/us_stock_volatility_management', methods=['GET'])
def download_page():
    return render_template('stock_volatility_management.html')

@stock_data_bp.route('/download', methods=['POST'])
def download_data():
    stock_code = request.json['stock_code']  # 从请求中获取股票代码
    
    logging.info(f"开始下载美股数据: {stock_code}")
    
    try:
        # 计算时间范围（10年）
        end_date = datetime.now() - timedelta(days=1)  # 昨天
        start_date = end_date - timedelta(days=365*10)  # 10年前
        
        # 获取股票信息
        ticker = yf.Ticker(stock_code)
        stock_info = ticker.info
        stock_name = stock_info.get('longName') or stock_info.get('shortName', '')
        
        # 下载股价数据
        logging.info(f"从 Yahoo Finance 获取 {stock_code} ({stock_name}) 的历史数据")
        data = yf.download(stock_code, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
        
        if data.empty:
            logging.warning(f"股票 {stock_code} 没有获取到任何数据")
            return jsonify({"error": "未能获取到任何数据"}), 404
        
        # 存储到数据库
        success_count = 0
        for date, row in data.iterrows():
            try:
                # 使用 item() 方法获取单个值并转换为浮点数
                open_price = float(row['Open'].item())
                high_price = float(row['High'].item())
                low_price = float(row['Low'].item())
                close_price = float(row['Close'].item())
                # 如果有 Adj Close 则使用，否则使用 Close
                adj_close = float(row['Adj Close'].item()) if 'Adj Close' in row else close_price
                
                db.save_stock_data(
                    stock_code, 
                    date.date(), 
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    adj_close,
                    'US',
                    stock_name  # 添加股票名称
                )
                success_count += 1
            except (TypeError, ValueError) as e:
                logging.error(f"处理数据时出错: {e}, 股票代码: {stock_code}, 日期: {date}")
                continue
        
        if success_count == 0:
            logging.warning(f"股票 {stock_code} 没有保存任何有效数据")
            return jsonify({"error": "未能保存任何有效数据"}), 404
            
        logging.info(f"股票 {stock_code} 数据下载完成，成功保存 {success_count} 条记录")
        return jsonify({
            "message": f"{stock_code} 数据下载并保存成功",
            "count": success_count
        })
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"下载美股数据时出错: {e}\n{stack_trace}")
        return jsonify({
            "error": "下载数据失败",
            "details": str(e),
            "stack_trace": stack_trace
        }), 500
    
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

        # 获取股票名称
        meta = result.get('meta', {})
        stock_name = meta.get('longName', '') or meta.get('shortName', '')
        
        # 保存数据到数据库
        success_count = 0
        for i, timestamp in enumerate(timestamps):
            try:
                # 转换时间戳为日期
                date = datetime.fromtimestamp(timestamp).date()
                
                # 获取价格数据
                open_price = float(quotes['open'][i]) if quotes['open'][i] is not None else None
                high_price = float(quotes['high'][i]) if quotes['high'][i] is not None else None
                low_price = float(quotes['low'][i]) if quotes['low'][i] is not None else None
                close_price = float(quotes['close'][i]) if quotes['close'][i] is not None else None
                adj_close = float(adjclose[i]) if adjclose[i] is not None else None
                
                if all(x is not None for x in [open_price, high_price, low_price, close_price, adj_close]):
                    db.save_stock_data(
                        stock_code,
                        date,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        adj_close,
                        'HK',
                        stock_name  # 添加股票名称参数
                    )
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

@stock_data_bp.route('/api/current_price/<stock_code>', methods=['GET'])
def get_current_price(stock_code):
    """获取指定股票的当前价格"""
    try:
        # 从请求参数中获取市场类型，默认为US
        market_type = request.args.get('market_type', 'US')
        
        logging.info(f"开始获取{market_type}市场的{stock_code}当前价格")
        
        # 根据市场类型构建完整的股票代码
        full_code = f"{stock_code}.HK" if market_type == 'HK' else stock_code
        
        # 使用yfinance获取实时数据
        ticker = yf.Ticker(full_code)
        current_data = ticker.history(period='1d')
        
        if current_data.empty:
            logging.warning(f"无法获取{stock_code}的当前价格数据")
            return jsonify({"error": "无法获取当前价格"}), 404
            
        # 获取最新价格
        latest_price = float(current_data['Close'].iloc[-1])
        
        logging.info(f"成功获取{stock_code}当前价格: {latest_price}")
        return jsonify({
            "stock_code": stock_code,
            "market_type": market_type,
            "current_price": latest_price,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"获取当前价格时出错: {e}\n{stack_trace}")
        return jsonify({
            "error": "获取当前价格失败",
            "details": str(e),
            "stack_trace": stack_trace
        }), 500



@stock_data_bp.route('/api/stock_list', methods=['GET'])
def get_stock_list():
    """获取已下载的股票列表"""
    stock_list = db.get_stock_list()
    return jsonify(stock_list)

@stock_data_bp.route('/api/price_range/<stock_code>', methods=['GET'])
def get_price_range(stock_code):
    """获取指定股票的价格区间数据"""
    try:
        market_type = request.args.get('market_type', 'US')
        
        # 获取价格数据
        price_data = db.get_stock_prices(stock_code, market_type)
        
        if not price_data:
            return jsonify({"error": "未找到股票数据"}), 404
            
        # 处理数据
        dates = []
        closes = []
        
        for row in price_data:
            dates.append(row[0])  # 日期
            closes.append(float(row[1]))  # 收盘价
            
        # 获取最新收盘价
        latest_price = closes[-1] if closes else None

        # 获取月度波动率数据
        volatility_generator = create_volatility_generator(market_type, db)
        monthly_stats_data, _ = volatility_generator.calculate_volatility_stats(stock_code)
        
        # 初始化价格水平线数据
        price_levels = {}
        
        # 如果有月度统计数据，计算不同时间段的价格水平线
        periods = ['3个月', '6个月', '1年', '3年']
        for period in periods:
            if monthly_stats_data and period in monthly_stats_data:
                stats = monthly_stats_data[period]
                if 'up_volatility' in stats:
                    up_stats = stats['up_volatility']
                    price_levels[f'monthly_max_up_{period}'] = latest_price * (1 + up_stats['max'])
                    price_levels[f'monthly_p90_up_{period}'] = latest_price * (1 + up_stats['percentiles']['90'])
                
                if 'down_volatility' in stats:
                    down_stats = stats['down_volatility']
                    price_levels[f'monthly_max_down_{period}'] = latest_price * (1 - down_stats['max'])
                    price_levels[f'monthly_p90_down_{period}'] = latest_price * (1 - down_stats['percentiles']['90'])

        # 获取财报波动统计数据
        if market_type == 'US':
            fetcher = EarningsDatesFetcher.create()
            results = fetcher.get_earnings_volatility(stock_code)
            
            if results:
                # 计算波动率
                up_volatilities = []
                down_volatilities = []
                
                for row in results:
                    _, _, _, pre_close, _, close_price, *_ = row
                    volatility = (close_price - pre_close) / pre_close * 100
                    if volatility > 0:
                        up_volatilities.append(volatility)
                    else:
                        down_volatilities.append(abs(volatility))
                
                if up_volatilities:
                    up_volatilities.sort(reverse=True)
                    max_up = up_volatilities[0]
                    p90_up = up_volatilities[int(len(up_volatilities) * 0.1)] if len(up_volatilities) >= 10 else max_up
                    price_levels['earnings_max_up'] = latest_price * (1 + max_up/100)
                    price_levels['earnings_p90_up'] = latest_price * (1 + p90_up/100)
                
                if down_volatilities:
                    down_volatilities.sort(reverse=True)
                    max_down = down_volatilities[0]
                    p90_down = down_volatilities[int(len(down_volatilities) * 0.1)] if len(down_volatilities) >= 10 else max_down
                    price_levels['earnings_max_down'] = latest_price * (1 - max_down/100)
                    price_levels['earnings_p90_down'] = latest_price * (1 - p90_down/100)
            
        return jsonify({
            "dates": dates,
            "closes": closes,
            "latest_price": latest_price,
            "price_levels": price_levels
        })
        
    except Exception as e:
        logging.error(f"获取价格区间数据时出错: {e}\n{traceback.format_exc()}")
        return jsonify({
            "error": "获取价格区间数据失败",
            "details": str(e)
        }), 500

# 创建异常类
class UnsupportedMarketError(Exception):
    """不支持的市场类型异常"""
    pass

def create_volatility_generator(market_type, db):
    """
    根据市场类型创建对应的波动率生成器
    
    Args:
        market_type: 市场类型 ('US' 或 'HK')
        db: 数据库实例
    
    Returns:
        VolatilityDataGenerator: 波动率生成器实例
    
    Raises:
        UnsupportedMarketError: 当市场类型不支持时抛出
    """
    if market_type == 'US':
        return USVolatilityDataGenerator(db)
    elif market_type == 'HK':
        return HKVolatilityDataGenerator(db)
    raise UnsupportedMarketError(f"不支持的市场类型: {market_type}")

@stock_data_bp.route('/api/generate_volatility/<stock_code>', methods=['POST'])
def generate_volatility(stock_code):
    """生成指定股票的历史波动率数据"""
    try:
        market_type = request.json.get('market_type', 'US')
        volatility_generator = create_volatility_generator(market_type, db)
        volatility_generator.generate_data([stock_code])
        return jsonify({
            "message": f"{market_type}市场的{stock_code}波动率数据生成并保存成功"
        }), 201
    except UnsupportedMarketError as e:
        return jsonify({"error": str(e)}), 400

@stock_data_bp.route('/api/volatility/<stock_code>', methods=['GET'])
def get_volatility(stock_code):
    """获取指定股票的波动率数据"""
    try:
        window_days = int(request.args.get('window_days', 21))
        market_type = request.args.get('market_type', 'US')
        
        volatility_generator = create_volatility_generator(market_type, db)
        monthly_stats_data, weekly_stats_data = volatility_generator.calculate_volatility_stats(stock_code, window_days)
        
        if monthly_stats_data:
            return jsonify({
                'monthly_stats': monthly_stats_data,
                'weekly_stats': weekly_stats_data
            })
        else:
            return jsonify({"message": "无法计算波动率数据"}), 404
            
    except UnsupportedMarketError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"计算波动率数据时出错: {e}\n{traceback.format_exc()}")
        return jsonify({
            "error": "计算波动率数据失败",
            "details": str(e)
        }), 500

@stock_data_bp.route('/api/download_earnings', methods=['POST'])
def download_earnings():
    """下载股票的历史财报数据"""
    try:
        data = request.get_json()
        stock_code = data.get('stock_code')
        market_type = data.get('market_type')
        
        if not stock_code or not market_type:
            return jsonify({'message': '股票代码和市场类型不能为空'}), 400
            
        # 使用工厂方法创建获取器并下载数据
        fetcher = EarningsDatesFetcher.create()
        success, message, count = fetcher.download_earnings(stock_code, market_type)
        
        if not success:
            return jsonify({'message': message}), 404
            
        return jsonify({
            'message': message,
            'count': count
        })
        
    except Exception as e:
        logging.error(f"下载财报数据时出错: {e}\n{traceback.format_exc()}")
        return jsonify({
            'error': '下载财报数据失败',
            'details': str(e)
        }), 500

@stock_data_bp.route('/api/earnings_volatility/<stock_code>', methods=['GET'])
def get_earnings_volatility(stock_code):
    """获取股票财报日期前后的波动率统计"""
    try:
        market_type = request.args.get('market_type', 'US')
        if market_type != 'US':
            return jsonify({"error": "目前只支持美股财报波动分析"}), 400

        # 使用 EarningsDatesFetcher 获取数据
        fetcher = EarningsDatesFetcher.create()
        results = fetcher.get_earnings_volatility(stock_code)

        if not results:
            return jsonify({"error": "未找到相关财报数据"}), 404

        # 计算波动率
        volatilities = []
        up_volatilities = []
        down_volatilities = []

        for row in results:
            fiscal_date, report_date, report_time, pre_close, trade_date, close_price, *_ = row
            
            # 计算总波动率
            volatility = (close_price - pre_close) / pre_close * 100  # 直接转换为百分比
            
            volatilities.append({
                'fiscal_date': fiscal_date,
                'report_date': report_date,
                'volatility': volatility
            })

            if volatility > 0:
                up_volatilities.append(volatility)
            else:
                down_volatilities.append(abs(volatility))

        # 计算统计数据
        def calculate_stats(data):
            if not data:
                return None
                
            sorted_data = sorted(data)
            length = len(sorted_data)
            
            return {
                'count': length,
                'avg_volatility': sum(sorted_data) / length,
                'max_volatility': max(sorted_data),
                'min_volatility': min(sorted_data),
                'percentiles': {
                    '90': sorted_data[int(length * 0.9)] if length >= 10 else sorted_data[-1],
                    '75': sorted_data[int(length * 0.75)] if length >= 4 else sorted_data[-1],
                    '50': sorted_data[int(length * 0.5)] if length >= 2 else sorted_data[-1],
                    '25': sorted_data[int(length * 0.25)] if length >= 4 else sorted_data[0],
                    '10': sorted_data[int(length * 0.1)] if length >= 10 else sorted_data[0]
                }
            }

        response_data = {
            # 'volatilities': volatilities,
            'up_stats': calculate_stats(up_volatilities),
            'down_stats': calculate_stats(down_volatilities)
        }

        return jsonify(response_data)

    except Exception as e:
        logging.error(f"获取财报波动数据时出错: {e}\n{traceback.format_exc()}")
        return jsonify({
            'error': '获取财报波动数据失败',
            'details': str(e)
        }), 500