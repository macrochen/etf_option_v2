from typing import Optional
import pandas as pd
from db.database import Database
from akshare.fund.fund_em import fund_name_em

class FundInfoManager:
    def __init__(self, db_path: str):
        """初始化基金信息管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db = Database(db_path)
        self._init_table()
        
    def _init_table(self):
        """初始化基金信息表"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS fund_info (
                fund_code TEXT PRIMARY KEY,
                fund_name TEXT,
                fund_type TEXT,
                pinyin_abbr TEXT,
                pinyin_full TEXT,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
    def sync_fund_info(self) -> int:
        """同步基金基本信息
        
        Returns:
            int: 更新的基金数量
        """
        # 获取东方财富网的基金列表
        df = fund_name_em()
        
        # 准备插入数据
        insert_sql = """
            INSERT OR REPLACE INTO fund_info 
            (fund_code, fund_name, fund_type, pinyin_abbr, pinyin_full)
            VALUES (?, ?, ?, ?, ?)
        """
        
        data = [
            (row["基金代码"], row["基金简称"], row["基金类型"], 
             row["拼音缩写"], row["拼音全称"])
            for _, row in df.iterrows()
        ]
        
        # 批量插入数据
        self.db.execute_many(insert_sql, data)
        self.db.commit()
        
        return len(data)
    
    def get_fund_info(self, fund_code: str) -> Optional[dict]:
        """获取基金信息
        
        Args:
            fund_code: 基金代码
            
        Returns:
            dict: 基金信息字典，包含代码、名称、类型等信息
        """
        result = self.db.fetch_one("""
            SELECT fund_code, fund_name, fund_type, pinyin_abbr, pinyin_full
            FROM fund_info
            WHERE fund_code = ?
        """, (fund_code,))
        
        if result:
            return {
                "fund_code": result[0],
                "fund_name": result[1],
                "fund_type": result[2],
                "pinyin_abbr": result[3],
                "pinyin_full": result[4]
            }
        return None