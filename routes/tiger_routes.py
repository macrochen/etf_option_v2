from flask import Blueprint, jsonify, render_template, request
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.common.consts import Language
from tigeropen.trade.trade_client import TradeClient
import os
import logging
import traceback
import requests
from tigeropen.common.consts import SecurityType
from tigeropen.quote.quote_client import QuoteClient
from futu import OpenQuoteContext, RET_OK

tiger_bp = Blueprint('tiger', __name__)

@tiger_bp.route('/positions_page')
def positions_page():
    """渲染持仓信息页面"""
    return render_template('positions.html')

def get_tiger_client():
    # 获取配置文件的绝对路径
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(current_dir, 'config', 'tiger_openapi_config.properties')
    
    # 创建Tiger API配置
    client_config = TigerOpenClientConfig(props_path=config_path)
    client_config.language = Language.zh_CN  # 设置语言为中文
    
    # 创建交易客户端
    return TradeClient(client_config), QuoteClient(client_config) 

# 在文件开头添加港股代码与名称的映射
HK_STOCK_NAMES = {
    '00388': '香港交易所',
    '00700': '腾讯控股',
    '01448': '福寿园',
    '02318': '中国平安',
    '02800': '盈富基金',
    '03032': '恒生科技ETF', 
    '03069': '华夏恒生生科',
    '03690': '美团-W',
    '03968': '招商银行',
    '09618': '京东集团-SW'
}

@tiger_bp.route('/api/update_hk_prev_close', methods=['GET'])
def update_hk_prev_close():
    """更新港股上一个交易日收盘价"""
    try:
        # 从持仓中获取港股代码列表
        client, _ = get_tiger_client()
        stock_positions = client.get_positions(sec_type=SecurityType.STK)
        
        # 只提取港股代码
        hk_codes = [
            f"HK.{position.contract.symbol}" 
            for position in stock_positions 
            if position.contract 
            and position.contract.symbol 
            and position.contract.market == 'HK'
            and ' ' not in position.contract.symbol  # 排除期权
        ]
        
        if not hk_codes:
            return jsonify({
                'status': 'error',
                'message': '没有找到任何港股持仓'
            }), 400
            
        # 连接富途API获取快照数据
        quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        try:
            ret, data = quote_ctx.get_market_snapshot(hk_codes)
            if ret != RET_OK:
                raise Exception(f"获取市场快照失败: {data}")
            
            # 解析快照数据并保存到数据库
            db = USStockDatabase()
            price_data_list = []
            
            for _, row in data.iterrows():
                symbol = row['code'].split('.')[-1]  # 从 'HK.00700' 提取 '00700'
                price_data_list.append({
                    'symbol': symbol,
                    'market': 'HK',
                    'prev_close_date': datetime.now().strftime('%Y-%m-%d'),
                    'prev_close_price': float(row['prev_close_price'])
                })
            
            if price_data_list:
                db.batch_save_prev_close_prices(price_data_list)
                logging.info(f"成功更新 {len(price_data_list)} 个港股的收盘价数据")
            
            return jsonify({
                'status': 'success',
                'message': f'成功更新 {len(price_data_list)} 个港股的收盘价数据'
            })
            
        finally:
            quote_ctx.close()
            
    except Exception as e:
        logging.error(f"更新港股收盘价失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@tiger_bp.route('/raw_positions')
def get_raw_positions():
    """获取原始持仓数据"""
    try:
        client, _ = get_tiger_client()
        # 获取股票和期权持仓信息
        stock_positions = client.get_positions(sec_type=SecurityType.STK)
        option_positions = client.get_positions(sec_type=SecurityType.OPT)
        
        # 直接序列化对象，并过滤掉None值
        def filter_none(d):
            return {k: v for k, v in d.items() if v is not None}
            
        stock_data = [
            {**filter_none(p.__dict__), 
             'contract': filter_none(p.contract.__dict__) if p.contract else None}
            for p in stock_positions
        ]
        
        option_data = [
            {**filter_none(p.__dict__), 
             'contract': filter_none(p.contract.__dict__) if p.contract else None}
            for p in option_positions
        ]

        return jsonify({
            'status': 'success',
            'data': {
                'stocks': stock_data,
                'options': option_data
            }
        })
    except Exception as e:
        error_context = {
            'function': 'get_raw_positions',
            'endpoint': '/raw_positions',
            'error_type': type(e).__name__
        }
        logging.error(
            f"Error in Tiger API raw positions request. Context: {error_context}\n"
            f"Error message: {str(e)}\n"
            f"Stacktrace:\n{traceback.format_exc()}"
        )
        return jsonify({
            'status': 'error',
            'message': str(e),
            'context': error_context
        }), 500

# 在文件开头添加导入
from datetime import datetime
from db.us_stock_db import USStockDatabase

# 添加新的下载接口
@tiger_bp.route('/download_prev_close', methods=['POST'])
def download_prev_close():
    """下载指定持仓标的的上一个交易日收盘价"""
    try:
        client, _ = get_tiger_client()
        db = USStockDatabase()
        
        # 从请求中获取需要更新的标的列表
        request_data = request.get_json()
        symbols_to_update = request_data.get('symbols', [])
        
        if not symbols_to_update:
            return jsonify({
                'status': 'error',
                'message': '没有需要更新的标的'
            })
        
        # 按市场分组symbols
        us_symbols = []
        hk_symbols = []
        for symbol, market in symbols_to_update:
            if market == 'US':
                us_symbols.append(symbol)
            elif market == 'HK':
                hk_symbols.append(symbol)
        
        price_data_list = []
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 获取美股数据
        for symbol in us_symbols:
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")
                if not hist.empty and len(hist) > 1:
                    price_data_list.append({
                        'symbol': symbol,
                        'market': 'US',
                        'prev_close_date': hist.index[-2].strftime('%Y-%m-%d'),
                        'prev_close_price': float(hist.iloc[-2]['Close'])
                    })
            except Exception as e:
                logging.error(f"从Yahoo获取{symbol}数据失败: {str(e)}")
        
        # 获取港股数据
        if hk_symbols:
            try:
                quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
                
                try:
                    # 过滤掉期权，只获取股票的快照数据
                    stock_codes = [f"HK.{symbol}" for symbol in hk_symbols if ' ' not in symbol]  # 期权代码中包含空格
                    ret, data = quote_ctx.get_market_snapshot(stock_codes)
                    
                    if ret == RET_OK and not data.empty:
                        for _, row in data.iterrows():
                            symbol = row['code'].split('.')[-1]  # 从 'HK.00700' 提取 '00700'
                            price_data_list.append({
                                'symbol': symbol,
                                'market': 'HK',
                                'prev_close_date': datetime.now().strftime('%Y-%m-%d'),  # 使用当前日期，因为快照数据不返回日期
                                'prev_close_price': float(row['prev_close_price'])
                            })
                except Exception as e:
                    logging.error(f"从富途获取快照数据失败: {str(e)}\n{traceback.format_exc()}")

                quote_ctx.close()
            except Exception as e:
                logging.error(f"富途API连接失败: {str(e)}\n{traceback.format_exc()}")
        
        # 批量保存到数据库
        if price_data_list:
            db.batch_save_prev_close_prices(price_data_list)
            
        return jsonify({
            'status': 'success',
            'message': f'成功下载 {len(price_data_list)} 个标的的收盘价数据'
        })
        
    except Exception as e:
        logging.error(f"下载收盘价失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 修改get_positions函数中获取收盘价的部分
@tiger_bp.route('/positions')
def get_positions():
    try:
        client, quote_client = get_tiger_client()
        
        # 获取实时港币兑美元汇率
        try:
            response = requests.get("https://open.er-api.com/v6/latest/HKD")
            data = response.json()
            HKD_TO_USD_RATE = data['rates']['USD']
        except Exception as e:
            error_context = {
                'function': 'get_positions',
                'step': 'get_exchange_rate',
                'api': 'open.er-api.com',
                'error_type': type(e).__name__
            }
            logging.error(
                f"获取汇率失败. Context: {error_context}\n"
                f"Error message: {str(e)}\n"
                f"Stacktrace:\n{traceback.format_exc()}"
            )
            HKD_TO_USD_RATE = 0.128  # 如果获取失败，使用默认汇率

        # 获取股票和期权持仓信息
        stock_positions = client.get_positions(sec_type=SecurityType.STK)
        option_positions = client.get_positions(sec_type=SecurityType.OPT)

        db = USStockDatabase()

        # 获取所有持仓的昨日收盘价
        symbols = [p.contract.symbol for p in stock_positions + option_positions if p.contract]
        prev_close_prices = {}
        missing_prices = []
        
        # 按市场分组symbols
        us_symbols = []
        hk_symbols = []
        for p in stock_positions + option_positions:
            if p.contract:
                if p.contract.market == 'US':
                    us_symbols.append(p.contract.symbol)
                elif p.contract.market == 'HK':
                    hk_symbols.append(p.contract.symbol)
        
        # 从数据库获取收盘价
        us_prices = db.batch_get_prev_close_prices(us_symbols, 'US')
        hk_prices = db.batch_get_prev_close_prices(hk_symbols, 'HK')
        
        # 合并收盘价数据并记录缺失的价格
        for symbol in us_symbols:
            date, price = us_prices.get(symbol, (None, None))
            if price is not None:
                prev_close_prices[symbol] = price
            else:
                missing_prices.append((symbol, 'US'))
                
        for symbol in hk_symbols:
            date, price = hk_prices.get(symbol, (None, None))
            if price is not None:
                prev_close_prices[symbol] = price
            else:
                missing_prices.append((symbol, 'HK'))

        # 创建按标的分组的字典和非分组列表
        grouped_positions = {}
        ungrouped_positions = []
        
        # 计算总市值（用于计算持仓占比）- 港股市值需要转换为美元
        total_market_value = sum(
            p.market_value * HKD_TO_USD_RATE if p.contract.market == 'HK' else p.market_value
            for p in stock_positions
        ) + sum(
            p.market_value * HKD_TO_USD_RATE if p.contract.market == 'HK' else p.market_value
            for p in option_positions
        )

        # 处理股票持仓
        for position in stock_positions:
            symbol = position.contract.symbol if position.contract else None
            if symbol:
                # 计算盈亏百分比 - 考虑持仓数量正负
                cost_basis = abs(position.quantity * position.average_cost) if position.quantity and position.average_cost else 0
                pnl_percentage = (position.unrealized_pnl / cost_basis * 100) if cost_basis else 0
                # 计算现价
                latest_price = position.market_value / position.quantity if position.quantity else 0
                # 计算每日盈亏
                prev_close = prev_close_prices.get(symbol, 0)
                daily_pnl = (latest_price - prev_close) * position.quantity if prev_close else 0
                # 如果是港股，使用名称映射
                if position.contract.market == 'HK':
                    display_symbol = HK_STOCK_NAMES.get(symbol, symbol)
                else:
                    display_symbol = symbol

                # 如果是港币，计算持仓占比需要考虑汇率
                if position.contract.market == 'HK':
                    market_value = position.market_value * HKD_TO_USD_RATE
                else:
                    market_value = position.market_value

                stock_data = {
                    'symbol': display_symbol,  # 使用映射后的名称
                    'quantity': position.quantity,
                    'average_cost': position.average_cost,
                    'market_value': position.market_value,
                    'latest_price': latest_price,  # 添加现价
                    'unrealized_pnl': position.unrealized_pnl,
                    'unrealized_pnl_percentage': pnl_percentage,  # 添加盈亏百分比
                    'realized_pnl': position.realized_pnl,
                    'market': position.contract.market if position.contract else None,
                    'sec_type': 'STK',
                    'position_ratio': (market_value / total_market_value * 100) if total_market_value else 0,
                    'daily_pnl': daily_pnl, 
                }
                
                # 检查是否有相关的期权持仓
                has_options = any(opt.contract.symbol.startswith(symbol + ' ') for opt in option_positions)
                
                if has_options:
                    if display_symbol not in grouped_positions:
                        grouped_positions[display_symbol] = {
                            'symbol': display_symbol,
                            'stock': stock_data,
                            'options': [],
                            'market': stock_data['market'],
                            'latest_price': latest_price,  # 添加现价
                            'total_market_value': stock_data['market_value'],
                            'total_unrealized_pnl': stock_data['unrealized_pnl'],
                            'total_realized_pnl': stock_data['realized_pnl'],
                            'total_position_ratio': stock_data['position_ratio'],
                            'total_daily_pnl': stock_data['daily_pnl'],
                            'is_group': True
                        }
                else:
                    ungrouped_positions.append(stock_data)
        
        # 对期权持仓进行排序
        def option_sort_key(position):
            symbol_parts = position.contract.symbol.split()
            if len(symbol_parts) >= 4:
                base_symbol = symbol_parts[0]
                expiry_date = symbol_parts[1]
                strike_price = float(symbol_parts[2])  # 转换执行价格为数字
                option_type = symbol_parts[3]
                # PUT排在CALL前面，所以PUT用0，CALL用1
                type_order = 0 if option_type == 'PUT' else 1
                return (base_symbol, expiry_date, type_order, strike_price)
            return ('', '', 0, 0)  # 默认值，用于无效数据
            
        option_positions = sorted(option_positions, key=option_sort_key)

        # 处理期权持仓
        for position in option_positions:
            contract = position.contract
            symbol_parts = contract.symbol.split()
            
            if len(symbol_parts) >= 4:
                base_symbol = symbol_parts[0]
                # 如果是港股，使用名称映射
                if contract.market == 'HK':
                    base_symbol = HK_STOCK_NAMES.get(base_symbol, base_symbol)
                expiry_date = symbol_parts[1]
                strike_price = symbol_parts[2]
                option_type = symbol_parts[3]
                
                formatted_expiry = f"{expiry_date[:4]}-{expiry_date[4:6]}-{expiry_date[6:]}"
                multiplier = contract.multiplier or 100  # 默认使用100作为合约乘数
                # 计算期权现价（注意要考虑合约乘数）
                latest_price = (position.market_value / (position.quantity * multiplier)) if position.quantity else 0

                # 计算期权每日盈亏
                prev_close = prev_close_prices.get(contract.symbol, 0)
                daily_pnl = (latest_price - prev_close) * position.quantity * multiplier if prev_close else 0
                
                # 计算期权盈亏百分比 - 使用成本价作为基准计算百分比
                cost_basis = abs(position.quantity * position.average_cost) if position.quantity and position.average_cost else 0
                pnl_percentage = (position.unrealized_pnl / cost_basis * 100) if cost_basis else 0
                market_value = position.market_value * HKD_TO_USD_RATE if contract.market == 'HK' else position.market_value
                option_data = {
                    'symbol': base_symbol,
                    'quantity': position.quantity,
                    'average_cost': position.average_cost / multiplier if position.average_cost else None,
                    'market_value': position.market_value,
                    'latest_price': latest_price, 
                    'unrealized_pnl': position.unrealized_pnl,
                    'unrealized_pnl_percentage': pnl_percentage,  # 添加盈亏百分比
                    'realized_pnl': position.realized_pnl,
                    'market': contract.market,
                    'sec_type': 'OPT',
                    'strike': float(strike_price),
                    'expiry': formatted_expiry,
                    'put_call': option_type,
                    'daily_pnl': daily_pnl,
                    'position_ratio': (market_value / total_market_value * 100) if total_market_value else 0
                }
                
                if base_symbol in grouped_positions:
                    grouped_positions[base_symbol]['options'].append(option_data)
                    # 更新分组统计数据
                    group = grouped_positions[base_symbol]
                    group['total_market_value'] += option_data['market_value']
                    group['total_unrealized_pnl'] += option_data['unrealized_pnl']
                    group['total_realized_pnl'] += option_data['realized_pnl']
                    group['total_position_ratio'] += option_data['position_ratio']
                    group['total_daily_pnl'] += option_data['daily_pnl']
                else:
                    # 如果没有对应的股票持仓，创建只包含期权的分组
                    grouped_positions[base_symbol] = {
                        'symbol': base_symbol,
                        'stock': None,
                        'options': [option_data],
                        'market': option_data['market'],
                        'total_market_value': option_data['market_value'],
                        'total_unrealized_pnl': option_data['unrealized_pnl'],
                        'total_realized_pnl': option_data['realized_pnl'],
                        'is_group': True,
                        'total_position_ratio': option_data['position_ratio'],
                        'total_daily_pnl': option_data['daily_pnl']
                    }
        
        # 合并分组和非分组数据
        final_positions = list(grouped_positions.values()) + ungrouped_positions
        
        # 按市场分类并按symbol排序
        us_positions = sorted([p for p in final_positions if p.get('market') == 'US'], 
                            key=lambda x: x['symbol'])
        hk_positions = sorted([p for p in final_positions if p.get('market') == 'HK'], 
                            key=lambda x: x['symbol'])
        
        return jsonify({
            'status': 'success',
            'data': {
                'us_positions': us_positions,
                'hk_positions': hk_positions,
                'missing_prev_close': missing_prices  # 添加缺失收盘价的标的列表
            }
        })
        
    except Exception as e:
        error_context = {
            'function': 'get_positions',
            'endpoint': '/positions',
            'error_type': type(e).__name__
        }
        logging.error(
            f"Error in Tiger API positions request. Context: {error_context}\n"
            f"Error message: {str(e)}\n"
            f"Stacktrace:\n{traceback.format_exc()}"
        )
        return jsonify({
            'status': 'error',
            'message': str(e),
            'context': error_context
        }), 500