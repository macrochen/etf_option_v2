from flask import Blueprint, render_template, request, Response, jsonify
import akshare as ak
import pandas as pd
from datetime import datetime
import io
import logging
import traceback

data_download_bp = Blueprint('data_download', __name__)

@data_download_bp.route('/data_download_page')
def index():
    return render_template('data_download.html')

@data_download_bp.route('/download_csv', methods=['POST'])
def download_csv():
    try:
        symbol = request.form.get('symbol')
        market_type = request.form.get('market_type')
        start_date = request.form.get('start_date', '2010-01-01')
        end_date = request.form.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        
        if not symbol or not market_type:
            return jsonify({'error': "Missing symbol or market type"}), 400

        logging.info(f"Downloading CSV for {symbol} ({market_type}) from {start_date} to {end_date}")

        df = fetch_data(symbol, market_type, start_date, end_date)
        
        if df is None or df.empty:
             return jsonify({'error': "No data found for the given parameters."}), 404
             
        # Fetch name for better filename
        name = get_symbol_name(symbol, market_type)
        name_prefix = f"{name}_" if name else ""
        
        # Create CSV in memory
        output = io.StringIO()
        # Ensure utf-8-sig for Excel compatibility with Chinese characters
        df.to_csv(output, index=False, encoding='utf-8-sig') 
        csv_data = output.getvalue()
        
        filename = f"{name_prefix}{symbol}_{market_type}_{datetime.now().strftime('%Y%m%d')}.csv"
        
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"Error downloading data: {e}\n{stack_trace}")
        return jsonify({'error': str(e)}), 500

def get_symbol_name(symbol, market_type):
    """根据代码获取公司/基金名称"""
    try:
        if market_type == 'china_stock':
            # A股实时数据包含名称
            df = ak.stock_zh_a_spot_em()
            match = df[df['代码'] == symbol]
            if not match.empty:
                return match['名称'].values[0]
        elif market_type == 'hk_stock':
            # 港股代码补齐
            symbol_hk = f"{int(symbol):05d}" if symbol.isdigit() else symbol
            df = ak.stock_hk_spot_em()
            match = df[df['代码'] == symbol_hk]
            if not match.empty:
                return match['名称'].values[0]
        elif market_type == 'china_etf':
            # ETF实时数据包含名称
            df = ak.fund_etf_spot_em()
            match = df[df['代码'] == symbol]
            if not match.empty:
                return match['名称'].values[0]
        elif market_type == 'us_stock':
            # 美股实时数据获取名称
            df = ak.stock_us_spot_em()
            # 美股代码通常是大写，且 match 需要对齐
            match = df[df['代码'].str.upper() == symbol.upper()]
            if not match.empty:
                return match['名称'].values[0]
    except Exception as e:
        logging.warning(f"Could not fetch name for {symbol}: {e}")
    return ""

def fetch_data(symbol, market_type, start_date, end_date):
    # AKShare expects YYYYMMDD strings for dates
    start_date_ak = start_date.replace('-', '')
    end_date_ak = end_date.replace('-', '')
    
    df = None
    
    try:
        if market_type == 'china_etf':
            # ETF
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=start_date_ak,
                end_date=end_date_ak,
                adjust="qfq"
            )
            
        elif market_type == 'china_stock':
            # A股
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date_ak,
                end_date=end_date_ak,
                adjust="qfq"
            )
            
        elif market_type == 'us_stock':
            # 美股
            if '.' in symbol:
                df = ak.stock_us_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date_ak,
                    end_date=end_date_ak,
                    adjust="qfq"
                )
            else:
                prefixes = ["105", "106", "107", "100"]
                found = False
                last_error = None
                
                for prefix in prefixes:
                    try:
                        test_symbol = f"{prefix}.{symbol}"
                        logging.info(f"Trying US stock symbol: {test_symbol}")
                        df = ak.stock_us_hist(
                            symbol=test_symbol,
                            period="daily",
                            start_date=start_date_ak,
                            end_date=end_date_ak,
                            adjust="qfq"
                        )
                        if df is not None and not df.empty:
                            found = True
                            logging.info(f"Successfully found US stock data with {test_symbol}")
                            break
                    except Exception as e:
                        last_error = e
                        continue
                
                if not found:
                    if last_error:
                        raise last_error
                    else:
                        raise ValueError(f"Could not find US stock data for {symbol}")
            
        elif market_type == 'hk_stock':
            # 港股
            if symbol.isdigit():
                symbol = f"{int(symbol):05d}"
                
            df = ak.stock_hk_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date_ak,
                end_date=end_date_ak,
                adjust="qfq"
            )
            
    except Exception as e:
        logging.error(f"AKShare download failed for {symbol} ({market_type}): {str(e)}")
        raise e
        
    return df
