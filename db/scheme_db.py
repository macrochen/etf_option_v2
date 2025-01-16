from datetime import datetime
from typing import Dict, List, Optional

from .config import BACKTEST_SCHEMES_DB
from .database import Database
from utils.error_handler import log_error
import sqlite3
import json

class SchemeDatabase:
    def __init__(self, db_path: str = BACKTEST_SCHEMES_DB):
        """初始化方案数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db = Database(db_path)
        self._init_table()
        
    def _init_table(self):
        """初始化数据表"""
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS backtest_schemes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                params TEXT NOT NULL,
                results TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        ''')
        
    def create_scheme(self, name: str, params: str, results: Optional[str] = None) -> int:
        """创建新方案
        
        Args:
            name: 方案名称
            params: 方案参数(JSON字符串)
            results: 回测结果(JSON字符串)
            
        Returns:
            int: 新创建方案的ID
        """
        try:
            now = datetime.now().isoformat()
            self.db.execute('''
                INSERT INTO backtest_schemes (name, params, results, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, params, results, now, now))
            
            return self.db.fetch_one('SELECT last_insert_rowid()')[0]
        except Exception as e:
            log_error(e, "创建方案失败")
            raise
        
    def get_scheme(self, scheme_id: int) -> Optional[Dict]:
        """获取方案详情
        
        Args:
            scheme_id: 方案ID
            
        Returns:
            Optional[Dict]: 方案详情
        """
        row = self.db.fetch_one('''
            SELECT id, name, params, results, created_at, updated_at
            FROM backtest_schemes
            WHERE id = ?
        ''', (scheme_id,))
        
        return dict(row) if row else None
        
    def get_all_schemes(self) -> List[Dict]:
        """获取所有方案
        
        Returns:
            List[Dict]: 方案列表
        """
        rows = self.db.fetch_all('''
            SELECT id, name, params, created_at, updated_at
            FROM backtest_schemes
            ORDER BY updated_at DESC
        ''')
        
        return [dict(row) for row in rows]
        
    def update_scheme(self, scheme_id: int, name: Optional[str] = None, 
                     params: Optional[str] = None, results: Optional[str] = None) -> bool:
        """更新方案
        
        Args:
            scheme_id: 方案ID
            name: 新方案名称
            params: 新方案参数
            results: 新回测结果
            
        Returns:
            bool: 更新是否成功
        """
        updates = []
        values = []
        
        if name is not None:
            updates.append('name = ?')
            values.append(name)
        if params is not None:
            updates.append('params = ?')
            values.append(params)
        if results is not None:
            updates.append('results = ?')
            values.append(results)
            
        if not updates:
            return False
            
        updates.append('updated_at = ?')
        values.append(datetime.now().isoformat())
        values.append(scheme_id)
        
        self.db.execute(f'''
            UPDATE backtest_schemes
            SET {', '.join(updates)}
            WHERE id = ?
        ''', tuple(values))
        
        return True
        
    def delete_scheme(self, scheme_id: int) -> bool:
        """删除方案
        
        Args:
            scheme_id: 方案ID
            
        Returns:
            bool: 删除是否成功
        """
        self.db.execute('DELETE FROM backtest_schemes WHERE id = ?', (scheme_id,))
        return True 


    def get_scheme_by_name(self, name: str):
        """根据方案名称获取方案"""
        row = self.db.fetch_one('''
            SELECT id, name, params, results, created_at, updated_at
            FROM backtest_schemes
            WHERE name = ?
        ''', (name,))
        
        if row:
            return {
                'id': row[0],
                'name': row[1],
                'params': json.loads(row[2]),
                'results': json.loads(row[3]),
                'created_at': row[4],
                'updated_at': row[5]
            }
        return None
