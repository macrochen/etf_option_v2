import pandas as pd
import os
from datetime import datetime

class DateAnalyzer:
    def __init__(self):
        self.date_column = '日期'
        # ETF代码和名称的映射
        self.etf_names = {
            '510050': '上证50ETF',
            '510300': '沪深300ETF',
            '510500': '中证500ETF',
            '159901': '深证100ETF',
            '159915': '创业板ETF',
            '159919': '沪深300ETF',
            '159922': '中证500ETF',
            '588000': '科创50ETF',
            '588080': '科创100ETF'
        }
    
    def get_etf_label(self, etf_code):
        """获取ETF的标签信息"""
        etf_name = self.etf_names.get(etf_code, f'{etf_code}ETF')  # 如果没有预定义名称，使用代码作为名称
        return {'value': etf_code, 'label': f'{etf_name} ({etf_code})'}
    
    def get_exchange_suffix(self, etf_code):
        """根据ETF代码判断交易所后缀"""
        # 上交所ETF代码特征
        if etf_code.startswith(('51', '506', '588')):
            return 'XSHG'
        # 深交所ETF代码特征
        elif etf_code.startswith(('15', '16')):
            return 'XSHE'
        # 默认返回上交所
        return 'XSHG'
    
    def analyze_file(self, input_file):
        """分析单个文件的日期范围"""
        try:
            # 读取Excel文件
            df = pd.read_excel(input_file)
            
            # 检查是否存在日期列
            if self.date_column not in df.columns:
                print(f"警告: 文件 {input_file} 中没有找到'{self.date_column}'列")
                return None, None
            
            # 将日期列转换为datetime类型，无效日期将变为NaT
            df[self.date_column] = pd.to_datetime(df[self.date_column], errors='coerce')
            
            # 删除无效的日期行
            df = df.dropna(subset=[self.date_column])
            
            # 如果所有日期都无效，返回None
            if len(df) == 0:
                print(f"警告: 文件 {input_file} 中没有有效的日期数据")
                return None, None
            
            # 获取最早和最晚的日期
            start_date = df[self.date_column].min()
            end_date = df[self.date_column].max()
            
            return start_date, end_date
            
        except Exception as e:
            print(f"处理文件 {input_file} 时出错: {str(e)}")
            return None, None
    
    def analyze_directories(self, input_dirs):
        """分析多个目录中的所有Excel文件的日期范围"""
        # 分割目录字符串
        dir_list = [d.strip() for d in input_dirs.split(',') if d.strip()]
        
        if not dir_list:
            print("错误: 未提供有效的目录")
            return
        
        # 处理每个目录
        for directory in dir_list:
            print(f"\n分析目录: {directory}")
            
            # 获取所有Excel文件
            try:
                excel_files = [f for f in os.listdir(directory) 
                             if f.endswith('.xlsx') and not f.startswith('~$')]
                excel_files.sort()  # 按文件名排序
            except Exception as e:
                print(f"读取目录 {directory} 时出错: {str(e)}")
                continue
            
            if not excel_files:
                print(f"在 {directory} 目录中没有找到Excel文件")
                continue
            
            # 处理目录中的每个文件
            dir_start_date = None
            dir_end_date = None
            
            for file in excel_files:
                input_path = os.path.join(directory, file)
                start_date, end_date = self.analyze_file(input_path)
                
                if start_date and end_date:
                    # 更新目录的日期范围
                    if dir_start_date is None or start_date < dir_start_date:
                        dir_start_date = start_date
                    if dir_end_date is None or end_date > dir_end_date:
                        dir_end_date = end_date
            
            # 打印当前目录的日期范围
            if dir_start_date and dir_end_date:
                # 获取目录名（ETF代码）
                etf_code = os.path.basename(directory)
                # 获取交易所后缀
                exchange_suffix = self.get_exchange_suffix(etf_code)
                # 获取ETF标签信息
                etf_label = self.get_etf_label(etf_code)
                
                print(f'etf_code = "{etf_code}.{exchange_suffix}"')
                print(f'start_date = "{dir_start_date.strftime("%Y-%m-%d")}"  # 起始日期')
                print(f'end_date = "{dir_end_date.strftime("%Y-%m-%d")}"  # 结束日期')
                print(str(etf_label))

def main():
    # 创建日期分析器实例
    analyzer = DateAnalyzer()
    
    # 获取用户输入的目录列表
    input_dirs = input("请输入要分析的目录（多个目录用逗号分隔, 510050,510300,510500,159901,159915,159919,159922,588000,588080）: ")
    
    # 运行分析程序
    analyzer.analyze_directories(input_dirs)

if __name__ == "__main__":
    main() 