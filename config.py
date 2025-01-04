import os
import pandas as pd

class BacktestConfig:
    def __init__(self, symbol, delta=0.3, initial_capital=1000000, contract_multiplier=10000,
                 transaction_cost=3.6, risk_free_rate=0.02, start_date=None, end_date=None,
                 holding_type='stock', margin_ratio=1.0):
        """
        回测配置类
        
        Args:
            symbol: str, ETF代码
            delta: float, 目标delta值
            initial_capital: float, 初始资金
            contract_multiplier: int, 合约乘数
            transaction_cost: float, 每张合约交易成本
            risk_free_rate: float, 无风险利率
            start_date: datetime, 回测开始日期
            end_date: datetime, 回测结束日期
            holding_type: str, 持仓类型 ('stock' 或 'synthetic')
            margin_ratio: float, 保证金比例，默认为1.0表示全额保证金
        """
        self.symbol = symbol
        self.delta = delta
        self.initial_capital = initial_capital
        self.contract_multiplier = contract_multiplier
        self.transaction_cost = transaction_cost
        self.risk_free_rate = risk_free_rate
        self.start_date = pd.to_datetime(start_date) if start_date else None
        self.end_date = pd.to_datetime(end_date) if end_date else None
        self.holding_type = holding_type
        self.margin_ratio = margin_ratio
        
        # 自动获取文件列表
        self.option_file_paths = []
        self.etf_file_path = None
        self._load_files(symbol)
    
    def _load_files(self, folder_name: str):
        """根据文件夹名自动加载文件列表"""
        try:
            # 获取文件夹中的所有文件
            files = os.listdir(folder_name)
            
            # 获取期权文件（xlsx文件）
            self.option_file_paths = [
                os.path.join(folder_name, f) 
                for f in files 
                if f.endswith('.xlsx') and not f.startswith('~$')
            ]
            
            # 获取ETF文件（csv文件）
            csv_files = [f for f in files if f.endswith('.csv')]
            if csv_files:
                self.etf_file_path = os.path.join(folder_name, csv_files[0])
            
            # 验证文件是否存在
            if not self.option_file_paths:
                raise ValueError(f"在 {folder_name} 文件夹中未找到期权数据文件(.xlsx)")
            if not self.etf_file_path:
                raise ValueError(f"在 {folder_name} 文件夹中未找到ETF数据文件(.csv)")
                
            # 按文件名排序期权文件，确保按时间顺序处理
            self.option_file_paths.sort()
            
            print(f"\n=== 已加载 {folder_name} 的数据文件 ===")
            print("期权文件:")
            for f in self.option_file_paths:
                print(f"  - {os.path.basename(f)}")
            print(f"ETF文件: {os.path.basename(self.etf_file_path)}")
            print()
            
        except Exception as e:
            raise ValueError(f"加载 {folder_name} 文件夹中的数据文件时出错: {str(e)}") 