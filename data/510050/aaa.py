import pandas as pd
import akshare as ak
import io
from datetime import datetime
import os

def get_exchange_suffix(etf_code):
    """根据ETF代码判断交易所后缀"""
    # 上交所ETF代码特征
    if etf_code.startswith(('51', '506', '588')):
        return 'XSHG'
    # 深交所ETF代码特征
    elif etf_code.startswith(('15', '16')):
        return 'XSHE'
    # 默认返回上交所
    return 'XSHG'

def download_option_data(etf_code, start_date, end_date, output_dir='./'):
    """
    下载指定 ETF 期权的历史数据并保存为Excel文件。

    Args:
        etf_code (str): ETF 代码，例如 "510050"。
        start_date (str): 起始日期，格式为 "yyyy-mm-dd"。
        end_date (str): 结束日期，格式为 "yyyy-mm-dd"。
        output_dir (str): 输出目录，默认为当前目录
    """
    try:
        # 添加交易所后缀
        exchange_suffix = get_exchange_suffix(etf_code)
        full_etf_code = f"{etf_code}.{exchange_suffix}"

        # 验证起始和结束日期是否为有效
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')

        # 获取 ETF 期权交易数据
        option_data = ak.option_finance_board(symbol=full_etf_code, end_month=end_date[:7])
        option_data['日期'] = pd.to_datetime(option_data['日期']).dt.strftime('%Y-%m-%d')

        if option_data.empty:
            print(f"错误：未能获取到 {full_etf_code} 在 {start_date} 至 {end_date} 期间的期权交易数据")
            return

        # 筛选指定日期范围内的数据
        option_data = option_data[(option_data['日期'] >= start_date) & (option_data['日期'] <= end_date)]

        # 重命名 columns
        option_data.rename(columns={
            '合约交易代码': '交易代码',
            '当前价': '收盘价',
            '涨跌幅': '涨跌幅(%)',
            '前结价': '前结算价',
            '行权价': '行权价',
            '数量': '持仓量'
        }, inplace=True)

        # 生成文件名
        file_name = f"{etf_code}_ETF期权数据_{start_date}_{end_date}.xlsx"
        file_path = os.path.join(output_dir, file_name)

        # 保存为Excel文件
        option_data.to_excel(file_path, index=False)

        print(f"成功：数据已保存到 {file_path}")
    except Exception as e:
        print(f"发生错误：{e}")

# 在本地运行的代码
etf_code = "510500"  # 不带交易所后缀
start_date = "2022-09-19"  # 起始日期
end_date = "2024-12-31"  # 结束日期
output_dir = '../'  # 输出目录

download_option_data(etf_code, start_date, end_date, output_dir)