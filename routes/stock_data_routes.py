import re
from flask import Blueprint, request, jsonify, render_template
import pandas as pd
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
from futu import OpenQuoteContext, RET_OK  # 添加富途API导入

import requests
import json
from pathlib import Path
import os

from utils.config_utils import get_config_value, save_config_value

# 创建蓝图
stock_data_bp = Blueprint('stock_data', __name__)
db = USStockDatabase()


# 从配置文件读取 API keys

# 替换原有的静态 API key
ALPHA_VANTAGE_API_KEY = get_config_value('api_keys.alpha_vantage')
TIINGO_API_KEY = get_config_value('api_keys.tiingo')

# 添加 API key 检查
if not ALPHA_VANTAGE_API_KEY:
    logging.warning("AlphaVantage API key 未配置")
if not TIINGO_API_KEY:
    logging.warning("Tiingo API key 未配置")
# 速率限制：最多 500 次请求/天，10 次/分钟。
def download_from_tiingo(stock_code, start_date):
    """从 Tiingo 下载数据"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Token {TIINGO_API_KEY}'
    }
    
    # Tiingo API endpoint
    url = f'https://api.tiingo.com/tiingo/daily/{stock_code}/prices'
    params = {
        'startDate': start_date.strftime('%Y-%m-%d'),
        'endDate': datetime.now().strftime('%Y-%m-%d'),
        'format': 'json'
    }
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    
    if not data:
        raise Exception("Tiingo API 返回空数据")
    
    # 转换数据格式
    df_data = []
    for item in data:
        # 将字符串日期转换为 datetime 对象
        date_str = item['date'].split('T')[0]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        df_data.append({
            'Date': date_obj,  # 使用 datetime 对象而不是字符串
            'Open': float(item['open']),
            'High': float(item['high']),
            'Low': float(item['low']),
            'Close': float(item['close']),
            'Adj Close': float(item['adjClose']),
        })
    
    return pd.DataFrame(df_data).set_index('Date')

def get_preferred_data_source(stock_code):
    """获取股票首选的数据源"""
    return get_config_value('data_source.default','yahoo')

def save_preferred_data_source(stock_code, source):
    """保存股票的首选数据源"""
    if not save_config_value('data_source.default', source):
        logging.error(f"保存数据源配置失败: {source}")

def download_from_alpha_vantage(stock_code, start_date):
    """从 AlphaVantage 下载数据"""
    url = f'https://www.alphavantage.co/query'
    params = {
        'function': 'TIME_SERIES_DAILY_ADJUSTED',
        'symbol': stock_code,
        'apikey': ALPHA_VANTAGE_API_KEY,
        'outputsize': 'full'
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    if 'Time Series (Daily)' not in data:
        raise Exception(f"AlphaVantage API 返回无效数据: {data.get('Note', '未知错误')}")
    
    # 转换数据格式
    daily_data = data['Time Series (Daily)']
    df_data = []
    for date, values in daily_data.items():
        if date >= start_date.strftime('%Y-%m-%d'):
            df_data.append({
                'Date': date,
                'Open': float(values['1. open']),
                'High': float(values['2. high']),
                'Low': float(values['3. low']),
                'Close': float(values['4. close']),
                'Adj Close': float(values['5. adjusted close']),
            })
    
    return pd.DataFrame(df_data).set_index('Date')

        

@stock_data_bp.route('/watchlist', methods=['GET'])
def watchlist_page():
    """渲染自选股列表页面"""
    return render_template('watchlist.html')

@stock_data_bp.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    """获取富途自选股列表数据"""
    try:
        group_name = request.args.get('group_name', '赌财报(当日)')  # 默认获取"港美股"分组
        
        # 连接富途API
        # 修改 futu 的导入语句
        
        # from futu.common import OpenQuoteContext
        # from futu.common.constant import RET_OK
        quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        
        try:
            # 获取自选股分组下的股票列表
            ret, data = quote_ctx.get_user_security(group_name)
            
            if ret != RET_OK:
                raise Exception(f"获取自选股列表失败: {data}")
            
            # 获取股票的基本信息（包括名称等）
            stock_list = []
            for code in data['code']:
                # 直接从data中获取name信息
                stock_list.append({
                    'code': code.split('.')[1],  # 股票代码
                    'name': data['name'][data['code'] == code].iloc[0],  # 从data中获取对应的name
                    'market': code.split('.')[0],  # 市场类型（US/HK）
                })
            
            return jsonify({
                'status': 'success',
                'data': stock_list
            })
            
        finally:
            # 确保关闭连接
            quote_ctx.close()
            
    except Exception as e:
        logging.error(f"获取自选股列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    

@stock_data_bp.route('/us_stock_volatility_management', methods=['GET'])
def download_page():
    return render_template('stock_volatility_management.html')

@stock_data_bp.route('/api/update_stock_prices', methods=['POST'])
def update_stock_prices():
    """批量更新股票价格"""
    try:
        market_type = "US"  # 从请求中获取市场类型，默认为 US
        
        # 使用 get_position_symbols 获取股票列表
        from routes.tiger_routes import get_position_symbols
        symbols = get_position_symbols(market_type)
        
        if not symbols:
            return jsonify({
                'status': 'error',
                'message': f'没有找到任何{market_type}市场的持仓'
            }), 400
        
        logging.info(f"开始批量更新股票价格，共 {len(symbols)} 个股票")
        results = []
        for symbol in symbols:
            try:
                logging.info(f"开始处理股票: {symbol}")
                # 使用与 download_data 相同的逻辑更新历史数据
                end_date = datetime.now().date()
                last_update = db.get_last_update_date(symbol, 'US')
                if last_update:
                    start_date = last_update + timedelta(days=1)
                    logging.info(f"{symbol} 最后更新日期: {last_update.strftime('%Y-%m-%d')}")
                else:
                    start_date = end_date - timedelta(days=365*10)
                    logging.info(f"{symbol} 无历史数据，将下载10年数据")

                if start_date >= end_date:
                    logging.info(f"{symbol} 数据已是最新")
                    results.append({
                        'code': symbol,
                        'market': market_type,
                        'message': '数据已是最新',
                        'status': 'success'
                    })
                    continue

                # 获取股票数据
                preferred_source = get_preferred_data_source(symbol)
                logging.info(f"使用数据源: {preferred_source} 获取 {symbol} 数据")
                try:
                    if preferred_source == 'alphavantage':
                        data = download_from_alpha_vantage(symbol, start_date)
                    elif preferred_source == 'tiingo':
                        data = download_from_tiingo(symbol, start_date)
                    else:
                        ticker = yf.Ticker(symbol)
                        data = yf.download(symbol, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))

                    if not data.empty:
                        # 保存数据到数据库
                        success_count = 0
                        total_rows = len(data)
                        logging.info(f"{symbol} 获取到 {total_rows} 条数据记录")
                        
                        for index, (date, row) in enumerate(data.iterrows()):
                            try:
                                db.save_stock_data(
                                    symbol,
                                    date.date(),
                                    float(row['Open']),
                                    float(row['High']),
                                    float(row['Low']),
                                    float(row['Close']),
                                    float(row['Adj Close']),
                                    'US',
                                    symbol  # 使用代码作为名称
                                )
                                success_count += 1
                                logging.info(f"{symbol} [{success_count}/{total_rows}] 保存数据: {date.date()} 开:{row['Open']:.2f} 高:{row['High']:.2f} 低:{row['Low']:.2f} 收:{row['Close']:.2f}")
                            except Exception as e:
                                logging.error(f"保存数据失败: {symbol}, {date}, {e}\n{traceback.format_exc()}")
                                continue

                        results.append({
                            'code': symbol,
                            'market': market_type,
                            'updated_count': success_count,
                            'status': 'success'
                        })
                        logging.info(f"{symbol} 更新完成，成功保存 {success_count}/{total_rows} 条记录")
                        time.sleep(3)  # 添加延迟避免请求过快
                    else:
                        raise Exception("未获取到数据")

                except Exception as e:
                    if preferred_source == 'yahoo':
                        # 直接抛出异常，不切换数据源
                        raise Exception(f"Yahoo Finance 下载失败: {e}")
                    else:
                        raise e

            except Exception as e:
                logging.error(f"{symbol} 更新失败: {str(e)}")
                results.append({
                    'code': symbol,
                    'market': market_type,
                    'error': str(e),
                    'status': 'error'
                })

        logging.info("批量更新股票价格完成")
        return jsonify({
            'status': 'success',
            'data': results
        })
        
    except Exception as e:
        error_msg = f"更新股价失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@stock_data_bp.route('/download', methods=['POST'])
def download_data():
    stock_code = request.json['stock_code']
    
    logging.info(f"开始下载美股数据: {stock_code}")
    
    try:
        # 计算时间范围（10年）
        end_date = datetime.now().date()  # 转换为 date 对象
        
        # 从数据库获取最后更新日期
        last_update = db.get_last_update_date(stock_code, 'US')
        if last_update:
            start_date = last_update + timedelta(days=1)  # 从上次更新的下一天开始
            logging.info(f"检测到已有数据，最后更新日期: {last_update.strftime('%Y-%m-%d')}")
        else:
            start_date = end_date - timedelta(days=365*10)  # 如果没有数据，则下载10年的数据
            logging.info("未检测到历史数据，将下载完整的10年数据")
            
        logging.info(f"设定下载时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
        
        # 如果已经是最新的，直接返回
        if start_date >= end_date:
            logging.info(f"股票 {stock_code} 数据已经是最新的，无需更新")
            return jsonify({
                "message": f"{stock_code} 数据已经是最新的",
                "count": 0,
                "total": 0,
                "errors": 0
            })

        # 获取股票信息
        # 获取股票信息和数据
        logging.info(f"正在获取 {stock_code} 的数据...")
        preferred_source = get_preferred_data_source(stock_code)
        
        try:
            if preferred_source == 'alphavantage':
                data = download_from_alpha_vantage(stock_code, start_date)
                stock_name = stock_code  # AlphaVantage 可能无法获取股票名称
            elif preferred_source == 'tiingo':
                data = download_from_tiingo(stock_code, start_date)
                stock_name = stock_code  # Tiingo 也可能无法获取股票名称
            else:
                # 尝试使用 Yahoo Finance
                ticker = yf.Ticker(stock_code)
                stock_info = ticker.info
                stock_name = stock_info.get('longName') or stock_info.get('shortName', '')
                data = yf.download(stock_code, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
        except Exception as e:
            if preferred_source == 'yahoo':
                # Yahoo 失败时切换到 AlphaVantage
                logging.warning(f"Yahoo Finance 下载失败，切换到 AlphaVantage: {e}")
                try:
                    data = download_from_alpha_vantage(stock_code, start_date)
                    stock_name = stock_code
                    save_preferred_data_source(stock_code, 'alphavantage')
                    logging.info(f"成功从 AlphaVantage 获取数据，已更新首选数据源")
                except Exception as alpha_error:
                    raise Exception(f"所有数据源都失败。Yahoo: {e}, AlphaVantage: {alpha_error}")
            else:
                raise e
        if data.empty:
            logging.warning(f"股票 {stock_code} 没有获取到任何数据")
            return jsonify({"error": "未能获取到任何数据"}), 404
        
        total_rows = len(data)
        logging.info(f"获取到 {total_rows} 条历史数据记录，开始保存到数据库...")
        
        # 存储到数据库
        success_count = 0
        error_count = 0
        last_progress = 0
        
        for index, (date, row) in enumerate(data.iterrows(), 1):
            try:
                # 每处理10%输出一次进度
                progress = (index * 100) // total_rows
                if progress >= last_progress + 10:
                    logging.info(f"数据保存进度: {progress}% ({index}/{total_rows})")
                    last_progress = progress
                
                open_price = float(row['Open'].item())
                high_price = float(row['High'].item())
                low_price = float(row['Low'].item())
                close_price = float(row['Close'].item())
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
                    stock_name
                )
                success_count += 1
            except (TypeError, ValueError) as e:
                error_count += 1
                logging.error(f"处理数据时出错: {e}, 股票代码: {stock_code}, 日期: {date}")
                continue
        
        if success_count == 0:
            logging.warning(f"股票 {stock_code} 没有保存任何有效数据")
            return jsonify({"error": "未能保存任何有效数据"}), 404
            
        logging.info(f"股票 {stock_code} 数据下载完成:")
        logging.info(f"- 总记录数: {total_rows}")
        logging.info(f"- 成功保存: {success_count}")
        logging.info(f"- 处理失败: {error_count}")
        
        return jsonify({
            "message": f"{stock_code} 数据下载并保存成功",
            "count": success_count,
            "total": total_rows,
            "errors": error_count
        })
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"下载美股数据时出错: {e}\n{stack_trace}")
        return jsonify({
            "error": "下载数据失败",
            "details": str(e),
            "stack_trace": stack_trace
        }), 500
    

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
    

def get_price_from_web(stock_code, market_type):
    """从雅虎财经网页抓取当前价格"""
    symbol = f"{stock_code}.HK" if market_type == 'HK' else stock_code
    url = f"https://finance.yahoo.com/quote/{symbol}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # 查找价格元素 - 更新选择器以匹配实际的HTML结构
        price_element = soup.find('span', {'class': 'base', 'data-testid': 'qsp-price'})
        
        if price_element:
            # 移除逗号和空格后再转换为浮点数
            price_text = price_element.text.replace(',', '').strip()
            return float(price_text)
        else:
            raise Exception(f"未找到{stock_code}的价格数据")
            
    except Exception as e:
        logging.error(f"从网页抓取价格失败: {e}")
        raise

@stock_data_bp.route('/api/current_price/<stock_code>', methods=['GET'])
def get_current_price(stock_code):
    """获取指定股票的当前价格"""
    try:
        market_type = request.args.get('market_type', 'US')
        logging.info(f"开始获取{market_type}市场的{stock_code}当前价格")
        
        full_code = f"{stock_code}.HK" if market_type == 'HK' else stock_code
        price_source = get_config_value('price_source.type', 'web')
        
        if price_source == 'web':
            latest_price = get_price_from_web(stock_code, market_type)
        else:
            # 使用原有的API方式
            ticker = yf.Ticker(full_code)
            current_data = ticker.history(period='1d')
            
            if current_data.empty:
                raise Exception("无法获取当前价格数据")
                
            latest_price = float(current_data['Close'].iloc[-1])
        
        logging.info(f"成功获取{stock_code}当前价格: {latest_price} (来源: {price_source})")
        return jsonify({
            "stock_code": stock_code,
            "market_type": market_type,
            "current_price": latest_price,
            "source": price_source,
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
        
        # 处理港股代码格式
        if market_type == 'HK':
            # 只保留最后4位数字
            stock_code = stock_code[-4:].zfill(4)
        
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
            
        # 获取最新收盘价，优先使用传入的当前价格
        current_price = request.args.get('current_price')
        latest_price = float(current_price) if current_price else (closes[-1] if closes else None)

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
        market_type = data.get('market_type', 'US')
        
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
    
def get_option_delta_from_barchart(stock_code, expiry_date, strike_price, option_type):
    """从 BarChart 获取期权的 delta 值"""
    url = f'https://www.barchart.com/stocks/quotes/{stock_code}|{expiry_date}|{strike_price:.2f}{option_type}/overview'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # 更新选择器以匹配实际的HTML结构
        delta_element = soup.find('span', {
            'class': 'right ng-hide',
            'data-ng-show': "key === 'source'"
        })
        
        if delta_element:
            # 查找内部的 span 元素
            value_span = delta_element.find('span', {'data-ng-bind-html': 'value'})
            if value_span and value_span.text:
                try:
                    return float(value_span.text.strip())
                except ValueError:
                    raise Exception(f"无法解析delta值: {value_span.text}")
        
        raise Exception("未找到delta数据")
            
    except Exception as e:
        logging.error(f"从BarChart获取期权delta值失败: {e}")
        raise

@stock_data_bp.route('/api/option_delta/<option_symbol>', methods=['GET'])
def get_option_delta_api(option_symbol):
    """获取期权delta值的API接口"""
    try:
        # 解析期权代码，例如：AAPL250321P00205000
        match = re.match(r'([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d+)', option_symbol)
        if not match:
            return jsonify({"error": "无效的期权代码格式"}), 400
            
        stock_code = match.group(1)
        year = '20' + match.group(2)
        month = match.group(3)
        day = match.group(4)
        option_type = match.group(5)
        strike_price = float(match.group(6)) / 1000  # 转换为实际价格
        
        expiry_date = f"{year}{month}{day}"
        
        delta = get_option_delta_from_barchart(stock_code, expiry_date, strike_price, option_type)
        return jsonify({"delta": delta})
        
    except Exception as e:
        return jsonify({
            "error": "获取期权delta值失败",
            "details": str(e)
        }), 500