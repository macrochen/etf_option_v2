from flask import Blueprint, render_template, request, jsonify
from strategies.wyckoff_analyzer import WyckoffAnalyzer
from routes.data_download_routes import fetch_data, get_symbol_name
import pandas as pd
import io
import os
import logging
import traceback
from datetime import datetime

wyckoff_bp = Blueprint('wyckoff', __name__)
analyzer = WyckoffAnalyzer()

# 定义缓存目录
CACHE_DIR = os.path.join(os.getcwd(), 'data', 'wyckoff_cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

@wyckoff_bp.route('/wyckoff_analysis')
def index():
    return render_template('wyckoff_analysis.html')

@wyckoff_bp.route('/api/wyckoff/cache_list', methods=['GET'])
def cache_list():
    """获取本地缓存的文件列表"""
    try:
        files = []
        for f in os.listdir(CACHE_DIR):
            if f.endswith('.csv'):
                path = os.path.join(CACHE_DIR, f)
                stats = os.stat(path)
                files.append({
                    'filename': f,
                    'mtime': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'size': f"{stats.st_size / 1024:.1f} KB"
                })
        # 按修改时间倒序排列
        files.sort(key=lambda x: x['mtime'], reverse=True)
        return jsonify({'status': 'success', 'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@wyckoff_bp.route('/api/wyckoff/analyze_cached', methods=['POST'])
def analyze_cached():
    """分析已缓存的文件"""
    try:
        filename = request.json.get('filename')
        file_path = os.path.join(CACHE_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404
            
        with open(file_path, 'rb') as f:
            df, error = analyzer.process_csv(f)
            
        if error: return jsonify({'error': error}), 400
        chart_data, signals = analyzer.analyze(df)
        
        # 从文件名尝试提取名称 (格式: 名称_代码_市场.csv)
        display_name = filename.split('_')[0] if '_' in filename else filename.replace('.csv', '')
        chart_data['stock_name'] = display_name
        
        return jsonify({'status': 'success', 'chart_data': chart_data, 'signals': signals})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@wyckoff_bp.route('/api/wyckoff/delete_cache', methods=['POST'])
def delete_cache():
    """删除本地缓存的文件"""
    try:
        filename = request.json.get('filename')
        if not filename:
            return jsonify({'error': '未提供文件名'}), 400
            
        file_path = os.path.join(CACHE_DIR, filename)
        # 安全检查：确保文件确实在缓存目录内，防止目录遍历攻击
        if not os.path.abspath(file_path).startswith(os.path.abspath(CACHE_DIR)):
            return jsonify({'error': '非法路径'}), 403

        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'status': 'success', 'message': f'文件 {filename} 已删除'})
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@wyckoff_bp.route('/api/wyckoff/download_and_analyze', methods=['POST'])
def download_and_analyze():
    """下载最新数据并分析 (带增量更新逻辑)"""
    try:
        data = request.json
        symbol = data.get('symbol', '').strip()
        market_type = data.get('market_type')
        
        if market_type == 'us_stock':
            symbol = symbol.upper()
        
        # 1. 查找是否存在该股票的缓存文件
        # 文件名格式为: 名称_代码_市场.csv
        cache_file = None
        suffix = f"_{symbol}_{market_type}.csv"
        for f in os.listdir(CACHE_DIR):
            if f.endswith(suffix):
                cache_file = f
                break
        
        df = None
        save_path = None
        
        if cache_file:
            # --- 增量下载逻辑 ---
            save_path = os.path.join(CACHE_DIR, cache_file)
            existing_df = pd.read_csv(save_path)
            existing_df['date'] = pd.to_datetime(existing_df['date'])
            
            latest_date_in_cache = existing_df['date'].max()
            today = datetime.now()
            
            # 如果缓存数据已经到今天（或昨天，考虑开盘时间），则不下载
            if (today - latest_date_in_cache).days <= 0:
                logging.info(f"Cache is up to date for {symbol}")
                df = existing_df
            else:
                # 只下载从缓存日期之后的数据
                start_date = (latest_date_in_cache + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                end_date = today.strftime('%Y-%m-%d')
                
                logging.info(f"Incremental download for {symbol} from {start_date} to {end_date}")
                new_data = fetch_data(symbol, market_type, start_date, end_date)
                
                if new_data is not None and not new_data.empty:
                    # 合并并去重
                    new_data['date'] = pd.to_datetime(new_data['date']) # 确保新数据也是 datetime
                    df = pd.concat([existing_df, new_data]).drop_duplicates(subset=['date']).sort_values('date')
                    df.to_csv(save_path, index=False, encoding='utf-8-sig')
                else:
                    df = existing_df
        
        if df is None:
            # --- 全量下载逻辑 (第一次下载) ---
            start_date = (datetime.now().replace(year=datetime.now().year - 1)).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            df = fetch_data(symbol, market_type, start_date, end_date)
            if df is None or df.empty:
                return jsonify({'error': '未获取到数据，请检查代码或市场类型'}), 404
                
            name = get_symbol_name(symbol, market_type)
            name_prefix = f"{name}_" if name else ""
            filename = f"{name_prefix}{symbol}_{market_type}.csv".replace('/', '_')
            save_path = os.path.join(CACHE_DIR, filename)
            df.to_csv(save_path, index=False, encoding='utf-8-sig')

        # 2. 执行分析
        chart_data, signals = analyzer.analyze(df)
        
        # 提取名称用于标题
        filename = os.path.basename(save_path)
        name = filename.split('_')[0] if '_' in filename else symbol
        chart_data['stock_name'] = f"{name} ({symbol})" if name != symbol else symbol
        
        return jsonify({
            'status': 'success', 
            'chart_data': chart_data, 
            'signals': signals,
            'filename': filename
        })
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"Incremental download error: {e}\n{stack_trace}")
        return jsonify({'error': str(e)}), 500

@wyckoff_bp.route('/api/wyckoff/analyze_csv', methods=['POST'])
def analyze_csv():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '未选择文件'}), 400

        # 保存上传的文件到缓存，方便下次使用
        save_path = os.path.join(CACHE_DIR, file.filename)
        file.save(save_path)
        
        # 重新读取分析
        with open(save_path, 'rb') as f:
            df, error = analyzer.process_csv(f)
            
        if error: return jsonify({'error': error}), 400
        chart_data, signals = analyzer.analyze(df)
        # 使用文件名作为显示名称
        chart_data['stock_name'] = file.filename.replace('.csv', '')
        
        return jsonify({'status': 'success', 'chart_data': chart_data, 'signals': signals})

    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"威科夫分析出错: {str(e)}\n{stack_trace}")
        return jsonify({'error': f"服务器内部错误: {str(e)}"}), 500
