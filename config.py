import os
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class BacktestConfig:
    """回测配置类"""
    symbol: str                    # ETF代码
    delta: float                   # 目标delta值
    start_date: Optional[datetime] = None  # 回测开始日期
    end_date: Optional[datetime] = None    # 回测结束日期
    initial_capital: float = 1000000.0     # 初始资金
    contract_multiplier: int = 10000       # 合约乘数
    transaction_cost: float = 3.6          # 每张合约交易成本
    stop_loss_ratio: Optional[float] = None  # 止损比例，None表示不止损
    risk_free_rate: float = 0.02          # 无风险利率
    holding_type: str = 'stock'           # 持仓类型 ('stock' 或 'synthetic')
    
    def __post_init__(self):
        """数据验证和文件加载"""
        # 转换日期格式
        if self.start_date and not isinstance(self.start_date, datetime):
            try:
                self.start_date = pd.to_datetime(self.start_date)
            except (ValueError, TypeError):
                self.start_date = None
            
        if self.end_date and not isinstance(self.end_date, datetime):
            try:
                self.end_date = pd.to_datetime(self.end_date)
            except (ValueError, TypeError):
                self.end_date = None
            
        # 验证参数
        if self.initial_capital <= 0:
            raise ValueError("初始资金必须大于0")
        if self.contract_multiplier <= 0:
            raise ValueError("合约乘数必须大于0")
        if self.transaction_cost < 0:
            raise ValueError("交易成本不能为负")
        if self.stop_loss_ratio is not None and (self.stop_loss_ratio <= 0 or self.stop_loss_ratio > 1):
            raise ValueError("止损比例必须在0到1之间")
        if self.holding_type not in ['stock', 'synthetic']:
            raise ValueError("持仓类型必须是 'stock' 或 'synthetic'")
            
        # 自动获取文件列表
        self.option_file_paths = []
        self.etf_file_path = None
        self._load_files(self.symbol)
    
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