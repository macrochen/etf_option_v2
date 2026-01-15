from datetime import datetime
from typing import List, Dict, Optional, Any
from .config import PORTFOLIO_DB
from .database import Database
import logging

class PortfolioDatabase:
    def __init__(self, db_path: str = PORTFOLIO_DB):
        """初始化资产组合数据库"""
        self.db = Database(db_path)
        self._init_table()

    def _init_table(self):
        """初始化资产持仓表"""
        # 资产持仓表
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS asset_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                category_1 TEXT,
                category_2 TEXT,
                symbol TEXT NOT NULL,
                name TEXT,
                quantity REAL DEFAULT 0,
                cost_price REAL DEFAULT 0,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 账户管理表
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                type TEXT,  -- 账户类型：券商、银行卡、支付宝等
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账户"""
        sql = 'SELECT * FROM accounts ORDER BY created_at'
        rows = self.db.fetch_all(sql)
        
        accounts = []
        for row in rows:
            accounts.append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'description': row[3],
                'created_at': row[4]
            })
        return accounts

    def add_account(self, name: str, type: str = None, description: str = None) -> int:
        """添加新账户"""
        try:
            sql = '''
                INSERT INTO accounts (name, type, description, created_at) 
                VALUES (?, ?, ?, ?)
            '''
            params = (
                name, 
                type, 
                description,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            self.db.execute(sql, params)
            return self.db.cursor.lastrowid
        except Exception as e:
            logging.error(f"Failed to add account {name}: {e}")
            raise

    def update_account(self, account_id: int, name: str, type: str = None, description: str = None) -> bool:
        """更新账户信息"""
        try:
            sql = '''
                UPDATE accounts 
                SET name = ?, type = ?, description = ?
                WHERE id = ?
            '''
            self.db.execute(sql, (name, type, description, account_id))
            return True
        except Exception as e:
            logging.error(f"Failed to update account {account_id}: {e}")
            return False

    def delete_account(self, account_id: int) -> bool:
        """删除账户"""
        try:
            self.db.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
            return True
        except Exception as e:
            logging.error(f"Failed to delete account {account_id}: {e}")
            return False

    def add_asset(self, data: Dict[str, Any]) -> int:
        """添加新资产"""
        sql = '''
            INSERT INTO asset_holdings (
                account_name, asset_type, category_1, category_2, 
                symbol, name, quantity, cost_price, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            data['account_name'],
            data['asset_type'],
            data.get('category_1'),
            data.get('category_2'),
            data['symbol'],
            data.get('name', ''),
            data.get('quantity', 0),
            data.get('cost_price', 0),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        self.db.execute(sql, params)
        return self.db.cursor.lastrowid

    def update_asset(self, asset_id: int, data: Dict[str, Any]) -> bool:
        """更新资产信息"""
        fields = []
        values = []
        
        valid_fields = ['account_name', 'asset_type', 'category_1', 'category_2', 
                       'symbol', 'name', 'quantity', 'cost_price']
        
        for field in valid_fields:
            if field in data:
                fields.append(f"{field} = ?")
                values.append(data[field])
                
        if not fields:
            return False
            
        fields.append("update_time = ?")
        values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        values.append(asset_id)
        
        sql = f'''
            UPDATE asset_holdings 
            SET {', '.join(fields)}
            WHERE id = ?
        '''
        
        try:
            self.db.execute(sql, tuple(values))
            return True
        except Exception as e:
            logging.error(f"Failed to update asset {asset_id}: {e}")
            return False

    def delete_asset(self, asset_id: int) -> bool:
        """删除资产"""
        try:
            self.db.execute('DELETE FROM asset_holdings WHERE id = ?', (asset_id,))
            return True
        except Exception as e:
            logging.error(f"Failed to delete asset {asset_id}: {e}")
            return False

    def get_all_assets(self) -> List[Dict[str, Any]]:
        """获取所有资产记录"""
        sql = 'SELECT * FROM asset_holdings ORDER BY category_1, category_2'
        rows = self.db.fetch_all(sql)
        
        assets = []
        for row in rows:
            assets.append({
                'id': row[0],
                'account_name': row[1],
                'asset_type': row[2],
                'category_1': row[3],
                'category_2': row[4],
                'symbol': row[5],
                'name': row[6],
                'quantity': row[7],
                'cost_price': row[8],
                'update_time': row[9]
            })
        return assets

    def get_asset_by_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取资产"""
        sql = 'SELECT * FROM asset_holdings WHERE id = ?'
        row = self.db.fetch_one(sql, (asset_id,))
        
        if row:
            return {
                'id': row[0],
                'account_name': row[1],
                'asset_type': row[2],
                'category_1': row[3],
                'category_2': row[4],
                'symbol': row[5],
                'name': row[6],
                'quantity': row[7],
                'cost_price': row[8],
                'update_time': row[9]
            }
        return None
