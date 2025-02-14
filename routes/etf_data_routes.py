import logging
import traceback

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, render_template
from statsmodels.stats.diagnostic import acorr_ljungbox

from db.market_db import MarketDatabase

# 创建蓝图
etf_data_bp = Blueprint('etf_data', __name__)
db = MarketDatabase()

@etf_data_bp.route('/etf_volatility_management', methods=['GET'])
def download_page():
    return render_template('etf_volatility_management.html')

# 添加 ETF 代码到名称的映射
ETF_NAME_MAP = {
    '510050': '上证50',
    '510300': '沪深300',
    '510500': '中证500',
    '159901': '深证100',
    '159915': '创业板',
    '159919': '深市沪深300',
    '159922': '深市中证500',
    '588000': '科创板50',
    '588080': '科创板100'
}

@etf_data_bp.route('/api/etf_list', methods=['GET'])
def get_etf_list():
    try:
        # 从数据库获取ETF列表
        etf_list = db.get_etf_list()
        
        # 格式化数据，添加 ETF 名称
        formatted_list = []
        for etf in etf_list:
            etf_code = etf['etf_code']
            formatted_list.append({
                'etf_code': etf_code,
                'etf_name': ETF_NAME_MAP.get(etf_code, '未知'),  # 如果找不到映射关系，显示"未知"
                'start_date': etf['start_date'],
                'end_date': etf['end_date']
            })
        
        return jsonify(formatted_list)
    except Exception as e:
        logging.error(f"获取ETF列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': '获取ETF列表失败'}), 500

@etf_data_bp.route('/api/volatility_analysis/<etf_code>', methods=['GET'])
def get_volatility_analysis(etf_code):
    try:
        # 从数据库获取历史价格数据
        prices, dates = db.get_price_data(etf_code)
        # 将日期字符串转换为datetime类型
        df = pd.DataFrame({'Close': prices}, index=pd.to_datetime(dates))
        
        # 计算月度收益率（使用月末数据）
        df_monthly = df['Close'].resample('ME').last()  # 使用'ME'替代已废弃的'M'
        monthly_returns = np.log(df_monthly / df_monthly.shift(1))
        
        # 1. 描述性统计（年化处理）
        desc_stats = monthly_returns.describe()
        stats = {
            'mean': round(desc_stats['mean'] * 12 * 100, 2),  # 年化月均收益率
            'std': round(desc_stats['std'] * np.sqrt(12) * 100, 2),  # 年化月波动率
            'skew': round(monthly_returns.skew(), 2),
            'kurt': round(monthly_returns.kurtosis(), 2),
        }
        
        # 2. 波动率聚类检验（改为6个月滞后）
        lb_test = acorr_ljungbox(monthly_returns.dropna()**2, lags=6)
        clustering = {
            'q_stats': [round(x, 2) for x in lb_test.iloc[:,0].tolist()],
            'p_values': [round(x, 2) for x in lb_test.iloc[:,1].tolist()]
        }
        
        # 3. 多周期波动率分析
        periods = {
            'monthly': {'window': 3, 'factor': np.sqrt(12)},   # 3个月
            'quarterly': {'window': 12, 'factor': np.sqrt(4)}, # 12个月
            'yearly': {'window': 24, 'factor': 1}              # 24个月
        }
        
        # 处理 NaN 的辅助函数
        def safe_round(value, decimals=2):
            if pd.isna(value):
                return 0
            return round(float(value), decimals)
            
        # 修改 volatilities 的处理逻辑
        volatilities = {}
        for period, params in periods.items():
            # 计算上涨和下跌的波动率
            up_mask = monthly_returns > 0
            down_mask = monthly_returns < 0
            
            # 计算整体波动率
            vol = monthly_returns.rolling(params['window']).std() * params['factor'] * 100
            # 计算上涨波动率
            up_vol = monthly_returns[up_mask].rolling(params['window']).std() * params['factor'] * 100
            # 计算下跌波动率
            down_vol = monthly_returns[down_mask].rolling(params['window']).std() * params['factor'] * 100
            
            volatilities[period] = {
                'current': safe_round(vol.iloc[-1]),
                'mean': safe_round(vol.mean()),
                'max': safe_round(vol.max()),
                'min': safe_round(vol.min()),
                'up': {
                    'current': safe_round(up_vol.iloc[-1]),
                    'mean': safe_round(up_vol.mean()),
                    'max': safe_round(up_vol.max()),
                    'min': safe_round(up_vol.min())
                },
                'down': {
                    'current': safe_round(down_vol.iloc[-1]),
                    'mean': safe_round(down_vol.mean()),
                    'max': safe_round(down_vol.max()),
                    'min': safe_round(down_vol.min())
                }
            }

        # 4. 波动率锥分析（改为月度周期）
        windows = [1, 3, 6, 12]  # 1个月、3个月、6个月、1年
        quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]  # 增加10%和90%分位数
        vol_cone = {}
        
        for w in windows:
            vol = monthly_returns.rolling(w).std() * np.sqrt(12) * 100
            vol_cone[f'{w}月'] = {
                'quantiles': [safe_round(x) for x in vol.quantile(quantiles).tolist()],
                'current': safe_round(vol.iloc[-1])
            }
            
        return jsonify({
            'stats': stats,
            'clustering': clustering,
            'volatilities': volatilities,
            'vol_cone': vol_cone
        })
        
    except Exception as e:
        logging.error(f"波动率分析失败 - ETF代码: {etf_code}\n错误信息: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': '波动率分析失败'}), 500

