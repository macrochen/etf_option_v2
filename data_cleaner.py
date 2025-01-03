import pandas as pd
import os
from datetime import datetime

class DataCleaner:
    def __init__(self):
        # 需要保留的列名列表
        self.columns_to_keep = [
            '日期', '交易代码', '收盘价', '行权价', 'Delta', '结算价'
        ]
        
    def clean_file(self, input_file):
        """清洗单个文件"""
        try:
            # 读取Excel文件
            print(f"正在处理文件: {input_file}")
            df = pd.read_excel(input_file)
            
            # 检查文件中是否包含所需的列
            missing_columns = [col for col in self.columns_to_keep if col not in df.columns]
            if missing_columns:
                print(f"警告: 文件 {input_file} 缺少以下列: {missing_columns}")
                return False
            
            # 只保留需要的列
            df_cleaned = df[self.columns_to_keep]
            
            # 打印数据统计信息
            print(f"原始数据行数: {len(df)}")
            print(f"清洗后数据行数: {len(df_cleaned)}")
            print(f"保留的列: {', '.join(self.columns_to_keep)}")
            
            try:
                # 先删除原文件
                if os.path.exists(input_file):
                    os.remove(input_file)
                
                # 保存清洗后的数据到原文件位置
                df_cleaned.to_excel(input_file, index=False, engine='openpyxl')
                print(f"已覆盖原文件: {input_file}")
            except Exception as e:
                print(f"保存文件时出错: {str(e)}")
                return False
                
            print("-" * 50)
            return True
            
        except Exception as e:
            print(f"处理文件 {input_file} 时出错: {str(e)}")
            return False
    
    def process_directories(self, input_dirs):
        """处理多个目录中的所有Excel文件"""
        # 分割目录字符串
        dir_list = [d.strip() for d in input_dirs.split(',') if d.strip()]
        
        if not dir_list:
            print("错误: 未提供有效的目录")
            return
        
        total_files = 0
        total_success = 0
        
        # 处理每个目录
        for directory in dir_list:
            print(f"\n开始处理目录: {directory}")
            
            # 获取所有Excel文件
            try:
                excel_files = [f for f in os.listdir(directory) 
                             if f.endswith('.xlsx') and not f.startswith('~$')]
            except Exception as e:
                print(f"读取目录 {directory} 时出错: {str(e)}")
                continue
            
            if not excel_files:
                print(f"在 {directory} 目录中没有找到Excel文件")
                continue
            
            # 处理目录中的每个文件
            success_count = 0
            for file in excel_files:
                input_path = os.path.join(directory, file)
                if self.clean_file(input_path):
                    success_count += 1
            
            # 打印当前目录的统计信息
            print(f"\n{directory} 目录处理完成:")
            print(f"文件数: {len(excel_files)}")
            print(f"成功数: {success_count}")
            print(f"失败数: {len(excel_files) - success_count}")
            
            total_files += len(excel_files)
            total_success += success_count
        
        # 打印总体统计信息
        print("\n=== 总体处理结果 ===")
        print(f"处理的目录数: {len(dir_list)}")
        print(f"总文件数: {total_files}")
        print(f"总成功数: {total_success}")
        print(f"总失败数: {total_files - total_success}")

def main():
    # 创建数据清洗器实例
    cleaner = DataCleaner()
    
    # 获取用户输入的目录列表
    input_dirs = input("请输入要处理的目录（多个目录用逗号分隔）: ")
    
    # 运行清洗程序
    cleaner.process_directories(input_dirs)

if __name__ == "__main__":
    main() 