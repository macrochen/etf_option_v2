from flask import Blueprint, render_template, request, jsonify
from strategies.wyckoff_analyzer import WyckoffAnalyzer
import pandas as pd
import io
import logging
import traceback

wyckoff_bp = Blueprint('wyckoff', __name__)
analyzer = WyckoffAnalyzer()

@wyckoff_bp.route('/wyckoff_analysis')
def index():
    return render_template('wyckoff_analysis.html')

@wyckoff_bp.route('/api/wyckoff/analyze_csv', methods=['POST'])
def analyze_csv():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '未选择文件'}), 400

        if not file.filename.endswith('.csv'):
            return jsonify({'error': '仅支持 CSV 文件'}), 400

        # 读取并处理 CSV
        # 必须先读取为 stream 才能传给 pandas
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        
        df, error = analyzer.process_csv(stream)
        if error:
            return jsonify({'error': error}), 400
            
        # 执行威科夫分析
        chart_data, signals = analyzer.analyze(df)
        
        return jsonify({
            'status': 'success',
            'chart_data': chart_data,
            'signals': signals
        })

    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"威科夫分析出错: {str(e)}\n{stack_trace}")
        return jsonify({'error': f"服务器内部错误: {str(e)}"}), 500
