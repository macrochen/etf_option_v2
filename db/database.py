import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

class Database:
    def __init__(self, db_path: str):
        """初始化数据库连接
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._ensure_db_directory()
    
    def _ensure_db_directory(self):
        """确保数据库目录存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def execute(self, query: str, params: tuple = ()) -> None:
        """执行SQL语句"""
        with self.get_connection() as conn:
            with conn:  # 自动处理事务
                conn.execute(query, params)
    
    def execute_many(self, query: str, params_list: List[tuple]) -> None:
        """执行多条SQL语句"""
        with self.get_connection() as conn:
            with conn:  # 自动处理事务
                conn.executemany(query, params_list)
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """获取单条记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()
    
    def fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """获取所有记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() 
    
    def commit(self):
        """提交"""
        with self.get_connection() as conn:
            conn.commit()