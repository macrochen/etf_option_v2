from flask import Blueprint, render_template, request, jsonify
from strategies.wyckoff_analyzer import WyckoffAnalyzer
from routes.data_download_routes import fetch_data, get_symbol_name, find_symbol_by_name
import pandas as pd
import io
import os
import logging
import traceback
import re
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
        symbol_input = data.get('symbol', '').strip()
        market_type = data.get('market_type')
        
        symbol = symbol_input
        stock_name_zh = "" # 用于保存中文名称
        
        # 智能识别：如果是中文或明显不是代码格式，尝试反查代码
        # A股/港股/ETF通常是纯数字，美股是字母。如果输入了中文，肯定需要查找。
        is_chinese = bool(re.search(r'[\u4e00-\u9fa5]', symbol_input))
        
        if is_chinese:
            logging.info(f"Searching code for name: {symbol_input}")
            found_code, found_name = find_symbol_by_name(symbol_input, market_type)
            if found_code:
                symbol = found_code
                stock_name_zh = found_name # 拿到确切的中文名
                logging.info(f"Resolved '{symbol_input}' to code '{symbol}' ({found_name})")
            else:
                return jsonify({'error': f"未找到名称包含 '{symbol_input}' 的股票，请尝试输入准确代码。"}), 404
        
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
            try:
                existing_df = pd.read_csv(save_path)
                # 关键修复：读取后立即标准化，处理“日期”vs“date”列名问题
                existing_df, norm_err = analyzer.normalize_df(existing_df)
                
                if norm_err:
                    logging.warning(f"Cache file {cache_file} format invalid, triggering full download. Error: {norm_err}")
                    df = None # 标记为 None，触发后续全量下载
                else:
                    latest_date_in_cache = existing_df['date'].max()
                    today = datetime.now()
                    
                    if (today - latest_date_in_cache).days <= 0:
                        logging.info(f"Cache is up to date for {symbol}")
                        df = existing_df
                    else:
                        start_date = (latest_date_in_cache + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                        end_date = today.strftime('%Y-%m-%d')
                        logging.info(f"Incremental download for {symbol} from {start_date} to {end_date}")
                        new_data = fetch_data(symbol, market_type, start_date, end_date)
                        
                        if new_data is not None and not new_data.empty:
                            # 新数据也要标准化，确保列名一致才能 concat
                            new_data, new_err = analyzer.normalize_df(new_data)
                            if not new_err:
                                df = pd.concat([existing_df, new_data]).drop_duplicates(subset=['date']).sort_values('date')
                                df.to_csv(save_path, index=False, encoding='utf-8-sig')
                            else:
                                logging.warning(f"New data normalization failed: {new_err}")
                                df = existing_df
                        else:
                            df = existing_df
            except Exception as e:
                logging.error(f"Error reading/processing cache for {symbol}: {e}")
                df = None # 出错则回退到全量下载

        if df is None:
            # --- 全量下载逻辑 (第一次下载 或 缓存失效) ---
            # 增加到 500 天，确保有足够数据计算 MA200
            start_date = (datetime.now() - pd.Timedelta(days=500)).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            df = fetch_data(symbol, market_type, start_date, end_date)
            if df is None or df.empty:
                return jsonify({'error': '未获取到数据，请检查代码或市场类型'}), 404
            
            # 关键修复：保存前先标准化，确保存入的是标准格式
            df, norm_err = analyzer.normalize_df(df)
            if norm_err:
                return jsonify({'error': f'数据标准化失败: {norm_err}'}), 500

            # 获取名称用于文件名
            # 如果之前通过搜索拿到了名字，直接用；否则去查一遍
            if not stock_name_zh:
                stock_name_zh = get_symbol_name(symbol, market_type)
            
            name_prefix = f"{stock_name_zh}_" if stock_name_zh else ""
            filename = f"{name_prefix}{symbol}_{market_type}.csv".replace('/', '_')
            save_path = os.path.join(CACHE_DIR, filename)
            df.to_csv(save_path, index=False, encoding='utf-8-sig')

        # 2. 执行分析
        chart_data, signals = analyzer.analyze(df)
        
        # 提取名称用于标题 (从文件名或我们拿到的变量)
        filename = os.path.basename(save_path)
        # 优先使用我们已经拿到的 stock_name_zh，如果没有再从文件名拆
        display_name = stock_name_zh if stock_name_zh else (filename.split('_')[0] if '_' in filename else symbol)
        
        chart_data['stock_name'] = f"{display_name} ({symbol})"
        
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
