from flask import Blueprint, jsonify, render_template, request
from futu import OpenQuoteContext, RET_OK
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.common.consts import Language
from tigeropen.trade.trade_client import TradeClient
from utils.futu_data_service import get_cached_option_delta

import os
import logging
import traceback
import requests
from tigeropen.common.consts import SecurityType
from tigeropen.quote.quote_client import QuoteClient

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
    '02020': '安踏体育',
    '02382': '舜宇光学',
    '09961': '携程集团',
    '01211': '比亚迪股份',
    '09999': '网易',
    '09618': '京东集团-SW',
    '09988': '阿里巴巴-W',
    '01818': '小米集团',
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


def get_prev_close_prices(stock_positions, option_positions, db):
    """获取所有持仓的昨日收盘价"""
    def process_market_symbols(symbols, market, prices):
        """处理指定市场的标的收盘价
        
        Args:
            symbols: 标的代码列表
            market: 市场类型（'US' 或 'HK'）
            prices: 从数据库获取的价格字典
            
        Returns:
            更新后的 prev_close_prices 和 missing_prices
        """
        for symbol in symbols:
            date, price = prices.get(symbol, (None, None))
            if price is not None:
                prev_close_prices[symbol] = price
            else:
                # 查找对应的持仓（股票或期权）
                stock = next((p for p in stock_positions if p.contract.symbol == symbol), None)
                option = next((p for p in option_positions if p.contract.symbol == symbol), None)
                
                if stock:
                    current_price = stock.market_value / stock.quantity if stock.quantity else 0
                    missing_prices.append({
                        'symbol': symbol,
                        'market': market,
                        'prev_close_date': datetime.now().strftime('%Y-%m-%d'),
                        'prev_close_price': current_price
                    })
                elif option:
                    multiplier = option.contract.multiplier or 100
                    current_price = option.market_value / (option.quantity * multiplier) if option.quantity else 0
                    missing_prices.append({
                        'symbol': symbol,
                        'market': market,
                        'prev_close_date': datetime.now().strftime('%Y-%m-%d'),
                        'prev_close_price': current_price
                    })
    
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
    
    # 处理美股和港股数据
    process_market_symbols(us_symbols, 'US', us_prices)
    process_market_symbols(hk_symbols, 'HK', hk_prices)
    
    # 如果有缺失的价格，记录日志
    if missing_prices:
        logging.info(f"使用当前价格作为前收价的标的: {[f'{p['symbol']}({p['market']})' for p in missing_prices]}")
    
    return prev_close_prices

# 修改get_positions函数中获取收盘价的部分
@tiger_bp.route('/positions')
def get_positions():
    try:
        client, quote_client = get_tiger_client()
        
        # 获取实时港币兑美元汇率
        # try:
        #     response = requests.get("https://open.er-api.com/v6/latest/HKD")
        #     data = response.json()
        #     HKD_TO_USD_RATE = data['rates']['USD']
        # except Exception as e:
        #     error_context = {
        #         'function': 'get_positions',
        #         'step': 'get_exchange_rate',
        #         'api': 'open.er-api.com',
        #         'error_type': type(e).__name__
        #     }
        #     logging.error(
        #         f"获取汇率失败. Context: {error_context}\n"
        #         f"Error message: {str(e)}\n"
        #         f"Stacktrace:\n{traceback.format_exc()}"
        #     )
        HKD_TO_USD_RATE = 0.128  # 如果获取失败，使用默认汇率

        # 获取股票和期权持仓信息
        stock_positions = client.get_positions(sec_type=SecurityType.STK)
        option_positions = client.get_positions(sec_type=SecurityType.OPT)

        db = USStockDatabase()
        
        # 获取所有持仓的昨日收盘价
        prev_close_prices = get_prev_close_prices(stock_positions, option_positions, db)

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
                    'hk_symbol': symbol,  # 保留港股的代码
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
                type_order = 0 if option_type == 'CALL' else 1
                return (base_symbol, expiry_date, type_order, -strike_price)
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

                # 在option_data字典定义处添加delta值获取逻辑
                # 构建富途期权代码格式：NVDA250321C132000
                futu_option_symbol = (
                    f"{base_symbol}"  # 基础股票代码
                    f"{expiry_date[2:4]}"  # 年份后两位
                    f"{expiry_date[4:6]}"  # 月份
                    f"{expiry_date[6:8]}"  # 日期
                    f"{option_type[0]}"  # C或P
                    f"{int(float(strike_price)*1000)}"  # 行权价*1000
                )

                # 修改这里，添加force_cache=True参数，确保只从缓存中获取delta值
                delta_value = get_cached_option_delta(futu_option_symbol, force_cache=True)

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
                    'position_ratio': (market_value / total_market_value * 100) if total_market_value else 0,
                    'delta': delta_value,
                    'futu_symbol': futu_option_symbol
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